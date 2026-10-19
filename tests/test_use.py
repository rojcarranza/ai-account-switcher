"""FR-3.16 to FR-3.20: `ais use` picks the account for one terminal window."""
import contextlib
import io
import json
import os
import shlex
import subprocess
import sys
from pathlib import Path
from unittest import mock

from ais import cli
from ais.providers.claude import BILLING_ENV, CONFIG_DIR_ENV, ClaudeProvider
from tests.helpers import SRC, TempHomeCase

SLOT = "CLAUDE_SECURESTORAGE_CONFIG_DIR"


class UseTest(TempHomeCase):
    def setUp(self):
        super().setUp()
        self.work = str(self.home / ".claude-accounts" / "work dir")  # a space: quoting matters
        self.ais_dir.mkdir(parents=True)
        (self.ais_dir / "config.json").write_text(json.dumps({
            "version": 1, "default": "personal", "accounts": {
                "personal": {"label": "Personal", "provider": "claude", "credDir": None},
                "work": {"label": "Work", "provider": "claude", "credDir": self.work}}}))
        self.proj = self.home / "proj"
        self.proj.mkdir()
        old = os.getcwd()
        os.chdir(str(self.proj))
        self.addCleanup(os.chdir, old)
        self.argv_log = self.home / "argv.log"
        self.clip = self.home / "clip.txt"
        env = {"FAKE_CLAUDE_ARGV_LOG": str(self.argv_log), "FAKE_PBCOPY_OUT": str(self.clip)}
        for k in list(env) + list(BILLING_ENV) + [SLOT, CONFIG_DIR_ENV, "AIS_ACCOUNT"]:
            if k in os.environ:
                saved = os.environ.pop(k)
                self.addCleanup(os.environ.__setitem__, k, saved)
            self.addCleanup(os.environ.pop, k, None)
        os.environ.update(env)
        roots = {"home": self.home, "managed": self.home / "managed", "managed_prefs": self.home / "prefs"}
        patch = mock.patch.object(ClaudeProvider, "default_settings_roots", lambda _self: roots)
        patch.start()
        self.addCleanup(patch.stop)

    def ais(self, *args):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = cli.main(list(args))
        return code, out.getvalue(), err.getvalue()

    def slot(self):
        p = Path(str(self.argv_log) + ".env")
        return p.read_text().strip() if p.exists() else None

    def test_shell_exports_extra_account(self):
        code, out, err = self.ais("use", "--shell", "work")
        self.assertEqual(code, 0)
        self.assertEqual(out.splitlines(), ["export %s=%s" % (SLOT, shlex.quote(self.work)),
                                            "export AIS_ACCOUNT=work"])
        self.assertEqual(err, "This terminal: Work\n")
        self.assertIsNone(self.slot())  # starts nothing

    def test_shell_unsets_slot_for_default_account(self):
        os.environ[SLOT] = self.work
        os.environ[CONFIG_DIR_ENV] = "/x"
        code, out, err = self.ais("use", "--shell", "personal")
        self.assertEqual(code, 0)
        self.assertEqual(sorted(out.splitlines()),
                         sorted(["export AIS_ACCOUNT=personal", "unset " + SLOT, "unset " + CONFIG_DIR_ENV]))
        self.assertEqual(err, "This terminal: Personal\n")  # no FR-1.3 warning: the unset is the point

    def test_shell_unknown_account_prints_nothing(self):
        code, out, err = self.ais("use", "--shell", "nope")
        self.assertEqual(code, 64)
        self.assertEqual(out, "")
        self.assertIn("unknown account 'nope'", err)

    def test_use_without_function_warns_and_runs(self):
        code, out, err = self.ais("use", "work")
        self.assertEqual(code, 0)
        self.assertEqual(self.slot(), "slot=" + self.work)
        self.assertIn('eval "$(ais shell-init)"', err)
        self.assertIn("this terminal was not set", err)

    def test_use_alone_names_the_window_account(self):
        os.environ["AIS_ACCOUNT"] = "work"
        self.assertEqual(self.ais("use"), (0, "This terminal: Work\n", ""))

    def test_use_alone_defaults(self):
        self.assertEqual(self.ais("use"), (0, "This terminal: Personal (default)\n", ""))
        os.environ["AIS_ACCOUNT"] = "gone"
        self.assertEqual(self.ais("use"), (0, "This terminal: Personal (default)\n", ""))

    def test_copy_puts_command_on_clipboard(self):
        code, _, _ = self.ais("use", "--copy", "work")
        self.assertEqual(code, 0)
        self.assertEqual(self.clip.read_text(), "ais use work")
        self.assertIsNone(self.slot())

    def test_copy_unknown_account(self):
        code, _, _ = self.ais("use", "--copy", "nope")
        self.assertEqual(code, 64)
        self.assertFalse(self.clip.exists())

    def test_shell_and_copy_cannot_be_combined(self):
        code, _, err = self.ais("use", "--shell", "--copy", "work")
        self.assertEqual(code, 64)

    def shell(self, script, before=""):
        """Run script in bash after loading `ais shell-init`, with a real `ais` command on PATH."""
        bin_dir = self.home / "bin"
        bin_dir.mkdir(exist_ok=True)
        wrapper = bin_dir / "ais"
        wrapper.write_text('#!/bin/sh\nPYTHONPATH=%s exec %s -m ais "$@"\n'
                           % (shlex.quote(str(SRC)), shlex.quote(sys.executable)))
        wrapper.chmod(0o755)
        env = dict(os.environ, PATH=str(bin_dir) + os.pathsep + os.environ["PATH"])
        return subprocess.run(["bash", "-c", before + 'eval "$(command ais shell-init)" || exit 9\n' + script],
                              env=env, cwd=str(self.proj), capture_output=True, text=True, timeout=60)

    def test_function_sets_window_then_plain_claude_follows(self):
        r = self.shell('ais use work; echo "rc=$? acct=$AIS_ACCOUNT"\n'
                       'rm -f "$FAKE_CLAUDE_ARGV_LOG.env"\n'
                       'claude; echo "rc=$?"\n')
        self.assertEqual(r.stdout.splitlines(), ["rc=0 acct=work", "rc=0"], r.stderr)
        self.assertEqual(self.slot(), "slot=" + self.work)  # the plain claude ran on work
        self.assertIn("This terminal: Work", r.stderr)

    def test_function_unknown_account_changes_nothing(self):
        r = self.shell('ais use nope; echo "rc=$? acct=${AIS_ACCOUNT-unset}"\n')
        self.assertEqual(r.stdout.splitlines(), ["rc=64 acct=unset"], r.stderr)
        self.assertIsNone(self.slot())

    def test_plain_claude_with_args_is_untouched(self):
        r = self.shell('ais use work >/dev/null 2>&1\nrm -f "$FAKE_CLAUDE_ARGV_LOG.env"\n'
                       'claude -c; echo "rc=$?"\n')
        self.assertEqual(r.stdout.splitlines(), ["rc=0"], r.stderr)
        self.assertEqual(self.argv_log.read_text().splitlines(), ["-c"])  # ais run would refuse -c
        self.assertEqual(self.slot(), "slot=" + self.work)  # the exported slot still applies

    def test_claude_without_ais_use_is_untouched(self):
        r = self.shell('claude; echo "rc=$?"\n')
        self.assertEqual(r.stdout.splitlines(), ["rc=0"], r.stderr)
        self.assertEqual(self.slot(), "slot=<unset>")

    def test_other_ais_commands_pass_through(self):
        r = self.shell('ais use; echo "rc=$?"\n')
        self.assertEqual(r.stdout.splitlines(), ["This terminal: Personal (default)", "rc=0"], r.stderr)

    def test_init_survives_an_alias_named_claude(self):
        r = self.shell('ais use work >/dev/null 2>&1\nrm -f "$FAKE_CLAUDE_ARGV_LOG.env"\n'
                       'claude; echo "rc=$?"\n', before="shopt -s expand_aliases\nalias claude=false ais=false\n")
        self.assertEqual(r.stdout.splitlines(), ["rc=0"], r.stderr)
        self.assertEqual(self.slot(), "slot=" + self.work)
