"""FR-3.1 to FR-3.4, FR-3.6, FR-3.9 to FR-3.12, FR-3.14: `ais switch` resumes a session on another account."""
import contextlib
import io
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

from ais import cli
from ais.providers.claude import BILLING_ENV, CONFIG_DIR_ENV, ClaudeProvider
from tests.helpers import SRC, TempHomeCase

SLOT = "CLAUDE_SECURESTORAGE_CONFIG_DIR"
UUID = "44444444-4444-4444-8444-444444444444"
OTHER = "66666666-6666-4666-8666-666666666666"
MISSING = "77777777-7777-4777-8777-777777777777"

# a child ais with the test's settings roots: never reads the host's /Library
CHILD = """
import sys
from pathlib import Path
from ais import cli
from ais.providers.claude import ClaudeProvider
h = Path(sys.argv[1])
ClaudeProvider.default_settings_roots = lambda self: {"home": h, "managed": h / "managed", "managed_prefs": h / "prefs"}
sys.exit(cli.main(sys.argv[2:]))
"""


def line(content, cwd, **extra):
    d = {"type": "user", "message": {"content": content}, "cwd": str(cwd)}
    d.update(extra)
    return json.dumps(d) + "\n"


class SwitchCase(TempHomeCase):
    def setUp(self):
        super().setUp()
        self.work = str(self.home / ".claude-work")
        self.ais_dir.mkdir(parents=True)
        self.write_config()
        self.proj = self.home / "proj"
        self.proj.mkdir()
        old = os.getcwd()
        os.chdir(str(self.proj))
        self.addCleanup(os.chdir, old)
        self.projects = self.home / ".claude" / "projects"
        self.transcript = self.add_session(UUID, self.proj, "Main task", 2000)
        self.argv_log = self.home / "argv.log"
        self.calls = self.home / "calls.log"
        # the developer shell may run inside Claude Code: clear billing and fake-control variables
        for k in [k for k in os.environ if k.startswith("FAKE_")] + list(BILLING_ENV) + [SLOT, CONFIG_DIR_ENV]:
            if k in os.environ:
                saved = os.environ.pop(k)
                self.addCleanup(os.environ.__setitem__, k, saved)
        self.env(FAKE_CLAUDE_ARGV_LOG=str(self.argv_log), FAKE_CALL_LOG=str(self.calls))
        self.roots = {"home": self.home, "managed": self.home / "managed", "managed_prefs": self.home / "prefs"}
        patch = mock.patch.object(ClaudeProvider, "default_settings_roots", lambda _self: self.roots)
        patch.start()
        self.addCleanup(patch.stop)

    def env(self, **kw):
        for k, v in kw.items():
            self.addCleanup(os.environ.pop, k, None)
            os.environ[k] = v

    def write_config(self, extra_accounts=None, acks=None):
        accounts = {"personal": {"label": "Personal", "provider": "claude", "credDir": None},
                    "work": {"label": "Work", "provider": "claude", "credDir": self.work}}
        accounts.update(extra_accounts or {})
        cfg = {"version": 1, "default": "personal", "accounts": accounts, "menu_privacy": False}
        if acks is not None:
            cfg["cross_account_ack"] = acks
        (self.ais_dir / "config.json").write_text(json.dumps(cfg))

    def add_session(self, sid, folder, title, mtime, extra_lines=""):
        p = self.projects / "p" / (sid + ".jsonl")
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(line(title, folder) + extra_lines)
        os.utime(str(p), (mtime, mtime))
        return p

    def last_used(self, account, transcript=None):
        (self.ais_dir / "state.json").write_text(json.dumps(
            {"sessions": {str(transcript or self.transcript): {"account": account, "at": "t"}}}))

    def ais(self, *args, stdin=""):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err), \
                mock.patch("sys.stdin", io.StringIO(stdin)):
            code = cli.main(list(args))
        return code, out.getvalue(), err.getvalue()

    def argv(self):
        return self.argv_log.read_text().splitlines() if self.argv_log.exists() else None

    def slot(self):
        return Path(str(self.argv_log) + ".env").read_text().strip()

    def claude_cwd(self):
        return Path(str(self.argv_log) + ".cwd").read_text().strip()

    def state(self):
        p = self.ais_dir / "state.json"
        return json.loads(p.read_text()) if p.exists() else {}

    def config(self):
        return json.loads((self.ais_dir / "config.json").read_text())

    def log_lines(self):
        p = self.ais_dir / "ais.log"
        return [json.loads(x) for x in p.read_text().splitlines()] if p.exists() else []

    def calls_text(self):
        return self.calls.read_text() if self.calls.exists() else ""

    def snapshots(self):
        d = self.ais_dir / "snapshots"
        return sorted(p.name for p in d.iterdir()) if d.exists() else []


