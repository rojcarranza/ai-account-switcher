import os
import shutil
import unicodedata
from pathlib import Path
from unittest import mock

from ais.core import Cache
from ais.providers import claude
from ais.providers.claude import ClaudeProvider
from ais.store import Store
from tests.helpers import TESTS, TempHomeCase

A = "11111111-1111-4111-8111-111111111111"
B = "22222222-2222-4222-8222-222222222222"
C = "33333333-3333-4333-8333-333333333333"


class SessionsTest(TempHomeCase):
    def setUp(self):
        super().setUp()
        self.p = ClaudeProvider()
        self.projects = self.home / ".claude" / "projects"
        # fixtures hold @HOME@ so their cwd values point into the temp HOME
        for src in (TESTS / "fixtures" / "projects").rglob("*.jsonl"):
            dst = self.projects / src.relative_to(TESTS / "fixtures" / "projects")
            dst.parent.mkdir(parents=True, exist_ok=True)
            dst.write_text(src.read_text(encoding="utf-8").replace("@HOME@", str(self.home)),
                           encoding="utf-8")
        self.file_a = self.projects / "p1" / (A + ".jsonl")
        self.file_b = self.projects / "p2" / (B + ".jsonl")
        self.file_c = self.projects / "p3" / (C + ".jsonl")
        for f, t in ((self.file_a, 1000), (self.file_b, 2000), (self.file_c, 3000)):
            os.utime(str(f), (t, t))
        self.cache = Cache(Store(self.home))

    def test_newest_session_ignores_subagent_files(self):
        sub = self.projects / "p1" / A / "subagents" / "agent-1.jsonl"
        os.utime(str(sub), (9000, 9000))
        s = self.p.newest_session(self.home / "proj", self.cache)
        self.assertEqual(s.id, A)
        self.assertEqual(s.transcript, self.file_a)

    def test_cwd_taken_from_first_line_that_has_it(self):
        s = self.p.find_session(A, self.cache)
        self.assertEqual(s.folder, self.home / "proj")
        self.assertEqual(s.title, "Fix the login bug")
        self.assertEqual(s.modified, 1000)

    def test_newest_session_unicode_space_and_symlink_folder(self):
        (self.home / "café dir").mkdir()
        nfd = unicodedata.normalize("NFD", str(self.home / "café dir"))
        self.assertEqual(self.p.newest_session(Path(nfd), self.cache).id, B)
        link = self.home / "link"
        link.symlink_to(self.home / "café dir")
        self.assertEqual(self.p.newest_session(link, self.cache).id, B)

    def test_no_session_returns_none(self):
        self.assertIsNone(self.p.newest_session(self.home / "nothing", self.cache))
        shutil.rmtree(str(self.projects))
        self.assertIsNone(self.p.newest_session(self.home / "proj", self.cache))
        self.assertEqual(self.p.recent_sessions(5, self.cache), [])

    def test_recent_across_folders_sorted(self):
        self.assertEqual([s.id for s in self.p.recent_sessions(5, self.cache)], [C, B, A])
        self.assertEqual([s.id for s in self.p.recent_sessions(2, self.cache)], [C, B])

    def test_find_session_by_uuid(self):
        self.assertEqual(self.p.find_session(C, self.cache).title, "Other task")
        self.assertIsNone(self.p.find_session("44444444-4444-4444-8444-444444444444", self.cache))
        self.assertIsNone(self.p.find_session("not-a-uuid", self.cache))

    def test_cache_hit_skips_reading_file(self):
        self.p.find_session(A, self.cache)
        entry = Store(self.home).read_json("cache.json")["transcripts"][str(self.file_a)]
        self.assertEqual(entry["title"], "Fix the login bug")
        self.file_a.chmod(0)  # reading would now fail; stat (mtime, size) still works
        self.addCleanup(self.file_a.chmod, 0o600)
        s = self.p.find_session(A, Cache(Store(self.home)))
        self.assertEqual(s.title, "Fix the login bug")

    def _no_cwd_file(self):
        f = self.projects / "p4" / "44444444-4444-4444-8444-444444444444.jsonl"
        f.parent.mkdir()
        f.write_text('{"type": "last-prompt"}\n', encoding="utf-8")
        return f

    def test_no_cwd_file_is_cached_and_not_reread(self):
        self._no_cwd_file()
        self.p.recent_sessions(5, self.cache)
        with mock.patch("ais.providers.claude._read_transcript", wraps=claude._read_transcript) as rd:
            self.assertEqual(len(self.p.recent_sessions(5, Cache(Store(self.home)))), 3)
        rd.assert_not_called()

    def test_same_cache_reused_does_not_reparse(self):
        self.p.recent_sessions(5, self.cache)
        with mock.patch("ais.providers.claude._read_transcript", wraps=claude._read_transcript) as rd:
            self.p.recent_sessions(5, self.cache)
        rd.assert_not_called()

    def test_title_cut_to_60_characters(self):
        self.file_c.write_text('{"type": "user", "message": {"content": "%s"}, "cwd": "%s"}\n'
                               % ("x" * 100, self.home / "other"), encoding="utf-8")
        self.assertEqual(self.p.find_session(C, self.cache).title, "x" * 60)

    def test_warm_scan_does_not_rewrite_cache(self):
        self.p.recent_sessions(5, self.cache)
        warm = Cache(Store(self.home))
        with mock.patch.object(warm.store, "update_json") as upd:
            self.p.recent_sessions(5, warm)
        upd.assert_not_called()
