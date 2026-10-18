"""FR-4.19, FR-4.21: the menu reads Claude Desktop's session records (ADR-0009), read only."""
import json
import os
import subprocess
import sys
import time
from pathlib import Path

from ais import cli, core
from ais.providers import claude
from ais.providers.claude import ClaudeProvider
from unittest import mock
from tests.helpers import SRC
from tests.test_switch import OTHER, UUID, MISSING, SwitchCase

ACCT = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
OLD_ACCT = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
ORG = "cccccccc-cccc-4ccc-8ccc-cccccccccccc"
S1 = "11111111-1111-4111-8111-111111111111"
S2 = "22222222-2222-4222-8222-222222222222"


def record(cli_id, title="Fixture task one", at=1792000000000, **extra):
    d = {"sessionId": "local_" + cli_id, "cliSessionId": cli_id, "title": title, "cwd": "/Users/x/proj",
         "lastActivityAt": at, "isArchived": False, "createdAt": 1791990000000}
    d.update(extra)
    return d


class DesktopFixture(SwitchCase):
    def folder(self, name="Claude"):
        return self.home / "Library" / "Application Support" / name

    def desktop(self, name="Claude", acct=ACCT, config=True):
        d = self.folder(name)
        d.mkdir(parents=True, exist_ok=True)
        if config:
            (d / "config.json").write_text(json.dumps({"lastKnownAccountUuid": acct, "theme": "dark"}))
        return d

    def put(self, data_dir, rec, acct=ACCT, org=ORG, fname=None, raw=None):
        d = data_dir / "claude-code-sessions" / acct / org
        d.mkdir(parents=True, exist_ok=True)
        p = d / (fname or "local_%s.json" % (rec["cliSessionId"] if isinstance(rec, dict) else "x"))
        p.write_text(raw if raw is not None else json.dumps(rec))
        return p

    def records(self, data_dir):
        return ClaudeProvider().desktop_records(data_dir, self.home)


class RecordsTest(DesktopFixture):
    def test_record_read(self):
        d = self.desktop()
        self.put(d, record(S1))
        self.assertEqual(self.records(d), {S1: ("Fixture task one", 1792000000000)})

    def test_none_means_default_folder(self):
        self.put(self.desktop(), record(S1))
        self.assertEqual(self.records(None), {S1: ("Fixture task one", 1792000000000)})

    def test_archived_skipped_only_when_true(self):
        d = self.desktop()
        self.put(d, record(S1, isArchived=True))
        self.put(d, record(S2, isArchived="yes"))
        self.assertEqual(list(self.records(d)), [S2])

    def test_oversized_record_skipped(self):
        d = self.desktop()
        self.put(d, record(S1, pad="x" * (1024 * 1024)))
        self.assertEqual(self.records(d), {})

    def test_other_account_folder_skipped(self):
        d = self.desktop()
        self.put(d, record(S1), acct=OLD_ACCT)
        self.assertEqual(self.records(d), {})

    def test_malformed_and_non_dict_skipped(self):
        d = self.desktop()
        self.put(d, None, fname="local_a.json", raw="{nope")
        self.put(d, None, fname="local_b.json", raw="[1, 2]")
        (d / "claude-code-sessions" / ACCT / ORG / "local_c.json").write_bytes(b"\xff\xfe")
        self.put(d, record(S1, cliSessionId=5), fname="local_d.json")
        self.put(d, record(S2))
        self.assertEqual(list(self.records(d)), [S2])

    def test_missing_or_bad_config_gives_nothing(self):
        d = self.desktop(config=False)
        self.put(d, record(S1))
        self.assertEqual(self.records(d), {})
        for bad in ("../x", 5, None, "", ACCT.upper() + "x"):
            with self.subTest(bad=bad):
                (d / "config.json").write_text(json.dumps({"lastKnownAccountUuid": bad}))
                self.assertEqual(self.records(d), {})
        (d / "config.json").write_text("not json")
        self.assertEqual(self.records(d), {})
        self.assertEqual(self.records(self.folder("Nope")), {})

    def test_bad_title_and_time_defaults(self):
        d = self.desktop()
        self.put(d, record(S1, title=7, at=True))
        self.put(d, record(S2, at="soon"))
        self.assertEqual(self.records(d), {S1: ("", 0), S2: ("Fixture task one", 0)})

    def test_duplicate_session_keeps_newer(self):
        d = self.desktop()
        a = self.put(d, record(S1, title="Newer", at=200), fname="local_a.json")
        b = self.put(d, record(S1, title="Older", at=100), org="dddddddd-dddd-4ddd-8ddd-dddddddddddd")
        os.utime(str(a), (2000, 2000))  # read first: "last one wins" would keep Older
        os.utime(str(b), (1000, 1000))
        self.assertEqual(self.records(d), {S1: ("Newer", 200)})

    def test_deeply_nested_json_skipped(self):
        d = self.desktop()
        self.put(d, None, fname="local_deep.json", raw="[" * 200000)
        self.put(d, record(S1))
        self.assertEqual(list(self.records(d)), [S1])
        (d / "config.json").write_text("[" * 200000)
        self.assertEqual(self.records(d), {})

    def test_fifo_skipped_without_hanging(self):
        d = self.desktop()
        sub = d / "claude-code-sessions" / ACCT / ORG
        sub.mkdir(parents=True)
        os.mkfifo(str(sub / "local_f.json"))
        self.put(d, record(S1))
        self.assertEqual(list(self.records(d)), [S1])

    def test_symlinked_data_folder_or_config_gives_nothing(self):
        outside = self.home / "outside"
        outside.mkdir()
        (outside / "config.json").write_text(json.dumps({"lastKnownAccountUuid": ACCT}))
        self.put(outside, record(S1))
        sup = self.folder().parent
        sup.mkdir(parents=True)
        os.symlink(str(outside), str(self.folder()))
        self.assertEqual(self.records(None), {})
        os.unlink(str(self.folder()))
        d = self.desktop(config=False)
        os.symlink(str(outside / "config.json"), str(d / "config.json"))
        self.put(d, record(S1))
        self.assertEqual(self.records(d), {})

    def test_cap_keeps_newest_files(self):
        d = self.desktop()
        for i, name in enumerate("dcba"):  # path order (a, b first) is the reverse of age order
            p = self.put(d, record("00000000-0000-4000-8000-00000000000%d" % i), fname="local_%s.json" % name)
            os.utime(str(p), (2000 - i, 2000 - i))
        with mock.patch.object(claude, "DESKTOP_MAX_FILES", 2):
            self.assertEqual(sorted(self.records(d)), ["00000000-0000-4000-8000-000000000000",
                                                       "00000000-0000-4000-8000-000000000001"])

    def test_symlink_out_skipped(self):
        d = self.desktop()
        outside = self.home / "outside.json"
        outside.write_text(json.dumps(record(S1)))
        sub = d / "claude-code-sessions" / ACCT / ORG
        sub.mkdir(parents=True)
        os.symlink(str(outside), str(sub / "local_link.json"))
        self.assertEqual(self.records(d), {})

    def test_at_most_1000_files(self):
        d = self.desktop()
        sub = d / "claude-code-sessions" / ACCT / ORG
        sub.mkdir(parents=True)
        for i in range(1003):
            (sub / ("local_%04d.json" % i)).write_text(json.dumps(record("00000000-0000-4000-8000-%012d" % i)))
        self.assertEqual(len(self.records(d)), 1000)


