import os
import re
import shlex
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Optional, Tuple

from ais import guards, runner
from ais.accounts import EXIT_USAGE, Account, Config
from ais.errors import AisError
from ais.providers.base import Provider
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


@dataclass
class Context:
    store: Store
    config: Config
    provider_for: Callable[[Account], Provider]
    env: Dict[str, str]
    cwd: Path
    settings_roots: Optional[Mapping[str, Path]] = None  # None = the provider's default


def cmd_login(ctx: Context, account: str, dry_run: bool, allow_api_key: bool = False) -> int:
    acc = ctx.config.get(account)
    provider = ctx.provider_for(acc)
    env, warnings = provider.env_for(acc, ctx.env)
    guards.print_warnings(warnings)
    risks = provider.billing_risks(env, ctx.cwd, [], ctx.settings_roots or provider.default_settings_roots())
    guards.refuse_on_risks(risks, allow_api_key)
    cmd = provider.login_command()
    if dry_run:
        print(provider.describe_env(env) + " ".join(shlex.quote(a) for a in cmd))
        return 0
    rc = _spawn(ctx, provider, cmd, env, acc.label)
    try:
        ctx.store.log("login", acc.name, "", "exit %d" % rc)
    except AisError as e:  # claude already ran: its exit code wins over a failed log write
        guards.print_warnings([e.message])
    return rc


_SWITCH_HINT = "use `ais switch` to resume a session"


def _check_run_args(provider: Provider, args: List[str], allow_api_key: bool) -> None:
    # a short flag may carry its value attached (-r5, -r=abc) or sit in a cluster (-pr5)
    short = re.compile(r"^-[A-Za-z]*[%s]" % re.escape(provider.short_resume_letters))
    for a in args:
        flag = a.split("=", 1)[0]
        if flag in provider.resume_flags or (not a.startswith("--") and short.match(a)):
            raise AisError(EXIT_USAGE, "ais run does not take %s; %s" % (a, _SWITCH_HINT))
        if flag == "--settings" and not allow_api_key:
            raise AisError(EXIT_USAGE, "ais run does not take --settings (it can set an API key); %s" % _SWITCH_HINT)


def _spawn(ctx: Context, provider: Provider, cmd: List[str], env: Dict[str, str], label: str) -> int:
    try:
        return runner.run_claude(cmd, env, ctx.cwd, label, on_started=lambda: None)
    except AisError as e:
        if e.code == 69:
            raise AisError(69, "%s; %s" % (e.message, provider.install_hint))
        raise


def cmd_run(ctx: Context, account: Optional[str], args: List[str], allow_api_key: bool, dry_run: bool) -> int:
    acc = ctx.config.get(account or ctx.config.default)
    provider = ctx.provider_for(acc)
    _check_run_args(provider, args, allow_api_key)
    env, warnings = provider.env_for(acc, ctx.env)
    guards.print_warnings(warnings)
    risks = provider.billing_risks(env, ctx.cwd, args, ctx.settings_roots or provider.default_settings_roots())
    guards.refuse_on_risks(risks, allow_api_key)
    cmd = provider.start_command(args)
    if dry_run:
        print(provider.describe_env(env) + " ".join(shlex.quote(a) for a in cmd))
        return 0
    launched = time.time()
    rc = _spawn(ctx, provider, cmd, env, acc.label)
    session_id = ""
    try:  # claude already ran: its exit code wins over a failed record or log write
        s = provider.newest_session(ctx.cwd, Cache(ctx.store))
        # accepted residual risk: a concurrent new session in this folder could be attributed to this run
        if s is not None:
            st = os.stat(str(s.transcript))
            if getattr(st, "st_birthtime", st.st_mtime) >= launched - 2:
                session_id = s.id
                at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

                def fn(d: dict) -> dict:
                    sessions = d.setdefault("sessions", {})
                    if not isinstance(sessions, dict):
                        raise AisError(EXIT_CONFIG, "%s: sessions is not an object" % (ctx.store.dir / "state.json"))
                    sessions[str(s.transcript)] = {"account": acc.name, "at": at}
                    return d
                ctx.store.update_json("state.json", fn)
        ctx.store.log("run", acc.name, session_id, "exit %d" % rc)
    except (AisError, OSError) as e:
        guards.print_warnings([getattr(e, "message", str(e))])
    return rc
