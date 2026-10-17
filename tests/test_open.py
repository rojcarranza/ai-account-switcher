import os
import time
import unicodedata
from pathlib import Path

from ais import procs
from ais.providers.base import Session
from ais.providers.claude import ClaudeProvider
from tests.helpers import TempHomeCase

DESKTOP = "/Users/x/Library/Application Support/Claude/claude-code/2.1.299/claude.app/Contents/MacOS/claude"


class OpenTest(TempHomeCase):
    def setUp(self):
        super().setUp()
        self.p = ClaudeProvider()
        self.log = self.home / "calls"
        self.folder = self.home / "proj"
        self.folder.mkdir()
        self._env = {}
        self.addCleanup(self._unset)
        self.env(FAKE_CALL_LOG=str(self.log))

    def env(self, **kw):
        for k, v in kw.items():
            self._env[k] = os.environ.get(k)
            os.environ[k] = v

    def _unset(self):
        for k, v in self._env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    def fake(self, procs_):
        """procs_: list of (pid, args, cwd)."""
        self.env(FAKE_PGREP_OUT="\n".join(str(p) for p, _, _ in procs_),
                 FAKE_PS_OUT="\n".join("%d %s" % (p, a) for p, a, _ in procs_),
                 FAKE_LSOF_OUT="\n".join("p%d\nn%s" % (p, c) for p, _, c in procs_))

    def session(self):
        return Session("s", self.folder, self.home / "t.jsonl", "", 0.0)

    def pid(self):
        found, warns = procs.process_cwds("claude", 5)
        self.assertEqual(warns, [])
        return self.p.open_session_pid(self.session(), found)

    def test_any_claude_in_folder_marks_open(self):
        self.fake([(300, "claude", str(self.folder)), (200, "claude --resume x", str(self.folder)),
                   (100, "claude", str(self.home))])
        self.assertEqual(self.pid(), 200)

    def test_open_session_started_without_ais(self):
        self.fake([(7, "claude -p hi", str(self.folder))])
        self.assertEqual(self.pid(), 7)

    def test_other_folder_is_not_open(self):
        self.fake([(7, "claude", str(self.home))])
        self.assertIsNone(self.pid())

    def test_nfd_spelling_matches(self):
        nfd = Path(unicodedata.normalize("NFD", str(self.home / "café")))
        (self.home / "café").mkdir()
        self.folder = Path(unicodedata.normalize("NFC", str(nfd)))
        self.fake([(7, "claude", str(nfd))])
        self.assertEqual(self.pid(), 7)

    def test_daemon_and_bg_helpers_are_ignored(self):
        f = str(self.folder)
        self.fake([(1, "claude daemon run", f), (2, "claude bg-pty-host", f), (3, "/x/claude bg-spare", f)])
        self.assertIsNone(self.pid())

    def test_desktop_session_counts(self):
        self.fake([(9, DESKTOP, str(self.folder))])
        self.assertEqual(self.pid(), 9)

    def test_no_match_is_empty_without_warning(self):
        self.assertEqual(procs.process_cwds("claude", 5), ({}, []))
        self.assertFalse("lsof" in self.log.read_text())

    def test_one_batched_lsof_call(self):
        self.fake([(11, "claude", "/a"), (12, "claude", "/b"), (13, "claude", "/c")])
        found, _ = procs.process_cwds("claude", 5)
        self.assertEqual(sorted(found), [11, 12, 13])
        calls = self.log.read_text().splitlines()
        self.assertEqual(len([c for c in calls if c.startswith("lsof")]), 1)
        self.assertEqual(len([c for c in calls if c.startswith("ps")]), 1)
        self.assertIn("-p 11,12,13", [c for c in calls if c.startswith("lsof")][0])

    def test_hung_lsof_times_out_and_is_killed(self):
        child = self.home / "child.pid"
        self.fake([(11, "claude", "/a")])
        self.env(FAKE_LSOF_HANG="1", FAKE_LSOF_CHILD_FILE=str(child))
        t = time.time()
        found, warns = procs.process_cwds("claude", 1)
        self.assertLess(time.time() - t, 5)
        self.assertEqual(found, {})
        self.assertTrue(warns and "lsof timed out" in warns[0])
        pid = int(child.read_text())
        for _ in range(20):
            try:
                os.kill(pid, 0)
            except ProcessLookupError:
                return
            time.sleep(0.1)
        self.fail("lsof child still running")

    def test_missing_tool_warns(self):
        self.env(PATH=str(self.home))  # no pgrep anywhere
        found, warns = procs.process_cwds("claude", 5)
        self.assertEqual(found, {})
        self.assertTrue(warns and "pgrep" in warns[0])
