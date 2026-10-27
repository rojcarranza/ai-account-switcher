"""ADR-0011: `ais default` makes the machine's default sign-in hold the other account.

Intent (the captain's bug report): after a session limit, `ais switch` left Infinitary's crewmates and first
mate on the spent account, because they run on the default Keychain item. After `ais default secondary`, a
program started with no slot variable must get the secondary's login. Everything runs against a stateful fake
`security` in a scratch HOME; the real Keychain is never touched.
"""
import contextlib
import io
import json
import os
import subprocess
from unittest import mock

from ais import cli
from ais.providers.claude import BILLING_ENV, CONFIG_DIR_ENV, ClaudeProvider, keychain_service
from tests.helpers import TempHomeCase

SLOT = "CLAUDE_SECURESTORAGE_CONFIG_DIR"
P_SECRET, S_SECRET = '{"token":"primary-secret"}', '{"token":"secondary-secret"}'
P_ID = {"emailAddress": "rojjamescarranza@gmail.com", "accountUuid": "uuid-p"}
S_ID = {"emailAddress": "rojjcarranza@gmail.com", "accountUuid": "uuid-s"}


class DefaultTest(TempHomeCase):
    def setUp(self):
        super().setUp()
        self.secondary = str(self.home / ".claude-secondary")
        self.ais_dir.mkdir(parents=True)
        (self.ais_dir / "config.json").write_text(json.dumps({
            "version": 1, "default": "primary", "accounts": {
                "primary": {"label": "Primary", "provider": "claude", "credDir": None},
                "secondary": {"label": "Secondary", "provider": "claude", "credDir": self.secondary}}}))
        self.kc = self.home / "keychain"
        self.kc.mkdir()
        self.default_svc = keychain_service(None)
        self.second_svc = keychain_service(self.secondary)
        self.put(self.default_svc, P_SECRET)
        self.put(self.second_svc, S_SECRET)
        self.klog = self.home / "keychain.log"
        self.claude_json = self.home / ".claude.json"
        self.claude_json.write_text(json.dumps({"userID": "u1", "oauthAccount": P_ID}))
        (self.ais_dir / "state.json").write_text(json.dumps({"identities": {"primary": P_ID, "secondary": S_ID}}))
        for k, v in (("FAKE_KEYCHAIN_DIR", str(self.kc)), ("FAKE_KEYCHAIN_LOG", str(self.klog))):
            os.environ[k] = v
            self.addCleanup(os.environ.pop, k, None)
        self.addCleanup(os.environ.pop, "FAKE_KEYCHAIN_FAIL_ADD", None)
        for k in BILLING_ENV + (SLOT, CONFIG_DIR_ENV):
            if k in os.environ:
                saved = os.environ.pop(k)
                self.addCleanup(os.environ.__setitem__, k, saved)
        roots = {"home": self.home, "managed": self.home / "managed", "managed_prefs": self.home / "prefs"}
        patch = mock.patch.object(ClaudeProvider, "default_settings_roots", lambda _self: roots)
        patch.start()
        self.addCleanup(patch.stop)

    def put(self, service, secret):
        (self.kc / service).write_text("lab\n" + secret)

    def item(self, service):
        return (self.kc / service).read_text().partition("\n")[2]

    def ais(self, *args):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = cli.main(list(args))
        return code, out.getvalue(), err.getvalue()

    def state(self):
        return json.loads((self.ais_dir / "state.json").read_text())

    def default_login_seen_by_a_program_without_slot_variable(self):
        """What Infinitary's claude gets: the item for no slot variable (read with the same fake)."""
        env = {k: v for k, v in os.environ.items() if k != SLOT}
        return subprocess.run(["security", "find-generic-password", "-s", self.default_svc, "-w"],
                              env=env, capture_output=True, text=True).stdout.strip()

    def test_failing_check_before_the_fix_default_login_follows_ais_default(self):
        self.assertEqual(self.default_login_seen_by_a_program_without_slot_variable(), P_SECRET)
        code, out, err = self.ais("default", "secondary")
        self.assertEqual(code, 0, err)
        self.assertEqual(self.default_login_seen_by_a_program_without_slot_variable(), S_SECRET)

    def test_swap_exchanges_both_items_and_records_it(self):
        self.assertEqual(self.ais("default", "secondary")[0], 0)
        self.assertEqual(self.item(self.default_svc), S_SECRET)
        self.assertEqual(self.item(self.second_svc), P_SECRET)
        self.assertEqual(self.state()["default_holds"], "secondary")

    def test_secret_never_in_argv_or_in_ais_files(self):
        calls = self.home / "calls.log"
        os.environ["FAKE_CALL_LOG"] = str(calls)
        self.addCleanup(os.environ.pop, "FAKE_CALL_LOG", None)
        self.assertEqual(self.ais("default", "secondary")[0], 0)
        logged = calls.read_text() + self.klog.read_text()
        for secret in ("primary-secret", "secondary-secret"):
            self.assertNotIn(secret, logged)
            self.assertNotIn(secret, (self.ais_dir / "state.json").read_text())
            for f in self.ais_dir.rglob("*"):
                if f.is_file():
                    self.assertNotIn(secret, f.read_text(errors="replace"))
        self.assertNotIn("FORBIDDEN", logged)

    def test_ais_keeps_meaning_the_same_accounts_after_a_swap(self):
        self.ais("default", "secondary")
        code, out, _ = self.ais("run", "secondary", "--dry-run")
        self.assertEqual((code, SLOT in out), (0, False))  # secondary's login is now in the default slot
        code, out, _ = self.ais("run", "primary", "--dry-run")
        self.assertIn("%s=%s" % (SLOT, self.secondary), out)  # primary's login moved to the secondary slot

    def test_swap_back_restores_everything(self):
        self.ais("default", "secondary")
        self.assertEqual(self.ais("default", "primary")[0], 0)
        self.assertEqual((self.item(self.default_svc), self.item(self.second_svc)), (P_SECRET, S_SECRET))
        self.assertNotIn("default_holds", self.state())

    def test_already_holding_changes_nothing(self):
        self.ais("default", "secondary")
        self.klog.write_text("")
        code, out, _ = self.ais("default", "secondary")
        self.assertEqual(code, 0)
        self.assertIn("already", out)
        self.assertNotIn("add-generic-password", self.klog.read_text())

    def test_identity_in_claude_json_follows_so_infinitary_sees_a_new_login_stamp(self):
        self.ais("default", "secondary")
        data = json.loads(self.claude_json.read_text())
        self.assertEqual(data["oauthAccount"], S_ID)
        self.assertEqual(data["userID"], "u1")  # no other key touched

    def test_missing_identity_still_swaps_and_warns(self):
        (self.ais_dir / "state.json").write_text("{}")
        code, _, err = self.ais("default", "secondary")
        self.assertEqual(code, 0)
        self.assertIn("ais login secondary", err)
        self.assertEqual(json.loads(self.claude_json.read_text())["oauthAccount"], P_ID)

    def test_missing_item_refuses_and_changes_nothing(self):
        (self.kc / self.second_svc).unlink()
        code, _, err = self.ais("default", "secondary")
        self.assertEqual(code, 66)
        self.assertIn("ais login secondary", err)
        self.assertEqual(self.item(self.default_svc), P_SECRET)
        self.assertNotIn("default_holds", self.state())

    def test_failed_second_write_restores_the_first(self):
        os.environ["FAKE_KEYCHAIN_FAIL_ADD"] = self.second_svc
        code, _, _ = self.ais("default", "secondary")
        self.assertNotEqual(code, 0)
        self.assertEqual((self.item(self.default_svc), self.item(self.second_svc)), (P_SECRET, S_SECRET))
        self.assertNotIn("default_holds", self.state())

    def test_no_argument_says_which_account_the_default_sign_in_holds(self):
        self.assertIn("primary", self.ais("default")[1])
        self.ais("default", "secondary")
        self.assertIn("secondary", self.ais("default")[1])

    def test_dry_run_writes_nothing(self):
        code, out, _ = self.ais("default", "secondary", "--dry-run")
        self.assertEqual(code, 0)
        self.assertEqual(self.item(self.default_svc), P_SECRET)
        self.assertNotIn("add-generic-password", self.klog.read_text() if self.klog.exists() else "")

    def test_login_records_the_signed_in_identity(self):
        (self.ais_dir / "state.json").write_text("{}")
        self.claude_json.write_text(json.dumps({"oauthAccount": S_ID}))
        self.assertEqual(self.ais("login", "secondary")[0], 0)
        self.assertEqual(self.state()["identities"]["secondary"], S_ID)
