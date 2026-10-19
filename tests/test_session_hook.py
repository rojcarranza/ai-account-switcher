"""FR-5.7, FR-5.8, ADR-0010: `ais hook install` / `uninstall` add and remove only ais's SessionStart hook."""
import json
import os
import stat
import subprocess

from ais import core
from tests.test_menu_install import MenuInstallCase

CMD = '[ -x "$HOME/.local/bin/ais" ] && "$HOME/.local/bin/ais" record || true'
OURS = {"hooks": [{"type": "command", "command": CMD}]}
THEIRS = {"hooks": [{"type": "command", "command": "echo hi"}]}


class HookCase(MenuInstallCase):
    def setUp(self):
        super().setUp()
        self.settings = self.home / ".claude" / "settings.json"
        self.settings.parent.mkdir(exist_ok=True)

    def install(self, answers=("y",), dry_run=False):
        return self.run_cmd(core.cmd_hook_install, answers, dry_run)

    def uninstall(self, answers=("y",), dry_run=False):
        return self.run_cmd(core.cmd_hook_uninstall, answers, dry_run)

    def write(self, data):
        self.settings.write_text(json.dumps(data, indent=2) + "\n")

    def read(self):
        return json.loads(self.settings.read_text())


class HookInstallTest(HookCase):
    def test_install_creates_settings_file_after_yes(self):
        code, out, err = self.install()
        self.assertEqual(code, 0, err)
        self.assertEqual(self.read(), {"hooks": {"SessionStart": [OURS]}})
        self.assertEqual(stat.S_IMODE(self.settings.stat().st_mode), 0o600)
        self.assertIn(CMD, out)  # shown before the question
        self.assertEqual([p.name for p in self.settings.parent.iterdir() if p.name.startswith(".")], [])  # no temp left

    def test_install_keeps_every_other_key_and_hook(self):
        before = {"model": "opus", "env": {"A": "é"},
                  "hooks": {"PreToolUse": [THEIRS], "SessionStart": [THEIRS]}}
        self.write(before)
        code, _, err = self.install()
        self.assertEqual(code, 0, err)
        before["hooks"]["SessionStart"].append(OURS)
        self.assertEqual(self.read(), before)
        self.assertEqual(list(self.read()), ["model", "env", "hooks"])  # key order kept
        self.assertIn('"A": "é"', self.settings.read_text())

    def test_install_twice_changes_nothing(self):
        self.install()
        before = self.settings.read_text()
        code, out, _ = self.install(answers=())  # no question asked
        self.assertEqual(code, 0)
        self.assertIn("already installed", out)
        self.assertEqual(self.settings.read_text(), before)

    def test_install_writes_through_symlink(self):
        dotfiles = self.home / "dotfiles" / "claude"
        dotfiles.mkdir(parents=True)
        real = dotfiles / "settings.json"
        real.write_text('{"model": "opus"}\n')
        os.chmod(str(real), 0o644)
        self.settings.symlink_to(real)
        code, _, err = self.install()
        self.assertEqual(code, 0, err)
        self.assertTrue(self.settings.is_symlink())
        self.assertEqual(json.loads(real.read_text()), {"model": "opus", "hooks": {"SessionStart": [OURS]}})
        self.assertEqual(stat.S_IMODE(real.stat().st_mode), 0o644)
        self.assertEqual(sorted(p.name for p in dotfiles.iterdir()), ["settings.json"])

    def test_install_declined_or_dry_run_writes_nothing(self):
        self.write({"model": "opus"})
        for answers in (("n",), ()):
            code, out, _ = self.install(answers)
            self.assertEqual(code, 65)
            self.assertIn(CMD, out)
        code, out, _ = self.install(dry_run=True)
        self.assertEqual(code, 0)
        self.assertIn("Would", out)
        self.assertEqual(self.read(), {"model": "opus"})

    def test_install_refuses_malformed_settings(self):
        for text in ("{", "[]", '{"hooks": []}', '{"hooks": {"SessionStart": {}}}'):
            with self.subTest(text=text):
                self.settings.write_text(text)
                code, _, err = self.install()
                self.assertEqual(code, 78)
                self.assertIn(str(self.settings), err)
                self.assertEqual(self.settings.read_text(), text)

    def test_install_refuses_target_outside_home_or_not_a_file(self):
        self.settings.mkdir()
        code, _, _ = self.install()
        self.assertEqual(code, 73)
        self.settings.rmdir()
        self.settings.symlink_to("/etc/hosts")
        code, _, _ = self.install()
        self.assertEqual(code, 73)


