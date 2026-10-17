import json
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
        c = {"version": 1, "default": "personal",
             "accounts": {
                 "personal": {"label": "Personal", "provider": "claude", "credDir": None},
                 "work": {"label": "Work", "provider": "claude",
                          "credDir": str(self.home / ".claude-work")}}}
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

    def work(self, **over):
        c = self.cfg()
        c["accounts"]["work"].update(over)
        return c

    def test_loads_valid_config(self):
        c = self.load(self.cfg(cross_account_ack={"a->b": "2026-10-16"}, menu_privacy=True))
        self.assertEqual(c.default, "personal")
        self.assertTrue(c.accounts["personal"].is_default)
        self.assertFalse(c.accounts["work"].is_default)
        self.assertEqual(c.accounts["work"].cred_dir, str(self.home / ".claude-work"))
        self.assertEqual(c.acks, {"a->b": "2026-10-16"})
        self.assertTrue(c.menu_privacy)

    def test_unknown_account_exits_64_lists_names(self):
        c = self.load(self.cfg())
        for name in ("nope", "Bad_Name", "", "a" * 40):
            with self.subTest(name=name):
                with self.assertRaises(AisError) as cm:
                    c.get(name)
                self.assertEqual(cm.exception.code, 64)
                self.assertIn("personal, work", cm.exception.message)
        self.assertEqual(c.get("work").label, "Work")

    def test_nfd_cred_dir_rejected(self):
        nfd = str(self.home / unicodedata.normalize("NFD", "Café"))
        with self.assertRaises(AisError) as cm:
            self.load(self.work(credDir=nfd))
        self.assertEqual(cm.exception.code, 78)
        self.assertIn("work", cm.exception.message)
        self.assertIn("NFC", cm.exception.message)

    def test_get_rejects_trailing_newline(self):
        with self.assertRaises(AisError) as cm:
            self.load(self.cfg()).get("work\n")
        self.assertEqual(cm.exception.code, 64)

    def test_cred_dir_symlink_out_of_home_rejected(self):
        with tempfile.TemporaryDirectory() as outside:
            link = self.home / "link"
            link.symlink_to(outside)
            with self.assertRaises(AisError) as cm:
                self.load(self.work(credDir=str(link)))
        self.assertEqual(cm.exception.code, 78)
        self.assertIn("outside", cm.exception.message)

    def test_cred_dir_equal_to_home_accepted(self):
        c = self.load(self.work(credDir=str(self.home)))
        self.assertEqual(c.accounts["work"].cred_dir, str(self.home))

    def test_shared_cred_dir_rejected(self):
        c = self.cfg(accounts=dict(self.cfg()["accounts"], third={
            "label": "T", "provider": "claude", "credDir": str(self.home / ".claude-work")}))
        for label, other in (("same string", None), ("same realpath", "link")):
            with self.subTest(label):
                if other:
                    (self.home / "link").symlink_to(self.home / ".claude-work")
                    c["accounts"]["third"]["credDir"] = str(self.home / "link")
                with self.assertRaises(AisError) as cm:
                    self.load(c)
                self.assertEqual(cm.exception.code, 78)
                for n in ("work", "third"):
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
            ("relative", self.work(credDir="rel/dir"), "work", "absolute"),
            ("tilde", self.work(credDir=h + "/~x"), "work", "~"),
            ("trailing slash", self.work(credDir=h + "/x/"), "work", "end with"),
            ("outside home", self.work(credDir="/etc/claude"), "work", "outside"),
            ("unknown provider", self.work(provider="gpt"), "work", "claude"),
            ("unhashable provider", self.work(provider=["claude"]), "work", "claude"),
            ("id with trailing newline", self.cfg(accounts={
                "work\n": {"label": "x", "provider": "claude", "credDir": h + "/w"},
                "personal": {"label": "x", "provider": "claude", "credDir": None}}), "work", "^[a-z]"),
            ("dotdot", self.work(credDir=h + "/a/../b"), "work", "canonical"),
            ("dot", self.work(credDir=h + "/./b"), "work", "canonical"),
            ("double slash", self.work(credDir=h + "//b"), "work", "canonical"),
            ("leading double slash", self.work(credDir="//" + h.lstrip("/") + "/b"), "work", "canonical"),
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
            ("empty label", self.work(label=""), "work", "label"),
            ("default with credDir", self.cfg(default="work"), "work", "default"),
            ("extra without credDir", self.work(credDir=None), "work", "credDir"),
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
