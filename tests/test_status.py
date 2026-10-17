"""FR-4.1, FR-4.5, FR-4.6: `ais status` and the dict the menu reuses."""
import json
import os
from unittest import mock

from tests.test_switch import OTHER, SwitchCase, UUID

SEE_LINE = "ais cannot see which account each slot is signed in to; sign in to the matching account in each"


class StatusTest(SwitchCase):
    def setUp(self):
        super().setUp()
        self.env(FAKE_CLAUDE_AUTH_JSON='{"loggedIn": true}')
        patch = mock.patch("ais.procs.process_cwds", return_value=({}, []))
        self.procs = patch.start()
        self.addCleanup(patch.stop)

    def test_status_text(self):
        self.last_used("work")
        code, out, _ = self.ais("status")
        self.assertEqual(code, 0)
        self.assertIn("  personal (Personal): credential present: yes", out)
        self.assertIn("  work (Work): credential present: yes", out)
        self.assertIn("session %s: last used work, not open" % UUID, out)
        self.assertIn("self-check: ok", out)
        self.assertIn(SEE_LINE + "\n", out)

    def test_status_text_marks_keychain_and_open_session(self):
        self.env(FAKE_CLAUDE_AUTH_RC="1")
        self.procs.return_value = ({7: ("claude", self.proj)}, [])
        _, out, _ = self.ais("status")
        self.assertIn("credential present: yes (Keychain item exists; not a validity check)", out)
        self.assertIn("last used unknown, open", out)
        self.assertEqual(self.procs.call_count, 1)

    def test_status_json_schema(self):
        self.add_session(OTHER, self.home, "T\x1b[2Jitle", 1000)
        code, out, _ = self.ais("status", "--json")
        d = json.loads(out)
        self.assertEqual(code, 0)
        self.assertEqual(set(d), {"accounts", "session", "recent", "self_check"})
        self.assertEqual([a["name"] for a in d["accounts"]], ["personal", "work"])
        self.assertEqual(set(d["accounts"][0]), {"name", "label", "credential_present",
                                                 "credential_source", "credential_error"})
        self.assertEqual(set(d["session"]), {"id", "last_used", "open"})
        self.assertEqual(len(d["recent"]), 2)
        self.assertEqual(set(d["recent"][0]), {"id", "folder", "title", "last_used", "open", "modified"})
        self.assertTrue(d["recent"][0]["modified"].endswith("Z"))
        self.assertEqual(d["self_check"], {"ok": True, "messages": []})
        self.assertEqual(self.procs.call_count, 1)

    def test_status_no_session_in_folder(self):
        other = self.home / "elsewhere"
        other.mkdir()
        os.chdir(str(other))
        _, out, _ = self.ais("status")
        self.assertIn("no session in this folder", out)
        _, out, _ = self.ais("status", "--json")
        self.assertIsNone(json.loads(out)["session"])

    def test_status_last_used_unknown(self):
        _, out, _ = self.ais("status", "--json")
        d = json.loads(out)
        self.assertIsNone(d["session"]["last_used"])
        self.assertIsNone(d["recent"][0]["last_used"])
        _, out, _ = self.ais("status")
        self.assertIn("last used unknown", out)
        self.assertFalse((self.ais_dir / "state.json").exists())

    def test_status_keychain_error_unknown_exit_0(self):
        self.env(FAKE_CLAUDE_AUTH_RC="1", FAKE_SECURITY_RC="51", FAKE_SECURITY_ERR="boom")
        code, out, _ = self.ais("status")
        self.assertEqual(code, 0)
        self.assertIn("credential present: unknown — security exited 51: boom", out)

    def test_self_check_warns_version_and_cred_dir(self):
        self.env(FAKE_CLAUDE_VERSION="9.9.9")
        code, out, _ = self.ais("status")
        self.assertEqual(code, 0)
        self.assertIn("warning: Claude Code 9.9.9 is outside the tested range", out)
        _, out, _ = self.ais("status", "--json")
        sc = json.loads(out)["self_check"]
        self.assertFalse(sc["ok"])
        self.assertEqual(len(sc["messages"]), 1)
        self.write_config({"bad": {"label": "Bad", "provider": "claude", "credDir": "~/x"}})
        code, _, err = self.ais("status")
        self.assertEqual(code, 78)
        self.assertIn("bad", err)

    def test_corrupt_state_json_is_a_warning_not_an_abort(self):
        (self.ais_dir / "state.json").write_text("{not json")
        code, out, _ = self.ais("status")
        self.assertEqual(code, 0)
        self.assertIn("last used unknown", out)
        self.assertIn("warning: ", out)
        self.assertIn("state.json", out)
        _, out, _ = self.ais("status", "--json")
        self.assertFalse(json.loads(out)["self_check"]["ok"])

    def test_unwritable_store_still_prints(self):
        self.ais_dir.chmod(0o500)
        self.addCleanup(self.ais_dir.chmod, 0o700)
        code, out, _ = self.ais("status")
        self.assertEqual(code, 0)
        self.assertIn("credential present: yes", out)
        self.assertIn("warning: ", out)

    def test_absurd_mtime_gives_null_modified(self):
        from ais.core import _iso_utc  # the filesystem clamps utime, so test the conversion itself
        self.assertIsNone(_iso_utc(1e30))
        self.assertIsNone(_iso_utc(float("nan")))
        self.assertEqual(_iso_utc(0), "1970-01-01T00:00:00Z")

    def test_one_transcript_scan_per_gather(self):
        from ais.providers.claude import ClaudeProvider
        real = ClaudeProvider._scan
        with mock.patch.object(ClaudeProvider, "_scan", autospec=True, side_effect=real) as scan:
            _, out, _ = self.ais("status", "--json")
        d = json.loads(out)
        self.assertEqual(scan.call_count, 1)
        self.assertEqual(d["session"]["id"], UUID)
        self.assertEqual(len(d["recent"]), 1)

    def test_unreadable_cache_json_still_prints(self):
        self.ais("status")  # creates cache.json
        cache = self.ais_dir / "cache.json"
        self.assertTrue(cache.exists())
        cache.chmod(0)
        self.addCleanup(cache.chmod, 0o600)
        code, out, _ = self.ais("status")
        self.assertEqual(code, 0)
        self.assertIn("credential present: yes", out)
        self.assertIn("session %s" % UUID, out)
        warnings = [l for l in out.splitlines() if l.startswith("warning: ")]
        self.assertEqual(len(warnings), 2)  # one read failure, one write failure, each reported once
        self.assertEqual(sum(w.startswith("warning: cannot write cache.json") for w in warnings), 1)
