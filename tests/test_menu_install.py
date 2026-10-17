"""FR-4.7, FR-4.10, FR-5.4: `ais menu install` / `uninstall` write and remove the SwiftBar plugin."""
import contextlib
import io
import json
import os
import shutil
import stat
from pathlib import Path

from unittest import mock

from ais import cli, core
from ais.errors import AisError
from ais.store import Store
from tests.helpers import TESTS
from tests.test_switch import SwitchCase


class MenuInstallCase(SwitchCase):
    def setUp(self):
        super().setUp()
        self.apps = self.home / "Apps"
        (self.apps / "SwiftBar.app").mkdir(parents=True)
        self.plugins = self.home / "plugins"
        self.plugins.mkdir()
        self.target = self.plugins / "ais.1m.sh"
        self.env(FAKE_SWIFTBAR_DIR=str(self.plugins))

    def run_cmd(self, fn, answers=(), dry_run=False):
        ctx = cli._context(0.0, cwd_optional=True)
        ctx.app_roots = [self.apps]
        return self._call(lambda: fn(ctx, dry_run, answers))

    def _call(self, fn):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            try:
                code = fn()
            except core.AisError as e:
                code = e.code
                err.write(e.message)
        return code, out.getvalue(), err.getvalue()

    def install(self, answers=("y",), dry_run=False):
        return self.run_cmd(core.cmd_menu_install, answers, dry_run)

    def uninstall(self, answers=("y",), dry_run=False):
        return self.run_cmd(core.cmd_menu_uninstall, answers, dry_run)

    def body(self):
        claude_dir = os.path.dirname(shutil.which("claude"))
        return '#!/bin/sh\nexport PATH="%s/.local/bin:%s:/usr/bin:/bin"\nexec ais menu render\n' % (self.home, claude_dir)


