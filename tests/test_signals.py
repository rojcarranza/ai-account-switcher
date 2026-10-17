"""FR-3.8: the runner spawns the child with default handlers, ignores SIGINT/SIGQUIT, forwards SIGHUP/SIGTERM.

Each test runs the runner in its own Python process and process group, like ais in a terminal,
so a group SIGINT reaches ais and the child together, as Ctrl-C does.
"""
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

from ais.errors import AisError
from ais.runner import run_claude
from tests.helpers import SRC, TESTS, TempHomeCase

FAKES = TESTS / "fakes"
DRIVER = """
import os, sys
from pathlib import Path
from ais.runner import run_claude
def started():
    with open(sys.argv[1], "a") as f:
        f.write("started\\n")
sys.exit(run_claude(sys.argv[2:], dict(os.environ), Path.cwd(), "work", started))
"""
SETTLE = 0.3  # ais installs its handlers just after the child starts; no observable marker for that


class SignalTest(TempHomeCase):
    def setUp(self):
        super().setUp()
        self.ready = self.home / "ready"
        self.stop = self.home / "stop"
        self.marker = self.home / "started"

    def start(self, cmd, **env):
        if self.marker.exists():
            self.marker.unlink()
        full = dict(os.environ, PYTHONPATH=str(SRC), FAKE_READY=str(self.ready), FAKE_STOP=str(self.stop), **env)
        proc = subprocess.Popen([sys.executable, "-c", DRIVER, str(self.marker)] + cmd, env=full, cwd=str(self.home),
                                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                                start_new_session=True)
        self.addCleanup(self._kill, proc)
        return proc

    @staticmethod
    def _kill(proc):
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except OSError:
            pass
        proc.communicate(timeout=5)

    def child_pid(self):
        deadline = time.monotonic() + 5
        while not self.ready.exists():
            self.assertLess(time.monotonic(), deadline, "fake claude never became ready")
            time.sleep(0.02)
        time.sleep(SETTLE)
        return int(self.ready.read_text())

    def finish(self, proc):
        _, err = proc.communicate(timeout=10)
        self.assertEqual(self.marker.read_text(), "started\n")
        self.assertIn(b"ais: work", err)
        self.assertNotIn(b"Traceback", err)
        return proc.returncode

    def assertGone(self, pid):
        deadline = time.monotonic() + 5
        while True:
            try:
                os.kill(pid, 0)
            except ProcessLookupError:
                return
            self.assertLess(time.monotonic(), deadline, "child %d still alive" % pid)
            time.sleep(0.02)

    def test_child_exit_code_and_signal_passthrough(self):
        self.assertEqual(self.finish(self.start(["sh", "-c", "exit 7"])), 7)
        self.assertEqual(self.finish(self.start(["sh", "-c", "exit 0"])), 0)
        self.assertEqual(self.finish(self.start(["sh", "-c", "kill -KILL $$"])), 137)
        self.assertEqual(self.finish(self.start(["sh", "-c", "kill -TERM $$"])), 143)

    def test_child_keeps_default_sigint(self):
        proc = self.start([str(FAKES / "claude_default_sigint")])
        pid = self.child_pid()
        os.killpg(proc.pid, signal.SIGINT)
        self.assertEqual(self.finish(proc), 130)  # ais exited normally with 128+SIGINT, not killed by SIGINT
        self.assertGone(pid)

    def test_ais_survives_sigint_until_child_exits(self):
        proc = self.start([str(FAKES / "claude_trap")], FAKE_RC="5")
        self.child_pid()
        os.killpg(proc.pid, signal.SIGINT)
        os.killpg(proc.pid, signal.SIGQUIT)
        time.sleep(0.5)
        self.assertIsNone(proc.poll(), "ais died while the child was still running")
        self.stop.touch()
        self.assertEqual(self.finish(proc), 5)

    def test_sigterm_forwarded(self):
        proc = self.start([str(FAKES / "claude_trap")])
        pid = self.child_pid()
        os.kill(proc.pid, signal.SIGTERM)  # ais only, not the group
        self.assertEqual(self.finish(proc), 143)
        self.assertGone(pid)

    def test_sighup_forwarded(self):
        proc = self.start([str(FAKES / "claude_default_sigint")])
        pid = self.child_pid()
        os.kill(proc.pid, signal.SIGHUP)
        self.assertEqual(self.finish(proc), 128 + signal.SIGHUP)
        self.assertGone(pid)


class SpawnErrorTest(TempHomeCase):
    def run_bad(self, cmd, cwd):
        calls = []
        with self.assertRaises(AisError) as cm:
            run_claude(cmd, dict(os.environ), cwd, "work", lambda: calls.append(1))
        self.assertEqual(calls, [1])  # the mutex is released even though nothing started
        self.assertEqual(cm.exception.code, 69)
        return cm.exception.message

    def test_missing_executable_is_69(self):
        self.assertEqual(self.run_bad(["no-such-claude-xyz"], self.home), "no-such-claude-xyz is not on PATH")

    def test_missing_cwd_is_not_reported_as_missing_executable(self):
        msg = self.run_bad(["sh", "-c", "exit 0"], Path(self.home / "gone"))
        self.assertTrue(msg.startswith("cannot start sh: "), msg)
