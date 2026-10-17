"""SwiftBar menu output (FR-4.8 to FR-4.14, FR-6.5). Provider-agnostic: works on the gather_status dict."""
import os
import re
import sys
import threading
import time
import unicodedata
import uuid
from typing import Any, Callable, Dict, List, NoReturn

from ais import core, procs
from ais.accounts import NAME_RE

DEADLINE = 4.5  # FR-4.11 allows 5 s; the rest is for killing children and printing


def sanitize(text: str) -> str:
    """FR-4.12: drop control and format characters (core._clean), `|`, and line and paragraph separators."""
    return "".join(c for c in core._clean(text) if c not in "|\u2028\u2029")


def _name(name: str) -> str:
    if not NAME_RE.match(name):
        raise ValueError("invalid account name %r" % name)
    return name


def _uuid(sid: str) -> str:
    try:
        ok = str(uuid.UUID(sid)) == sid
    except ValueError:
        ok = False
    if not ok:
        raise ValueError("invalid session ID %r" % sid)
    return sid


def _bash(ais_path: str) -> str:
    if any(c in ('"', "|") or unicodedata.category(c).startswith("C") for c in ais_path):
        raise ValueError("the ais path contains a character SwiftBar cannot take: %r" % ais_path)
    return 'bash="%s"' % ais_path if " " in ais_path else "bash=" + ais_path


def _folder(folder: str) -> str:
    home = os.path.expanduser("~")
    if home not in ("", "/") and (folder == home or folder.startswith(home + os.sep)):
        folder = "~" + folder[len(home):]
    return sanitize(folder)


def render(status: dict, privacy: bool, ais_path: str) -> str:
    """The menu text. Untrusted text (titles, folders, labels) never starts a line or enters an action."""
    bash = _bash(ais_path)
    accounts = status["accounts"]
    # a leading "-" would make the line a submenu or separator
    labels = {a["name"]: sanitize(a["label"]).lstrip("-") or _name(a["name"]) for a in accounts}
    recent = status["recent"]
    first = recent[0]["last_used"] if recent else None
    out = [labels.get(first, "ais") if first else "ais", "---"]
    for a in accounts:
        out.append("%s: credential %s" % (labels[a["name"]], sanitize(a["credential_present"])))
    out.append("---")
    if privacy:
        out.append("recent sessions: %d, open: %d" % (len(recent), sum(1 for s in recent if s["open"])))
    else:
        for s in recent:
            sid = _uuid(s["id"])
            folder = _folder(s["folder"])
            used = labels.get(s["last_used"], "unknown") if s["last_used"] else "unknown"
            out.append("• %s — %s (%s)%s" % (folder, sanitize(s["title"]) or "(untitled)", used,
                                           " · open" if s["open"] else ""))
            if s["open"]:
                out.append("--Quit Claude in %s to resume | disabled=true" % folder)
                continue
            for a in accounts:
                if a["name"] != s["last_used"]:
                    out.append("--Resume in %s | %s param1=switch param2=--session param3=%s param4=%s terminal=true"
                               % (labels[a["name"]], bash, sid, _name(a["name"])))
    msgs = status["self_check"]["messages"]
    if privacy:
        if msgs:
            out.append("warnings: %d" % len(msgs))
    else:
        out.extend("Warning: " + sanitize(m) for m in msgs)
    out.append("---")
    for a in accounts:
        out.append("Open %s Desktop | %s param1=desktop param2=%s terminal=false"
                   % (labels[a["name"]], bash, _name(a["name"])))
    return "\n".join(out)


HIDDEN = "error (details hidden by menu_privacy; run ais status)"


def _failure(message: str, hide: bool = False) -> str:
    """FR-4.14: with menu_privacy on, error text (which can hold folders) is not shown."""
    return "ais ⚠\n---\nais: " + (HIDDEN if hide else sanitize(message)[:300])


def cmd_menu_render(make_ctx: Callable[[], core.Context], ais_path: str, started: float) -> NoReturn:
    """FR-4.11: any failure or timeout prints the warning menu; always exits 0 without waiting for leftovers."""
    box = {}  # type: Dict[str, Any]

    def work() -> None:
        try:
            ctx = make_ctx()
            box["store"] = ctx.store
            box["hide"] = ctx.config.menu_privacy
            warnings = []  # type: List[str]
            st = core.gather_status(ctx, True, warnings)
            if warnings:  # an unknown open state would offer Resume for an open session
                raise RuntimeError(warnings[0])
            box["out"] = render(st, ctx.config.menu_privacy, ais_path)
        except BaseException as e:  # a thread must not die with a traceback on stderr
            box["out"] = _failure(getattr(e, "message", None) or str(e) or type(e).__name__, box.get("hide", False))

    t = threading.Thread(target=work, daemon=True)
    t.start()
    t.join(max(0.0, started + DEADLINE - time.monotonic()))
    if t.is_alive():
        procs.kill_live()
        tmp = box["store"].inflight_tmp if "store" in box else None
        if tmp:  # os._exit would strand a half-written temp file in ~/.config/ais
            try:
                os.unlink(tmp)
            except OSError:
                pass
        box.setdefault("out", _failure("timed out after %g s" % DEADLINE, box.get("hide", False)))
    sys.stdout.write(box["out"] + "\n")
    sys.stdout.flush()
    os._exit(0)
