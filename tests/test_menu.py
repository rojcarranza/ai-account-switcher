"""FR-4.8, FR-4.9, FR-4.11 to FR-4.14, FR-6.5, NFR-PERF: `ais menu render` (SwiftBar)."""
import copy
import os
import subprocess
import sys
import time
import unicodedata

from ais import menu
from tests.helpers import SRC
from tests.test_switch import OTHER, UUID, SwitchCase

AIS = "/opt/ais/ais"
SECOND = "55555555-5555-4555-8555-555555555555"


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
        out = menu.render(status(), False, AIS).split("\n")
        self.assertEqual(out, [
            "Personal",
            "---",
            "Personal: credential yes",
            "Work: credential unknown",
            "---",
            "• /Users/x/proj — Main task (Personal)",
            "--Resume in Work | bash=%s param1=switch param2=--session param3=%s param4=work terminal=true"
            % (AIS, UUID),
            "• /Users/x/other — Second (unknown) · open",
            "--Quit Claude in /Users/x/other to resume | disabled=true",
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
        out = menu.render(s, False, AIS)
        lines = out.split("\n")
        for ln in lines:
            self.assertNotRegex(ln, r"^-+[^-]*(Evil|a )" )
            self.assertFalse(any(unicodedata.category(c).startswith("C") for c in ln), ln)
        # every " | " introduces one of our own actions: 2 resume (unknown last_used), 2 desktop, 1 quit
        acts = [ln.split(" | ")[1].split()[0] for ln in lines if " | " in ln]
        self.assertEqual(sorted(acts), ["bash=" + AIS] * 4 + ["disabled=true"])
        self.assertEqual(sum(1 for ln in lines if ln.startswith("• ")), 2)
        self.assertEqual(lines[2], "Personal: credential yes")  # label "Per|sonal\n" cleaned in the account line
        self.assertEqual([ln for ln in lines if "Evil" in ln or "/tmp" in ln],
                         [ln for ln in lines if ln.startswith("• /tmp")])

    def test_open_session_shows_disabled_quit_item(self):
        out = menu.render(status(), False, AIS)
        self.assertIn("--Quit Claude in /Users/x/other to resume | disabled=true", out)
        self.assertNotIn(OTHER, out)

    def test_privacy_mode_hides_folders_and_titles(self):
        out = menu.render(status(), True, AIS)
        self.assertEqual(out.split("\n")[2:6], ["Personal: credential yes", "Work: credential unknown", "---",
                                                "2 recent sessions, 1 open"])
        for hidden in ("/Users/x", "Main task", "Resume", "Quit", UUID):
            self.assertNotIn(hidden, out)
        self.assertIn("Open Work Desktop | bash=%s param1=desktop param2=work terminal=false" % AIS, out)

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
        code, out, err, _ = self.render()
        self.assertEqual(code, 0, err)
        lines = out.split("\n")
        self.assertEqual(lines[:2], ["Work", "---"])
        self.assertIn("Personal: credential yes", lines)
        self.assertIn("• ~/proj — Main task (Work)", lines)
        self.assertTrue(any(ln.startswith("--Resume in Personal | bash=") and "param3=" + UUID in ln
                            for ln in lines), out)
        self.assertNotIn("auth", self.calls_text())
        self.assertFalse((self.ais_dir / "state.json").exists() and "menu" in self.state())
        self.assertFalse((self.ais_dir / "ais.log").exists())

    def test_render_never_reads_stdin(self):
        code, out, _, took = self.render(timeout=10)
        self.assertEqual(code, 0)
        self.assertLess(took, 8)
        self.assertTrue(out.startswith("Personal\n") or out.startswith("ais\n") or out.startswith("Work\n"), out)

    def test_render_with_hung_lsof_finishes_in_5s(self):
        child = self.home / "lsof.child"
        self.env(FAKE_PGREP_OUT="123", FAKE_PS_OUT="123 claude", FAKE_LSOF_HANG="1",
                 FAKE_LSOF_CHILD_FILE=str(child))
        code, out, _, took = self.render(timeout=15)
        self.assertEqual(code, 0)
        self.assertLess(took, 5.5)
        self.assertTrue(out.startswith("ais ⚠\n---\n"), out)
        self.assertNotIn("bash=", out)
        pid = int(child.read_text())
        time.sleep(0.3)
        with self.assertRaises(OSError):  # no child left behind
            os.kill(pid, 0)

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
