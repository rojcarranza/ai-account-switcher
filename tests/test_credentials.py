import os
from unittest import mock

from ais.accounts import Account
from ais.core import credential_state
from ais.providers import claude
from ais.providers.claude import ClaudeProvider, keychain_service
from ais.store import Store
from tests.helpers import TempHomeCase

WORK = Account("work", "Work", "claude", "/x/work")
PERSONAL = Account("personal", "Personal", "claude", None)


class CredentialsTest(TempHomeCase):
    def setUp(self):
        super().setUp()
        self.p = ClaudeProvider()
        self.log = self.home / "calls.log"
        self.log.write_text("")
        # security runs with the process env (no env parameter), so fakes are driven through os.environ
        patcher = mock.patch.dict(os.environ, {"FAKE_CALL_LOG": str(self.log)})
        patcher.start()
        self.addCleanup(patcher.stop)
        self.env = os.environ
        self.store = Store(self.home)

    def calls(self):
        return self.log.read_text().splitlines()

    def test_auth_status_uses_only_logged_in_not_email(self):
        self.env["FAKE_CLAUDE_AUTH_JSON"] = '{"loggedIn": false, "email": "work@example.com"}'
        self.assertEqual(self.p.has_credential(WORK, self.env), ("no", "auth status", ""))
        self.env["FAKE_CLAUDE_AUTH_JSON"] = '{"loggedIn": true, "email": "someone-else@example.com"}'
        self.assertEqual(self.p.has_credential(WORK, self.env), ("yes", "auth status", ""))

    def test_auth_status_yes_cached_10_min(self):
        t = [1000.0]

        def get(acct=WORK):
            return credential_state(self.store, self.p, acct, False, self.env, lambda: t[0])
        self.assertEqual(get(), ("yes", "auth status", ""))
        t[0] += 599
        self.assertEqual(get(), ("yes", "auth status", ""))
        self.assertEqual(len(self.calls()), 1)
        t[0] += 2
        get()
        self.assertEqual(len(self.calls()), 2)
        # a changed credDir invalidates the entry
        get(Account("work", "Work", "claude", "/y"))
        self.assertEqual(len(self.calls()), 3)

    def test_cache_write_keeps_transcripts(self):
        self.store.update_json("cache.json", lambda d: dict(d, transcripts={"a": 1}))
        credential_state(self.store, self.p, WORK, False, self.env)
        d = self.store.read_json("cache.json")
        self.assertEqual(d["transcripts"], {"a": 1})
        self.assertEqual(d["credentials"]["work"]["state"], "yes")

    def test_fallback_to_keychain_on_timeout_marks_source(self):
        self.env["FAKE_CLAUDE_AUTH_SLEEP"] = "3"
        with mock.patch.object(claude, "AUTH_TIMEOUT", 0.3):
            self.assertEqual(self.p.has_credential(WORK, self.env), ("yes", "keychain", ""))
            self.env["FAKE_SECURITY_RC"] = "44"
            self.assertEqual(self.p.has_credential(WORK, self.env), ("no", "keychain", ""))
            # keychain results are not cached
            credential_state(self.store, self.p, WORK, False, self.env)
        self.assertNotIn("work", self.store.read_json("cache.json").get("credentials", {}))

    def test_logged_out_exit_2_falls_back(self):
        self.env["FAKE_CLAUDE_AUTH_RC"] = "2"
        self.env["FAKE_CLAUDE_AUTH_JSON"] = '{"loggedIn": false}'
        self.env["FAKE_SECURITY_RC"] = "44"
        self.assertEqual(self.p.has_credential(WORK, self.env), ("no", "keychain", ""))

    def test_keychain_error_is_unknown(self):
        self.env["FAKE_CLAUDE_AUTH_RC"] = "1"
        self.env["FAKE_SECURITY_RC"] = "36"
        state, source, err = self.p.has_credential(WORK, self.env)
        self.assertEqual((state, source), ("unknown", "keychain"))
        self.assertTrue(err and "\n" not in err)

    def test_never_calls_security_with_w_or_g(self):
        self.env["FAKE_CLAUDE_AUTH_RC"] = "1"
        self.p.has_credential(WORK, self.env)
        calls = self.calls()
        self.assertNotIn("FORBIDDEN", calls)
        # the fake logs "security $*": exactly these four argv tokens, nothing else
        self.assertEqual([c for c in calls if c.startswith("security")],
                         ["security find-generic-password -s " + keychain_service("/x/work")])

    def test_cache_only_never_spawns_claude(self):
        r = credential_state(self.store, self.p, PERSONAL, True, self.env)
        self.assertEqual(r, ("yes", "keychain", ""))
        self.assertFalse([c for c in self.calls() if c.startswith("claude")])
        self.assertEqual(self.store.read_json("cache.json"), {})
