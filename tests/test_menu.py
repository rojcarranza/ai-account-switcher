"""FR-4.8, FR-4.9, FR-4.11 to FR-4.17, FR-6.5, NFR-PERF: `ais menu render` (SwiftBar)."""
import calendar
import copy
import json
import os
import re
import subprocess
import sys
import time
import unicodedata
import base64
import struct
import zlib

from ais import menu
from tests.helpers import SRC
from tests.test_switch import OTHER, UUID, SwitchCase

AIS = "/opt/ais/ais"
SECOND = "55555555-5555-4555-8555-555555555555"
NOW = calendar.timegm((2026, 10, 16, 12, 0, 0))


def status(**over):
    d = {"accounts": [{"name": "personal", "label": "Personal", "credential_present": "yes",
                       "credential_source": "keychain", "credential_error": ""},
                      {"name": "work", "label": "Work", "credential_present": "unknown",
                       "credential_source": "keychain", "credential_error": "x"}],
         "session": None,
         "recent": [{"id": UUID, "folder": "/Users/x/proj", "title": "Main task", "last_used": "personal",
                     "open": False, "modified": "2026-10-16T10:00:00Z"},
                    {"id": OTHER, "folder": "/Users/x/other", "title": "Second", "last_used": None,
                     "open": True, "modified": "2026-10-16T09:00:00Z"}],
         "self_check": {"ok": True, "messages": []}}
    d.update(over)
    return d


