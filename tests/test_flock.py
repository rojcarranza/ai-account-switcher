import fcntl
import os
import subprocess
import sys
import threading
import unittest

from ais.store import Store
from tests.helpers import SRC, TempHomeCase

INC = """
import sys
from pathlib import Path
from ais.store import Store
s = Store(Path(sys.argv[1]))
for _ in range(50):
    s.update_json("n.json", lambda d: {"n": d.get("n", 0) + 1})
"""

TRY = """
import fcntl, sys
f = open(sys.argv[1] + "/.config/ais/switch.lock", "a")
try:
    fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
    print("acquired")
except OSError:
    print("blocked")
"""


def run_py(code, home):
    env = dict(os.environ, HOME=str(home), PYTHONPATH=str(SRC))
    return subprocess.Popen([sys.executable, "-c", code, str(home)], env=env,
                            stdout=subprocess.PIPE, universal_newlines=True)


class FlockTest(TempHomeCase):
    def test_concurrent_updates_not_lost(self):
        procs = [run_py(INC, self.home) for _ in range(2)]
        for p in procs:
            p.communicate(timeout=30)
            self.assertEqual(p.returncode, 0)
        self.assertEqual(Store(self.home).read_json("n.json"), {"n": 100})

    def test_update_json_fn_may_log_and_update_other_file(self):
        s = Store(self.home)

        def fn(d):
            s.log("switch", "a", "sid", "ok")
            s.update_json("other.json", lambda o: {"o": 1})
            return {"n": 1}

        t = threading.Thread(target=s.update_json, args=("n.json", fn), daemon=True)
        t.start()
        t.join(5)
        self.assertFalse(t.is_alive(), "re-entrant call self-deadlocked")
        self.assertEqual(s.read_json("other.json"), {"o": 1})

    def test_switch_mutex_blocks_second_holder(self):
        s = Store(self.home)
        with s.switch_mutex():
            out, _ = run_py(TRY, self.home).communicate(timeout=30)
            self.assertEqual(out.strip(), "blocked")
        out, _ = run_py(TRY, self.home).communicate(timeout=30)
        self.assertEqual(out.strip(), "acquired")

    def test_log_rotates_at_1mb_under_lock(self):
        s = Store(self.home)
        s.log("switch", "a", "sid", "ok")
        log = self.ais_dir / "ais.log"
        with open(str(log), "ab") as f:
            f.write(b"x" * (1024 * 1024))
        held = open(str(self.ais_dir / ".lock"), "a")
        self.addCleanup(held.close)  # closing releases the flock even if an assert fails
        fcntl.flock(held, fcntl.LOCK_EX)
        t = threading.Thread(target=s.log, args=("switch", "a", "sid2", "ok"), daemon=True)
        t.start()
        t.join(0.5)
        self.assertTrue(t.is_alive(), "log() must wait for .lock")
        self.assertFalse((self.ais_dir / "ais.log.1").exists())
        fcntl.flock(held, fcntl.LOCK_UN)
        t.join(5)
        self.assertFalse(t.is_alive())
        self.assertGreaterEqual((self.ais_dir / "ais.log.1").stat().st_size, 1024 * 1024)
        self.assertIn("sid2", log.read_text())
        self.assertLess(log.stat().st_size, 1024)


if __name__ == "__main__":
    unittest.main()