def usage_file(data_dir, samples, version=2, raw=None):
    p = data_dir / "plan-usage-history.json"
    p.write_text(raw if raw is not None else json.dumps({"version": version, "samples": samples}))
    return p


def sample(t, fh=10, sd=20, **u):
    u.update({"fh": fh, "sd": sd})
    return {"t": t, "org": ORG, "u": {k: v for k, v in u.items() if v is not MISSING_KEY}}


MISSING_KEY = object()


class UsageTest(DesktopFixture):
    """FR-4.20: the newest usage sample Desktop saved, read only."""

    def usage(self, data_dir):
        return ClaudeProvider().desktop_usage(data_dir, self.home)

    def test_newest_sample_by_t(self):
        d = self.desktop("Claude-Work")
        usage_file(d, [sample(100, 1, 2), sample(300, 69, 68), sample(200, 5, 6)])
        self.assertEqual(self.usage(d), {"t": 300, "fh": 69, "sd": 68})

    def test_none_means_default_folder(self):
        usage_file(self.desktop(), [sample(100, 0, 73)])
        self.assertEqual(self.usage(None), {"t": 100, "fh": 0, "sd": 73})

    def test_missing_or_bad_values_are_none(self):
        d = self.desktop()
        usage_file(d, [sample(100, fh=MISSING_KEY, sd=True)])
        self.assertEqual(self.usage(d), {"t": 100, "fh": None, "sd": None})
        usage_file(d, [sample(100, fh="9", sd=68.6)])
        self.assertEqual(self.usage(d), {"t": 100, "fh": None, "sd": 68.6})

    def test_bad_samples_skipped(self):
        d = self.desktop()
        usage_file(d, [sample(900, 1, 1, ), "x", {"t": True, "u": {}}, {"t": 999}, {"t": 950, "u": [1]},
                       sample("1000", 2, 2)])
        self.assertEqual(self.usage(d), {"t": 900, "fh": 1, "sd": 1})

    def test_missing_or_unexpected_file_gives_none(self):
        d = self.desktop()
        self.assertIsNone(self.usage(d))
        for raw in ("{nope", "[1]", json.dumps({"version": 3, "samples": [sample(1)]}),
                    json.dumps({"version": 2, "samples": {}}), json.dumps({"version": 2, "samples": []}),
                    "[" * 200000):
            with self.subTest(raw=raw[:40]):
                usage_file(d, None, raw=raw)
                self.assertIsNone(self.usage(d))
        self.assertIsNone(self.usage(self.folder("Nope")))

    def test_size_cap_is_2_mb(self):
        d = self.desktop()
        p = usage_file(d, [sample(100)] + [sample(1, pad="x" * 1000)] * 1400)  # about 1.4 MB: read
        self.assertLess(p.stat().st_size, 2 * 1024 * 1024)
        self.assertEqual(self.usage(d)["t"], 100)
        usage_file(d, [sample(100)] + [sample(1, pad="x" * 1000)] * 2200)
        self.assertIsNone(self.usage(d))

    def test_symlink_out_or_fifo_gives_none(self):
        d = self.desktop()
        outside = self.home / "outside.json"
        outside.write_text(json.dumps({"version": 2, "samples": [sample(1)]}))
        os.symlink(str(outside), str(d / "plan-usage-history.json"))
        self.assertIsNone(self.usage(d))
        os.unlink(str(d / "plan-usage-history.json"))
        os.mkfifo(str(d / "plan-usage-history.json"))
        self.assertIsNone(self.usage(d))