class RenderTest(SwitchCase):
    def test_render_from_fixed_status(self):
        out = menu.render(status(), False, AIS, NOW).split("\n")
        self.assertEqual(out, [
            "| sfimage=gauge.medium",
            "---",
            "Personal | sfimage=person.crop.circle",
            "Sessions (1) | sfimage=list.bullet",
            "--Main task · 2 h ago",
            "----/Users/x/proj",
            "----Resume in Work | bash=%s param1=switch param2=--session param3=%s param4=work terminal=true sfimage=play.fill"
            % (AIS, UUID),
            "---",
            "Work · credential unknown | sfimage=person.crop.circle",
            "---",
            "Open Personal Desktop | bash=%s param1=desktop param2=personal terminal=false sfimage=desktopcomputer" % AIS,
            "Open Work Desktop | bash=%s param1=desktop param2=work terminal=false sfimage=desktopcomputer" % AIS,
            "Open Personal Terminal | bash=%s param1=run param2=personal terminal=true sfimage=terminal" % AIS,
            "Open Work Terminal | bash=%s param1=run param2=work terminal=true sfimage=terminal" % AIS,
        ])

    def test_render_bar_is_ais_without_sessions(self):
        self.assertEqual(menu.render(status(recent=[]), False, AIS).split("\n")[0], "| sfimage=gauge.medium")

    def test_sessions_with_unknown_owner_are_not_shown(self):
        s = status()
        s["recent"][0]["last_used"] = None
        s["recent"][1]["last_used"] = "ghost"  # an unconfigured owner is as unknown as none
        out = menu.render(s, False, AIS, NOW)
        for hidden in ("Other sessions", "Main task", "Second", "Resume", "Quit"):
            self.assertNotIn(hidden, out)

    def test_path_with_space_is_quoted_and_bad_path_fails(self):
        self.assertIn('bash="/a b/ais" param1=desktop', menu.render(status(), False, "/a b/ais"))
        for bad in ('/a"b/ais', "/a|b/ais"):
            with self.assertRaises(ValueError):
                menu.render(status(), False, bad)

    def test_malicious_title_and_folder_sanitized_not_in_action(self):
        s = status()
        s["recent"][0]["title"] = "x | bash=/bin/rm param1=-rf\n--Resume in Evil | bash=/bin/sh\x1b[2J"
        s["recent"][0]["folder"] = "/tmp/--a | terminal=true\r\n---"
        s["accounts"][0]["label"] = "Per|sonal\n"
        out = menu.render(s, False, AIS, NOW)
        lines = out.split("\n")
        for ln in lines:
            self.assertFalse(any(unicodedata.category(c).startswith("C") for c in ln), ln)
        # every " | " introduces one of our own actions: 1 resume, 2 desktop, 2 terminal,
        # or only a fixed icon (FR-4.22): 2 headers, 1 Sessions
        params = [ln.split(" | ")[1] for ln in lines if " | " in ln]
        icons = [p for p in params if re.fullmatch(r"sfimage=(person\.crop\.circle|list\.bullet)", p)]
        self.assertEqual(len(icons), 3)
        acts = [p.split()[0] for p in params if p not in icons]
        self.assertEqual(sorted(acts), ["bash=" + AIS] * 5)
        self.assertEqual(sum(1 for ln in lines if re.match(r"--[^-]", ln)), 1)
        self.assertEqual(lines[2], "Personal | sfimage=person.crop.circle")  # label "Per|sonal\n" cleaned in the header
        evil = [ln for ln in lines if "Evil" in ln]
        self.assertEqual(len(evil), 1)
        self.assertRegex(evil[0], r"^--x  bash=/bin/rm")  # one level, text kept inert
        self.assertEqual([ln for ln in lines if "/tmp" in ln], ["----/tmp/--a  terminal=true---"])

    def test_open_session_shows_disabled_quit_item(self):
        s = status()
        s["recent"][1]["last_used"] = "work"
        out = menu.render(s, False, AIS, NOW)
        self.assertIn("----Quit Claude in /Users/x/other to resume | disabled=true", out)
        self.assertNotIn(OTHER, out)

    def test_privacy_mode_hides_folders_and_titles(self):
        out = menu.render(status(), True, AIS, NOW)
        self.assertEqual(out.split("\n")[2:6], ["Personal | sfimage=person.crop.circle", "Work · credential unknown | sfimage=person.crop.circle", "---",
                                                "recent sessions: 2, open: 1"])
        for hidden in ("/Users/x", "Main task", "Resume", "Quit", UUID):
            self.assertNotIn(hidden, out)
        self.assertIn("Open Work Desktop | bash=%s param1=desktop param2=work terminal=false sfimage=desktopcomputer" % AIS, out)
        self.assertIn("Open Work Terminal | bash=%s param1=run param2=work terminal=true sfimage=terminal" % AIS, out)

    def test_label_leading_dashes_stripped(self):
        s = status()
        s["accounts"][0]["label"] = "--x"
        s["accounts"][1]["label"] = "---"
        out = menu.render(s, False, AIS, NOW).split("\n")
        self.assertEqual(out[2], "x | sfimage=person.crop.circle")
        self.assertIn("work · credential unknown | sfimage=person.crop.circle", out)
        self.assertTrue(any(ln.startswith("----Resume in work | bash=") for ln in out))

    def test_age_buckets(self):
        def ago(delta):
            return menu._ago(time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(NOW - delta)), NOW)
        self.assertEqual(ago(30), "just now")
        self.assertEqual(ago(-300), "just now")
        self.assertEqual(ago(59 * 60 + 59), "59 min ago")
        self.assertEqual(ago(47 * 3600 + 3599), "47 h ago")
        self.assertEqual(ago(49 * 3600), "2 d ago")
        self.assertIsNone(menu._ago(None, NOW))
        self.assertIsNone(menu._ago("yesterday", NOW))

    def test_short_folder_and_title(self):
        long = "a" * 60
        self.assertEqual(menu._short_folder("/Users/x/" + long), "/Users/…/" + long)
        self.assertEqual(menu._short_folder(os.path.expanduser("~") + "/dev/" + long), "~/…/" + long)
        self.assertEqual(menu._short_folder("/Users/x/proj"), "/Users/x/proj")
        self.assertEqual(menu._short_title("t" * 60), "t" * 49 + "…")
        self.assertEqual(menu._short_title("t" * 50), "t" * 50)

    def test_short_folder_with_nothing_to_elide_stays_whole(self):
        long = "a" * 60
        self.assertEqual(menu._short_folder("/" + long), "/" + long)
        self.assertEqual(menu._short_folder("/Users/" + long), "/Users/" + long)

    def test_dash_title_does_not_nest(self):
        s = status()
        s["recent"][0]["title"] = "--Evil"
        self.assertIn("--Evil · 2 h ago", menu.render(s, False, AIS, NOW).split("\n"))

    def test_ten_per_group_newest_first(self):
        s = status()
        s["recent"] = [{"id": "00000000-0000-4000-8000-%012d" % i, "folder": "/Users/x/p", "title": "T%d" % i,
                        "last_used": "personal", "open": False, "modified": "2026-10-16T10:00:00Z"}
                       for i in range(12)]
        lines = menu.render(s, False, AIS, NOW).split("\n")
        self.assertIn("Sessions (10) | sfimage=list.bullet", lines)
        items = [ln for ln in lines if ln.startswith("--T")]
        self.assertEqual(items, ["--T%d · 2 h ago" % i for i in range(10)])

    def test_run_refuses_to_spawn_after_kill_live(self):
        from ais import procs
        self.addCleanup(setattr, procs, "_STOPPED", False)
        procs.kill_live()
        rc, _, warn, _ = procs.run(["true"], 5)
        self.assertEqual((rc, warn), (None, "cannot run true: stopped"))

    def test_privacy_count_covers_the_5_recent_sessions(self):
        s = status()
        s["recent"] = [dict(s["recent"][0], open=False) for _ in range(8)]
        self.assertIn("\nrecent sessions: 5, open: 0\n", menu.render(s, True, AIS))

    def test_privacy_mode_counts_warnings_without_text(self):
        s = status(self_check={"ok": False, "messages": ["secret /Users/x", "b"]})
        out = menu.render(s, True, AIS)
        self.assertIn("\nwarnings: 2\n", out)
        self.assertNotIn("secret", out)

    def test_desktop_item_per_account_only_account_in_action(self):
        s = status()
        s["accounts"][1]["label"] = "Wo|rk\nx"
        lines = [ln for ln in menu.render(s, False, AIS).split("\n") if ln.startswith("Open ")]
        self.assertEqual(lines, ["Open Personal Desktop | bash=%s param1=desktop param2=personal terminal=false sfimage=desktopcomputer" % AIS,
                                 "Open Workx Desktop | bash=%s param1=desktop param2=work terminal=false sfimage=desktopcomputer" % AIS,
                                 "Open Personal Terminal | bash=%s param1=run param2=personal terminal=true sfimage=terminal" % AIS,
                                 "Open Workx Terminal | bash=%s param1=run param2=work terminal=true sfimage=terminal" % AIS])

    def test_invalid_session_id_or_account_name_fails(self):
        s = status()
        s["recent"][0]["id"] = "x y"
        with self.assertRaises(ValueError):
            menu.render(s, False, AIS)
        s = status()
        s["accounts"][0]["name"] = "Bad Name"
        with self.assertRaises(ValueError):
            menu.render(s, False, AIS)

    def test_self_check_messages_are_plain_lines(self):
        s = status(self_check={"ok": False, "messages": ["Claude Code 9 | bad"]})
        out = menu.render(s, False, AIS).split("\n")
        self.assertIn("Warning: Claude Code 9  bad", out)

    def test_warnings_are_separated_from_the_groups(self):
        s = status(self_check={"ok": False, "messages": ["w"]})
        out = menu.render(s, False, AIS, NOW).split("\n")
        i = out.index("Warning: w")
        self.assertEqual((out[i - 1], out[i + 1]), ("---", "---"))

    def test_sanitize(self):
        self.assertEqual(menu.sanitize("a|b\nc\r\x1b[0m‮d​"), "abc[0md")
        # input unchanged by copy semantic
        s = status()
        before = copy.deepcopy(s)
        menu.render(s, False, AIS)
        self.assertEqual(s, before)


