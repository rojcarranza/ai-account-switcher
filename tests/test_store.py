import json
import os
import stat
import unittest
from unittest import mock

from ais.errors import AisError
from ais.store import Store
from tests.helpers import TempHomeCase


def mode(p):
    return stat.S_IMODE(os.stat(str(p)).st_mode)


class StoreTest(TempHomeCase):
    def test_files_created_0600_dirs_0700(self):
        old = os.umask(0)
        self.addCleanup(os.umask, old)
        s = Store(self.home)
        s.update_json("state.json", lambda d: {"a": 1})
        s.log("switch", "a", "sid", "ok")
        with s.switch_mutex():
            pass
        with open(str(self.ais_dir / "ais.log"), "ab") as f:
            f.write(b"x" * (1024 * 1024))
        s.log("switch", "a", "sid", "ok")  # rotates to ais.log.1
        self.assertEqual(mode(self.ais_dir), 0o700)
        self.assertEqual(mode(self.home / ".config"), 0o700)
        for n in ("state.json", ".lock", "ais.log", "ais.log.1", "switch.lock"):
            self.assertEqual(mode(self.ais_dir / n), 0o600, n)

    def test_update_json_failure_leaves_original_and_exits_73(self):
        s = Store(self.home)
        s.update_json("state.json", lambda d: {"v": 1})
        path = self.ais_dir / "state.json"
        with mock.patch("ais.store._sync", side_effect=OSError("disk full")):
            with self.assertRaises(AisError) as cm:
                s.update_json("state.json", lambda d: {"v": 2})
        self.assertEqual(cm.exception.code, 73)
        self.assertIn(str(path), cm.exception.message)
        self.assertEqual(json.loads(path.read_text()), {"v": 1})
        self.assertEqual(sorted(p.name for p in self.ais_dir.iterdir()), [".lock", "state.json"])

    def test_update_json_cleans_temp_on_non_oserror(self):
        s = Store(self.home)
        with self.assertRaises(TypeError):
            s.update_json("state.json", lambda d: {"x": object()})
        self.assertEqual([p.name for p in self.ais_dir.iterdir()], [".lock"])

    def test_read_json_bad_content_exits_78_and_unreadable_73(self):
        s = Store(self.home)
        s.update_json("state.json", lambda d: {})
        path = self.ais_dir / "state.json"
        for text in ("{not json", "[1, 2]"):
            path.write_text(text)
            with self.assertRaises(AisError) as cm:
                s.read_json("state.json")
            self.assertEqual(cm.exception.code, 78)
            self.assertIn(str(path), cm.exception.message)
        with mock.patch("builtins.open", side_effect=PermissionError("denied")):
            with self.assertRaises(AisError) as cm:
                s.read_json("state.json")
        self.assertEqual(cm.exception.code, 73)
        self.assertIn(str(path), cm.exception.message)

    def test_log_line_has_no_args_field(self):
        s = Store(self.home)
        s.log("switch", "a", "sid", "ok", tool_seconds=1.5)
        rec = json.loads((self.ais_dir / "ais.log").read_text())
        self.assertEqual(list(rec), ["time", "command", "account", "session_id",
                                     "result", "tool_seconds", "e2e_seconds"])
        self.assertTrue(rec["time"].endswith("Z"))
        self.assertEqual((rec["tool_seconds"], rec["e2e_seconds"]), (1.5, None))

    def test_prune_state_drops_missing_transcripts(self):
        s = Store(self.home)
        s.update_json("state.json", lambda d: {
            "plugin": True,
            "sessions": {"/keep": {"account": "a"}, "/gone": {"account": "b"}}})
        s.prune_state(lambda p: p == "/keep")
        self.assertEqual(s.read_json("state.json"),
                         {"plugin": True, "sessions": {"/keep": {"account": "a"}}})
        self.assertEqual(s.read_json("missing.json"), {})


if __name__ == "__main__":
    unittest.main()