class StatusTest(DesktopFixture):
    def setUp(self):
        super().setUp()
        self.env(FAKE_PGREP_OUT="")
        self.work_dir = self.folder("Claude-Work")
        self.write_config({"work": {"label": "Work", "provider": "claude", "credDir": self.work,
                                    "desktop_data_dir": str(self.work_dir)}})

    def status(self, desktop=True):
        ctx = cli._context(time.monotonic())
        return core.gather_status(ctx, True, [], core.MENU_RECENT, desktop=desktop)

    def session(self, st, sid=UUID):
        return next(s for s in st["recent"] if s["id"] == sid)

    def test_desktop_title_and_owner_fill_unknown(self):
        self.put(self.desktop("Claude-Work", OLD_ACCT), record(UUID, title="Desktop title"), acct=OLD_ACCT)
        s = self.session(self.status())
        self.assertEqual((s["title"], s["last_used"]), ("Desktop title", "work"))

    def test_status_without_desktop_unchanged(self):
        self.put(self.desktop("Claude-Work", OLD_ACCT), record(UUID, title="Desktop title"), acct=OLD_ACCT)
        s = self.session(self.status(desktop=False))
        self.assertEqual((s["title"], s["last_used"]), ("Main task", None))
        code, out, _ = self.ais("status", "--json")
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)["recent"][0]["title"], "Main task")

    def test_state_owner_beats_desktop_but_title_is_newest(self):
        self.last_used("personal")
        self.put(self.desktop("Claude-Work", OLD_ACCT), record(UUID, title="Work title"), acct=OLD_ACCT)
        s = self.session(self.status())
        self.assertEqual((s["title"], s["last_used"]), ("Work title", "personal"))

    def test_newer_activity_wins_across_accounts(self):
        self.put(self.desktop("Claude", ACCT), record(UUID, title="Personal title", at=100))
        self.put(self.desktop("Claude-Work", OLD_ACCT), record(UUID, title="Work title", at=200), acct=OLD_ACCT)
        s = self.session(self.status())
        self.assertEqual((s["title"], s["last_used"]), ("Work title", "work"))
        self.put(self.folder(), record(UUID, title="Personal newest", at=300))
        s = self.session(self.status())
        self.assertEqual((s["title"], s["last_used"]), ("Personal newest", "personal"))

    def test_blank_desktop_title_keeps_transcript_title(self):
        self.put(self.desktop(), record(UUID, title="   "))
        self.assertEqual(self.session(self.status())["title"], "Main task")

    def test_empty_desktop_title_keeps_transcript_title(self):
        self.put(self.desktop(), record(UUID, title=""))
        s = self.session(self.status())
        self.assertEqual((s["title"], s["last_used"]), ("Main task", "personal"))

    def test_record_without_transcript_is_ignored(self):
        self.put(self.desktop(), record(MISSING))
        st = self.status()
        self.assertEqual([s["id"] for s in st["recent"]], [UUID])

    def test_usage_per_account(self):
        usage_file(self.desktop("Claude-Work", OLD_ACCT), [sample(100, 69, 68)])
        st = self.status()
        self.assertEqual([a["usage"] for a in st["accounts"]], [None, {"t": 100, "fh": 69, "sd": 68}])
        self.assertNotIn("usage", self.status(desktop=False)["accounts"][1])

    def test_render_end_to_end(self):
        self.put(self.desktop("Claude-Work", OLD_ACCT), record(UUID, title="Desktop title"), acct=OLD_ACCT)
        p = subprocess.run([sys.executable, "-m", "ais", "menu", "render"], stdin=subprocess.DEVNULL,
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True, cwd=str(self.home),
                           env=dict(os.environ, PYTHONPATH=str(SRC), HOME=str(self.home)), timeout=30)
        self.assertEqual(p.returncode, 0, p.stderr)
        lines = p.stdout.split("\n")
        self.assertTrue(any(ln.startswith("--Desktop title · ") for ln in lines), p.stdout)
        self.assertNotIn("Other sessions (account unknown) | sfimage=list.bullet", lines)