def png_pixels(data):
    """(width, height, dpi x, dpi y, rows of RGBA tuples) of an 8-bit RGBA PNG with filter 0 rows."""
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    pos, chunks, idat = 8, {}, b""
    while pos < len(data):
        n, kind = struct.unpack(">I4s", data[pos:pos + 8])
        body = data[pos + 8:pos + 8 + n]
        assert zlib.crc32(kind + body) & 0xffffffff == struct.unpack(">I", data[pos + 8 + n:pos + 12 + n])[0]
        if kind == b"IDAT":
            idat += body
        chunks[kind] = body
        pos += 12 + n
    w, h, depth, ctype = struct.unpack(">IIBB", chunks[b"IHDR"][:10])
    assert (depth, ctype) == (8, 6)
    px, py, unit = struct.unpack(">IIB", chunks[b"pHYs"])
    raw = zlib.decompress(idat)
    rows = []
    for y in range(h):
        line = raw[y * (4 * w + 1):(y + 1) * (4 * w + 1)]
        assert line[0] == 0
        rows.append([tuple(line[1 + 4 * x:5 + 4 * x]) for x in range(w)])
    return w, h, (px, py, unit), rows


USAGE_T = (NOW - 2 * 3600) * 1000


def with_usage(personal=None, work=None, **over):
    s = status(**over)
    s["accounts"][0]["usage"] = personal
    s["accounts"][1]["usage"] = work
    return s


