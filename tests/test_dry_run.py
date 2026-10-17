"""FR-5.4: --dry-run changes nothing in the temp HOME (paths, modes, contents)."""
import hashlib
import json
import os
from pathlib import Path

from tests.test_switch import SwitchCase


def tree_hash(root):
    h = hashlib.sha256()
    for p in sorted(Path(root).rglob("*")):
        st = p.lstat()
        h.update(("%s %o\n" % (p.relative_to(root), st.st_mode)).encode())
        if p.is_file() and not p.is_symlink():
            h.update(p.read_bytes())
    return h.hexdigest()


class DryRunTest(SwitchCase):
    def test_dry_run_changes_nothing(self):
        (self.ais_dir / "state.json").write_text(json.dumps({"menu_plugin": str(self.home / "p.py")}))
        (self.ais_dir / "snapshots").mkdir()
        for cmd in (["setup"], ["switch", "work"], ["run", "work"], ["login", "work"], ["uninstall"]):
            with self.subTest(cmd=cmd[0]):
                before = tree_hash(self.home)
                code, _, err = self.ais(*(cmd + ["--dry-run"]), stdin="\n" * 6)
                self.assertEqual(code, 0, err)
                self.assertEqual(tree_hash(self.home), before, sorted(str(q) for q in self.home.rglob('*')))
