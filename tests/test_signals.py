"""FR-3.8: the runner spawns the child with default handlers, ignores SIGINT/SIGQUIT, forwards SIGHUP/SIGTERM.

Each test runs the runner in its own Python process and process group, like ais in a terminal,
so a group SIGINT reaches ais and the child together, as Ctrl-C does.
"""
import io
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from unittest import mock

from ais import runner

from ais.errors import AisError
from ais.runner import run_claude
from tests.helpers import SRC, TESTS, TempHomeCase

FAKES = TESTS / "fakes"
DRIVER = """
import os, sys
from pathlib import Path
from ais.runner import run_claude
import signal
def started():
    with open(sys.argv[1], "a") as f:
        f.write("started\\n")
    for name in os.environ.get("SELF_SIGNAL", "").split():  # signals arriving right after the spawn
        os.kill(os.getpid(), getattr(signal, name))
sys.exit(run_claude(sys.argv[2:], dict(os.environ), Path.cwd(), "work", started))
"""


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

    def test_signals_right_after_spawn(self):
        # SIGINT/SIGQUIT/SIGTERM land during on_started, before ais's wait loop
        # the forwarded SIGTERM may reach the child before its trap is set: 143 either way
        proc = self.start([str(FAKES / "claude_trap")], SELF_SIGNAL="SIGINT SIGQUIT SIGTERM")
        self.assertEqual(self.finish(proc), 143)


class InProcessTest(TempHomeCase):
    def run_ok(self, label="work", on_started=lambda: None):
        return run_claude(["sh", "-c", "exit 0"], dict(os.environ), self.home, label, on_started)

    def test_label_control_chars_stripped(self):
        class Tty(io.StringIO):
            def isatty(self):
                return True
        out, err = Tty(), io.StringIO()
        with mock.patch.object(sys, "stdout", out), mock.patch.object(sys, "stderr", err):
            self.assertEqual(self.run_ok(label="wo\007rk\033]0;x\x7f\n"), 0)
        self.assertEqual(err.getvalue(), "ais: work]0;x\n")
        self.assertEqual(out.getvalue(), "\033]0;claude (work]0;x)\007")

    def test_previous_handlers_restored(self):
        sigs = (signal.SIGINT, signal.SIGQUIT, signal.SIGHUP, signal.SIGTERM)
        mine = lambda *_: None
        before = {s: signal.signal(s, mine) for s in sigs}
        self.addCleanup(lambda: [signal.signal(s, h) for s, h in before.items()])
        self.assertEqual(self.run_ok(), 0)
        self.assertEqual({s: signal.getsignal(s) for s in sigs}, {s: mine for s in sigs})

    def test_on_started_error_still_waits_for_child(self):
        children = []
        real = subprocess.Popen

        def popen(*a, **kw):
            children.append(real(*a, **kw))
            return children[-1]

        def boom():
            raise RuntimeError("mutex release failed")
        before = signal.getsignal(signal.SIGTERM)
        with mock.patch.object(runner.subprocess, "Popen", popen), self.assertRaises(RuntimeError):
            self.run_ok(on_started=boom)
        self.assertEqual(children[0].returncode, 0)  # reaped, not orphaned
        self.assertIs(signal.getsignal(signal.SIGTERM), before)

    def test_on_started_error_does_not_hide_spawn_error(self):
        def boom():
            raise RuntimeError("mutex release failed")
        with self.assertRaises(AisError) as cm:
            run_claude(["no-such-claude-xyz"], dict(os.environ), self.home, "work", boom)
        self.assertEqual(cm.exception.code, 69)

    def test_sigterm_before_child_exists_is_replayed(self):
        real = subprocess.Popen

        def popen(*a, **kw):
            os.kill(os.getpid(), signal.SIGTERM)  # arrives while there is no child yet
            return real(*a, **kw)
        env = dict(os.environ, FAKE_READY=str(self.home / "ready"), FAKE_STOP=str(self.home / "stop"))
        with mock.patch.object(runner.subprocess, "Popen", popen):
            rc = run_claude([str(FAKES / "claude_trap")], env, self.home, "work", lambda: None)
        self.assertEqual(rc, 143)


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