class UsageRenderTest(SwitchCase):
    """FR-4.20: drawn usage bars under each account header."""

    def bar(self, line):
        m = re.fullmatch(r"(.*) \| image=([A-Za-z0-9+/=]+) width=120 height=8", line)  # SwiftBar ignores the dpi
        self.assertIsNotNone(m, line)
        return m.group(1), png_pixels(base64.b64decode(m.group(2)))

    def test_bar_png_size_dpi_and_fill(self):
        w, h, dpi, rows = png_pixels(menu._bar_png(69))
        self.assertEqual((w, h), (240, 16))  # 120 x 8 points at 2x
        self.assertEqual(dpi, (5669, 5669, 1))  # 144 dpi
        mid = rows[8]
        self.assertEqual(mid[0], menu.BAR_BLUE)
        self.assertEqual(mid[165], menu.BAR_BLUE)  # round(240 * 0.69) = 166 filled
        self.assertEqual(mid[166], menu.BAR_TRACK)
        self.assertEqual(mid[239], menu.BAR_TRACK)

    def test_bar_is_a_rounded_capsule(self):
        _, _, _, rows = png_pixels(menu._bar_png(50))
        self.assertEqual(rows[0][0][3], 0)  # corners outside the round ends are transparent
        self.assertEqual(rows[15][239][3], 0)
        self.assertEqual(rows[0][120], menu.BAR_TRACK)  # straight edge in the middle
        self.assertEqual(rows[8][0], menu.BAR_BLUE)
        self.assertNotIn(rows[0][114], (menu.BAR_BLUE, menu.BAR_TRACK))  # fill's round end blends into the track
        self.assertEqual(rows[0][119], menu.BAR_TRACK)
        self.assertEqual(rows[8][119], menu.BAR_BLUE)
        self.assertEqual(rows[8][120], menu.BAR_TRACK)
        small = png_pixels(menu._bar_png(1))[3]  # 2 px of fill: the left cap, cut at the fill's width
        self.assertEqual(small[8][1], menu.BAR_BLUE)
        self.assertEqual(small[8][2], menu.BAR_TRACK)

    def test_bar_colour_by_value(self):
        for value, colour, filled in ((79, menu.BAR_BLUE, 190), (80, menu.BAR_ORANGE, 192),
                                      (99, menu.BAR_ORANGE, 238), (100, menu.BAR_RED, 240),
                                      (150, menu.BAR_RED, 240), (-5, None, 0), (None, None, 0), (0, None, 0)):
            with self.subTest(value=value):
                mid = png_pixels(menu._bar_png(value))[3][8]
                self.assertEqual(sum(1 for c in mid if c != menu.BAR_TRACK), filled)
                if colour:
                    self.assertEqual(mid[0], colour)

    def test_usage_lines_under_header(self):
        out = menu.render(with_usage(work={"t": USAGE_T, "fh": 69, "sd": 68.6}), False, AIS, NOW).split("\n")
        i = out.index("Work · credential unknown · updated 2 h ago | sfimage=person.crop.circle")
        self.assertEqual(self.bar(out[i + 1])[0], "5h  69%")
        self.assertEqual(self.bar(out[i + 2])[0], "week  69%")
        self.assertEqual(out[i + 3], "---")
        self.assertEqual(out[2:4], ["Personal | sfimage=person.crop.circle", "Sessions (1) | sfimage=list.bullet"])  # no usage: nothing

    def test_missing_value_shows_question_mark_and_empty_bar(self):
        out = menu.render(with_usage({"t": USAGE_T, "fh": None, "sd": 150}), False, AIS, NOW).split("\n")
        self.assertEqual(out[2], "Personal · updated 2 h ago | sfimage=person.crop.circle")
        text, (_, _, _, rows) = self.bar(out[3])
        self.assertEqual(text, "5h  ?")
        self.assertEqual(set(rows[8]), {menu.BAR_TRACK})
        self.assertEqual(self.bar(out[4])[0], "week  100%")

    def test_old_sample_shows_no_sample_line(self):
        old = (NOW - 24 * 3600 - 1) * 1000
        out = menu.render(with_usage({"t": old, "fh": 9, "sd": 9}), False, AIS, NOW).split("\n")
        self.assertEqual(out[2:5], ["Personal | sfimage=person.crop.circle", "usage: no sample in the last 24 h", "Sessions (1) | sfimage=list.bullet"])
        edge = menu.render(with_usage({"t": (NOW - 24 * 3600) * 1000, "fh": 9, "sd": 9}), False, AIS, NOW)
        self.assertIn("Personal · updated 24 h ago | sfimage=person.crop.circle", edge.split("\n"))

    def test_far_future_sample_time_does_not_break_the_menu(self):
        out = menu.render(with_usage({"t": 10 ** 22, "fh": 1, "sd": 2}), False, AIS, NOW).split("\n")
        self.assertEqual(out[2], "Personal | sfimage=person.crop.circle")  # no age for a time out of range
        self.assertEqual([self.bar(out[3])[0], self.bar(out[4])[0], out[5]], ["5h  1%", "week  2%", "Sessions (1) | sfimage=list.bullet"])

    def test_privacy_mode_shows_usage(self):
        out = menu.render(with_usage({"t": USAGE_T, "fh": 0, "sd": 73}), True, AIS, NOW).split("\n")
        self.assertEqual(out[2], "Personal · updated 2 h ago | sfimage=person.crop.circle")
        self.assertEqual([self.bar(out[3])[0], self.bar(out[4])[0], out[5]],
                         ["5h  0%", "week  73%", "Work · credential unknown | sfimage=person.crop.circle"])


