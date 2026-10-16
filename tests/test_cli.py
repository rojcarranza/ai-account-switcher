import contextlib
import io
import os
import subprocess
import unittest

from ais import cli

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class CliTest(unittest.TestCase):
    def test_version(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = cli.main(["--version"])
        self.assertEqual(code, 0)
        self.assertEqual(out.getvalue(), "ais 0.1.0\n")

    def test_unknown_command_exits_64(self):
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(cli.main(["bogus"]), 64)

    def test_built_binary_exit_code(self):
        subprocess.run(["make", "build"], cwd=ROOT, check=True, timeout=60,
                       stdout=subprocess.DEVNULL)
        r = subprocess.run([os.path.join(ROOT, "dist", "ais"), "bogus"],
                           timeout=30, stderr=subprocess.DEVNULL)
        self.assertEqual(r.returncode, 64)


if __name__ == "__main__":
    unittest.main()
