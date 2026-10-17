"""FR-6.1 to FR-6.4: `ais desktop` opens a Claude Desktop instance per account."""
import contextlib
import io
import os
import shlex
from pathlib import Path
from unittest import mock

from ais import cli, core
from ais.errors import AisError
from ais.providers.claude import _desktop_pid
from tests.helpers import TESTS
from tests.test_dry_run import tree_hash
from tests.test_switch import SwitchCase

FIXTURE = TESTS / "fixtures" / "ps_desktop.txt"
SUPPORT = "/Users/u/Library/Application Support/"


class DesktopTest(SwitchCase):
    def setUp(self):
        super().setUp()
        self.apps = self.home / "Applications"
        (self.apps / "Claude.app").mkdir(parents=True)
        self.roots = [self.apps]

    def desktop(self, account, *flags, roots=None):
        out, err = io.StringIO(), io.StringIO()
        real = cli._context

        def context(*a, **kw):
            ctx = real(*a, **kw)
            ctx.app_roots = self.roots if roots is None else roots
            return ctx
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err), \
                mock.patch.object(cli, "_context", context):
            code = cli.main(["desktop", account] + list(flags))
        return code, out.getvalue(), err.getvalue()

    def forbid_open(self):
        self.env(FAKE_OPEN_FORBID="1")

    def open_calls(self):
        return [l for l in self.calls_text().splitlines() if l.startswith("open ")]

    def test_default_opens_new_instance_while_work_runs(self):
        self.env(FAKE_PS_FILE=str(self.home / "ps.txt"))
        (self.home / "ps.txt").write_text(
            "301 /Applications/Claude.app/Contents/MacOS/Claude --user-data-dir=%s/Library/Application Support/Claude-ais-work\n"
            % self.home)
        code, _, err = self.desktop("personal")
        self.assertEqual(code, 0, err)
        self.assertEqual(self.open_calls(), ["open -n -a %s" % (self.apps / "Claude.app")])

    def test_extra_account_opens_new_instance_with_its_folder(self):
        code, _, err = self.desktop("work")
        self.assertEqual(code, 0, err)
        folder = self.home / "Library" / "Application Support" / "Claude-ais-work"
        self.assertEqual(self.open_calls(), ["open -n -a %s --args --user-data-dir=%s"
                                             % (self.apps / "Claude.app", folder)])

    def test_already_running_does_not_launch(self):
        self.forbid_open()
        self.env(FAKE_PS_OUT="4242 /Applications/Claude.app/Contents/MacOS/Claude --user-data-dir=%s"
                 "/Library/Application Support/Claude-ais-work" % self.home)
        code, out, err = self.desktop("work")
        self.assertEqual(code, 0, err)
        self.assertEqual(out.strip(), "Work Desktop is already open (PID 4242)")
        self.assertEqual(self.open_calls(), [])

    def test_ps_parsing_helpers_other_instances_and_spaces(self):
        text = FIXTURE.read_text()
        work = Path(SUPPORT + "Claude-ais-work")
        self.assertEqual(_desktop_pid(text, work), 301)  # helpers and the Switcher's Claude-work never match
        self.assertEqual(_desktop_pid(text, None), 101)
        self.assertIsNone(_desktop_pid(text, Path(SUPPORT + "Claude-ais-other")))
        self.assertIsNone(_desktop_pid(text, Path(SUPPORT + "Claude-work-x")))
        self.assertIsNone(_desktop_pid("", None))
        tools = "\n".join(l for l in text.splitlines() if l.split()[0] in ("401", "402"))
        self.assertIsNone(_desktop_pid(tools, None))  # a tool that merely names the executable
        self.assertEqual(_desktop_pid("7 /Users/u/My Apps/Claude.app/Contents/MacOS/Claude", None), 7)

    def test_default_not_matched_by_extra_instances(self):
        text = "\n".join(l for l in FIXTURE.read_text().splitlines() if not l.strip().startswith("101"))
        self.assertIsNone(_desktop_pid(text, None))

    def test_app_missing_exits_69(self):
        a, b = self.home / "nope1", self.home / "nope2"
        code, _, err = self.desktop("work", roots=[a, b])
        self.assertEqual(code, 69)
        self.assertIn("Claude Desktop not found in %s or %s" % (a, b), err)
        self.assertEqual(self.open_calls(), [])

    def test_dangling_symlink_root_falls_through(self):
        bad = self.home / "bad"
        bad.mkdir()
        os.symlink(str(self.home / "gone"), str(bad / "Claude.app"))
        code, _, err = self.desktop("personal", roots=[bad, self.apps])
        self.assertEqual(code, 0, err)
        self.assertEqual(self.open_calls(), ["open -n -a %s" % (self.apps / "Claude.app")])

    def test_open_failure_exits_69_with_stderr(self):
        self.env(FAKE_OPEN_RC="1", FAKE_OPEN_ERR="open: boom")
        code, _, err = self.desktop("work")
        self.assertEqual(code, 69)
        self.assertIn("open: boom", err)

    def test_ps_failure_exits_69_and_launches_nothing(self):
        self.env(FAKE_PS_RC="1", FAKE_PS_ERR="ps: nope")
        code, _, err = self.desktop("work")
        self.assertEqual(code, 69)
        self.assertIn("cannot check for a running Claude Desktop: ps: nope", err)
        self.assertEqual(self.open_calls(), [])

    def test_open_timeout_exits_69(self):
        self.env(FAKE_OPEN_SLEEP="5")
        with mock.patch.object(core, "OPEN_TIMEOUT", 0.3):
            code, _, err = self.desktop("work")
        self.assertEqual(code, 69)
        self.assertIn("timed out", err)

    def test_works_without_cwd(self):
        with mock.patch.object(cli.Path, "cwd", side_effect=OSError("gone")):
            code, _, err = self.desktop("work")
        self.assertEqual(code, 0, err)

    def test_unknown_account_exits_64(self):
        code, _, err = self.desktop("nobody")
        self.assertEqual(code, 64)
        self.assertIn("personal", err)
        code, _, err = self.desktop("")
        self.assertEqual(code, 64)

    def test_dry_run_checks_but_never_opens(self):
        self.forbid_open()
        code, out, err = self.desktop("work", "--dry-run")
        self.assertEqual(code, 0, err)
        folder = self.home / "Library" / "Application Support" / "Claude-ais-work"
        want = ["open", "-n", "-a", str(self.apps / "Claude.app"), "--args", "--user-data-dir=" + str(folder)]
        self.assertEqual(out.strip(), "Would run: " + " ".join(shlex.quote(a) for a in want))
        self.assertIn("ps -x -ww -o pid=,args=\n", self.calls_text())  # -x: Desktop has no terminal
        self.assertEqual(self.open_calls(), [])
        self.env(FAKE_PS_OUT="9 /Applications/Claude.app/Contents/MacOS/Claude --user-data-dir=%s" % folder)
        code, out, _ = self.desktop("work", "--dry-run")
        self.assertEqual((code, out.strip()), (0, "Work Desktop is already open (PID 9)"))

    def test_never_touches_claude_keychain_or_switcher_files(self):
        for d in (".claude", ".claude-accounts", ".config/claude-switcher"):
            (self.home / d).mkdir(parents=True, exist_ok=True)
            (self.home / d / "f").write_text("x")
        (self.home / ".claude.json").write_text("{}")
        self.env(FAKE_SECURITY_RC="1")
        watched = [".claude", ".claude.json", ".claude-accounts", ".config/claude-switcher", ".config/ais"]

        def hashes():
            return [tree_hash(self.home / w) if (self.home / w).is_dir()
                    else ((self.home / w).read_bytes(), os.lstat(str(self.home / w)).st_mtime_ns) for w in watched]
        before = os.listdir(str(self.ais_dir)), hashes()
        for acct in ("personal", "work"):
            self.assertEqual(self.desktop(acct)[0], 0)
        self.assertEqual((os.listdir(str(self.ais_dir)), hashes()), before)
        self.assertNotIn("security", self.calls_text())
