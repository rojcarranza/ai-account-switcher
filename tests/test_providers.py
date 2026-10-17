import json
import os
import plistlib
from unittest import mock

from ais import providers
from ais.accounts import Account, load_config
from ais.errors import AisError
from ais.providers import claude
from ais.providers.claude import BILLING_ENV, ClaudeProvider, keychain_service
from ais.store import Store
from tests.fake_provider import FakeProvider
from tests.helpers import TempHomeCase

SLOT = "CLAUDE_SECURESTORAGE_CONFIG_DIR"


class ProvidersTest(TempHomeCase):
    def setUp(self):
        super().setUp()
        self.p = ClaudeProvider()
        self.folder = self.home / "proj"
        self.roots = {"home": self.home, "managed": self.home / "managed",
                      "managed_prefs": self.home / "prefs"}
        self.personal = Account("personal", "Personal", "claude", None)

    def risks(self, env=None, args=()):
        return self.p.billing_risks(env or {}, self.folder, list(args), self.roots)

    def write_json(self, path, data):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data) if not isinstance(data, str) else data)

    def test_keychain_service_default_and_extra(self):
        self.assertEqual(keychain_service(None), "Claude Code-credentials")
        vectors = {"/Users/roj/.claude-accounts/work": "f9fb4ac6",
                   "/Users/roj/.claude-accounts/work/": "cf3ea493",
                   "/Users/roj/.claude": "fb50e6da",
                   "/Users/roj/.claude-accounts/personal": "65ac6854",
                   "/Users/roj/.claude-accounts/spike": "8cef0543"}
        for d, h in vectors.items():
            with self.subTest(d=d):
                self.assertEqual(keychain_service(d), "Claude Code-credentials-" + h)

    def test_env_default_removes_securestorage_with_warning(self):
        for value in ("/x", ""):
            with self.subTest(value=value):
                base = {"PATH": "/bin", SLOT: value}
                env, warnings = self.p.env_for(self.personal, base)
                self.assertNotIn(SLOT, env)
                self.assertEqual(env["PATH"], "/bin")
                self.assertEqual(len(warnings), 1)
                self.assertIn(SLOT, warnings[0])
                self.assertIn(SLOT, base)  # base_env untouched
        env, warnings = self.p.env_for(self.personal, {"PATH": "/bin"})
        self.assertEqual((env, warnings), ({"PATH": "/bin"}, []))

    def test_env_extra_sets_exact_cred_dir_string(self):
        cred = "/Users/roj/.claude-accounts/wörk"
        work = Account("work", "Work", "claude", cred)
        base = {SLOT: "/other"}
        env, warnings = self.p.env_for(work, base)
        self.assertEqual(env[SLOT], cred)
        self.assertEqual(warnings, [])
        self.assertEqual(base, {SLOT: "/other"})

    def test_env_removes_config_dir_with_warning(self):
        work = Account("work", "Work", "claude", "/w")
        for account in (self.personal, work):
            with self.subTest(account=account.name):
                base = {"CLAUDE_CONFIG_DIR": "/c"}
                env, warnings = self.p.env_for(account, base)
                self.assertNotIn("CLAUDE_CONFIG_DIR", env)
                self.assertEqual(len(warnings), 1)
                self.assertIn("CLAUDE_CONFIG_DIR", warnings[0])
                self.assertIn("CLAUDE_CONFIG_DIR", base)

    def test_billing_risks_each_env_var(self):
        self.assertEqual(self.risks({"PATH": "/bin"}), [])
        self.assertIn("ANTHROPIC_API_KEY", BILLING_ENV)
        self.assertIn("CLAUDE_CODE_PROVIDER_MANAGED_BY_HOST", BILLING_ENV)
        for name in BILLING_ENV:
            with self.subTest(name=name):
                self.assertEqual(self.risks({name: "1"}), ["%s in the environment" % name])
                self.assertEqual(self.risks({name: ""}), ["%s in the environment" % name])

    def test_billing_risks_each_settings_scope_and_profile(self):
        files = [self.home / ".claude" / "settings.json",
                 self.home / ".claude" / "settings.local.json",
                 self.folder / ".claude" / "settings.json",
                 self.folder / ".claude" / "settings.local.json",
                 self.roots["managed"] / "managed-settings.json"]
        self.assertEqual(self.risks(), [])  # no files at all is fine
        for path in files:
            for key in claude.SETTINGS_KEYS:
                with self.subTest(path=str(path), key=key):
                    self.write_json(path, {key: "x", "model": "opus"})
                    self.assertEqual(self.risks(), ["%s in %s" % (key, path)])
            with self.subTest(path=str(path), key="env"):
                self.write_json(path, {"env": {"ANTHROPIC_BASE_URL": "https://x", "FOO": "1"}})
                self.assertEqual(self.risks(), ["ANTHROPIC_BASE_URL in %s env" % path])
            with self.subTest(path=str(path), key="env empty value"):
                self.write_json(path, {"env": {"ANTHROPIC_API_KEY": ""}})
                self.assertEqual(self.risks(), ["ANTHROPIC_API_KEY in %s env" % path])
            with self.subTest(path=str(path), key="env not an object"):
                self.write_json(path, {"env": "x"})
                self.assertEqual(self.risks(), ["cannot read %s: env is not an object" % path])
            with self.subTest(path=str(path), key="harmless"):
                self.write_json(path, {"env": {"FOO": "1"}, "model": "opus"})
                self.assertEqual(self.risks(), [])
            with self.subTest(path=str(path), key="invalid"):
                self.write_json(path, "{not json")
                r = self.risks()
                self.assertEqual(len(r), 1)
                self.assertTrue(r[0].startswith("cannot read %s: " % path), r[0])
            path.unlink()
        prefs = self.roots["managed_prefs"]
        for plist in (prefs / "com.anthropic.claudecode.plist",
                      prefs / claude.getpass.getuser() / "com.anthropic.claudecode.plist"):
            with self.subTest(plist=str(plist)):
                plist.parent.mkdir(parents=True, exist_ok=True)
                with open(str(plist), "wb") as f:
                    plistlib.dump({"forceLoginMethod": "console"}, f)
                self.assertEqual(self.risks(), ["forceLoginMethod in %s" % plist])
                plist.write_bytes(b"not a plist")
                r = self.risks()
                self.assertEqual(len(r), 1)
                self.assertTrue(r[0].startswith("cannot read %s: " % plist), r[0])
                plist.unlink()

    def test_billing_risks_settings_flag_both_forms(self):
        self.assertEqual(self.risks(args=["-p", "hi"]), [])
        for args, flag in ((["--settings", "x.json"], "--settings"),
                           (["--settings=x.json"], "--settings"),
                           (["--bare"], "--bare")):
            with self.subTest(args=args):
                self.assertEqual(self.risks(args=args), ["%s in arguments" % flag])

    def test_unknown_provider_exits_78(self):
        self.assertIsInstance(providers.get("claude"), ClaudeProvider)
        with self.assertRaises(AisError) as cm:
            providers.get("nope")
        self.assertEqual(cm.exception.code, 78)
        self.assertIn("'nope'", cm.exception.message)
        self.assertIn("registered providers: claude", cm.exception.message)

    def test_fake_provider_registers_with_one_entry(self):
        with mock.patch.dict(providers.REGISTRY, {"fake": FakeProvider}, clear=True):
            self.assertIsInstance(providers.get("fake"), FakeProvider)
            self.ais_dir.mkdir(parents=True)
            (self.ais_dir / "config.json").write_text(json.dumps(
                {"version": 1, "default": "solo",
                 "accounts": {"solo": {"label": "Solo", "provider": "fake", "credDir": None}}}))
            c = load_config(Store(self.home), providers=providers.REGISTRY)
            self.assertEqual(c.accounts["solo"].provider, "fake")
        self.assertEqual(list(providers.REGISTRY), ["claude"])

    def test_version_outside_range_warns(self):
        self.addCleanup(os.environ.pop, "FAKE_CLAUDE_VERSION", None)
        self.assertEqual(self.p.self_check(), [])
        os.environ["FAKE_CLAUDE_VERSION"] = "2.1.400"
        self.assertEqual(self.p.self_check(),
                         ["Claude Code 2.1.400 is outside the tested range 2.1.301-2.1.301"])
        os.environ["FAKE_CLAUDE_VERSION"] = "garbage"
        self.assertEqual(len(self.p.self_check()), 1)
        self.addCleanup(os.environ.pop, "FAKE_CLAUDE_BAD_BYTES", None)
        os.environ["FAKE_CLAUDE_BAD_BYTES"] = "1"
        self.assertEqual(len(self.p.self_check()), 1)
        os.environ["PATH"] = str(self.home)  # no claude on PATH
        self.assertEqual(len(self.p.self_check()), 1)

    def test_commands(self):
        self.assertEqual(self.p.resume_command("abc"), ["claude", "--resume", "abc"])
        self.assertEqual(self.p.start_command(("-p", "x")), ["claude", "-p", "x"])
        self.assertEqual(self.p.login_command(), ["claude", "auth", "login"])