class MenuInstallTest(MenuInstallCase):
    def test_install_writes_plugin_after_yes(self):
        code, out, err = self.install()
        self.assertEqual(code, 0, err)
        self.assertEqual(self.target.read_text(), self.body())
        self.assertEqual(stat.S_IMODE(self.target.stat().st_mode), 0o700)
        self.assertIn(self.body(), out)  # shown before the question
        self.assertEqual(self.state()["menu_plugin"], str(self.target.resolve()))
        self.assertEqual([p.name for p in self.plugins.iterdir()], ["ais.1m.sh"])  # no temp left

    def test_install_declined_65_writes_nothing(self):
        for answers in (("n",), (), ("maybe",)):
            code, out, _ = self.install(answers)
            self.assertEqual(code, 65)
            self.assertIn("exec ais menu render", out)
        self.assertFalse(self.target.exists())
        self.assertNotIn("menu_plugin", self.state())

    def test_install_swiftbar_missing_71_prints_brew(self):
        shutil.rmtree(str(self.apps / "SwiftBar.app"))
        code, _, err = self.install()
        self.assertEqual(code, 71)
        self.assertIn("brew install --cask swiftbar", err)
        self.assertFalse(self.target.exists())

    def test_install_plugin_folder_unset_71(self):
        os.environ.pop("FAKE_SWIFTBAR_DIR")  # the defaults fake then exits 1
        code, _, err = self.install()
        self.assertEqual(code, 71)
        self.assertIn("choose a plugin folder", err)
        self.assertIn("defaults read com.ameba.SwiftBar PluginDirectory", self.calls_text())
        self.assertEqual(list(self.plugins.iterdir()), [])

    def test_install_claude_missing_69(self):
        only = self.home / "only"  # defaults but no claude
        only.mkdir()
        shutil.copy(str(TESTS / "fakes" / "defaults"), str(only / "defaults"))
        self.env(PATH=str(only))
        code, _, err = self.install()
        self.assertEqual(code, 69)
        self.assertIn("install Claude Code", err)
        self.assertFalse(self.target.exists())

    def test_install_bad_characters_78(self):
        bad = self.home / "bin$x"
        bad.mkdir()
        shutil.copy(str(TESTS / "fakes" / "claude"), str(bad / "claude"))
        shutil.copy(str(TESTS / "fakes" / "defaults"), str(bad / "defaults"))
        self.env(PATH=str(bad))
        code, _, err = self.install()
        self.assertEqual(code, 78)
        self.assertIn("cannot build the plugin PATH", err)
        self.assertFalse(self.target.exists())

    def test_install_refuses_symlink_target_73(self):
        victim = self.home / "victim"
        victim.write_text("keep")
        self.target.symlink_to(victim)
        code, _, _ = self.install()
        self.assertEqual(code, 73)
        self.assertEqual(victim.read_text(), "keep")
        self.assertTrue(self.target.is_symlink())

    def test_install_replaces_existing_file(self):
        self.target.write_text("old")
        code, out, _ = self.install()
        self.assertEqual(code, 0)
        self.assertIn("replace", out)
        self.assertEqual(self.target.read_text(), self.body())

    def test_install_expands_tilde_plugin_folder(self):
        self.env(FAKE_SWIFTBAR_DIR="~/plugins")
        self.assertEqual(self.install()[0], 0)
        self.assertTrue(self.target.exists())

    def test_install_plugin_folder_missing_or_relative_71(self):
        for d in (str(self.home / "gone"), "plugins"):
            self.env(FAKE_SWIFTBAR_DIR=d)
            self.assertEqual(self.install()[0], 71, d)
        self.assertEqual(list(self.plugins.iterdir()), [])

    def test_install_corrupt_state_78_before_writing(self):
        (self.ais_dir / "state.json").write_text("{nope")
        for dry in (False, True):
            self.assertEqual(self.install(dry_run=dry)[0], 78)
        self.assertFalse(self.target.exists())

    def test_install_relative_path_entry_gives_absolute_claude_dir(self):
        rel = self.home / "rel"
        rel.mkdir()
        shutil.copy(str(TESTS / "fakes" / "claude"), str(rel / "claude"))
        shutil.copy(str(TESTS / "fakes" / "defaults"), str(rel / "defaults"))
        os.chdir(str(self.home))
        self.env(PATH="rel")
        self.assertEqual(self.install()[0], 0)
        self.assertIn(":%s:/usr/bin" % os.path.realpath(str(self.home / "rel")), self.target.read_text())

    def test_install_warns_about_other_recorded_plugin_and_missing_ais(self):
        old = self.home / "old.sh"
        old.write_text("x")
        (self.ais_dir / "state.json").write_text(json.dumps({"menu_plugin": str(old)}))
        code, _, err = self.install()
        self.assertEqual(code, 0)
        self.assertIn("state.json also records %s" % old, err)
        self.assertIn("missing; the menu finds no ais", err)
        (self.home / ".local" / "bin").mkdir(parents=True)
        (self.home / ".local" / "bin" / "ais").write_text("x")
        self.assertNotIn("finds no ais", self.install()[2])

    def test_install_dry_run_shows_also_records_warning(self):
        old = self.home / "old.sh"
        old.write_text("x")
        (self.ais_dir / "state.json").write_text(json.dumps({"menu_plugin": str(old)}))
        code, _, err = self.install(dry_run=True)
        self.assertEqual(code, 0)
        self.assertIn("state.json also records %s" % old, err)

    def test_install_state_write_failure_leaves_no_plugin(self):
        with mock.patch.object(Store, "update_json", side_effect=AisError(73, "disk full")):
            code, _, err = self.install()
        self.assertEqual(code, 73)
        self.assertEqual(list(self.plugins.iterdir()), [])

    def test_install_dry_run_writes_nothing_asks_nothing(self):
        code, out, err = self.install(dry_run=True)
        self.assertEqual(code, 0)
        self.assertIn("exec ais menu render", out)
        self.assertNotIn("? [", err)
        self.assertFalse(self.target.exists())
        self.assertNotIn("menu_plugin", self.state())


