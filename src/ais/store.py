import contextlib
import fcntl
import json
import os
import re
import shutil
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, ContextManager, Iterator, List, Optional

from ais import procs
from ais.errors import AisError

EXIT_CANNOT_WRITE = 73
EXIT_CONFIG = 78
LOG_MAX = 1024 * 1024
SNAPSHOT_MAX_COUNT = 20
SNAPSHOT_MAX_BYTES = 500 * 1024 * 1024
SNAPSHOT_MAX_AGE = 30 * 86400
SNAPSHOT_STAMP = "%Y%m%dT%H%M%SZ"
CP_TIMEOUT = 30


EXIT_USAGE = 64
SNAPSHOT_NAME = re.compile(r"^\d{8}T\d{6}Z-")


def _size(path: Path) -> int:
    # lstat: a symlink counts as itself, never as what it points at
    if not path.is_dir() or path.is_symlink():
        return path.lstat().st_size
    return sum(os.lstat(os.path.join(r, f)).st_size for r, _, fs in os.walk(str(path)) for f in fs)


def _restrict(root: Path) -> None:
    # FR-2.6: cp -c and copy2 keep source modes (0644); snapshots are private
    for r, dirs, files in os.walk(str(root)):
        for n in dirs + files:
            q = os.path.join(r, n)
            if not os.path.islink(q):
                os.chmod(q, 0o700 if os.path.isdir(q) else 0o600)
    os.chmod(str(root), 0o700)


def _entry_time(path: Path) -> float:
    try:
        return datetime.strptime(path.name[:16], SNAPSHOT_STAMP).replace(tzinfo=timezone.utc).timestamp()
    except ValueError:
        return path.stat().st_mtime


def _sync(fd: int) -> None:
    # macOS fsync does not flush the drive cache; F_FULLFSYNC does
    if hasattr(fcntl, "F_FULLFSYNC"):
        try:
            fcntl.fcntl(fd, fcntl.F_FULLFSYNC)
            return
        except OSError:  # some filesystems reject it
            pass
    os.fsync(fd)