class SwitchTest(SwitchCase):
    def test_switch_resumes_on_other_account(self):
        self.write_config(acks={"personal->work": "2026-10-01"})
        self.last_used("personal")
        code, _, err = self.ais("switch")
        self.assertEqual(code, 0, err)
        self.assertEqual(self.argv(), ["--resume", UUID])
        self.assertEqual(self.slot(), "slot=" + self.work)
        self.assertEqual(self.claude_cwd(), os.path.realpath(str(self.proj)))
        self.assertIn("ais: Work", err)
        rec = self.state()["sessions"][str(self.transcript)]
        self.assertEqual(rec["account"], "work")
        self.assertRegex(rec["at"], r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$")
        self.assertEqual(len(self.snapshots()), 1)
        log = self.log_lines()
        self.assertEqual([(x["command"], x["account"], x["session_id"], x["result"]) for x in log],
                         [("switch", "work", UUID, "exit 0")])
        # and back again: the other account of work is personal (default slot: variable unset)
        self.write_config(acks={"personal->work": "2026-10-01", "work->personal": "2026-10-01"})
        code, _, _ = self.ais("switch")
        self.assertEqual((code, self.slot()), (0, "slot=<unset>"))

    def test_switch_passes_claude_exit_code(self):
        self.last_used("work")
        self.env(FAKE_CLAUDE_RUN_RC="5")
        code, _, _ = self.ais("switch", "work")
        self.assertEqual(code, 5)
        self.assertEqual(self.log_lines()[0]["result"], "exit 5")

    def test_switch_drops_entries_for_missing_transcripts(self):
        # FR-5.6: the last-used update also drops records whose transcript is gone
        gone = str(self.home / "gone.jsonl")
        (self.ais_dir / "state.json").write_text(json.dumps({"menu_plugin": "/p", "sessions": {
            str(self.transcript): {"account": "work", "at": "t"}, gone: {"account": "work", "at": "t"}}}))
        code, _, err = self.ais("switch", "work")
        self.assertEqual(code, 0, err)
        self.assertEqual(list(self.state()["sessions"]), [str(self.transcript)])
        self.assertEqual(self.state()["menu_plugin"], "/p")

    def test_switch_unknown_last_used_assumes_default_account(self):
        # a session started with plain `claude` has no record: it ran on the default account
        self.write_config(acks={"personal->work": "2026-10-01"})
        code, _, err = self.ais("switch")
        self.assertEqual(code, 0, err)
        self.assertEqual(self.slot(), "slot=" + self.work)
        self.assertIn("assuming it last ran on Personal", err)
        self.assertEqual(self.state()["sessions"][str(self.transcript)]["account"], "work")

    def test_switch_unknown_last_used_still_asks_ack(self):
        code, _, err = self.ais("switch", stdin="")  # FR-2.8 for personal->work: EOF declines
        self.assertEqual(code, 65)
        self.assertIn("will be sent under Work", err)
        self.assertIsNone(self.argv())
        self.assertEqual(self.snapshots(), [])

    def test_switch_unknown_last_used_three_accounts_64_without_note(self):
        self.write_config(extra_accounts={"extra": {"label": "Extra", "provider": "claude",
                                                    "credDir": str(self.home / ".claude-extra")}})
        code, _, err = self.ais("switch")
        self.assertEqual(code, 64)
        self.assertNotIn("assuming", err)
        self.assertIsNone(self.argv())

    def test_switch_named_same_account_no_ack_prompt(self):
        self.last_used("work")
        code, _, err = self.ais("switch", "work", stdin="")  # a prompt would read EOF and exit 65
        self.assertEqual(code, 0, err)
        self.assertEqual(self.slot(), "slot=" + self.work)
        self.assertNotIn("transcript", err)
        self.assertNotIn("cross_account_ack", self.config())

    def test_switch_unknown_named_account_64(self):
        code, _, err = self.ais("switch", "nobody")
        self.assertEqual(code, 64)
        self.assertIn("personal, work", err)
        self.assertIsNone(self.argv())

    def test_pick_lists_five_and_resumes_choice(self):
        ids = ["%d%d%d%d%d%d%d%d-1111-4111-8111-111111111111" % ((i,) * 8) for i in range(1, 7)]
        for n, sid in enumerate(ids):
            self.add_session(sid, self.proj, "task %d" % n, 3000 + n)
        self.add_session(OTHER, self.home / "elsewhere", "elsewhere task", 9000)
        self.last_used("personal", self.projects / "p" / (ids[5] + ".jsonl"))
        code, _, err = self.ais("switch", "--pick", "work", stdin="2\n")
        self.assertEqual(code, 0, err)
        listed = [x for x in err.splitlines() if x[:1].isdigit()]
        self.assertEqual(len(listed), 5)
        self.assertTrue(listed[0].startswith("1  ") and "task 5" in listed[0] and "personal" in listed[0])
        self.assertTrue(listed[1].startswith("2  ") and "task 4" in listed[1] and "unknown" in listed[1])
        self.assertTrue(listed[0].endswith("  -"))
        self.assertNotIn("elsewhere", err)
        self.assertNotIn("task 0", err)
        self.assertEqual(self.argv(), ["--resume", ids[4]])
        self.assertEqual(self.slot(), "slot=" + self.work)

    def test_pick_bad_input_64(self):
        for stdin in ("9\n", "0\n", "x\n", "", "-1\n", "1.0\n"):
            code, _, err = self.ais("switch", "--pick", "work", stdin=stdin)
            self.assertEqual(code, 64, stdin)
        self.assertIsNone(self.argv())
        code, _, err = self.ais("switch", "--pick", "--session", UUID, "work")
        self.assertEqual(code, 64)
        self.assertIsNone(self.argv())

    def test_session_flag_changes_into_folder(self):
        other = self.home / "other dir"
        other.mkdir()
        self.add_session(OTHER, other, "other task", 1000)
        code, _, err = self.ais("switch", "--session", OTHER, "work")
        self.assertEqual(code, 0, err)
        self.assertEqual(self.argv(), ["--resume", OTHER])
        self.assertEqual(self.claude_cwd(), os.path.realpath(str(other)))

    def test_session_flag_bad_uuid_64(self):
        for bad in ("nope", UUID.replace("-", ""), "{" + UUID + "}", UUID + "x", "../" + UUID):
            code, _, err = self.ais("switch", "--session", bad, "work")
            self.assertEqual(code, 64, bad)
        # a session folder outside the home folder is refused
        self.add_session(OTHER, "/", "root task", 1000)
        code, _, err = self.ais("switch", "--session", OTHER, "work")
        self.assertEqual(code, 64)
        self.assertIn("outside", err)
        self.assertIsNone(self.argv())

    def test_session_folder_symlink_outside_home_64(self):
        outside = Path(os.path.realpath(str(self.home))).parent  # a real folder outside HOME
        (self.home / "escape").symlink_to(outside)
        self.add_session(OTHER, self.home / "escape", "escape task", 1000)
        code, _, err = self.ais("switch", "--session", OTHER, "work")
        self.assertEqual(code, 64)
        self.assertIn("outside", err)
        self.assertIsNone(self.argv())

    def test_session_folder_regular_file_or_relative_66(self):
        (self.home / "afile").write_text("x")
        for folder in (self.home / "afile", ".", "./proj"):  # relative: never resolved against our cwd
            self.add_session(OTHER, folder, "bad folder", 1000)
            code, _, err = self.ais("switch", "--session", OTHER, "work")
            self.assertEqual(code, 66, folder)
        self.assertIsNone(self.argv())

    def test_outside_folder_message_is_cleaned(self):
        bad = "/tmp/x\x1b]0;pwned\x07y"
        with mock.patch("os.path.realpath", lambda p: bad if p == bad else os.path.abspath(p)), \
                mock.patch("pathlib.Path.is_dir", lambda p: True):
            self.add_session(OTHER, bad, "esc task", 1000)
            code, _, err = self.ais("switch", "--session", OTHER, "work")
        self.assertEqual(code, 64)
        self.assertIn("outside", err)
        self.assertNotIn("\x1b", err)
        self.assertNotIn("\x07", err)

    def test_non_string_last_used_is_unknown(self):
        self.write_config(acks={"personal->work": "2026-10-01"})
        for value in (["work"], {"a": 1}, 3, None):
            (self.ais_dir / "state.json").write_text(json.dumps(
                {"sessions": {str(self.transcript): {"account": value, "at": "t"}}}))
            code, _, err = self.ais("switch")
            self.assertEqual((code, self.slot()), (0, "slot=" + self.work), value)
            self.assertIn("assuming it last ran on Personal", err)

    def test_spawn_failure_restores_state_and_logs_error(self):
        os.environ["PATH"] = str(self.home / "nobin") + os.pathsep + "/usr/bin:/bin"
        self.last_used("work")
        before = (self.ais_dir / "state.json").read_text()
        code, _, err = self.ais("switch", "work")
        self.assertEqual(code, 69)
        self.assertEqual(json.loads((self.ais_dir / "state.json").read_text()), json.loads(before))
        self.assertEqual([(x["command"], x["account"], x["session_id"], x["result"]) for x in self.log_lines()],
                         [("switch", "work", UUID, "error 69")])
        # no previous entry: the record is removed again
        (self.ais_dir / "state.json").unlink()
        code, _, _ = self.ais("switch", "work")
        self.assertEqual(code, 69)
        self.assertEqual(self.state().get("sessions"), {})

    def test_tool_time_excludes_prompts(self):
        real = time.monotonic
        offset = [0.0]

        class SlowHuman(io.StringIO):
            def readline(inner, *a):
                offset[0] += 1000  # the human takes 1000 s to answer each prompt
                return inner.answers.pop(0)

        stdin = SlowHuman()
        stdin.answers = ["1\n", "y\n"]  # pick the session, then acknowledge personal->work
        self.last_used("personal")
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err), \
                mock.patch("sys.stdin", stdin), mock.patch("time.monotonic", lambda: real() + offset[0]):
            code = cli.main(["switch", "--pick", "work"])
        self.assertEqual(code, 0, err.getvalue())
        self.assertEqual(offset[0], 2000)
        self.assertLess(self.log_lines()[0]["tool_seconds"], 1000)

    def limit(self, pre, post):
        """limit_time with pre-launch lines `pre` and lines appended after the launch `post`."""
        from ais.providers.base import Session
        head = "".join(x + "\n" for x in pre)
        self.transcript.write_text(head + "".join(x + "\n" for x in post), encoding="utf-8")
        return ClaudeProvider().limit_time(Session(UUID, self.proj, self.transcript, "", 0.0),
                                           len(head.encode("utf-8")))

    def test_limit_time_only_when_session_stopped_at_limit(self):
        marker = json.dumps({"isApiErrorMessage": True, "error": "rate_limit", "timestamp": "2026-10-16T11:00:00Z"})
        normal = json.dumps({"type": "user", "timestamp": "2026-10-16T11:30:00Z"})
        later = json.dumps({"type": "user", "timestamp": "2026-10-16T12:00:10Z"})
        self.assertIsNone(self.limit([marker, normal], [later]))  # limit hit, then work went on
        self.assertEqual(self.limit([normal, marker, "not json"], [later]), 3610.0)  # stopped at the limit
        self.assertIsNone(self.limit([normal, marker], []))  # nothing appended after the launch
        self.assertIsNone(self.limit([normal], [later]))  # no marker

    def test_limit_time_ignores_non_conversation_lines_after_marker(self):
        t = "2026-10-16T11:00:00Z"
        marker = json.dumps({"type": "assistant", "isApiErrorMessage": True, "error": "rate_limit", "timestamp": t})
        noise = [json.dumps(d) for d in (
            {"type": "system", "subtype": "turn_duration", "timestamp": t},
            {"type": "system", "subtype": "informational", "timestamp": t},
            {"type": "queue-operation", "operation": "enqueue", "timestamp": t},
            {"type": "attachment", "timestamp": t},
            {"type": "user", "isMeta": True, "timestamp": t})]
        later = json.dumps({"type": "user", "timestamp": "2026-10-16T12:00:10Z"})
        self.assertEqual(self.limit([marker] + noise, [later]), 3610.0)
        for kind in ("user", "assistant"):  # a conversation line means work went on after the limit
            convo = json.dumps({"type": kind, "timestamp": "2026-10-16T11:30:00Z"})
            self.assertIsNone(self.limit([marker, noise[0], convo], [later]), kind)

    def test_limit_time_uses_file_order_not_timestamps(self):
        marker = json.dumps({"isApiErrorMessage": True, "error": "rate_limit", "timestamp": "2026-10-16T11:00:00Z"})
        early_but_late_stamp = json.dumps({"type": "queue-operation", "timestamp": "2026-10-16T15:00:00Z"})
        appended = [json.dumps({"type": "system", "timestamp": "2026-10-16T09:00:00Z"}),  # stamped before the marker
                    json.dumps({"type": "user", "timestamp": "2026-10-16T12:00:10Z"})]
        # a pre-launch line stamped hours after the marker neither ends the scan nor counts as appended
        self.assertEqual(self.limit([early_but_late_stamp, "x" * 10, marker], appended[1:]), 3610.0)
        # the first appended line is used even when a later appended line is stamped earlier
        self.assertEqual(self.limit([marker], ["not json", appended[1], appended[0]]), 3610.0)
        # appended line stamped before the marker: negative -> None
        self.assertIsNone(self.limit([marker], appended[:1]))

    def test_limit_time_line_straddling_launch_is_neither(self):
        from ais.providers.base import Session
        marker = json.dumps({"isApiErrorMessage": True, "error": "rate_limit", "timestamp": "2026-10-16T11:00:00Z"})
        half = json.dumps({"type": "user", "timestamp": "2026-10-16T11:30:00Z"})
        later = json.dumps({"type": "user", "timestamp": "2026-10-16T12:00:10Z"})
        head = marker + "\n" + half[:10]  # claude was mid-write at launch
        self.transcript.write_text(head + half[10:] + "\n" + later + "\n")
        got = ClaudeProvider().limit_time(Session(UUID, self.proj, self.transcript, "", 0.0), len(head))
        self.assertEqual(got, 3610.0)

    def test_limit_time_odd_fraction_digits(self):
        cases = {"2026-10-16T11:59:00.5Z": 60.5 - 0.5, "2026-10-16T11:59:00.25Z": 60.5 - 0.25,
                 "2026-10-16T11:59:00.1234Z": 60.5 - 0.1234, "2026-10-16T11:59:00.12345Z": 60.5 - 0.12345,
                 "2026-10-16T11:59:00Z": 60.5, "2026-10-16T11:59:00.1234567Z": 60.5 - 0.123456}
        for stamp, want in cases.items():
            got = self.limit([json.dumps({"isApiErrorMessage": True, "error": "rate_limit", "timestamp": stamp})],
                             [json.dumps({"type": "user", "timestamp": "2026-10-16T12:00:00.5Z"})])
            self.assertIsNotNone(got, stamp)
            self.assertAlmostEqual(got, want, places=5, msg=stamp)

    def test_session_not_found_66(self):
        code, _, err = self.ais("switch", "--session", MISSING, "work")
        self.assertEqual(code, 66)
        self.assertIn(MISSING, err)
        self.add_session(OTHER, self.home / "gone", "gone task", 1000)  # folder does not exist
        code, _, err = self.ais("switch", "--session", OTHER, "work")
        self.assertEqual(code, 66)
        self.assertIsNone(self.argv())

    def test_three_accounts_unnamed_64(self):
        self.write_config({"lab": {"label": "Lab", "provider": "claude", "credDir": str(self.home / ".lab")}})
        self.last_used("personal")
        code, _, err = self.ais("switch")
        self.assertEqual(code, 64)
        self.assertIn("lab, personal, work", err)
        self.assertIsNone(self.argv())

    def test_nothing_to_resume_66(self):
        empty = self.home / "empty"
        empty.mkdir()
        os.chdir(str(empty))
        code, _, err = self.ais("switch", "work")
        self.assertEqual(code, 66)
        self.assertIn("nothing to resume in", err)
        self.assertIsNone(self.argv())
        code, _, err = self.ais("switch", "--pick", "work", stdin="1\n")
        self.assertEqual(code, 66)
        self.assertIsNone(self.argv())

    def test_open_session_75_with_exit_hint(self):
        self.last_used("work")
        self.env(FAKE_PGREP_OUT="4242", FAKE_PS_OUT="4242 claude", FAKE_LSOF_OUT="p4242\nn%s" % self.proj)
        code, _, err = self.ais("switch", "work")
        self.assertEqual(code, 75)
        self.assertIn("ais: Claude is still running in %s (PID 4242). Type /exit there, then run "
                      "`ais switch` again.\n" % os.path.realpath(str(self.proj)), err)
        self.assertIsNone(self.argv())
        self.assertEqual(self.snapshots(), [])
        self.assertEqual(self.state()["sessions"][str(self.transcript)]["account"], "work")
        self.assertEqual(self.state()["sessions"][str(self.transcript)]["at"], "t")
        self.assertEqual(self.log_lines(), [])

    def test_process_check_failure_warns_and_continues(self):
        self.last_used("work")
        self.env(FAKE_PGREP_OUT="4242", FAKE_PS_OUT="", FAKE_PS_RC="2")
        code, _, err = self.ais("switch", "work")
        self.assertEqual(code, 0)
        self.assertIn("ais: warning: ps failed", err)
        self.assertEqual(self.argv(), ["--resume", UUID])

    def test_logged_out_target_still_starts_claude(self):
        self.last_used("work")
        self.env(FAKE_SECURITY_RC="44", FAKE_CLAUDE_AUTH_JSON='{"loggedIn": false}')
        code, _, err = self.ais("switch", "work")
        self.assertEqual(code, 0, err)
        self.assertEqual(self.argv(), ["--resume", UUID])
        self.assertNotIn("security", self.calls_text())
        self.assertNotIn("auth status", self.calls_text())

    def test_switch_billing_risk_77(self):
        self.last_used("work")
        os.environ["ANTHROPIC_API_KEY"] = "x"
        code, _, err = self.ais("switch", "work")
        self.assertEqual(code, 77)
        self.assertIn("ANTHROPIC_API_KEY", err)
        self.assertIsNone(self.argv())
        code, _, _ = self.ais("switch", "work", "--allow-api-key")
        self.assertEqual(code, 0)

    def test_switch_dry_run_no_prompt_no_writes(self):
        self.last_used("personal")  # unacknowledged pair: a real switch would prompt
        before = (self.ais_dir / "state.json").read_text()
        code, out, err = self.ais("switch", "work", "--dry-run", stdin="")
        self.assertEqual(code, 0, err)
        self.assertEqual(out, "session %s\nfolder %s\naccount work\n%s=%s claude --resume %s\n"
                         % (UUID, os.path.realpath(str(self.proj)), SLOT, self.work, UUID))
        self.assertNotIn("transcript", err)
        self.assertIsNone(self.argv())
        self.assertEqual((self.ais_dir / "state.json").read_text(), before)
        self.assertEqual((self.snapshots(), self.log_lines()), ([], []))
        self.assertNotIn("cross_account_ack", self.config())

    def test_tool_time_logged(self):
        def iso(t):
            return datetime.fromtimestamp(t, timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
        limited, after = time.time() - 600, time.time() + 600
        marker = json.dumps({"type": "assistant", "isApiErrorMessage": True, "error": "rate_limit",
                             "timestamp": iso(limited)}) + "\n"
        self.transcript.write_text(line("Main task", self.proj, timestamp=iso(limited - 60)) + marker + "not json\n")
        # the resumed claude appends the next line
        self.env(FAKE_CLAUDE_APPEND_TO=str(self.transcript),
                 FAKE_CLAUDE_APPEND=json.dumps({"type": "user", "timestamp": iso(after)}))
        self.last_used("work")
        code, _, err = self.ais("switch", "work")
        self.assertEqual(code, 0, err)
        entry = self.log_lines()[0]
        self.assertIsInstance(entry["tool_seconds"], float)
        self.assertGreaterEqual(entry["tool_seconds"], 0)
        self.assertLess(entry["tool_seconds"], 30)
        self.assertAlmostEqual(entry["e2e_seconds"], 1200, delta=0.01)
        # no marker before the launch: no end-to-end time
        self.transcript.write_text(line("Main task", self.proj, timestamp=iso(limited)))
        self.ais("switch", "work")
        entry = self.log_lines()[1]
        self.assertIsInstance(entry["tool_seconds"], float)
        self.assertIsNone(entry["e2e_seconds"])

    def test_double_switch_second_gets_75(self):
        self.write_config(acks={"personal->work": "2026-10-01"})
        self.last_used("personal")
        ready, stop, gate = self.home / "ready", self.home / "stop", self.home / "gate"
        self.addCleanup(stop.touch)  # never leave the first fake claude waiting

        def start(**env):
            e = dict(os.environ, PYTHONPATH=str(SRC), **env)
            p = subprocess.Popen([sys.executable, "-c", CHILD, str(self.home), "switch", "work"],
                                 env=e, cwd=str(self.proj), stdin=subprocess.DEVNULL,
                                 stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
            self.addCleanup(lambda: p.poll() is None and p.kill())
            return p

        def wait_for(path):
            deadline = time.time() + 15
            while not path.exists():
                self.assertLess(time.time(), deadline, "timed out waiting for %s" % path.name)
                time.sleep(0.02)

        # first: holds the mutex while its snapshot cp waits on the gate; its claude waits for stop
        first = start(FAKE_CP_GATE=str(gate), FAKE_CLAUDE_READY=str(ready), FAKE_CLAUDE_STOP=str(stop),
                      FAKE_CALL_LOG=str(self.home / "calls1.log"))
        wait_for(Path(str(gate) + ".waiting"))
        # second: its process check reports the first claude (pid from the ready file) in the folder
        calls2 = self.home / "calls2.log"
        second = start(FAKE_PROCS_PIDFILE=str(ready), FAKE_PROCS_CWD=str(self.proj), FAKE_CALL_LOG=str(calls2),
                       FAKE_CLAUDE_ARGV_LOG=str(self.home / "argv2.log"))
        time.sleep(0.5)
        self.assertIsNone(second.poll())
        self.assertNotIn("pgrep", calls2.read_text() if calls2.exists() else "", "second ran its check under the mutex")
        gate.touch()
        wait_for(ready)
        try:
            _, err2 = second.communicate(timeout=20)
        finally:
            stop.touch()
        self.assertEqual(second.returncode, 75, err2)
        self.assertIn("(PID %s)" % ready.read_text().strip(), err2)
        self.assertFalse((self.home / "argv2.log").exists())
        _, err1 = first.communicate(timeout=20)
        self.assertEqual(first.returncode, 0, err1)
