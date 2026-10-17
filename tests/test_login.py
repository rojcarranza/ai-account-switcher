"""FR-1.1, FR-1.4, FR-1.6: `ais login` runs the provider's login in the account's own slot."""
import contextlib
import io
import json
import os
from pathlib import Path
from unittest import mock

from ais import cli
from ais.errors import AisError
from ais.providers.claude import BILLING_ENV, CONFIG_DIR_ENV, ClaudeProvider
from tests.helpers import TempHomeCase

SLOT = "CLAUDE_SECURESTORAGE_CONFIG_DIR"


class LoginTest(TempHomeCase):
    def setUp(self):
        super().setUp()
        self.work = str(self.home / ".claude-work")
        self.ais_dir.mkdir(parents=True)
        (self.ais_dir / "config.json").write_text(json.dumps({
            "version": 1, "default": "personal", "accounts": {
                "personal": {"label": "Personal", "provider": "claude", "credDir": None},
                "work": {"label": "Work", "provider": "claude", "credDir": self.work}}}))
        self.calls = self.home / "calls.log"
        os.environ["FAKE_CALL_LOG"] = str(self.calls)
        self.addCleanup(os.environ.pop, "FAKE_CALL_LOG", None)
        # the developer shell may itself run inside Claude Code and carry billing variables
        for k in BILLING_ENV + (SLOT, CONFIG_DIR_ENV, "FAKE_CLAUDE_LOGIN_RC"):
            if k in os.environ:
                saved = os.environ.pop(k)
                self.addCleanup(os.environ.__setitem__, k, saved)
            self.addCleanup(os.environ.pop, k, None)

        # never read the host's /Library settings
        roots = {"home": self.home, "managed": self.home / "managed", "managed_prefs": self.home / "prefs"}
        patch = mock.patch.object(ClaudeProvider, "default_settings_roots", lambda _self: roots)
        patch.start()
        self.addCleanup(patch.stop)

    def ais(self, *args):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = cli.main(list(args))
        return code, out.getvalue(), err.getvalue()

    def calls_text(self):
        return self.calls.read_text() if self.calls.exists() else ""

    def log_lines(self):
        p = self.ais_dir / "ais.log"
        return p.read_text().splitlines() if p.exists() else []

    def test_login_runs_provider_login_with_account_env(self):
        os.environ["FAKE_CLAUDE_LOGIN_RC"] = "3"
        code, _, _ = self.ais("login", "work")
        self.assertEqual(code, 3)
        self.assertEqual(self.calls_text(), "claude auth login\nslot=%s\n" % self.work)
        lines = self.log_lines()
        self.assertEqual(len(lines), 1)
        rec = json.loads(lines[0])
        self.assertEqual((rec["command"], rec["account"], rec["result"]), ("login", "work", "exit 3"))

    def test_login_other_slot_untouched(self):
        os.environ[SLOT] = "/stale"
        code, _, err = self.ais("login", "personal")
        self.assertEqual(code, 0)
        self.assertEqual(self.calls_text(), "claude auth login\nslot=<unset>\n")
        self.assertIn("removed inherited " + SLOT, err)
        self.assertNotIn("security", self.calls_text())  # the security fake logs every call

    def test_claude_missing_exits_69(self):
        os.environ["PATH"] = "/usr/bin:/bin"  # no claude there; restored by TempHomeCase
        code, _, err = self.ais("login", "work")
        self.assertEqual(code, 69)
        self.assertIn("install Claude Code", err)

    def test_login_dry_run_prints_command(self):
        code, out, _ = self.ais("login", "work", "--dry-run")
        self.assertEqual(code, 0)
        self.assertEqual(out, "%s=%s claude auth login\n" % (SLOT, self.work))
        code, out, _ = self.ais("login", "personal", "--dry-run")
        self.assertEqual(out, "claude auth login\n")
        self.assertEqual(self.calls_text(), "")
        self.assertEqual(self.log_lines(), [])

    def test_unknown_account_exits_64_listing_names(self):
        code, _, err = self.ais("login", "nope")
        self.assertEqual(code, 64)
        self.assertIn("personal, work", err)

    def test_api_key_refused_unless_allowed(self):
        os.environ["ANTHROPIC_API_KEY"] = "x"
        code, _, err = self.ais("login", "work")
        self.assertEqual(code, 77)
        self.assertIn("ANTHROPIC_API_KEY", err)
        self.assertEqual(self.calls_text(), "")
        code, _, _ = self.ais("login", "work", "--allow-api-key")
        self.assertEqual(code, 0)
        self.assertEqual(self.calls_text(), "claude auth login\nslot=%s\n" % self.work)
        self.assertEqual(len(self.log_lines()), 1)

    def test_log_failure_keeps_claude_exit_code(self):
        os.environ["FAKE_CLAUDE_LOGIN_RC"] = "3"
        with mock.patch("ais.store.Store.log", side_effect=AisError(73, "cannot write log")):
            code, _, err = self.ais("login", "work")
        self.assertEqual(code, 3)
        self.assertIn("ais: warning: cannot write log", err)

    def test_ctrl_c_returns_130_without_traceback(self):
        with mock.patch("ais.core.cmd_login", side_effect=KeyboardInterrupt):
            code, _, err = self.ais("login", "work")
        self.assertEqual((code, err), (130, ""))

    def test_missing_cwd_exits_66(self):
        with mock.patch.object(Path, "cwd", side_effect=FileNotFoundError):
            code, _, err = self.ais("login", "work")
        self.assertEqual(code, 66)
        self.assertIn("the current folder no longer exists", err)

    def test_missing_account_exits_64_listing_names(self):
        code, _, err = self.ais("login")
        self.assertEqual(code, 64)
        self.assertIn("personal, work", err)

    def test_abbreviated_flag_is_not_accepted(self):
        os.environ["ANTHROPIC_API_KEY"] = "x"
        code, _, _ = self.ais("login", "work", "--allow")
        self.assertEqual(code, 64)
        self.assertEqual(self.calls_text(), "")

    def test_usage_error_starts_with_message(self):
        _, _, err = self.ais("login", "work", "--bogus")
        self.assertTrue(err.startswith("ais: "))
        self.assertIn("\nusage: ais", err)
