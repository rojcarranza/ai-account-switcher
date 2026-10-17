from typing import Dict, Optional, Tuple

from ais.store import Store


class Cache:
    """Per-file (folder, title) cache in cache.json, keyed by path and valid for the same mtime and size."""

    def __init__(self, store: Store):
        self.store = store
        old = store.read_json("cache.json").get("transcripts", {})
        self._old = old if isinstance(old, dict) else {}
        self._seen = {}  # type: Dict[str, dict]

    def lookup(self, path: str, mtime: float, size: int) -> Optional[Tuple[str, str]]:
        e = self._old.get(path)
        if isinstance(e, dict) and e.get("mtime") == mtime and e.get("size") == size \
                and isinstance(e.get("folder"), str) and isinstance(e.get("title"), str):
            self._seen[path] = e
            return e["folder"], e["title"]
        return None

    def put(self, path: str, mtime: float, size: int, folder: str, title: str) -> None:
        self._seen[path] = {"mtime": mtime, "size": size, "folder": folder, "title": title}

    def save(self) -> None:
        def fn(d: dict) -> dict:
            d["transcripts"] = self._seen  # paths not seen in this scan are dropped
            return d
        self.store.update_json("cache.json", fn)
