import time
from typing import Any, Callable, Dict, Mapping, Optional, Tuple

from ais.accounts import Account
from ais.errors import AisError
from ais.store import EXIT_CONFIG, Store

CREDENTIAL_TTL = 600


def _read_cache(store: Store) -> dict:
    """cache.json is disposable: a corrupt one counts as empty and is removed so the next write replaces it."""
    try:
        return store.read_json("cache.json")
    except AisError as e:
        if e.code != EXIT_CONFIG:
            raise
        try:
            (store.dir / "cache.json").unlink()
        except OSError:
            pass
        return {}


def credential_state(store: Store, provider: Any, account: Account, cache_only: bool,
                     base_env: Mapping[str, str],
                     now: Callable[[], float] = time.time) -> Tuple[str, str, str]:
    """(state, source, error); `auth status` results are cached 10 minutes, Keychain ones are not."""
    entries = _read_cache(store).get("credentials", {})
    e = entries.get(account.name) if isinstance(entries, dict) else None
    if isinstance(e, dict) and e.get("cred_dir") == account.cred_dir \
            and isinstance(e.get("at"), (int, float)) and 0 <= now() - e["at"] < CREDENTIAL_TTL \
            and all(isinstance(e.get(k), str) for k in ("state", "source", "error")):
        return e["state"], e["source"], e["error"]
    if cache_only:
        return provider.keychain_credential(account)
    result = provider.has_credential(account, base_env)
    if result[1] == "auth status":
        def fn(d: dict) -> dict:
            creds = d.get("credentials")
            d["credentials"] = creds = creds if isinstance(creds, dict) else {}
            creds[account.name] = {"cred_dir": account.cred_dir, "state": result[0],
                                   "source": result[1], "error": result[2], "at": now()}
            return d
        store.update_json("cache.json", fn)
    return result


class Cache:
    """Per-file (folder, title) cache in cache.json, keyed by path and valid for the same mtime and size."""

    def __init__(self, store: Store):
        self.store = store
        old = _read_cache(store).get("transcripts", {})
        self._old = old if isinstance(old, dict) else {}
        self._seen = {}  # type: Dict[str, dict]
        self._dirty = False

    def lookup(self, path: str, mtime: float, size: int) -> Optional[Tuple[str, str]]:
        e = self._seen.get(path) or self._old.get(path)
        if isinstance(e, dict) and e.get("mtime") == mtime and e.get("size") == size \
                and isinstance(e.get("folder"), str) and isinstance(e.get("title"), str):
            self._seen[path] = e
            return e["folder"], e["title"]
        return None

    def put(self, path: str, mtime: float, size: int, folder: str, title: str) -> None:
        self._dirty = True
        self._seen[path] = {"mtime": mtime, "size": size, "folder": folder, "title": title}

    def save(self) -> None:
        if not self._dirty and self._seen.keys() == self._old.keys():
            return  # warm scan: skip the lock, rewrite and fsync
        def fn(d: dict) -> dict:
            d["transcripts"] = self._seen  # paths not seen in this scan are dropped
            return d
        self.store.update_json("cache.json", fn)
