"""FR-2.3 to FR-2.7: `ais setup` asks, lists what it creates, then writes and signs in."""
import contextlib
import io
import json
import os
import stat
from pathlib import Path
from unittest import mock

from ais import cli
from ais.providers.claude import BILLING_ENV, CONFIG_DIR_ENV, ClaudeProvider
from tests.helpers import TempHomeCase

SLOT = "CLAUDE_SECURESTORAGE_CONFIG_DIR"
PATH_LINE = 'export PATH="$HOME/.local/bin:$PATH"'
BLANK = "\n" * 5  # default name, label, extra name, label, credDir


def tree(root):
    return sorted(str(p.relative_to(root)) for p in root.rglob("*"))


class SetupTest(TempHomeCase):
    def setUp(self):
        super().setUp()
        self.work = str(self.home / ".claude-accounts" / "work")
        self.calls = self.home / "calls.log"
        os.environ["FAKE_CALL_LOG"] = str(self.calls)
        self.addCleanup(os.environ.pop, "FAKE_CALL_LOG", None)
        for k in BILLING_ENV + (SLOT, CONFIG_DIR_ENV, "FAKE_CLAUDE_LOGIN_RC", "FAKE_CLAUDE_LOGGED_OUT_SLOT"):
            if k in os.environ:
                saved = os.environ.pop(k)
                self.addCleanup(os.environ.__setitem__, k, saved)
            self.addCleanup(os.environ.pop, k, None)
        roots = {"home": self.home, "managed": self.home / "managed", "managed_prefs": self.home / "prefs"}
        patch = mock.patch.object(ClaudeProvider, "default_settings_roots", lambda _self: roots)
        patch.start()
        self.addCleanup(patch.stop)

    def ais(self, stdin, *args):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err), \
                mock.patch("sys.stdin", io.StringIO(stdin)):
            code = cli.main(["setup"] + list(args))
        return code, out.getvalue(), err.getvalue()

    def calls_text(self):
        return self.calls.read_text() if self.calls.exists() else ""

    def config(self):
        return json.loads((self.ais_dir / "config.json").read_text())

    def test_setup_lists_files_and_declines_65_writes_nothing(self):
        before = tree(self.home)
        code, out, err = self.ais(BLANK + "n\n")
        self.assertEqual(code, 65)
        for part in ("config.json", ".lock", "cache.json", "ais.log"):
            self.assertIn(part, out)
        self.assertIn("  %s/ (empty, mode 0700)\n" % self.work, out)  # the listing, not the prompt default
        self.assertEqual(tree(self.home), before)
        self.assertFalse(self.ais_dir.exists())
        self.assertEqual(self.calls_text(), "")
        code, _, _ = self.ais(BLANK)  # no answer at all is not a yes
        self.assertEqual((code, tree(self.home)), (65, before))

    def test_setup_offers_existing_claude_accounts_folders(self):
        root = self.home / ".claude-accounts"
        (root / "zeta").mkdir(parents=True)
        (root / "alpha").mkdir()
        code, out, err = self.ais("\n\n\n\n2\ny\n")  # 2 = zeta (sorted: alpha, zeta)
        self.assertEqual(code, 0)
        text = out + err
        self.assertIn("1) %s" % (root / "alpha"), text)
        self.assertIn("2) %s" % (root / "zeta"), text)
        self.assertEqual(self.config()["accounts"]["work"]["credDir"], str(root / "zeta"))
        self.assertIn("slot=%s" % (root / "zeta"), self.calls_text())

    def test_setup_defaults_write_config_schema(self):
        code, _, _ = self.ais(BLANK + "y\n")
        self.assertEqual(code, 0)
        self.assertEqual(self.config(), {"version": 1, "default": "personal", "accounts": {
            "personal": {"label": "Personal", "provider": "claude", "credDir": None},
            "work": {"label": "Work", "provider": "claude", "credDir": self.work}},
            "cross_account_ack": {}, "menu_privacy": False})
        self.assertEqual(stat.S_IMODE((self.ais_dir / "config.json").stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(self.ais_dir.stat().st_mode), 0o700)

    def test_setup_keeps_acks_and_privacy_of_existing_config(self):
        self.ais_dir.mkdir(parents=True)
        (self.ais_dir / "config.json").write_text(json.dumps(
            {"cross_account_ack": {"a->b": "2026-01-01"}, "menu_privacy": True}))
        code, out, err = self.ais(BLANK + "y\n")
        self.assertEqual(code, 0)
        self.assertIn("(replace)", out + err)
        self.assertEqual(self.config()["cross_account_ack"], {"a->b": "2026-01-01"})
        self.assertIs(self.config()["menu_privacy"], True)
        (self.ais_dir / "config.json").write_text("{nope")
        code, _, err = self.ais(BLANK + "y\n")
        self.assertEqual(code, 78)
        self.assertIn("config.json", err)

    def test_setup_logs_in_only_missing_accounts(self):
        os.environ["FAKE_CLAUDE_LOGGED_OUT_SLOT"] = self.work
        code, _, _ = self.ais(BLANK + "y\n")
        self.assertEqual(code, 0)
        self.assertEqual(self.calls_text(), (
            "claude auth status --json\nslot=<unset>\n"
            "claude auth status --json\nslot=%s\n"
            "claude auth login\nslot=%s\n" % (self.work, self.work)))
        os.environ["FAKE_CLAUDE_LOGIN_RC"] = "3"
        code, out, err = self.ais(BLANK + "y\n")
        self.assertEqual(code, 3)
        self.assertIn("ais login work", out + err)

    def test_setup_never_writes_inside_cred_dir(self):
        code, _, _ = self.ais(BLANK + "y\n")
        self.assertEqual(code, 0)
        d = self.home / ".claude-accounts" / "work"
        self.assertEqual(list(d.iterdir()), [])
        self.assertEqual(stat.S_IMODE(d.stat().st_mode), 0o700)
        self.assertEqual(stat.S_IMODE(d.parent.stat().st_mode), 0o700)

    def test_setup_path_line_only_when_needed(self):
        bin_dir = str(self.home / ".local" / "bin")
        os.environ["PATH"] = bin_dir + "/" + os.pathsep + os.environ["PATH"]
        _, out, _ = self.ais(BLANK + "y\n")
        self.assertNotIn(".local/bin", out)
        os.environ["PATH"] = os.environ["PATH"].replace(bin_dir + "/", "~/.local/bin")
        _, out, _ = self.ais(BLANK + "y\n")
        self.assertNotIn(PATH_LINE, out)
        os.environ["PATH"] = os.environ["PATH"].replace("~/.local/bin", "/usr/bin")
        _, out, _ = self.ais(BLANK + "y\n")
        self.assertIn(PATH_LINE, out)
        self.assertIn("~/.zshrc", out)
        self.assertNotIn("CLAUDE_SECURESTORAGE_CONFIG_DIR=", out.replace("slot=", ""))
        self.assertFalse((self.home / ".zshrc").exists())

    def test_setup_prints_shared_memory_statement(self):
        code, out, _ = self.ais(BLANK + "y\n")
        self.assertEqual(code, 0)
        self.assertIn(ClaudeProvider.shared_data_note, out)
        self.assertIn("every session", out)
        self.assertIn("not only on resume", out)

    def test_setup_dry_run(self):
        before = tree(self.home)
        code, out, _ = self.ais(BLANK, "--dry-run")
        self.assertEqual(code, 0)
        self.assertEqual(tree(self.home), before)
        self.assertEqual(self.calls_text(), "")
        self.assertIn('"credDir": null', out)
        self.assertIn("claude auth status --json", out)
        self.assertIn("%s=%s claude auth login" % (SLOT, self.work), out)
        self.assertIn(ClaudeProvider.shared_data_note, out)

    def test_setup_bad_input_exits_64(self):
        for stdin in ("Bad\n", "same\n\nsame\n", "\n\nwork\n\n/etc\n", "\n\nwork\n\nrel/dir\n"):
            code, _, err = self.ais(stdin + "y\n")
            self.assertEqual(code, 64, stdin)
            self.assertFalse(self.ais_dir.exists())

    def test_setup_unknown_state_prints_login_hint(self):
        os.environ["FAKE_CLAUDE_AUTH_RC"] = "1"
        os.environ["FAKE_SECURITY_RC"] = "1"
        os.environ["FAKE_SECURITY_ERR"] = "boom"
        for k in ("FAKE_CLAUDE_AUTH_RC", "FAKE_SECURITY_RC", "FAKE_SECURITY_ERR"):
            self.addCleanup(os.environ.pop, k, None)
        code, out, _ = self.ais(BLANK + "y\n")
        self.assertEqual(code, 0)
        self.assertIn("run `ais login work`", out)
        self.assertNotIn("auth login", self.calls_text())

    def test_setup_mkdir_failure_exits_73(self):
        with mock.patch("pathlib.Path.mkdir", side_effect=PermissionError("denied")):
            code, _, err = self.ais(BLANK + "y\n")
        self.assertEqual(code, 73)
        self.assertIn("denied", err)

    def test_setup_existing_cred_dir_is_left_alone(self):
        real = Path.mkdir

        def racing(path, *a, **k):  # the folder appears after the listing
            real(path, 0o755)
            raise FileExistsError(str(path))
        with mock.patch("pathlib.Path.mkdir", racing):
            code, _, _ = self.ais(BLANK + "y\n")
        self.assertEqual(code, 0)

    def test_setup_malformed_kept_keys_exit_78_writing_nothing(self):
        self.ais_dir.mkdir(parents=True)
        (self.ais_dir / "config.json").write_text('{"menu_privacy": "yes"}')
        code, _, err = self.ais(BLANK + "y\n")
        self.assertEqual(code, 78)
        self.assertIn("menu_privacy", err)
        self.assertEqual(tree(self.home), [".config", ".config/ais", ".config/ais/config.json"])

    def test_setup_billing_guard_after_write_prints_retry_hint(self):
        os.environ["ANTHROPIC_API_KEY"] = "x"
        self.addCleanup(os.environ.pop, "ANTHROPIC_API_KEY", None)
        os.environ["FAKE_CLAUDE_LOGGED_OUT_SLOT"] = self.work
        code, _, err = self.ais(BLANK + "y\n")
        self.assertEqual(code, 77)
        self.assertIn("ais login work", err)

    def test_setup_dry_run_prints_env_warnings(self):
        os.environ[CONFIG_DIR_ENV] = "/x"
        code, out, err = self.ais(BLANK, "--dry-run")
        self.assertEqual(code, 0)
        self.assertIn("Setup would create:", out)
        self.assertIn(CONFIG_DIR_ENV, err)

    def test_setup_non_ascii_digit_falls_to_path_and_exits_64(self):
        (self.home / ".claude-accounts" / "a").mkdir(parents=True)
        code, _, err = self.ais("\n\n\n\n\u00b2\ny\n")
        self.assertEqual(code, 64)
        self.assertNotIn("Traceback", err)

    def test_setup_skips_hidden_and_non_nfc_folders(self):
        root = self.home / ".claude-accounts"
        nfd = root / "cafe\u0301"
        (root / ".hidden").mkdir(parents=True)
        nfd.mkdir()
        (root / "ok").mkdir()
        code, out, err = self.ais(BLANK + "n\n")
        self.assertEqual(code, 65)
        self.assertIn("1) %s" % (root / "ok"), err)
        self.assertNotIn(".hidden", err.replace("skipping", ""))
        self.assertIn("skipping %s" % nfd, err)
        self.assertNotIn("2)", err)

    def test_setup_failed_config_write_removes_dirs_it_created(self):
        from ais.errors import AisError
        before = tree(self.home)
        with mock.patch("ais.store.Store.update_json", side_effect=AisError(73, "cannot write")):
            code, _, _ = self.ais(BLANK + "y\n")
        self.assertEqual(code, 73)
        self.assertFalse((self.home / ".claude-accounts").exists())
        self.assertFalse((self.home / ".claude-accounts" / "work").exists())
        self.assertNotIn(".claude-accounts", " ".join(tree(self.home)))
        self.assertLessEqual(set(tree(self.home)) - set(before), {".config", ".config/ais"})

    def test_setup_bad_cred_dir_message_is_about_the_answer(self):
        code, _, err = self.ais("\n\n\n\nrel/dir\ny\n")
        self.assertEqual(code, 64)
        self.assertIn("must be an absolute path", err)
        self.assertNotIn("config.json", err)

    def test_setup_dry_run_prints_each_warning_once(self):
        os.environ[CONFIG_DIR_ENV] = "/x"
        _, _, err = self.ais(BLANK, "--dry-run")
        self.assertEqual(err.count("removed inherited " + CONFIG_DIR_ENV), 1)

    def test_setup_second_mkdir_failure_removes_first_folder(self):
        real = Path.mkdir
        calls = []

        def flaky(path, *a, **k):
            calls.append(path)
            if len(calls) == 2:
                raise PermissionError("denied")
            real(path, *a, **k)
        with mock.patch("pathlib.Path.mkdir", flaky):
            code, _, _ = self.ais(BLANK + "y\n")
        self.assertEqual(code, 73)
        self.assertEqual(len(calls), 2)
        self.assertFalse((self.home / ".claude-accounts").exists())
