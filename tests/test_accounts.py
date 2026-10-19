import json
import os
import tempfile
import unicodedata

from ais.accounts import load_config
from ais.errors import AisError
from ais.store import Store
from tests.helpers import TempHomeCase

PROVIDERS = ("claude",)
CRED_DIR_CASES = ("relative", "tilde", "trailing slash", "outside home", "dotdot", "dot",
                  "double slash", "leading double slash")


class AccountsTest(TempHomeCase):
    def cfg(self, **over):
        c = {"version": 1, "default": "primary",
             "accounts": {
                 "primary": {"label": "Primary", "provider": "claude", "credDir": None},
                 "secondary": {"label": "Secondary", "provider": "claude",
                          "credDir": str(self.home / ".claude-secondary")}}}
        c.update(over)
        return c

    def write(self, c):
        self.ais_dir.mkdir(parents=True, exist_ok=True)
        with open(str(self.ais_dir / "config.json"), "w") as f:
            if isinstance(c, str):
                f.write(c)
            else:
                json.dump(c, f)

    def load(self, c):
        self.write(c)
        return load_config(Store(self.home), PROVIDERS)

    def secondary(self, **over):
        c = self.cfg()
        c["accounts"]["secondary"].update(over)
        return c

    def test_loads_valid_config(self):
        c = self.load(self.cfg(cross_account_ack={"a->b": "2026-10-16"}, menu_privacy=True))
        self.assertEqual(c.default, "primary")
        self.assertTrue(c.accounts["primary"].is_default)
        self.assertFalse(c.accounts["secondary"].is_default)
        self.assertEqual(c.accounts["secondary"].cred_dir, str(self.home / ".claude-secondary"))
        self.assertEqual(c.acks, {"a->b": "2026-10-16"})
        self.assertTrue(c.menu_privacy)

    def test_unknown_account_exits_64_lists_names(self):
        c = self.load(self.cfg())
        for name in ("nope", "Bad_Name", "", "a" * 40):
            with self.subTest(name=name):
                with self.assertRaises(AisError) as cm:
                    c.get(name)
                self.assertEqual(cm.exception.code, 64)
                self.assertIn("primary, secondary", cm.exception.message)
        self.assertEqual(c.get("secondary").label, "Secondary")

    def test_nfd_cred_dir_rejected(self):
        nfd = str(self.home / unicodedata.normalize("NFD", "Café"))
        with self.assertRaises(AisError) as cm:
            self.load(self.secondary(credDir=nfd))
        self.assertEqual(cm.exception.code, 78)
        self.assertIn("secondary", cm.exception.message)
        self.assertIn("NFC", cm.exception.message)

    def test_get_rejects_trailing_newline(self):
        with self.assertRaises(AisError) as cm:
            self.load(self.cfg()).get("secondary\n")
        self.assertEqual(cm.exception.code, 64)

    def test_cred_dir_symlink_out_of_home_rejected(self):
        with tempfile.TemporaryDirectory() as outside:
            link = self.home / "link"
            link.symlink_to(outside)
            with self.assertRaises(AisError) as cm:
                self.load(self.secondary(credDir=str(link)))
        self.assertEqual(cm.exception.code, 78)
        self.assertIn("outside", cm.exception.message)

    def test_cred_dir_equal_to_home_accepted(self):
        c = self.load(self.secondary(credDir=str(self.home)))
        self.assertEqual(c.accounts["secondary"].cred_dir, str(self.home))

    def test_shared_cred_dir_rejected(self):
        c = self.cfg(accounts=dict(self.cfg()["accounts"], third={
            "label": "T", "provider": "claude", "credDir": str(self.home / ".claude-secondary")}))
        for label, other in (("same string", None), ("same realpath", "link")):
            with self.subTest(label):
                if other:
                    (self.home / "link").symlink_to(self.home / ".claude-secondary")
                    c["accounts"]["third"]["credDir"] = str(self.home / "link")
                with self.assertRaises(AisError) as cm:
                    self.load(c)
                self.assertEqual(cm.exception.code, 78)
                for n in ("secondary", "third"):
                    self.assertIn(n, cm.exception.message)

    def test_config_errors_exit_78(self):
        h = str(self.home)
        no_version = self.cfg()
        del no_version["version"]
        no_default = self.cfg()
        del no_default["default"]
        bad_id = self.cfg(default="Bad_1", accounts={
            "Bad_1": {"label": "x", "provider": "claude", "credDir": None}})
        # (label, config or None for missing file, account named in message, rule text)
        cases = [
            ("relative", self.secondary(credDir="rel/dir"), "secondary", "absolute"),
            ("tilde", self.secondary(credDir=h + "/~x"), "secondary", "~"),
            ("trailing slash", self.secondary(credDir=h + "/x/"), "secondary", "end with"),
            ("outside home", self.secondary(credDir="/etc/claude"), "secondary", "outside"),
            ("unknown provider", self.secondary(provider="gpt"), "secondary", "claude"),
            ("unhashable provider", self.secondary(provider=["claude"]), "secondary", "claude"),
            ("id with trailing newline", self.cfg(accounts={
                "secondary\n": {"label": "x", "provider": "claude", "credDir": h + "/w"},
                "primary": {"label": "x", "provider": "claude", "credDir": None}}), "secondary", "^[a-z]"),
            ("dotdot", self.secondary(credDir=h + "/a/../b"), "secondary", "canonical"),
            ("dot", self.secondary(credDir=h + "/./b"), "secondary", "canonical"),
            ("double slash", self.secondary(credDir=h + "//b"), "secondary", "canonical"),
            ("leading double slash", self.secondary(credDir="//" + h.lstrip("/") + "/b"), "secondary", "canonical"),
            ("float version", self.cfg(version=1.0), None, "version"),
            ("ack non-str value", self.cfg(cross_account_ack={"a->b": 5}), None, "cross_account_ack"),
            ("ack list value", self.cfg(cross_account_ack={"a->b": ["x"]}), None, "cross_account_ack"),
            ("unknown version", self.cfg(version=2), None, "version"),
            ("missing version", no_version, None, "version"),
            ("broken json", "{not json", None, "invalid JSON"),
            ("missing file", None, None, "ais setup"),
            ("default undefined", self.cfg(default="ghost"), "ghost", "default"),
            ("default missing", no_default, None, "default"),
            ("bad id", bad_id, "Bad_1", "^[a-z]"),
            ("empty label", self.secondary(label=""), "secondary", "label"),
            ("default with credDir", self.cfg(default="secondary"), "secondary", "default"),
            ("extra without credDir", self.secondary(credDir=None), "secondary", "credDir"),
            ("accounts wrong type", self.cfg(accounts=[]), None, "accounts"),
            ("ack wrong type", self.cfg(cross_account_ack=[]), None, "cross_account_ack"),
            ("privacy wrong type", self.cfg(menu_privacy="yes"), None, "menu_privacy"),
        ]
        for label, c, who, rule in cases:
            with self.subTest(label):
                if c is None:
                    cp = self.ais_dir / "config.json"
                    if cp.exists():
                        cp.unlink()
                else:
                    self.write(c)
                with self.assertRaises(AisError) as cm:
                    load_config(Store(self.home), frozenset(PROVIDERS))
                self.assertEqual(cm.exception.code, 78)
                if who:
                    self.assertIn(who, cm.exception.message)
                if label in CRED_DIR_CASES:
                    self.assertIn("config.json", cm.exception.message)
                self.assertIn(rule, cm.exception.message)

    def support(self):
        d = self.home / "Library" / "Application Support"
        d.mkdir(parents=True, exist_ok=True)
        return d

    def test_desktop_data_dir_kept_exactly_and_need_not_exist(self):
        path = str(self.support() / "Claude-Secondary")
        c = self.load(self.secondary(desktop_data_dir=path))
        self.assertEqual(c.accounts["secondary"].desktop_data_dir, path)
        self.assertIsNone(c.accounts["primary"].desktop_data_dir)
        self.assertIsNone(self.load(self.cfg()).accounts["secondary"].desktop_data_dir)
        (self.support() / "Claude-Secondary").mkdir()
        self.assertEqual(self.load(self.secondary(desktop_data_dir=path)).accounts["secondary"].desktop_data_dir, path)

    def assert_bad_desktop_dir(self, c, account="secondary"):
        with self.assertRaises(AisError) as cm:
            self.load(c)
        self.assertEqual(cm.exception.code, 78)
        self.assertIn(account, cm.exception.message)
        self.assertIn("desktop_data_dir", cm.exception.message)

    def test_desktop_data_dir_on_default_account_exits_78(self):
        c = self.cfg()
        c["accounts"]["primary"]["desktop_data_dir"] = str(self.support() / "Claude-Secondary")
        self.assert_bad_desktop_dir(c, "primary")

    def test_bad_desktop_data_dir_exits_78(self):
        sup = self.support()
        (sup / "Claude-File").write_text("x")
        outside = self.home / "elsewhere"
        outside.mkdir()
        (sup / "Claude-Link").symlink_to(outside)
        cases = {"relative": "Library/Application Support/Claude-Secondary", "tilde": "~/Library/Application Support/X",
                 "outside": str(self.home / "Claude-Secondary"), "support itself": str(sup),
                 "nested": str(sup / "a" / "b"), "symlink out": str(sup / "Claude-Link"),
                 "regular file": str(sup / "Claude-File"), "not a string": 5,
                 "trailing slash": str(sup / "Claude-Secondary") + "/", "dot": str(sup) + "/./Claude-Secondary",
                 "double slash": str(sup) + "//Claude-Secondary"}
        for label, value in cases.items():
            with self.subTest(label):
                self.assert_bad_desktop_dir(self.secondary(desktop_data_dir=value))

    def test_two_accounts_sharing_a_desktop_data_dir_exit_78(self):
        path = str(self.support() / "Claude-Secondary")
        c = self.cfg()
        c["accounts"]["secondary"]["desktop_data_dir"] = path
        c["accounts"]["spare"] = {"label": "Spare", "provider": "claude", "credDir": str(self.home / ".claude-spare"),
                                  "desktop_data_dir": path}
        self.assert_bad_desktop_dir(c, "spare")

    def test_case_variant_desktop_data_dir_counts_as_shared(self):
        a = self.support() / "Claude-Secondary"
        a.mkdir()
        if not os.path.exists(str(self.support() / "claude-secondary")):
            self.skipTest("case-sensitive filesystem")
        c = self.cfg()
        c["accounts"]["secondary"]["desktop_data_dir"] = str(a)
        c["accounts"]["spare"] = {"label": "Spare", "provider": "claude", "credDir": str(self.home / ".claude-spare"),
                                  "desktop_data_dir": str(self.support() / "claude-secondary")}
        self.assert_bad_desktop_dir(c, "spare")

