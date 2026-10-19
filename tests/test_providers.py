import json
import os
import plistlib
from pathlib import Path
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
        self.primary = Account("primary", "Primary", "claude", None)

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
                env, warnings = self.p.env_for(self.primary, base)
                self.assertNotIn(SLOT, env)
                self.assertEqual(env["PATH"], "/bin")
                self.assertEqual(len(warnings), 1)
                self.assertIn(SLOT, warnings[0])
                self.assertIn(SLOT, base)  # base_env untouched
        env, warnings = self.p.env_for(self.primary, {"PATH": "/bin"})
        self.assertEqual((env, warnings), ({"PATH": "/bin"}, []))

    def test_env_extra_sets_exact_cred_dir_string(self):
        cred = "/Users/roj/.claude-accounts/wörk"
        secondary = Account("secondary", "Secondary", "claude", cred)
        base = {SLOT: "/other"}
        env, warnings = self.p.env_for(secondary, base)
        self.assertEqual(env[SLOT], cred)
        self.assertEqual(warnings, [])
        self.assertEqual(base, {SLOT: "/other"})

    def test_env_removes_config_dir_with_warning(self):
        secondary = Account("secondary", "Secondary", "claude", "/w")
        for account in (self.primary, secondary):
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

    def test_billing_risks_global_config_primary_api_key(self):
        path = self.home / ".claude.json"
        for data, expected in (({"primaryApiKey": "sk-secret", "x": 1}, ["primaryApiKey in %s" % path]),
                               ({"primaryApiKey": None}, []),
                               ({"apiKeyHelper": "x", "env": {"ANTHROPIC_API_KEY": "1"}}, []),
                               ([], [])):
            with self.subTest(data=data):
                self.write_json(path, data)
                r = self.risks()
                self.assertEqual(r, expected)
                self.assertNotIn("sk-secret", " ".join(r))
        self.write_json(path, "{not json")
        r = self.risks()
        self.assertEqual(len(r), 1)
        self.assertTrue(r[0].startswith("cannot read %s: " % path), r[0])
        path.unlink()
        self.assertEqual(self.risks(), [])

    def test_billing_risks_git_root_local_settings(self):
        repo = self.home / "repo"
        self.folder = repo / "sub"
        self.folder.mkdir(parents=True)
        local = repo / ".claude" / "settings.local.json"
        self.write_json(local, {"apiKeyHelper": "x"})
        self.assertEqual(self.risks(), [])  # no .git: not a git root
        for kind in ("dir", "file"):
            with self.subTest(kind=kind):
                git = repo / ".git"
                git.mkdir() if kind == "dir" else git.write_text("gitdir: /x")
                self.assertEqual(self.risks(), ["apiKeyHelper in %s" % local])
                git.rmdir() if kind == "dir" else git.unlink()
        # folder is the git root: its local settings are reported once, not twice
        (self.folder / ".git").mkdir()
        mine = self.folder / ".claude" / "settings.local.json"
        self.write_json(mine, {"apiKeyHelper": "x"})
        self.assertEqual(self.risks(), ["apiKeyHelper in %s" % mine])

    def test_billing_risks_worktree_main_checkout_local_settings(self):
        main = Path(os.path.realpath(str(self.home))) / "main"
        wt = main.parent / "wt"
        (main / ".git" / "worktrees" / "wt").mkdir(parents=True)
        wt.mkdir()
        main_local = main / ".claude" / "settings.local.json"
        self.write_json(main_local, {"apiKeyHelper": "x"})
        for gitdir in (str(main / ".git" / "worktrees" / "wt"), "../main/.git/worktrees/wt"):
            for folder in (wt, wt / "sub"):
                with self.subTest(gitdir=gitdir, folder=str(folder)):
                    folder.mkdir(exist_ok=True)
                    (wt / ".git").write_text("gitdir: %s\n" % gitdir)
                    self.folder = folder
                    self.assertEqual(self.risks(), ["apiKeyHelper in %s" % main_local])
        for odd in ("", "garbage", "gitdir: /nowhere/at/all", b"\xff\xfe"):
            with self.subTest(odd=odd):
                if isinstance(odd, bytes):
                    (wt / ".git").write_bytes(odd)
                else:
                    (wt / ".git").write_text(odd)
                self.folder = wt
                self.assertEqual(self.risks(), [])

    def test_billing_risks_symlinked_folder_uses_realpath(self):
        repo = Path(os.path.realpath(str(self.home))) / "repo"
        (repo / ".git").mkdir(parents=True)
        (repo / "sub").mkdir()
        local = repo / ".claude" / "settings.local.json"
        self.write_json(local, {"apiKeyHelper": "x"})
        link = self.home / "link"
        link.symlink_to(repo / "sub")
        self.folder = link
        self.assertEqual(self.risks(), ["apiKeyHelper in %s" % local])
        link.unlink()
        link.symlink_to(repo)  # folder is the repo root: reported once, by the folder scope
        self.assertEqual(self.risks(), ["apiKeyHelper in %s" % (link / ".claude" / "settings.local.json")])

    def test_billing_risks_managed_drop_ins(self):
        d = self.roots["managed"] / "managed-settings.d"
        self.write_json(d / "b.json", {"env": {"ANTHROPIC_API_KEY": "1"}})
        self.write_json(d / "a.json", {"forceLoginOrgUUID": "x"})
        self.write_json(d / "c.txt", {"apiKeyHelper": "x"})
        self.assertEqual(self.risks(), ["forceLoginOrgUUID in %s" % (d / "a.json"),
                                        "ANTHROPIC_API_KEY in %s env" % (d / "b.json")])
        self.write_json(d / "a.json", "{bad")
        self.assertTrue(self.risks()[0].startswith("cannot read %s: " % (d / "a.json")))

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

    def test_version_below_range_warns(self):
        self.addCleanup(os.environ.pop, "FAKE_CLAUDE_VERSION", None)
        os.environ["FAKE_CLAUDE_VERSION"] = "2.1.300"
        self.assertEqual(self.p.self_check(),
                         ["Claude Code 2.1.300 is outside the tested range 2.1.301-2.1.302"])

    def test_version_outside_range_warns(self):
        self.addCleanup(os.environ.pop, "FAKE_CLAUDE_VERSION", None)
        self.assertEqual(self.p.self_check(), [])
        os.environ["FAKE_CLAUDE_VERSION"] = "2.1.302"
        self.assertEqual(self.p.self_check(), [])
        os.environ["FAKE_CLAUDE_VERSION"] = "2.1.400"
        self.assertEqual(self.p.self_check(),
                         ["Claude Code 2.1.400 is outside the tested range 2.1.301-2.1.302"])
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
