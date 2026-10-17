import os
from unittest import mock

from ais.accounts import Account
from ais.core import Cache, credential_state
from ais.errors import AisError
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

    def claude_calls(self):
        return [c for c in self.calls() if c.startswith("claude")]

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
        self.assertEqual(len(self.claude_calls()), 1)
        t[0] += 2
        get()
        self.assertEqual(len(self.claude_calls()), 2)
        # a changed credDir invalidates the entry
        get(Account("work", "Work", "claude", "/y"))
        self.assertEqual(len(self.claude_calls()), 3)

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

    def test_keychain_error_includes_stderr_first_line(self):
        self.env["FAKE_CLAUDE_AUTH_RC"] = "1"
        self.env["FAKE_SECURITY_RC"] = "36"
        self.env["FAKE_SECURITY_ERR"] = "User interaction is not allowed.\nsecond line"
        self.assertEqual(self.p.has_credential(WORK, self.env),
                         ("unknown", "keychain", "security exited 36: User interaction is not allowed."))

    def test_auth_status_gets_the_accounts_own_slot(self):
        self.env["CLAUDE_SECURESTORAGE_CONFIG_DIR"] = "/stale"
        self.p.has_credential(WORK, self.env)
        self.p.has_credential(PERSONAL, self.env)
        self.assertEqual([c for c in self.calls() if c.startswith("slot=")],
                         ["slot=/x/work", "slot=<unset>"])

    def test_future_timestamp_is_not_fresh(self):
        t = [1000.0]
        get = lambda: credential_state(self.store, self.p, WORK, False, self.env, lambda: t[0])
        get()
        t[0] = 500.0
        get()
        self.assertEqual(len(self.claude_calls()), 2)

    def test_corrupt_cache_is_treated_as_empty_and_overwritten(self):
        self.store.dir.mkdir(parents=True)
        (self.store.dir / "cache.json").write_text("{not json")
        Cache(self.store)  # must not raise
        self.assertEqual(credential_state(self.store, self.p, WORK, False, self.env)[0], "yes")
        self.assertEqual(self.store.read_json("cache.json")["credentials"]["work"]["state"], "yes")

    def test_cache_only_corrupt_cache_does_not_raise(self):
        self.store.dir.mkdir(parents=True)
        (self.store.dir / "cache.json").write_text("[]")
        self.assertEqual(credential_state(self.store, self.p, WORK, True, self.env)[1], "keychain")

    def test_other_store_errors_still_raise(self):
        with mock.patch.object(self.store, "read_json", side_effect=AisError(73, "x")):
            with self.assertRaises(AisError):
                Cache(self.store)
            with self.assertRaises(AisError):
                credential_state(self.store, self.p, WORK, False, self.env)

    def test_fake_security_rejects_bundled_short_options(self):
        import subprocess
        for flags in (["-ag"], ["-sw"], ["-w"], ["-g"]):
            rc = subprocess.run(["security", "find-generic-password"] + flags,
                                stderr=subprocess.DEVNULL).returncode
            self.assertEqual(rc, 99, flags)
        self.assertEqual(subprocess.run(["security", "find-generic-password", "-s", "svc"]).returncode, 0)

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
