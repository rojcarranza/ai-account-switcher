"""FR-4.8, FR-4.9, FR-4.11 to FR-4.14, FR-6.5, NFR-PERF: `ais menu render` (SwiftBar)."""
import calendar
import copy
import json
import os
import re
import subprocess
import sys
import time
import unicodedata

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
            "Personal",
            "---",
            "✓ Personal",
            "Sessions (1)",
            "--Main task · 2 h ago",
            "----/Users/x/proj",
            "----Resume in Work | bash=%s param1=switch param2=--session param3=%s param4=work terminal=true"
            % (AIS, UUID),
            "---",
            "Work · credential unknown",
            "---",
            "Other sessions (account unknown)",
            "--Second · open",
            "----/Users/x/other",
            "----Quit Claude in /Users/x/other to resume | disabled=true",
            "---",
            "Open Personal Desktop | bash=%s param1=desktop param2=personal terminal=false" % AIS,
            "Open Work Desktop | bash=%s param1=desktop param2=work terminal=false" % AIS,
        ])

    def test_render_bar_is_ais_without_sessions(self):
        self.assertEqual(menu.render(status(recent=[]), False, AIS).split("\n")[0], "ais")

    def test_unknown_last_used_offers_every_account(self):
        s = status()
        s["recent"][0]["last_used"] = None
        out = menu.render(s, False, AIS)
        self.assertIn("Resume in Personal | bash=", out)
        self.assertIn("Resume in Work | bash=", out)

    def test_path_with_space_is_quoted_and_bad_path_fails(self):
        self.assertIn('bash="/a b/ais" param1=desktop', menu.render(status(), False, "/a b/ais"))
        for bad in ('/a"b/ais', "/a|b/ais"):
            with self.assertRaises(ValueError):
                menu.render(status(), False, bad)

    def test_malicious_title_and_folder_sanitized_not_in_action(self):
        s = status()
        s["recent"][0]["title"] = "x | bash=/bin/rm param1=-rf\n--Resume in Evil | bash=/bin/sh\x1b[2J"
        s["recent"][0]["folder"] = "/tmp/--a | terminal=true\r\n---"
        s["recent"][0]["last_used"] = None
        s["accounts"][0]["label"] = "Per|sonal\n"
        out = menu.render(s, False, AIS, NOW)
        lines = out.split("\n")
        for ln in lines:
            self.assertFalse(any(unicodedata.category(c).startswith("C") for c in ln), ln)
        # every " | " introduces one of our own actions: 2 resume (unknown last_used), 2 desktop, 1 quit
        acts = [ln.split(" | ")[1].split()[0] for ln in lines if " | " in ln]
        self.assertEqual(sorted(acts), ["bash=" + AIS] * 4 + ["disabled=true"])
        self.assertEqual(sum(1 for ln in lines if re.match(r"--[^-]", ln)), 2)
        self.assertEqual(lines[2], "✓ Personal")  # label "Per|sonal\n" cleaned in the header
        evil = [ln for ln in lines if "Evil" in ln]
        self.assertEqual(len(evil), 1)
        self.assertRegex(evil[0], r"^--x  bash=/bin/rm")  # one level, text kept inert
        self.assertEqual([ln for ln in lines if "/tmp" in ln], ["----/tmp/--a  terminal=true---"])

    def test_open_session_shows_disabled_quit_item(self):
        out = menu.render(status(), False, AIS, NOW)
        self.assertIn("----Quit Claude in /Users/x/other to resume | disabled=true", out)
        self.assertNotIn(OTHER, out)

    def test_privacy_mode_hides_folders_and_titles(self):
        out = menu.render(status(), True, AIS, NOW)
        self.assertEqual(out.split("\n")[2:6], ["✓ Personal", "Work · credential unknown", "---",
                                                "recent sessions: 2, open: 1"])
        for hidden in ("/Users/x", "Main task", "Resume", "Quit", UUID):
            self.assertNotIn(hidden, out)
        self.assertIn("Open Work Desktop | bash=%s param1=desktop param2=work terminal=false" % AIS, out)

    def test_label_leading_dashes_stripped(self):
        s = status()
        s["accounts"][0]["label"] = "--x"
        s["accounts"][1]["label"] = "---"
        out = menu.render(s, False, AIS, NOW).split("\n")
        self.assertEqual(out[0], "x")
        self.assertEqual(out[2], "✓ x")
        self.assertIn("work · credential unknown", out)
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
        self.assertIn("Sessions (10)", lines)
        items = [ln for ln in lines if ln.startswith("--T")]
        self.assertEqual(items, ["--T%d · 2 h ago" % i for i in range(10)])
        self.assertNotIn("Other sessions (account unknown)", lines)

    def test_run_refuses_to_spawn_after_kill_live(self):
        from ais import procs
        self.addCleanup(setattr, procs, "_STOPPED", False)
        procs.kill_live()
        rc, _, warn, _ = procs.run(["true"], 5)
        self.assertEqual((rc, warn), (None, "cannot run true: stopped"))

    def test_privacy_mode_counts_warnings_without_text(self):
        s = status(self_check={"ok": False, "messages": ["secret /Users/x", "b"]})
        out = menu.render(s, True, AIS)
        self.assertIn("\nwarnings: 2\n", out)
        self.assertNotIn("secret", out)

    def test_desktop_item_per_account_only_account_in_action(self):
        s = status()
        s["accounts"][1]["label"] = "Wo|rk\nx"
        lines = [ln for ln in menu.render(s, False, AIS).split("\n") if ln.startswith("Open ")]
        self.assertEqual(lines, ["Open Personal Desktop | bash=%s param1=desktop param2=personal terminal=false" % AIS,
                                 "Open Workx Desktop | bash=%s param1=desktop param2=work terminal=false" % AIS])

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

    def test_sanitize(self):
        self.assertEqual(menu.sanitize("a|b\nc\r\x1b[0m‮d​"), "abc[0md")
        # input unchanged by copy semantic
        s = status()
        before = copy.deepcopy(s)
        menu.render(s, False, AIS)
        self.assertEqual(s, before)


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
        self.assertEqual(lines[:2], ["Work", "---"])
        self.assertIn("✓ Personal", lines)
        self.assertTrue(any(ln.startswith("--Main task · ") for ln in lines), out)
        self.assertIn("----~/proj", lines)
        self.assertTrue(any(ln.startswith("----Resume in Personal | bash=") and "param3=" + UUID in ln
                            for ln in lines), out)
        self.assertNotIn("auth", self.calls_text())
        self.assertEqual(before, self.files())
        self.assertFalse((self.ais_dir / "ais.log").exists())

    def test_menu_uses_30_recent_status_json_keeps_5(self):
        for i in range(7):  # 8 sessions with the setUp one: more than 5, fewer than the 10 per group
            self.add_session("00000000-0000-4000-8000-%012d" % i, self.proj, "T%d" % i, 1000 + i)
        self.env(FAKE_PGREP_OUT="")
        code, out, err, _ = self.render()
        self.assertEqual(code, 0, err)
        lines = out.split("\n")
        i = lines.index("Other sessions (account unknown)")
        self.assertEqual(len([ln for ln in lines[i:] if re.match(r"--[^-]", ln)]), 8, out)
        _, js, _ = self.ais("status", "--json")
        self.assertEqual(len(json.loads(js)["recent"]), 5)

    def test_render_never_reads_stdin(self):
        code, out, _, took = self.render(timeout=10)
        self.assertEqual(code, 0)
        self.assertLess(took, 8)
        self.assertTrue(out.startswith("Personal\n") or out.startswith("ais\n") or out.startswith("Work\n"), out)

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
        self.env(FAKE_PGREP_OUT="")
        code, _, err, _ = self.render(timeout=60)  # warms cache.json
        self.assertEqual(code, 0, err)
        code, out, _, took = self.render()
        self.assertEqual(code, 0)
        self.assertFalse(out.startswith("ais ⚠"), out)
        self.assertLess(took, 2.0)
