"""SwiftBar menu output (FR-4.8 to FR-4.23, FR-6.5). Provider-agnostic: works on the gather_status dict."""
import base64
import calendar
import os
import re
import struct
import sys
import threading
import time
import unicodedata
import uuid
import zlib
from typing import Any, Callable, Dict, List, NoReturn, Optional, Tuple

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


BAR_W, BAR_H = 240, 16  # 120 x 8 points at 2x
BAR_TRACK = (142, 142, 147, 102)
BAR_BLUE = (10, 132, 255, 255)
BAR_ORANGE = (255, 159, 10, 255)
BAR_RED = (255, 69, 58, 255)
USAGE_MAX_AGE = 24 * 3600


def _clamp(value: Optional[float]) -> Optional[int]:
    return None if value is None else max(0, min(100, int(round(value))))


def _bar_png(value: Optional[float]) -> bytes:
    """FR-4.20: an RGBA PNG bar, filled from the left in proportion to `value`, tagged 144 dpi so it shows at 1x size."""
    v = _clamp(value)
    filled = 0 if v is None else int(round(BAR_W * v / 100))
    # shortcut: red from 90 is inferred (Claude Desktop shows 85 yellow, 92 red), move it if Claude differs at 86-91
    colour = BAR_BLUE if v is None or v < 80 else BAR_ORANGE if v < 90 else BAR_RED
    r = BAR_H / 2.0
    fill_end = max(r, filled - r)  # the fill's round end; a short fill is the left cap cut at `filled`

    def inside(x: float, y: float, x0: float, x1: float) -> bool:  # within r of the segment (x0..x1, r)
        dx = x0 - x if x < x0 else x - x1 if x > x1 else 0.0
        return dx * dx + (y - r) * (y - r) <= r * r

    raw = b""
    for py in range(BAR_H):
        row = b"\0"  # filter byte 0, then pixels
        for px in range(BAR_W):
            ct = cf = 0  # track and fill coverage out of 16 samples, for anti-aliased round ends
            for sy in range(4):
                for sx in range(4):
                    x, y = px + (sx + 0.5) / 4, py + (sy + 0.5) / 4
                    if inside(x, y, r, BAR_W - r):
                        ct += 1
                        cf += x < filled and inside(x, y, r, fill_end)
            a_f, a_t = 255 * cf, BAR_TRACK[3] * (ct - cf)
            a = a_f + a_t
            row += bytes([int(round((colour[i] * a_f + BAR_TRACK[i] * a_t) / a)) if a else 0 for i in range(3)]
                         + [int(round(a / 16.0))])
        raw += row

    def chunk(kind: bytes, body: bytes) -> bytes:
        return struct.pack(">I", len(body)) + kind + body + struct.pack(">I", zlib.crc32(kind + body) & 0xffffffff)

    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", BAR_W, BAR_H, 8, 6, 0, 0, 0))
            + chunk(b"pHYs", struct.pack(">IIB", 5669, 5669, 1)) + chunk(b"IDAT", zlib.compress(raw))
            + chunk(b"IEND", b""))


def _usage(usage: Optional[dict], now: float) -> Tuple[Optional[str], List[str]]:
    """FR-4.20: the sample's age and two bar items, or one line when the newest sample is over 24 h old."""
    if not usage:
        return None, []
    t = usage["t"] / 1000.0
    if now - t > USAGE_MAX_AGE:
        return None, ["usage: no sample in the last 24 h"]
    out = []
    for name, key in (("5h", "fh"), ("week", "sd")):
        v = _clamp(usage[key])
        # SwiftBar ignores the PNG's dpi and shrinks the image unless width and height are given
        out.append("%s  %s | image=%s width=120 height=8" % (name, "?" if v is None else "%d%%" % v,
                                                             base64.b64encode(_bar_png(v)).decode("ascii")))
    try:
        age = _ago(time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(t)), now)
    except (OverflowError, ValueError, OSError):  # a time far out of range in the file
        age = None
    return age, out


def _header(account: dict, label: str, now: float) -> List[str]:
    cred = account["credential_present"]
    head = label if cred == "yes" else "%s · credential %s" % (label, sanitize(cred))
    age, bars = _usage(account.get("usage"), now)
    if age:
        head += " · updated " + age
    return [head + " | sfimage=person.crop.circle"] + bars  # FR-4.22: icon names are fixed strings


def render(status: dict, privacy: bool, ais_path: str, now: Optional[float] = None) -> str:
    """The menu text. Untrusted text (titles, folders, labels) never starts a line or enters an action."""
    bash = _bash(ais_path)
    now = time.time() if now is None else now
    accounts = status["accounts"]
    # a leading "-" would make the line a submenu or separator
    labels = {a["name"]: sanitize(a["label"]).lstrip("-") or _name(a["name"]) for a in accounts}
    recent = status["recent"]
    out = ["| sfimage=gauge.medium", "---"]  # FR-4.8: an icon only in the menu bar
    if privacy:
        for a in accounts:
            out.extend(_header(a, labels[a["name"]], now))
        out.append("---")
        # FR-4.14 counts the recent sessions the menu would show, not its wider list
        shown = [s for s in recent if s["last_used"] in labels][:core.RECENT_COUNT]
        out.append("recent sessions: %d, open: %d" % (len(shown), sum(1 for s in shown if s["open"])))
    else:
        by_owner = {a["name"]: [] for a in accounts}  # type: Dict[str, List[dict]]
        for s in recent:  # newest first; a session with no configured owner is not shown
            if s["last_used"] in by_owner:
                by_owner[s["last_used"]].append(s)
        groups = []  # type: List[List[str]]
        for a in accounts:
            g = _header(a, labels[a["name"]], now)
            mine = by_owner[a["name"]][:10]
            if mine:
                g.append("Sessions (%d) | sfimage=list.bullet" % len(mine))
                for s in mine:
                    g.extend(_session(s, a["name"], accounts, labels, bash, now))
            groups.append(g)
        for i, g in enumerate(groups):
            out.extend(g)
            if i < len(groups) - 1:
                out.append("---")
    msgs = status["self_check"]["messages"]
    if privacy:
        if msgs:
            out.append("warnings: %d" % len(msgs))
    elif msgs:
        out.append("---")
        out.extend("Warning: " + sanitize(m) for m in msgs)
    out.append("---")
    for a in accounts:
        out.append("Open %s Desktop | %s param1=desktop param2=%s terminal=false sfimage=desktopcomputer"
                   % (labels[a["name"]], bash, _name(a["name"])))
    for a in accounts:
        out.append("Open %s Terminal | %s param1=run param2=%s terminal=true sfimage=terminal"
                   % (labels[a["name"]], bash, _name(a["name"])))
    return "\n".join(out)


def _session(s: dict, owner: str, accounts: List[dict], labels: Dict[str, str], bash: str,
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
            out.append("----Resume in %s | %s param1=switch param2=--session param3=%s param4=%s terminal=true sfimage=play.fill"
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
            st = core.gather_status(ctx, True, warnings, core.MENU_RECENT, desktop=True)
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