class IconTest(SwitchCase):
    """FR-4.22: fixed SF Symbol names on headers, Sessions, Resume, Open Desktop and Open Terminal items."""

    def test_icons(self):
        lines = menu.render(status(), False, AIS, NOW).split("\n")
        for line in ("Personal | sfimage=person.crop.circle",
                     "Work · credential unknown | sfimage=person.crop.circle",
                     "Sessions (1) | sfimage=list.bullet",
                     "----Resume in Work | bash=%s param1=switch param2=--session param3=%s param4=work terminal=true"
                     " sfimage=play.fill" % (AIS, UUID),
                     "Open Work Desktop | bash=%s param1=desktop param2=work terminal=false sfimage=desktopcomputer"
                     % AIS,
                     "Open Work Terminal | bash=%s param1=run param2=work terminal=true sfimage=terminal" % AIS):
            with self.subTest(line=line):
                self.assertIn(line, lines)

    def test_privacy_headers_have_icons(self):
        lines = menu.render(status(), True, AIS, NOW).split("\n")
        self.assertIn("Personal | sfimage=person.crop.circle", lines)

    def test_menu_bar_title_is_an_icon_only(self):
        for st, privacy in ((status(), False), (status(), True), (status(recent=[]), False)):
            with self.subTest(privacy=privacy, recent=len(st["recent"])):
                self.assertEqual(menu.render(st, privacy, AIS, NOW).split("\n")[:2], ["| sfimage=gauge.medium", "---"])

    def test_untrusted_text_never_sets_an_icon(self):
        s = status()
        s["accounts"][0]["label"] = "x sfimage=trash"
        s["recent"][0]["title"] = "t | sfimage=trash"
        out = menu.render(s, False, AIS, NOW)
        self.assertNotIn("| sfimage=trash", out)
        self.assertIn("x sfimage=trash | sfimage=person.crop.circle", out.split("\n"))


