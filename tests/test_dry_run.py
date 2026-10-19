"""FR-5.4: --dry-run changes nothing in the temp HOME (paths, modes, contents)."""
import hashlib
import json
import os
import shutil
import tempfile
from pathlib import Path

from tests.test_switch import SwitchCase


def tree_hash(root):
    h = hashlib.sha256()
    for p in sorted(Path(root).rglob("*")):
        st = p.lstat()
        h.update(("%s %o %d\n" % (p.relative_to(root), st.st_mode, st.st_mtime_ns)).encode())
        if p.is_file() and not p.is_symlink():
            h.update(p.read_bytes())
    return h.hexdigest()


class DryRunTest(SwitchCase):
    def test_dry_run_changes_nothing(self):
        plugin = self.home / "p.py"
        plugin.write_text("plugin")
        (self.ais_dir / "state.json").write_text(json.dumps({"menu_plugin": str(plugin)}))
        (self.ais_dir / "snapshots").mkdir()
        (self.home / "Applications" / "Claude.app").mkdir(parents=True)  # found on Linux CI too
        (self.home / "Applications" / "SwiftBar.app").mkdir()
        (self.home / "plugins").mkdir()
        self.env(FAKE_SWIFTBAR_DIR=str(self.home / "plugins"))
        log_dir = tempfile.mkdtemp()  # outside the hashed HOME
        self.addCleanup(shutil.rmtree, log_dir)
        log = Path(log_dir) / "calls.log"
        self.env(FAKE_CALL_LOG=str(log))
        for cmd in (["setup"], ["switch", "secondary"], ["run", "secondary"], ["login", "secondary"], ["desktop", "secondary"],
                    ["menu", "install"], ["menu", "uninstall"], ["uninstall"]):
            with self.subTest(cmd=cmd[0]):
                before = tree_hash(self.home)
                log.write_text("")
                code, _, err = self.ais(*(cmd + ["--dry-run"]), stdin="\n" * 6 if cmd == ["setup"] else "")
                self.assertEqual(code, 0, err)
                if cmd != ["setup"]:
                    self.assertNotIn("? [", err)  # dry-run asks nothing: no [y/N] or [1-n] prompt
                self.assertEqual(tree_hash(self.home), before, sorted(str(q) for q in self.home.rglob('*')))
                expected = {"desktop": "ps -x -ww -o pid=,args=\n"}.get(cmd[0], "")
                if cmd == ["menu", "install"]:
                    expected = "defaults read com.ameba.SwiftBar PluginDirectory\n"
                self.assertEqual(log.read_text(), expected)
                self.assertEqual(plugin.read_text(), "plugin")
