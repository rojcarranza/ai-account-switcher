import contextlib
import io
import os
import subprocess
import tempfile
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

    def test_no_args_prints_usage_exits_64(self):
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            code = cli.main([])
        self.assertEqual(code, 64)
        self.assertIn("usage: ais", err.getvalue())

    def test_built_binary_exit_code(self):
        # Build into a temp dir so a test run never overwrites the repo's dist/ais.
        with tempfile.TemporaryDirectory() as dist:
            subprocess.run(["make", "build", "DIST=" + dist], cwd=ROOT, check=True,
                           timeout=60, stdout=subprocess.DEVNULL)
            r = subprocess.run([os.path.join(dist, "ais"), "bogus"],
                               timeout=30, stderr=subprocess.DEVNULL)
        self.assertEqual(r.returncode, 64)


if __name__ == "__main__":
    unittest.main()
