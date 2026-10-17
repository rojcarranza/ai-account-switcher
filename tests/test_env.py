import contextlib
import io
import os
import tempfile
import unittest
from pathlib import Path

from ais.errors import AisError
from ais.guards import print_warnings, refuse_on_risks, safe_path


class GuardsTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name).resolve()
        self.root = self.tmp / "roj"
        self.root.mkdir()

    def test_risks_refused_77_names_setting(self):
        with self.assertRaises(AisError) as cm:
            refuse_on_risks(["ANTHROPIC_API_KEY is set", "second"], False)
        self.assertEqual(cm.exception.code, 77)
        self.assertEqual(cm.exception.message,
                         "ANTHROPIC_API_KEY is set; refusing to start claude "
                         "(pass --allow-api-key to override)")

    def test_allow_api_key_bypasses(self):
        self.assertIsNone(refuse_on_risks(["ANTHROPIC_API_KEY is set"], True))
        self.assertIsNone(refuse_on_risks([], False))

    def test_symlink_escape_rejected(self):
        outside = self.tmp / "outside"
        outside.mkdir()
        os.symlink(str(outside), str(self.root / "link"))
        with self.assertRaises(AisError) as cm:
            safe_path(self.root / "link" / "x", [self.root])
        self.assertEqual(cm.exception.code, 64)
        self.assertIn("is outside the allowed folders", cm.exception.message)

    def test_sibling_prefix_rejected(self):
        sibling = self.tmp / "ro"
        sibling.mkdir()
        with self.assertRaises(AisError) as cm:
            safe_path(self.root, [sibling])
        self.assertEqual(cm.exception.code, 64)

    def test_path_inside_root_accepted(self):
        (self.root / "a").mkdir()
        self.assertEqual(safe_path(self.root / "a" / "new.txt", [self.root]),
                         self.root / "a" / "new.txt")
        self.assertEqual(safe_path(self.root, [self.root]), self.root)

    def test_print_warnings(self):
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            print_warnings(["one", "two"])
        self.assertEqual(err.getvalue(), "ais: warning: one\nais: warning: two\n")
