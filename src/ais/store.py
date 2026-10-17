import contextlib
import fcntl
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, ContextManager, Iterator, Optional

from ais.errors import AisError

EXIT_CANNOT_WRITE = 73
EXIT_CONFIG = 78
LOG_MAX = 1024 * 1024


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
                with os.fdopen(fd, "w") as f:
                    json.dump(new, f)
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