class MenuUninstallTest(MenuInstallCase):
    def installed(self):
        self.assertEqual(self.install()[0], 0)

    def test_uninstall_removes_only_recorded_file(self):
        self.installed()
        other = self.plugins / "other.sh"
        other.write_text("other")
        code, _, err = self.uninstall()
        self.assertEqual(code, 0, err)
        self.assertFalse(self.target.exists())
        self.assertEqual(other.read_text(), "other")
        self.assertNotIn("menu_plugin", self.state())

    def test_uninstall_declined_65_keeps_file(self):
        self.installed()
        for answers in (("n",), ()):
            self.assertEqual(self.uninstall(answers)[0], 65)
        self.assertTrue(self.target.exists())
        self.assertIn("menu_plugin", self.state())

    def test_uninstall_nothing_recorded(self):
        code, out, _ = self.uninstall()
        self.assertEqual(code, 0)
        self.assertIn("No SwiftBar plugin recorded.", out)

    def test_uninstall_refuses_other_file_name(self):
        other = self.plugins / "precious.sh"
        other.write_text("keep")
        (self.ais_dir / "state.json").write_text(json.dumps({"menu_plugin": str(other)}))
        code, _, err = self.uninstall()
        self.assertEqual(code, 0)
        self.assertIn("ais.1m.sh", err)
        self.assertEqual(other.read_text(), "keep")

    def test_uninstall_recorded_file_gone_clears_state(self):
        self.installed()
        self.target.unlink()
        code, out, _ = self.uninstall(dry_run=True)
        self.assertEqual(code, 0)
        self.assertIn("is already gone", out)
        self.assertIn("menu_plugin", self.state())
        code, out, _ = self.uninstall()
        self.assertEqual(code, 0)
        self.assertIn("is already gone", out)
        self.assertNotIn("menu_plugin", self.state())

    def test_uninstall_folder_record_only_warns(self):
        (self.ais_dir / "state.json").write_text(json.dumps({"menu_plugin": str(self.plugins)}))
        code, out, err = self.uninstall()
        self.assertEqual(code, 0)
        self.assertIn("not an absolute file path", err)
        self.assertNotIn("No SwiftBar plugin recorded", out)
        self.assertTrue(self.plugins.is_dir())

    def test_uninstall_dry_run_removes_nothing(self):
        self.installed()
        code, out, err = self.uninstall(dry_run=True)
        self.assertEqual(code, 0)
        self.assertIn(str(self.target.resolve()), out)
        self.assertNotIn("? [", err)
        self.assertTrue(self.target.exists())
        self.assertIn("menu_plugin", self.state())


class MenuCliTest(MenuInstallCase):
    def test_menu_commands_dry_run_change_nothing(self):
        # cli level: the real parser; SwiftBar.app is found under ~/Applications of the temp HOME
        (self.home / "Applications" / "SwiftBar.app").mkdir(parents=True)
        for cmd in ("install", "uninstall"):
            code, _, err = self.ais("menu", cmd, "--dry-run")
            self.assertEqual(code, 0, err)
        self.assertEqual(list(self.plugins.iterdir()), [])
        self.assertEqual(Path(self.calls).read_text(), "defaults read com.ameba.SwiftBar PluginDirectory\n")

    def test_menu_uninstall_works_without_config(self):
        (self.ais_dir / "config.json").unlink()
        code, out, err = self.ais("menu", "uninstall", "--dry-run")
        self.assertEqual(code, 0, err)
        self.assertIn("No SwiftBar plugin recorded.", out)
        (self.ais_dir / "config.json").write_text("{broken")
        self.assertEqual(self.ais("menu", "uninstall", "--dry-run")[0], 0)

    def test_menu_alone_lists_commands(self):
        code, _, err = self.ais("menu")
        self.assertEqual(code, 64)
        self.assertIn("render, install, uninstall", err)
