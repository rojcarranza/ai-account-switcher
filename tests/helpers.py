import os
import tempfile
import unittest
from pathlib import Path

TESTS = Path(__file__).resolve().parent
SRC = TESTS.parent / "src"


class TempHomeCase(unittest.TestCase):
    """Temp HOME, tests/fakes first on PATH; env restored on cleanup."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.home = Path(tmp.name)
        saved = {k: os.environ.get(k) for k in ("HOME", "PATH")}
        self.addCleanup(self._restore, saved)
        os.environ["HOME"] = str(self.home)
        os.environ["PATH"] = str(TESTS / "fakes") + os.pathsep + os.environ.get("PATH", "")
        self.ais_dir = self.home / ".config" / "ais"

    @staticmethod
    def _restore(saved):
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
