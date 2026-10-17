"""FR-3.5, FR-3.15: `ais run` starts claude in an account's slot and records the new session."""
import contextlib
import io
import json
import os
import time
from pathlib import Path
from unittest import mock

from ais import cli
from ais.errors import AisError
from ais.providers.claude import BILLING_ENV, CONFIG_DIR_ENV, ClaudeProvider
from tests.helpers import TempHomeCase

SLOT = "CLAUDE_SECURESTORAGE_CONFIG_DIR"
UUID = "44444444-4444-4444-8444-444444444444"
OLD = "55555555-5555-4555-8555-555555555555"


class RunTest(TempHomeCase):
    def setUp(self):
        super().setUp()
        self.work = str(self.home / ".claude-work")
        self.ais_dir.mkdir(parents=True)
        (self.ais_dir / "config.json").write_text(json.dumps({
            "version": 1, "default": "personal", "accounts": {
                "personal": {"label": "Personal", "provider": "claude", "credDir": None},
                "work": {"label": "Work", "provider": "claude", "credDir": self.work}}}))
        self.proj = self.home / "proj"
        self.proj.mkdir()
        old = os.getcwd()
        os.chdir(str(self.proj))
        self.addCleanup(os.chdir, old)
        self.argv_log = self.home / "argv.log"
        self.transcript = self.home / ".claude" / "projects" / "x" / (UUID + ".jsonl")
        env = {"FAKE_CLAUDE_ARGV_LOG": str(self.argv_log), "FAKE_CLAUDE_CWD": str(self.proj),
               "FAKE_CLAUDE_WRITE_TRANSCRIPT": str(self.transcript)}
        os.environ.update(env)
        for k in list(env) + list(BILLING_ENV) + [SLOT, CONFIG_DIR_ENV, "FAKE_CLAUDE_RUN_RC"]:
            if k in os.environ and k not in env:
                saved = os.environ.pop(k)
                self.addCleanup(os.environ.__setitem__, k, saved)
            self.addCleanup(os.environ.pop, k, None)
        roots = {"home": self.home, "managed": self.home / "managed", "managed_prefs": self.home / "prefs"}
        patch = mock.patch.object(ClaudeProvider, "default_settings_roots", lambda _self: roots)
        patch.start()
        self.addCleanup(patch.stop)

    def ais(self, *args):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = cli.main(list(args))
        return code, out.getvalue(), err.getvalue()

    def argv(self):
        return self.argv_log.read_text().splitlines() if self.argv_log.exists() else None

    def slot(self):
        return Path(str(self.argv_log) + ".env").read_text().strip()

    def state(self):
        p = self.ais_dir / "state.json"
        return json.loads(p.read_text()) if p.exists() else {}

    def log_lines(self):
        p = self.ais_dir / "ais.log"
        return [json.loads(x) for x in p.read_text().splitlines()] if p.exists() else []

    def test_run_default_account(self):
        code, _, _ = self.ais("run")
        self.assertEqual(code, 0)
        self.assertEqual(self.slot(), "slot=<unset>")

    def test_run_named_account_sets_slot(self):
        self.ais("run", "work")
        self.assertEqual(self.slot(), "slot=" + self.work)

    def test_run_passes_args(self):
        code, _, _ = self.ais("run", "work", "--", "--model", "opus", "-p", "--flag=x y")
        self.assertEqual(code, 0)
        self.assertEqual(self.argv(), ["--model", "opus", "-p", "--flag=x y"])

    def test_run_passes_claude_exit_code(self):
        os.environ["FAKE_CLAUDE_RUN_RC"] = "5"
        code, _, _ = self.ais("run")
        self.assertEqual(code, 5)
        self.assertEqual(self.log_lines()[0]["result"], "exit 5")

    def test_run_rejects_resume_and_continue_flags(self):
        for flag in (["--resume"], ["--resume=abc"], ["--continue"], ["--continue=x"],
                     ["-r"], ["-c"], ["-pc"], ["-rp"], ["--resume", "abc"],
                     ["-r=abc"], ["-r5"], ["-pr5"], ["-c=1"], ["--from-pr"], ["--from-pr=12"],
                     ["--fork-session"]):
            code, _, err = self.ais("run", "--", *flag)
            self.assertEqual(code, 64, flag)
            self.assertIn("ais switch", err)
        self.assertIsNone(self.argv())

    def test_run_allows_unrelated_short_flags(self):
        code, _, _ = self.ais("run", "--", "-p", "-v")
        self.assertEqual(code, 0)

    def test_run_rejects_settings_both_forms(self):
        for flag in (["--settings", "f.json"], ["--settings=f.json"]):
            code, _, err = self.ais("run", "--", *flag)
            self.assertEqual(code, 64, flag)
            self.assertIn("ais switch", err)
        self.assertIsNone(self.argv())

    def test_run_settings_allowed_with_allow_api_key(self):
        code, _, _ = self.ais("run", "--allow-api-key", "--", "--settings", "f.json")
        self.assertEqual(code, 0)
        self.assertEqual(self.argv(), ["--settings", "f.json"])

    def test_run_extra_positional_exits_64(self):
        code, _, _ = self.ais("run", "work", "extra")
        self.assertEqual(code, 64)
        self.assertIsNone(self.argv())

    def test_run_records_last_used_after_exit(self):
        code, _, _ = self.ais("run", "work")
        self.assertEqual(code, 0)
        rec = self.state()["sessions"][str(self.transcript)]
        self.assertEqual(rec["account"], "work")
        self.assertRegex(rec["at"], r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$")
        self.assertEqual(self.log_lines()[0]["session_id"], UUID)

    def test_run_keeps_other_state(self):
        (self.ais_dir / "state.json").write_text(json.dumps(
            {"other": 1, "sessions": {"/a": {"account": "work", "at": "t"}}}))
        self.ais("run")
        st = self.state()
        self.assertEqual(st["other"], 1)
        self.assertIn("/a", st["sessions"])
        self.assertIn(str(self.transcript), st["sessions"])

    def test_run_does_not_record_preexisting_transcript(self):
        old = self.transcript.parent / (OLD + ".jsonl")
        old.parent.mkdir(parents=True)
        old.write_text('{"cwd": "%s"}\n' % self.proj)
        del os.environ["FAKE_CLAUDE_WRITE_TRANSCRIPT"]
        fake = mock.Mock()
        fake.time.return_value = time.time() + 100  # launch "later" than the file's birth
        with mock.patch("ais.core.time", fake):
            code, _, _ = self.ais("run")
        self.assertEqual(code, 0)
        self.assertEqual(self.state(), {})
        self.assertEqual(self.log_lines()[0]["session_id"], "")

    def test_run_flags_after_double_dash_go_to_claude(self):
        code, out, _ = self.ais("run", "--", "--dry-run")
        self.assertEqual((code, out), (0, ""))
        self.assertEqual(self.argv(), ["--dry-run"])

    def test_run_trailing_double_dash_means_no_args(self):
        code, _, _ = self.ais("run", "work", "--")
        self.assertEqual(code, 0)
        self.assertEqual(self.argv(), [])
        self.assertEqual(self.slot(), "slot=" + self.work)

    def test_run_non_object_sessions_warns_and_keeps_exit_code(self):
        (self.ais_dir / "state.json").write_text(json.dumps({"sessions": []}))
        code, _, err = self.ais("run")
        self.assertEqual(code, 0)
        self.assertIn("sessions is not an object", err)
        self.assertEqual(json.loads((self.ais_dir / "state.json").read_text()), {"sessions": []})

    def test_run_record_failure_keeps_exit_code(self):
        os.environ["FAKE_CLAUDE_RUN_RC"] = "4"
        with mock.patch("ais.store.Store.update_json", side_effect=AisError(73, "cannot write state")):
            code, _, err = self.ais("run")
        self.assertEqual(code, 4)
        self.assertIn("ais: warning: cannot write state", err)

    def test_run_billing_risk_77(self):
        os.environ["ANTHROPIC_API_KEY"] = "x"
        code, _, err = self.ais("run", "work")
        self.assertEqual(code, 77)
        self.assertIn("ANTHROPIC_API_KEY", err)
        self.assertIsNone(self.argv())

    def test_run_dry_run(self):
        code, out, _ = self.ais("run", "work", "--dry-run", "--", "--model", "o p")
        self.assertEqual(code, 0)
        self.assertEqual(out, "%s=%s claude --model 'o p'\n" % (SLOT, self.work))
        self.assertIsNone(self.argv())
        self.assertEqual(self.state(), {})
        self.assertEqual(self.log_lines(), [])

    def test_run_claude_missing_exits_69(self):
        os.environ["PATH"] = "/usr/bin:/bin"
        code, _, err = self.ais("run")
        self.assertEqual(code, 69)
        self.assertIn("install Claude Code", err)