class Store:
    def __init__(self, home: Path):
        self.home = Path(home)
        self.dir = self.home / ".config" / "ais"
        self._held = set()  # lock names held by this instance (flock is not re-entrant)
        self.inflight_tmp = None  # type: Optional[str]  # temp file of a write in progress, for a hard exit to remove

    def _ensure_dir(self) -> None:
        # chmod after mkdir so the mode holds under any umask
        for d in (self.dir.parent, self.dir):
            if not d.is_dir():
                try:
                    d.mkdir(mode=0o700)
                except FileExistsError:  # another ais process won the race
                    continue
                d.chmod(0o700)

    def _open(self, name: str, flags: int) -> int:
        fd = os.open(str(self.dir / name), flags | os.O_CREAT, 0o600)
        os.fchmod(fd, 0o600)
        return fd

    @contextlib.contextmanager
    def _flock(self, name: str) -> Iterator[None]:
        if name in self._held:
            yield
            return
        try:
            self._ensure_dir()
            fd = self._open(name, os.O_RDWR)
        except OSError as e:
            raise AisError(EXIT_CANNOT_WRITE, "%s: %s" % (self.dir / name, e))
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            self._held.add(name)
            yield
        finally:
            self._held.discard(name)
            os.close(fd)  # closing releases the flock

    def switch_mutex(self) -> ContextManager[None]:
        return self._flock("switch.lock")

    def read_json(self, name: str) -> dict:
        path = self.dir / name
        try:
            with open(str(path)) as f:
                data = json.load(f)
        except FileNotFoundError:
            return {}
        except OSError as e:
            raise AisError(EXIT_CANNOT_WRITE, "%s: %s" % (path, e))
        except ValueError as e:
            raise AisError(EXIT_CONFIG, "%s: invalid JSON: %s" % (path, e))
        if not isinstance(data, dict):
            raise AisError(EXIT_CONFIG, "%s: top level is not an object" % path)
        return data

    def update_json(self, name: str, fn: Callable[[dict], dict]) -> dict:
        path = self.dir / name
        with self._flock(".lock"):
            new = fn(self.read_json(name))
            tmp = None
            try:
                fd, tmp = tempfile.mkstemp(dir=str(self.dir), prefix="." + name + ".")
                self.inflight_tmp = tmp
                with os.fdopen(fd, "w") as f:
                    json.dump(new, f, indent=2)  # config.json is hand-edited: keep it readable
                    f.flush()
                    _sync(f.fileno())
                os.replace(tmp, str(path))
                # the replace is done; a dir-fsync failure must not report the write as failed
                with contextlib.suppress(OSError):
                    dfd = os.open(str(self.dir), os.O_RDONLY)
                    try:
                        os.fsync(dfd)
                    finally:
                        os.close(dfd)
            except BaseException as e:
                if tmp:
                    with contextlib.suppress(OSError):
                        os.unlink(tmp)
                if isinstance(e, OSError):
                    raise AisError(EXIT_CANNOT_WRITE, "%s: %s" % (path, e))
                raise
            finally:
                self.inflight_tmp = None
            return new

    def prune_state(self, exists: Callable[[str], bool]) -> None:
        def prune(d: dict) -> dict:
            if not isinstance(d.get("sessions", {}), dict):
                raise AisError(EXIT_CONFIG, "%s: sessions is not an object" % (self.dir / "state.json"))
            d["sessions"] = {k: v for k, v in d.get("sessions", {}).items() if exists(k)}
            return d
        self.update_json("state.json", prune)

    def log(self, command: str, account: str, session_id: str, result: str,
            tool_seconds: Optional[float] = None,
            e2e_seconds: Optional[float] = None) -> None:
        line = json.dumps({
            "time": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "command": command, "account": account, "session_id": session_id,
            "result": result, "tool_seconds": tool_seconds, "e2e_seconds": e2e_seconds,
        }) + "\n"
        path = self.dir / "ais.log"
        with self._flock(".lock"):
            try:
                if path.exists() and path.stat().st_size >= LOG_MAX:
                    os.replace(str(path), str(path) + ".1")
                fd = self._open("ais.log", os.O_WRONLY | os.O_APPEND)
                try:
                    os.write(fd, line.encode())
                finally:
                    os.close(fd)
            except OSError as e:
                raise AisError(EXIT_CANNOT_WRITE, "%s: %s" % (path, e))

    def snapshot(self, paths: List[Path], session_id: str,
                 now: Callable[[], float] = time.time) -> Optional[Path]:
        """Copy paths into snapshots/<UTC stamp>-<id>/ (APFS clone, else plain copy); None when impossible."""
        if not session_id or session_id in (".", "..") or "/" in session_id or "\0" in session_id:
            raise AisError(EXIT_USAGE, "invalid session id %r" % session_id)
        root = self.dir / "snapshots"
        stamp = datetime.fromtimestamp(now(), timezone.utc).strftime(SNAPSHOT_STAMP)
        target = None  # type: Optional[Path]
        try:
            self._ensure_dir()
            root.mkdir(mode=0o700, exist_ok=True)
            root.chmod(0o700)
            n = 0
            while target is None:
                cand = root / ("%s-%s%s" % (stamp, session_id, "-%d" % n if n else ""))
                try:
                    cand.mkdir(mode=0o700)
                    target = cand
                except FileExistsError:
                    n += 1
            target.chmod(0o700)
            cloned = all(self._clone(p, target) for p in paths)
            if not cloned:
                self._plain_copy(paths, target)
            _restrict(target)
        except OSError as e:
            if target is not None:
                shutil.rmtree(str(target), ignore_errors=True)
            print("ais: warning: snapshot failed (%s); continuing without one" % e, file=sys.stderr)
            return None
        except _NoSpace:
            shutil.rmtree(str(target), ignore_errors=True)
            print("ais: warning: not enough free space for a snapshot; continuing without one", file=sys.stderr)
            return None
        self._prune_snapshots(root, target, now())
        return target

    @staticmethod
    def _clone(src: Path, target: Path) -> bool:
        rc, _, warn, _ = procs.run(["cp", "-c", "-R", str(src), str(target) + "/"], CP_TIMEOUT)
        return rc == 0 and not warn

    @staticmethod
    def _plain_copy(paths: List[Path], target: Path) -> None:
        for child in target.iterdir():  # drop what a half-done clone left
            shutil.rmtree(str(child)) if child.is_dir() and not child.is_symlink() else child.unlink()
        if shutil.disk_usage(str(target)).free < 2 * sum(_size(p) for p in paths):
            raise _NoSpace()
        for p in paths:
            if p.is_dir() and not p.is_symlink():
                shutil.copytree(str(p), str(target / p.name), symlinks=True)
            else:
                shutil.copy2(str(p), str(target / p.name), follow_symlinks=False)

    @staticmethod
    def _prune_snapshots(root: Path, keep: Path, now: float) -> None:
        try:
            entries = sorted((e for e in root.iterdir() if SNAPSHOT_NAME.match(e.name) and e.is_dir()), key=_entry_time)
            sizes = {e: _size(e) for e in entries}
            for e in list(entries):
                if e != keep and now - _entry_time(e) > SNAPSHOT_MAX_AGE:
                    shutil.rmtree(str(e), ignore_errors=True)
                    entries.remove(e)
            total = sum(sizes[e] for e in entries)
            for e in list(entries):
                if len(entries) <= SNAPSHOT_MAX_COUNT and total <= SNAPSHOT_MAX_BYTES:
                    break
                if e == keep:
                    continue
                shutil.rmtree(str(e), ignore_errors=True)
                entries.remove(e)
                total -= sizes[e]
            if sizes[keep] > SNAPSHOT_MAX_BYTES:
                print("ais: warning: the snapshot alone exceeds the %d MB cap; kept anyway"
                      % (SNAPSHOT_MAX_BYTES // (1024 * 1024)), file=sys.stderr)
        except OSError as e:  # pruning is best effort
            print("ais: warning: cannot prune snapshots: %s" % e, file=sys.stderr)


class _NoSpace(Exception):
    pass