class HookUninstallTest(HookCase):
    def test_uninstall_removes_only_ais_hook(self):
        self.write({"model": "opus", "hooks": {"SessionStart": [THEIRS, OURS], "Stop": [THEIRS]}})
        code, out, err = self.uninstall()
        self.assertEqual(code, 0, err)
        self.assertEqual(self.read(), {"model": "opus", "hooks": {"SessionStart": [THEIRS], "Stop": [THEIRS]}})

    def test_uninstall_keeps_other_hooks_in_a_shared_group(self):
        shared = {"hooks": [{"type": "command", "command": "echo hi"}, {"type": "command", "command": CMD}]}
        self.write({"hooks": {"SessionStart": [shared]}})
        self.uninstall()
        self.assertEqual(self.read(), {"hooks": {"SessionStart": [THEIRS]}})

    def test_uninstall_drops_keys_it_left_empty(self):
        self.write({"model": "opus", "hooks": {"SessionStart": [OURS]}})
        self.uninstall()
        self.assertEqual(self.read(), {"model": "opus"})

    def test_uninstall_without_hook_changes_nothing(self):
        for text in (None, '{"model": "opus"}\n'):
            with self.subTest(text=text):
                if text is not None:
                    self.settings.write_text(text)
                code, out, _ = self.uninstall(answers=())
                self.assertEqual(code, 0)
                self.assertIn("No ais hook", out)
                self.assertEqual(self.settings.read_text() if text else None, text)

    def test_uninstall_declined_or_dry_run_keeps_hook(self):
        self.write({"hooks": {"SessionStart": [OURS]}})
        self.assertEqual(self.uninstall(("n",))[0], 65)
        self.assertEqual(self.uninstall(dry_run=True)[0], 0)
        self.assertEqual(self.read(), {"hooks": {"SessionStart": [OURS]}})

    def test_ais_uninstall_also_removes_hook(self):
        self.write({"model": "opus", "hooks": {"SessionStart": [OURS]}})
        code, out, err = self.run_cmd(core.cmd_uninstall, ("y", "y"))
        self.assertEqual(code, 0, err)
        self.assertIn("SessionStart hook", out)
        self.assertEqual(self.read(), {"model": "opus"})

    def test_ais_uninstall_dry_run_keeps_hook(self):
        self.write({"hooks": {"SessionStart": [OURS]}})
        code, out, _ = self.run_cmd(core.cmd_uninstall, (), dry_run=True)
        self.assertEqual(code, 0)
        self.assertIn("SessionStart hook", out)
        self.assertEqual(self.read(), {"hooks": {"SessionStart": [OURS]}})


class HookCommandTest(HookCase):
    def test_command_is_harmless_without_ais(self):
        r = subprocess.run(["sh", "-c", CMD], input="{}", capture_output=True, text=True, timeout=10,
                           env={"HOME": str(self.home), "PATH": "/usr/bin:/bin"})
        self.assertEqual((r.returncode, r.stdout, r.stderr), (0, "", ""))

    def test_command_runs_installed_ais_record_with_stdin(self):
        bin_dir = self.home / ".local" / "bin"
        bin_dir.mkdir(parents=True)
        fake = bin_dir / "ais"
        fake.write_text('#!/bin/sh\necho "$@" > "$HOME/args"; cat > "$HOME/stdin"\n')
        os.chmod(str(fake), 0o755)
        r = subprocess.run(["sh", "-c", CMD], input='{"x": 1}', capture_output=True, text=True, timeout=10,
                           env={"HOME": str(self.home), "PATH": "/usr/bin:/bin"})
        self.assertEqual(r.returncode, 0)
        self.assertEqual((self.home / "args").read_text(), "record\n")
        self.assertEqual((self.home / "stdin").read_text(), '{"x": 1}')


class HookCliTest(HookCase):
    def test_cli_dry_run_and_missing_subcommand(self):
        code, out, err = self.ais("hook", "install", "--dry-run")
        self.assertEqual(code, 0, err)
        self.assertIn("Would add to", out)
        self.assertFalse(self.settings.exists())
        self.assertEqual(self.ais("hook")[0], 64)

    def test_cli_install_then_uninstall(self):
        self.assertEqual(self.ais("hook", "install", stdin="y\n")[0], 0)
        self.assertEqual(self.read(), {"hooks": {"SessionStart": [OURS]}})
        self.assertEqual(self.ais("hook", "uninstall", stdin="y\n")[0], 0)
        self.assertEqual(self.read(), {})
