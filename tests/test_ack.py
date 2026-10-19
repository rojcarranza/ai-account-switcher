"""FR-2.8: resuming under a different account asks once per account pair, without holding a lock."""
import contextlib
import io
import os
import subprocess
import sys
from datetime import date
from unittest import mock

from ais import cli
from tests.helpers import SRC
from tests.test_switch import UUID, SwitchCase

TRY = """
import fcntl, sys
for name in ("switch.lock", ".lock"):
    f = open(sys.argv[1] + "/.config/ais/" + name, "a")
    try:
        fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
        print(name, "acquired")
    except OSError:
        print(name, "blocked")
"""


class AckTest(SwitchCase):
    def test_ack_per_pair_prompted_once(self):
        self.last_used("primary")
        code, _, err = self.ais("switch", stdin="Yes\n")
        self.assertEqual(code, 0, err)
        self.assertIn("full transcript", err)
        self.assertIn("Secondary", err)
        self.assertEqual(self.argv(), ["--resume", UUID])
        cfg = self.config()
        self.assertEqual(cfg["cross_account_ack"], {"primary->secondary": date.today().isoformat()})
        self.assertEqual((cfg["version"], cfg["default"], cfg["menu_privacy"]), (1, "primary", False))
        self.assertEqual(sorted(cfg["accounts"]), ["primary", "secondary"])
        # same pair again: no prompt (EOF would exit 65)
        self.last_used("primary")
        code, _, err = self.ais("switch", stdin="")
        self.assertEqual(code, 0, err)
        self.assertNotIn("full transcript", err)
        # the reverse pair is a new pair
        code, _, err = self.ais("switch", stdin="")
        self.assertEqual(code, 65)
        self.assertIn("full transcript", err)
        self.assertIn("Primary", err)

    def test_ack_keeps_config_readable(self):
        self.last_used("primary")
        code, _, err = self.ais("switch", stdin="y\n")
        self.assertEqual(code, 0, err)
        text = (self.ais_dir / "config.json").read_text()
        self.assertIn('\n  "accounts": {\n', text)  # indent=2, one key per line

    def test_ack_declined_65(self):
        self.last_used("primary")
        before = self.config()
        for answer in ("n\n", "", "yess\n", "\n"):
            code, _, err = self.ais("switch", "secondary", stdin=answer)
            self.assertEqual(code, 65, answer)
        self.assertIsNone(self.argv())
        self.assertEqual(self.config(), before)
        self.assertEqual(self.state()["sessions"][str(self.transcript)]["account"], "primary")
        self.assertEqual((self.snapshots(), self.log_lines()), ([], []))

    def test_ack_prompt_not_under_lock(self):
        self.last_used("primary")
        seen = []

        class Prompt(io.StringIO):
            def readline(inner, *a):
                env = dict(os.environ, PYTHONPATH=str(SRC))
                seen.append(subprocess.run([sys.executable, "-c", TRY, str(self.home)], env=env,
                                           stdout=subprocess.PIPE, universal_newlines=True, timeout=30).stdout)
                return "y\n"

        err = io.StringIO()
        with contextlib.redirect_stderr(err), contextlib.redirect_stdout(io.StringIO()), \
                mock.patch("sys.stdin", Prompt()):
            code = cli.main(["switch"])
        self.assertEqual(code, 0, err.getvalue())
        self.assertEqual(seen, ["switch.lock acquired\n.lock acquired\n"])
