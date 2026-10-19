"""FR-3.21: `ais record`, run by Claude Code's SessionStart hook, records the session's account."""
import json
import os

from tests.test_switch import OTHER, SLOT, UUID, SwitchCase

ENTRY = "CLAUDE_CODE_ENTRYPOINT"


class RecordTest(SwitchCase):
    def setUp(self):
        super().setUp()
        if ENTRY in os.environ:  # the developer shell may run inside Claude Desktop
            saved = os.environ.pop(ENTRY)
            self.addCleanup(os.environ.__setitem__, ENTRY, saved)

    def payload(self, sid=UUID, transcript=None, **extra):
        d = {"session_id": sid, "transcript_path": str(transcript or self.transcript), "cwd": str(self.proj),
             "hook_event_name": "SessionStart", "source": "startup"}
        d.update(extra)
        return json.dumps(d)

    def record(self, stdin=None):
        code, out, err = self.ais("record", stdin=self.payload() if stdin is None else stdin)
        self.assertEqual((code, out, err), (0, "", ""))  # never blocks or clutters the session
        return self.state().get("sessions", {})

    def test_unset_slot_records_default_account(self):
        self.assertEqual(self.record()[str(self.transcript)]["account"], "primary")

    def test_exact_cred_dir_records_that_account(self):
        self.env(**{SLOT: self.secondary})
        self.assertEqual(self.record()[str(self.transcript)]["account"], "secondary")

    def test_resume_on_other_slot_replaces_stale_record(self):
        self.last_used("primary")
        self.env(**{SLOT: self.secondary})
        sessions = self.record(self.payload(source="resume"))
        self.assertEqual(sessions[str(self.transcript)]["account"], "secondary")

    def test_other_slot_spellings_record_nothing(self):
        # ADR-0002: a different spelling is a different Keychain slot; "" is the empty-string slot
        for value in ("", self.secondary + "/", self.home / ".claude-other"):
            with self.subTest(value=value):
                self.env(**{SLOT: str(value)})
                self.assertEqual(self.record(), {})

    def test_cli_entrypoint_records(self):
        self.env(**{ENTRY: "cli"})
        self.assertEqual(self.record()[str(self.transcript)]["account"], "primary")

    def test_desktop_and_other_entrypoints_record_nothing(self):
        # a Desktop session has no slot variable whatever instance runs it: "unset" would mean default
        for value in ("claude-desktop", "claude-vscode", "sdk-ts"):
            with self.subTest(value=value):
                self.env(**{ENTRY: value})
                self.assertEqual(self.record(), {})

    def test_new_transcript_not_yet_written_is_recorded(self):
        new = self.projects / "p" / (OTHER + ".jsonl")
        sessions = self.record(self.payload(OTHER, new))
        self.assertEqual(sessions[str(new)]["account"], "primary")

    def test_record_is_logged(self):
        self.record()
        entry = json.loads((self.ais_dir / "ais.log").read_text().splitlines()[-1])
        self.assertEqual((entry["command"], entry["account"], entry["session_id"], entry["result"]),
                         ("record", "primary", UUID, "ok"))

    def test_bad_input_records_nothing(self):
        outside = self.home / "elsewhere" / (UUID + ".jsonl")
        deep = self.projects / "p" / UUID / "subagents" / (UUID + ".jsonl")
        upper = "AAAAAAAA-AAAA-4AAA-8AAA-AAAAAAAAAAAA"  # _scan keeps only canonical lowercase names
        for stdin in ("", "not json", "[]", json.dumps({"session_id": UUID}),
                      self.payload("not-a-uuid"), self.payload(upper, self.projects / "p" / (upper + ".jsonl")),
                      self.payload(OTHER),  # the name is not <session_id>.jsonl
                      self.payload(transcript=outside), self.payload(transcript=deep),
                      self.payload(transcript=self.projects / ".." / "p" / (UUID + ".jsonl")),
                      self.payload(transcript=self.projects / "p" / (UUID + ".txt")),
                      json.dumps({"session_id": UUID, "transcript_path": 7}),
                      "x" * (64 * 1024 + 1)):
            with self.subTest(stdin=stdin[:60]):
                self.assertEqual(self.record(stdin), {})

    def test_symlinked_project_folder_outside_projects_records_nothing(self):
        outside = self.home / "outside"
        outside.mkdir()
        (self.projects / "link").symlink_to(outside)
        self.assertEqual(self.record(self.payload(transcript=self.projects / "link" / (UUID + ".jsonl"))), {})

    def test_broken_config_exits_zero_silently(self):
        (self.ais_dir / "config.json").write_text("{")
        self.assertEqual(self.record(), {})

    def test_missing_config_exits_zero_silently(self):
        (self.ais_dir / "config.json").unlink()
        self.assertEqual(self.record(), {})

    def test_fresh_record_survives_another_record_before_its_transcript_exists(self):
        # Claude creates the transcript after SessionStart; another window's hook must not prune the record
        new = self.projects / "p" / (OTHER + ".jsonl")
        self.record(self.payload(OTHER, new))
        sessions = self.record()
        self.assertEqual(sorted(sessions), sorted([str(new), str(self.transcript)]))

    def test_old_record_without_transcript_is_still_pruned(self):
        gone = str(self.projects / "p" / "gone.jsonl")
        (self.ais_dir / "state.json").write_text(json.dumps(
            {"sessions": {gone: {"account": "secondary", "at": "2026-01-01T00:00:00Z"}}}))
        self.assertNotIn(gone, self.record())
