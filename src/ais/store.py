import contextlib
import fcntl
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterator, Optional

from ais.errors import AisError

EXIT_CANNOT_WRITE = 73
LOG_MAX = 1024 * 1024


class Store:
    def __init__(self, home: Path):
        self.dir = Path(home) / ".config" / "ais"

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
        try:
            self._ensure_dir()
            fd = self._open(name, os.O_RDWR)
        except OSError as e:
            raise AisError(EXIT_CANNOT_WRITE, "%s: %s" % (self.dir / name, e))
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            yield
        finally:
            os.close(fd)  # closing releases the flock

    def switch_mutex(self):
        return self._flock("switch.lock")

    def read_json(self, name: str) -> dict:
        try:
            with open(str(self.dir / name)) as f:
                return json.load(f)
        except FileNotFoundError:
            return {}

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
                    os.fsync(f.fileno())
                os.replace(tmp, str(path))
            except OSError as e:
                if tmp:
                    with contextlib.suppress(OSError):
                        os.unlink(tmp)
                raise AisError(EXIT_CANNOT_WRITE, "%s: %s" % (path, e))
            return new

    def prune_state(self, exists: Callable[[str], bool]) -> None:
        def prune(d: dict) -> dict:
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