class RenderProcessTest(SwitchCase):
    """`ais menu render` as SwiftBar runs it: a process, with a stdin pipe that is never closed."""

    def setUp(self):
        super().setUp()
        self.env(FAKE_CLAUDE_AUTH_RC="1")  # a call to `claude auth status` would show in the call log

    def files(self):
        return {n: (self.ais_dir / n).read_bytes() if (self.ais_dir / n).exists() else None
                for n in ("state.json", "config.json")}

    def startup(self):
        """Interpreter and import time, subtracted from the 5 s bound so a slow CI box does not flake."""
        t = time.monotonic()
        subprocess.run([sys.executable, "-m", "ais", "--version"], stdout=subprocess.DEVNULL, stdin=subprocess.DEVNULL,
                       env=dict(os.environ, PYTHONPATH=str(SRC), HOME=str(self.home)), check=True)
        return time.monotonic() - t

    def render(self, timeout=20, **env):
        e = dict(os.environ, PYTHONPATH=str(SRC), HOME=str(self.home), **env)
        t = time.monotonic()
        p = subprocess.Popen([sys.executable, "-m", "ais", "menu", "render"], stdin=subprocess.PIPE,
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE, encoding="utf-8", env=e,
                             cwd=str(self.home))
        try:
            out, err = p.communicate(timeout=timeout)  # stdin stays open: a read would hang
        finally:
            p.stdin.close()
        return p.returncode, out, err, time.monotonic() - t

    def test_render_end_to_end(self):
        self.last_used("work")
        self.env(FAKE_PGREP_OUT="")
        before = self.files()
        code, out, err, _ = self.render()
        self.assertEqual(code, 0, err)
        lines = out.split("\n")
        self.assertEqual(lines[:2], ["| sfimage=gauge.medium", "---"])
        self.assertIn("Personal | sfimage=person.crop.circle", lines)
        self.assertTrue(any(ln.startswith("--Main task · ") for ln in lines), out)
        self.assertIn("----~/proj", lines)
        self.assertTrue(any(ln.startswith("----Resume in Personal | bash=") and "param3=" + UUID in ln
                            for ln in lines), out)
        self.assertNotIn("auth", self.calls_text())
        self.assertEqual(before, self.files())
        self.assertFalse((self.ais_dir / "ais.log").exists())

    def test_menu_uses_30_recent_status_json_keeps_5(self):
        owned = {str(self.transcript): {"account": "personal", "at": "t"}}
        for i in range(7):  # 8 sessions with the setUp one: more than 5, fewer than the 10 per group
            p = self.add_session("00000000-0000-4000-8000-%012d" % i, self.proj, "T%d" % i, 1000 + i)
            owned[str(p)] = {"account": "personal", "at": "t"}
        (self.ais_dir / "state.json").write_text(json.dumps({"sessions": owned}))
        self.env(FAKE_PGREP_OUT="")
        code, out, err, _ = self.render()
        self.assertEqual(code, 0, err)
        lines = out.split("\n")
        i = lines.index("Sessions (8) | sfimage=list.bullet")
        self.assertEqual(len([ln for ln in lines[i:] if re.match(r"--[^-]", ln)]), 8, out)
        _, js, _ = self.ais("status", "--json")
        self.assertEqual(len(json.loads(js)["recent"]), 5)

    def test_render_never_reads_stdin(self):
        code, out, _, took = self.render(timeout=10)
        self.assertEqual(code, 0)
        self.assertLess(took, 8)
        self.assertTrue(out.startswith("| sfimage=gauge.medium\n"), out)

    def test_render_with_hung_lsof_finishes_in_5s(self):
        child = self.home / "lsof.child"
        self.env(FAKE_PGREP_OUT="123", FAKE_PS_OUT="123 claude", FAKE_LSOF_HANG="1",
                 FAKE_LSOF_CHILD_FILE=str(child))
        base = self.startup()
        code, out, _, took = self.render(timeout=15)
        self.assertEqual(code, 0)
        self.assertLess(took - base, 5.0)
        self.assertTrue(out.startswith("ais ⚠\n---\n"), out)
        self.assertNotIn("bash=", out)
        pid = int(child.read_text())
        time.sleep(0.3)
        with self.assertRaises(OSError):  # no child left behind
            os.kill(pid, 0)

    def test_render_deadline_kills_hung_keychain_check(self):
        child = self.home / "security.child"
        self.env(FAKE_PGREP_OUT="", FAKE_SECURITY_SLEEP="30", FAKE_SECURITY_CHILD_FILE=str(child))
        base = self.startup()
        code, out, _, took = self.render(timeout=15)  # no cache: the Keychain check hangs, so the 4.5 s deadline fires
        self.assertEqual(code, 0)
        self.assertGreater(took, 4.0)
        self.assertLess(took - base, 5.0)
        self.assertEqual(out, "ais ⚠\n---\nais: timed out after 4.5 s\n")
        self.assertNotIn("bash=", out)
        time.sleep(0.3)
        with self.assertRaises(OSError):
            os.kill(int(child.read_text()), 0)

    def test_failure_line_hides_details_in_privacy_mode(self):
        cfg = self.config()
        cfg["menu_privacy"] = True
        (self.ais_dir / "config.json").write_text(__import__("json").dumps(cfg))
        self.env(FAKE_PGREP_OUT="123", FAKE_PS_OUT="123 claude", FAKE_LSOF_RC="2")
        code, out, _, _ = self.render()
        self.assertEqual(code, 0)
        self.assertEqual(out, "ais ⚠\n---\nais: error (details hidden by menu_privacy; run ais status)\n")

    def test_deadline_removes_inflight_cache_temp(self):
        script = ("import sys\nfrom ais import store, cli\nimport time\n"
                  "store._sync = lambda fd: time.sleep(30)\nsys.exit(cli.main(['menu', 'render']))\n")
        self.env(FAKE_PGREP_OUT="")
        e = dict(os.environ, PYTHONPATH=str(SRC), HOME=str(self.home))
        p = subprocess.run([sys.executable, "-c", script], stdin=subprocess.PIPE, capture_output=True,
                           encoding="utf-8", env=e, cwd=str(self.home), timeout=20)
        self.assertEqual(p.stdout, "ais ⚠\n---\nais: timed out after 4.5 s\n", p.stderr)
        self.assertEqual([n.name for n in self.ais_dir.glob(".cache.json.*")], [])

    def test_malformed_config_is_ais_warning_not_traceback(self):
        (self.ais_dir / "config.json").write_text("{")
        code, out, err, _ = self.render()
        self.assertEqual(code, 0)
        self.assertTrue(out.startswith("ais ⚠\n---\n"), out)
        self.assertNotIn("Traceback", out + err)

    def test_menu_without_subcommand_is_usage_error(self):
        e = dict(os.environ, PYTHONPATH=str(SRC), HOME=str(self.home))
        p = subprocess.run([sys.executable, "-m", "ais", "menu"], capture_output=True, encoding="utf-8", env=e,
                           stdin=subprocess.DEVNULL)
        self.assertEqual(p.returncode, 64)

    def test_render_under_2s_with_5000_cached_transcripts(self):
        d = self.projects / "big"
        d.mkdir()
        for i in range(5000):
            (d / ("00000000-0000-4000-8000-%012d.jsonl" % i)).write_text(
                '{"type": "user", "message": {"content": "t%d"}, "cwd": "%s"}\n' % (i, self.proj))
        acct = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"  # NFR-PERF: 1,000 Desktop records for each of two accounts
        for folder in ("Claude", "Claude-ais-work"):
            data = self.home / "Library" / "Application Support" / folder
            sub = data / "claude-code-sessions" / acct / "cccccccc-cccc-4ccc-8ccc-cccccccccccc"
            sub.mkdir(parents=True)
            (data / "config.json").write_text(json.dumps({"lastKnownAccountUuid": acct}))
            for i in range(1000):
                sid = "00000000-0000-4000-8000-%012d" % i
                (sub / ("local_%s.json" % sid)).write_text(json.dumps(
                    {"cliSessionId": sid, "title": "D%d" % i, "lastActivityAt": 1792000000000 + i, "isArchived": False}))
        self.env(FAKE_PGREP_OUT="")
        code, _, err, _ = self.render(timeout=60)  # warms cache.json
        self.assertEqual(code, 0, err)
        code, out, _, took = self.render()
        self.assertEqual(code, 0)
        self.assertFalse(out.startswith("ais ⚠"), out)
        self.assertLess(took, 2.0)
