import os
import io
import uuid
from contextlib import redirect_stderr
from pathlib import Path
from unittest import mock

from ais import store as store_mod
from ais.providers.base import Session
from ais.providers.claude import ClaudeProvider
from ais.store import Store
from tests.helpers import TempHomeCase

BASE = 1_800_000_000.0  # injected clock; real time never matters


class SnapshotTest(TempHomeCase):
    def setUp(self):
        super().setUp()
        self.sid = str(uuid.uuid4())
        proj = self.home / ".claude" / "projects" / "p"
        proj.mkdir(parents=True)
        self.transcript = proj / (self.sid + ".jsonl")
        self.transcript.write_text("{}\n")
        self.store = Store(self.home)
        self.log = self.home / "calls.log"
        os.environ["FAKE_CALL_LOG"] = str(self.log)
        self.addCleanup(os.environ.pop, "FAKE_CALL_LOG", None)
        self.addCleanup(os.environ.pop, "FAKE_CP_FAIL", None)

    def snap(self, i=0, paths=None):
        return self.store.snapshot(paths or [self.transcript], self.sid, lambda: BASE + i)

    def entries(self):
        return sorted(p.name for p in (self.ais_dir / "snapshots").iterdir())

    def test_snapshot_clone_and_caps(self):
        target = self.snap()
        self.assertIn("cp -c -R " + str(self.transcript), self.log.read_text())
        self.assertEqual((target / self.transcript.name).read_text(), "{}\n")
        for i in range(1, 21):
            self.snap(i)
        names = self.entries()
        self.assertEqual(len(names), 20)
        self.assertNotIn(target.name, names)  # oldest went
        # an entry older than 30 days goes on the next snapshot
        old = self.ais_dir / "snapshots" / "20200101T000000Z-x"
        old.mkdir()
        self.snap(21)
        self.assertFalse(old.exists())
        # total size cap: keep the newest, drop oldest first
        with mock.patch.object(store_mod, "SNAPSHOT_MAX_BYTES", 5):
            last = self.snap(22)
        self.assertEqual(self.entries(), [last.name])

    def test_oversize_single_snapshot_kept(self):
        with mock.patch.object(store_mod, "SNAPSHOT_MAX_BYTES", 1), redirect_stderr(io.StringIO()) as err:
            t = self.snap()
        self.assertTrue(t.is_dir())
        self.assertIn("warning", err.getvalue())

    def test_same_second_gets_suffix(self):
        a, b = self.snap(), self.snap()
        self.assertNotEqual(a, b)
        self.assertTrue(b.is_dir())

    def test_clone_failure_falls_back_to_plain_copy(self):
        os.environ["FAKE_CP_FAIL"] = "1"
        t = self.snap()
        self.assertEqual((t / self.transcript.name).read_text(), "{}\n")

    def test_clone_failure_no_space_warns_and_returns_none(self):
        os.environ["FAKE_CP_FAIL"] = "1"
        with mock.patch("shutil.disk_usage", return_value=mock.Mock(free=0)), \
                redirect_stderr(io.StringIO()) as err:
            t = self.snap()
        self.assertIsNone(t)
        self.assertIn("ais: warning: not enough free space for a snapshot; continuing without one",
                      err.getvalue())
        self.assertEqual(self.entries(), [])

    def test_snapshot_paths_includes_dir_only_when_present(self):
        s = Session(self.sid, self.home, self.transcript, "", 0.0)
        p = ClaudeProvider()
        self.assertEqual(p.snapshot_paths(s), [self.transcript])
        d = self.transcript.with_suffix("")
        d.mkdir()
        self.assertEqual(p.snapshot_paths(s), [self.transcript, d])


class SnapshotFixTest(SnapshotTest):
    def sub_with_link(self):
        outside = self.home / "outside"
        outside.mkdir()
        (outside / "secret").write_text("s")
        d = self.transcript.with_suffix("")
        d.mkdir()
        (d / "a.jsonl").write_text("x")
        os.symlink(str(outside), str(d / "link"))
        return d

    def test_plain_copy_keeps_symlinks_as_links(self):
        os.environ["FAKE_CP_FAIL"] = "1"
        d = self.sub_with_link()
        t = self.snap(paths=[self.transcript, d])
        self.assertTrue(os.path.islink(str(t / d.name / "link")))

    def test_prune_ignores_foreign_entries(self):
        notes = self.ais_dir / "snapshots" / "notes"
        notes.mkdir(parents=True)
        os.utime(str(notes), (1, 1))
        for i in range(21):
            self.snap(i)
        self.assertTrue(notes.is_dir())
        self.assertEqual(len(self.entries()), 21)  # notes + 20 snapshots

    def test_modes_0600_0700_on_both_paths(self):
        d = self.transcript.with_suffix("")
        d.mkdir()
        (d / "a.jsonl").write_text("x")
        for p in (self.transcript, d / "a.jsonl"):
            os.chmod(str(p), 0o644)
        os.chmod(str(d), 0o755)
        for fail in (None, "1"):
            if fail:
                os.environ["FAKE_CP_FAIL"] = fail
            t = self.snap(1 if fail else 0, paths=[self.transcript, d])
            for _, dirs, files in os.walk(str(t)):
                pass
            modes = {}
            for root, dirs, files in os.walk(str(t)):
                for n in dirs + files:
                    q = os.path.join(root, n)
                    modes[q] = os.stat(q).st_mode & 0o777
            self.assertTrue(modes)
            for q, m in modes.items():
                self.assertEqual(m, 0o700 if os.path.isdir(q) else 0o600, q)

    def test_bad_session_id_64(self):
        from ais.errors import AisError
        for bad in ("a/b", "..", ".", "a\0b", ""):
            with self.assertRaises(AisError) as cm:
                self.store.snapshot([self.transcript], bad)
            self.assertEqual(cm.exception.code, 64)
        self.assertFalse((self.ais_dir / "snapshots").exists())
