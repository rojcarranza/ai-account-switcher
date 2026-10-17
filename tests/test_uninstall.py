"""FR-5.3, FR-5.5: `ais uninstall` lists, asks, removes ~/.config/ais and the recorded plugin, prints manual steps."""
import contextlib
import io
import json
import os
from unittest import mock

from ais import cli
from ais.providers.claude import keychain_service
from tests.helpers import TempHomeCase


def snapshot(root):
    return sorted((str(p.relative_to(root)), p.is_symlink()) for p in root.rglob("*"))


class UninstallTest(TempHomeCase):
    def setUp(self):
        super().setUp()
        self.work = str(self.home / ".claude-work")
        self.ais_dir.mkdir(parents=True)
        (self.ais_dir / "config.json").write_text(json.dumps({
            "version": 1, "default": "personal", "accounts": {
                "personal": {"label": "Personal", "provider": "claude", "credDir": None},
                "work": {"label": "Work", "provider": "claude", "credDir": self.work}}}))
        (self.ais_dir / "ais.log").write_text("x\n")
        self.claude = self.home / ".claude"
        self.claude.mkdir()
        (self.claude / "keep.txt").write_text("keep")
        (self.home / ".claude.json").write_text("{}")
        (self.home / ".claude-accounts" / "work").mkdir(parents=True)
        self.plugin = self.home / "plugins" / "ais.5m.py"
        self.plugin.parent.mkdir()
        self.plugin.write_text("plugin")
        self.other = self.home / "plugins" / "other.py"
        self.other.write_text("other")

    def ais(self, stdin, *args):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err), \
                mock.patch("sys.stdin", io.StringIO(stdin)):
            code = cli.main(["uninstall"] + list(args))
        return code, out.getvalue(), err.getvalue()

    def add_snapshots(self):
        s = self.ais_dir / "snapshots" / "one"
        s.mkdir(parents=True)
        (s / "t.jsonl").write_text("12345")

    def record_plugin(self):
        (self.ais_dir / "state.json").write_text(json.dumps({"menu_plugin": str(self.plugin)}))

    def test_uninstall_asks_about_snapshots(self):
        self.add_snapshots()
        code, out, err = self.ais("y\nn\n")
        self.assertEqual(code, 0)
        self.assertIn("snapshots", err)
        self.assertTrue((self.ais_dir / "snapshots" / "one" / "t.jsonl").exists())
        self.assertFalse((self.ais_dir / "ais.log").exists())
        self.assertIn(str(self.ais_dir / "snapshots"), out)  # kept: location and size
        self.assertIn("5 bytes", out)
        code, _, _ = self.ais("y\ny\n")
        self.assertEqual(code, 0)
        self.assertFalse(self.ais_dir.exists())

    def test_uninstall_declined_65_removes_nothing(self):
        before = snapshot(self.home)
        for stdin in ("n\n", "", "maybe\n"):
            code, out, _ = self.ais(stdin)
            self.assertEqual(code, 65)
            self.assertIn("ais.log", out)  # the listing came first
            self.assertEqual(snapshot(self.home), before)

    def test_uninstall_keeps_claude_data(self):
        self.add_snapshots()
        log = self.home / "security.log"
        os.environ["FAKE_CALL_LOG"] = str(log)
        self.addCleanup(os.environ.pop, "FAKE_CALL_LOG", None)
        code, out, _ = self.ais("y\ny\n")
        self.assertEqual(code, 0)
        self.assertEqual((self.claude / "keep.txt").read_text(), "keep")
        self.assertTrue((self.home / ".claude.json").exists())
        self.assertTrue((self.home / ".claude-accounts" / "work").is_dir())
        self.assertIn(self.work, out)
        self.assertIn(keychain_service(self.work), out)  # the hint; `security` is never run
        self.assertFalse(log.exists() and log.read_text())  # `security` never ran

    def test_uninstall_removes_recorded_plugin_only(self):
        self.record_plugin()
        code, out, _ = self.ais("y\n")
        self.assertEqual(code, 0)
        self.assertFalse(self.plugin.exists())
        self.assertTrue(self.other.exists())
        self.plugin.write_text("again")  # not recorded -> left alone
        code, _, _ = self.ais("y\n")
        self.assertEqual(code, 0)
        self.assertTrue(self.plugin.exists())

    def test_uninstall_plugin_symlink_not_followed_and_missing_skipped(self):
        target = self.home / "target.txt"
        target.write_text("t")
        link = self.home / "plugins" / "link.py"
        link.symlink_to(target)
        (self.ais_dir / "state.json").write_text(json.dumps({"menu_plugin": str(link)}))
        self.assertEqual(self.ais("y\n")[0], 0)
        self.assertFalse(link.is_symlink())
        self.assertEqual(target.read_text(), "t")
        self.ais_dir.mkdir()
        (self.ais_dir / "state.json").write_text(json.dumps({"menu_plugin": str(link)}))
        self.assertEqual(self.ais("y\n")[0], 0)  # file already gone

    def test_uninstall_symlink_inside_config_not_followed(self):
        outside = self.home / "outside"
        outside.mkdir()
        (outside / "f").write_text("f")
        (self.ais_dir / "lnk").symlink_to(outside)
        self.assertEqual(self.ais("y\n")[0], 0)
        self.assertEqual((outside / "f").read_text(), "f")
        self.assertFalse(self.ais_dir.exists())

    def test_uninstall_bad_state_json_skips_plugin_with_warning(self):
        (self.ais_dir / "state.json").write_text("{nope")
        code, _, err = self.ais("y\n")
        self.assertEqual(code, 0)
        self.assertIn("by hand", err)
        self.assertTrue(self.plugin.exists())
        self.assertFalse(self.ais_dir.exists())

    def test_uninstall_stops_on_error_73(self):
        self.record_plugin()
        real = os.unlink

        def failing(path, *a, **k):
            if str(path).endswith("ais.log"):
                raise PermissionError("denied")
            return real(path, *a, **k)
        with mock.patch("os.unlink", failing):
            code, out, err = self.ais("y\n")
        self.assertEqual(code, 73)
        self.assertIn("%s: " % (self.ais_dir / "ais.log"), err)
        self.assertIn("denied", err)
        self.assertNotIn("~/.local/bin/ais", out)  # no manual steps after a failure
        for f in ("ais.log", "config.json", "state.json"):
            self.assertTrue((self.ais_dir / f).exists(), f)

    def test_uninstall_plugin_folder_or_relative_path_ignored(self):
        self.addCleanup(os.chdir, os.getcwd())
        os.chdir(str(self.home))  # "relative/ais.py" resolves here
        sub = self.home / "Plugins" / "sub"
        sub.mkdir(parents=True)
        (sub / "other.py").write_text("o")
        for rec in (str(self.home / "Plugins"), "relative/ais.py"):
            (self.ais_dir / "state.json").write_text(json.dumps({"menu_plugin": rec}))
            (self.home / "relative").mkdir(exist_ok=True)
            (self.home / "relative" / "ais.py").write_text("r")
            code, _, err = self.ais("y\n")
            self.assertEqual(code, 0)
            self.assertIn("by hand", err)
            self.assertTrue((sub / "other.py").exists())
            self.assertTrue((self.home / "relative" / "ais.py").exists())
            self.ais_dir.mkdir(exist_ok=True)

    def test_uninstall_unreadable_config_dir_exits_73(self):
        self.ais_dir.chmod(0)
        self.addCleanup(self.ais_dir.chmod, 0o700)
        for args in ((), ("--dry-run",)):
            code, _, err = self.ais("y\n", *args)
            self.assertEqual(code, 73)
            self.assertIn(str(self.ais_dir), err)
            self.assertNotIn("Traceback", err)

    def test_uninstall_removes_empty_or_symlinked_config_dir(self):
        for p in list(self.ais_dir.iterdir()):
            p.unlink()
        code, out, _ = self.ais("y\n")
        self.assertEqual(code, 0)
        self.assertFalse(self.ais_dir.exists())
        real = self.home / "real"
        real.mkdir()
        (real / "f").write_text("f")
        self.ais_dir.parent.mkdir(exist_ok=True)
        self.ais_dir.symlink_to(real)
        self.assertEqual(self.ais("y\n")[0], 0)
        self.assertFalse(self.ais_dir.is_symlink())
        self.assertEqual((real / "f").read_text(), "f")
        self.ais_dir.write_text("a file")
        self.assertEqual(self.ais("y\n")[0], 0)
        self.assertFalse(os.path.lexists(str(self.ais_dir)))

    def test_uninstall_lists_local_bin(self):
        code, out, _ = self.ais("n\n")
        self.assertEqual(code, 65)
        code, out, _ = self.ais("y\n")
        for part in ("~/.local/bin/ais", "~/.local/bin/ais.prev", '~/.zshrc',
                     'export PATH="$HOME/.local/bin:$PATH"'):
            self.assertIn(part, out)

    def test_uninstall_nothing_to_remove(self):
        for p in list(self.ais_dir.iterdir()):
            p.unlink()
        self.ais_dir.rmdir()
        code, out, _ = self.ais("")
        self.assertEqual(code, 0)
        self.assertIn("Nothing to remove", out)
        self.assertIn("~/.local/bin/ais.prev", out)
        self.assertIn(str(self.home / ".claude-accounts" / "<account>"), out)  # no config: generic
        self.assertIn("Keychain: ", out)
        self.assertIn("Claude Code-credentials-", out)

    def test_uninstall_dry_run_lists_and_changes_nothing(self):
        self.add_snapshots()
        self.record_plugin()
        before = snapshot(self.home)
        code, out, _ = self.ais("", "--dry-run")
        self.assertEqual(code, 0)
        self.assertIn("snapshots", out)
        self.assertIn(str(self.plugin), out)
        self.assertIn("~/.local/bin/ais", out)
        self.assertEqual(snapshot(self.home), before)

    def test_uninstall_warns_on_broken_config_not_missing(self):
        (self.ais_dir / "config.json").write_text("{not json")
        code, out, err = self.ais("", "--dry-run")
        self.assertEqual(code, 0, err)
        self.assertIn("ais: warning: ", err)
        self.assertIn("; the manual steps below are generic", err)
        self.assertIn(str(self.home / ".claude-accounts" / "<account>"), out)
        (self.ais_dir / "config.json").unlink()
        code, _, err = self.ais("", "--dry-run")
        self.assertEqual(code, 0, err)
        self.assertNotIn("warning", err)

    def test_uninstall_works_without_cwd(self):
        for config in (True, False):
            with self.subTest(config=config):
                if not config:
                    (self.ais_dir / "config.json").unlink()
                with mock.patch.object(cli.Path, "cwd", side_effect=OSError("gone")):
                    code, out, err = self.ais("", "--dry-run")
                self.assertEqual(code, 0, err)
                self.assertIn("Uninstall would remove:", out)

    def test_uninstall_kept_snapshots_symlink_named_not_sized(self):
        real = self.home / "elsewhere"
        real.mkdir()
        (real / "big").write_text("x" * 100)
        (self.ais_dir / "snapshots").symlink_to(real)
        code, out, err = self.ais("y\nn\n")
        self.assertEqual(code, 0, err)
        self.assertIn("Kept %s (a symlink to %s)" % (self.ais_dir / "snapshots", real), out)
        self.assertNotIn("bytes", out)
        self.assertEqual((real / "big").read_text(), "x" * 100)

    def test_uninstall_plugin_swapped_for_folder_never_removed_recursively(self):
        self.record_plugin()

        def swap(prompt):  # after the file check, before removal
            self.plugin.unlink()
            self.plugin.mkdir()
            (self.plugin / "inner").write_text("keep")
            return "y"

        with mock.patch("ais.core._ask", side_effect=swap):
            code, _, err = self.ais("")
        self.assertEqual(code, 73, err)
        self.assertIn(str(self.plugin), err)
        self.assertEqual((self.plugin / "inner").read_text(), "keep")

    def test_uninstall_unsearchable_config_parent_exits_73(self):
        self.ais_dir.parent.chmod(0)
        self.addCleanup(self.ais_dir.parent.chmod, 0o700)
        for args in ((), ("--dry-run",)):
            with self.subTest(args=args):
                code, _, err = self.ais("y\n", *args)
                self.assertEqual(code, 73, err)
                self.assertIn(str(self.ais_dir), err)
                self.assertNotIn("Traceback", err)

    def test_uninstall_default_only_config_has_no_generic_lines(self):
        (self.ais_dir / "config.json").write_text(json.dumps({
            "version": 1, "default": "personal", "accounts": {
                "personal": {"label": "Personal", "provider": "claude", "credDir": None}}}))
        code, out, err = self.ais("", "--dry-run")
        self.assertEqual(code, 0, err)
        self.assertNotIn("<account>", out)
        self.assertNotIn("Keychain", out)

    def test_uninstall_lists_desktop_folders(self):
        folder = self.home / "Library" / "Application Support" / "Claude-ais-work"
        code, out, err = self.ais("", "--dry-run")
        self.assertEqual(code, 0, err)
        self.assertIn("%s: your Work Desktop data folder (kept; it holds the Desktop sign-in)" % folder, out)
        self.assertEqual(out.count("Desktop data folder"), 1)  # the default account has none
        (self.ais_dir / "config.json").unlink()
        code, out, err = self.ais("", "--dry-run")
        self.assertEqual(code, 0, err)
        self.assertIn(str(self.home / "Library" / "Application Support" / "Claude-ais-<account>")
                      + ": each extra account's Desktop data folder (kept; it holds the Desktop sign-in)", out)
