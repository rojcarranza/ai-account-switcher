"""SwiftBar menu output (FR-4.8 to FR-4.17, FR-6.5). Provider-agnostic: works on the gather_status dict."""
import calendar
import os
import re
import sys
import threading
import time
import unicodedata
import uuid
from typing import Any, Callable, Dict, List, NoReturn, Optional

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


def _ago(modified: Optional[str], now: float) -> Optional[str]:
    """FR-4.16: age of an ISO UTC time against `now`; None when missing or unreadable."""
    try:
        secs = now - calendar.timegm(time.strptime(modified, "%Y-%m-%dT%H:%M:%SZ"))  # type: ignore[arg-type]
    except (TypeError, ValueError, OverflowError):
        return None
    if secs < 60:
        return "just now"
    if secs < 3600:
        return "%d min ago" % (secs // 60)
    if secs < 48 * 3600:
        return "%d h ago" % (secs // 3600)
    return "%d d ago" % (secs // 86400)


def _short_folder(folder: str) -> str:
    """FR-4.17: `~/…` for the home folder, and `<first>/…/<last>` when longer than 48 characters."""
    f = _folder(folder)
    parts = f.split("/")
    if len(f) > 48 and len([p for p in parts if p]) > 2:  # something between first and last to elide
        first = parts[0] or "/" + parts[1]  # "/Users" for an absolute path
        f = first + "/…/" + parts[-1]
    return f


def _short_title(title: str) -> str:
    return title if len(title) <= 50 else title[:49] + "…"


def _header(account: dict, label: str) -> List[str]:
    cred = account["credential_present"]
    return ["✓ " + label if cred == "yes" else "%s · credential %s" % (label, sanitize(cred))]


def render(status: dict, privacy: bool, ais_path: str, now: Optional[float] = None) -> str:
    """The menu text. Untrusted text (titles, folders, labels) never starts a line or enters an action."""
    bash = _bash(ais_path)
    now = time.time() if now is None else now
    accounts = status["accounts"]
    # a leading "-" would make the line a submenu or separator
    labels = {a["name"]: sanitize(a["label"]).lstrip("-") or _name(a["name"]) for a in accounts}
    recent = status["recent"]
    first = recent[0]["last_used"] if recent else None
    out = [labels.get(first, "ais") if first else "ais", "---"]
    if privacy:
        for a in accounts:
            out.extend(_header(a, labels[a["name"]]))
        out.append("---")
        out.append("recent sessions: %d, open: %d" % (len(recent), sum(1 for s in recent if s["open"])))
    else:
        by_owner = {a["name"]: [] for a in accounts}  # type: Dict[Optional[str], List[dict]]
        by_owner[None] = []
        for s in recent:  # newest first; an unconfigured owner is as unknown as none
            by_owner[s["last_used"] if s["last_used"] in by_owner else None].append(s)
        groups = []  # type: List[List[str]]
        for a in accounts:
            g = _header(a, labels[a["name"]])
            mine = by_owner[a["name"]][:10]
            if mine:
                g.append("Sessions (%d)" % len(mine))
                for s in mine:
                    g.extend(_session(s, a["name"], accounts, labels, bash, now))
            groups.append(g)
        if by_owner[None]:
            g = ["Other sessions (account unknown)"]
            for s in by_owner[None][:10]:
                g.extend(_session(s, None, accounts, labels, bash, now))
            groups.append(g)
        for i, g in enumerate(groups):
            out.extend(g)
            if i < len(groups) - 1:
                out.append("---")
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


def _session(s: dict, owner: Optional[str], accounts: List[dict], labels: Dict[str, str], bash: str,
             now: float) -> List[str]:
    """FR-4.15: one session item and its submenu (folder, then Resume or Quit items)."""
    sid = _uuid(s["id"])
    folder = _short_folder(s["folder"])
    title = _short_title(sanitize(s["title"])).lstrip("-") or folder.lstrip("-")
    age = "open" if s["open"] else _ago(s["modified"], now)
    out = ["--" + title + (" · " + age if age else ""), "----" + folder.lstrip("-")]
    if s["open"]:
        out.append("----Quit Claude in %s to resume | disabled=true" % folder)
        return out
    for a in accounts:
        if a["name"] != owner:
            out.append("----Resume in %s | %s param1=switch param2=--session param3=%s param4=%s terminal=true"
                       % (labels[a["name"]], bash, sid, _name(a["name"])))
    return out


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
            st = core.gather_status(ctx, True, warnings, core.MENU_RECENT)
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
