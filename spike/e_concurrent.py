"""G-1(e) spike: two accounts running sessions at the same time for 30 minutes.

Throwaway; never imported by src/. Usage: python3 spike/e_concurrent.py [HH:MM start, local] [minutes]
Each account resumes its own session every 2 minutes with `claude -p` (a simulation of interactive use).
Every 30 s it checks that ~/.claude.json and every ~/.claude/**/*.json parse, logs a hash of
`oauthAccount` and `userID` (never the values), and checks that neither slot's Keychain item was
rewritten (modification time only, never the secret). Log: spike/raw/e.log.
"""
import datetime
import hashlib
import json
import os
import re
import subprocess
import sys
import threading
import time
from pathlib import Path

HOME = Path.home()
LOG = Path(__file__).resolve().parent / "raw" / "e.log"
WORK_DIR = str(HOME / ".claude-accounts" / "work")
SLOTS = {"personal": "Claude Code-credentials", "work": "Claude Code-credentials-f9fb4ac6"}
LIMIT_TEXT = "You've hit your session limit"
lock = threading.Lock()
stop = threading.Event()
stats = {"parse_fail": 0, "transient": 0, "identity_changes": 0, "slot_changes": 0,
         "personal_ok": 0, "work_ok": 0, "personal_limited": 0, "work_limited": 0,
         "personal_err": 0, "work_err": 0}


def bump(key):
    with lock:
        stats[key] += 1


def slot_mdat(service):
    # Attributes only: no -w/-g, so the secret is never read.
    out = subprocess.run(["security", "find-generic-password", "-s", service],
                         capture_output=True, text=True, timeout=10).stdout
    m = re.search(r'"mdat"<timedate>=\S+\s+"(\d+Z)', out)
    return m.group(1) if m else None


def log(msg):
    line = "%s %s" % (datetime.datetime.now().strftime("%H:%M:%S"), msg)
    with lock, open(LOG, "a") as f:
        f.write(line + "\n")
    print(line, flush=True)


def h(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()[:8]


def load(path):
    try:
        return json.loads(path.read_text())
    except (ValueError, OSError):
        time.sleep(0.5)  # a reader can catch a file mid-rename; count only a repeat failure
        try:
            data = json.loads(path.read_text())
            bump("transient")
            return data
        except (ValueError, OSError) as e:
            bump("parse_fail")
            log("PARSE FAIL %s: %s" % (path, type(e).__name__))
            return None


def monitor(start_mdats):
    last = None
    while not stop.is_set():
        d = load(HOME / ".claude.json") or {}
        ident = (h(d.get("oauthAccount")), h(d.get("userID")))
        if ident != last:
            if last is not None:
                bump("identity_changes")
            log("identity oauthAccount=%s userID=%s" % ident)
            last = ident
        for name, service in SLOTS.items():
            now = slot_mdat(service)
            if now != start_mdats[name]:
                bump("slot_changes")
                log("SLOT CHANGED %s: mdat %s -> %s (result no longer a clean two-account run)"
                    % (name, start_mdats[name], now))
                start_mdats[name] = now
        for p in (HOME / ".claude").rglob("*.json"):
            if "plugins/cache" not in str(p):
                load(p)
        stop.wait(30)


def account(name, folder, env):
    folder.mkdir(parents=True, exist_ok=True)
    session = None
    n = 0
    while not stop.is_set():
        n += 1
        cmd = ["claude", "-p", "Reply with exactly: %s-%d" % (name.upper(), n), "--output-format", "json"]
        if session:
            cmd[1:1] = ["--resume", session]
        try:
            r = subprocess.run(cmd, cwd=folder, env=env, capture_output=True, text=True, timeout=180)
            out = json.loads(r.stdout or "{}")
            session = session or out.get("session_id")
            ok = r.returncode == 0 and not out.get("is_error")
            limited = not ok and str(out.get("result", "")).startswith(LIMIT_TEXT)
            bump(name + ("_ok" if ok else "_limited" if limited else "_err"))
            log("%s #%d exit=%d session=%s result=%r" % (name, n, r.returncode, (session or "-")[:8], str(out.get("result"))[:60]))
        except (subprocess.TimeoutExpired, ValueError) as e:
            bump(name + "_err")
            log("%s #%d error %s" % (name, n, type(e).__name__))
        stop.wait(120)


def main():
    start = sys.argv[1] if len(sys.argv) > 1 else None
    minutes = int(sys.argv[2]) if len(sys.argv) > 2 else 30
    if start:
        hh, mm = map(int, start.split(":"))
        now = datetime.datetime.now()
        at = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
        if at < now - datetime.timedelta(minutes=1):
            at += datetime.timedelta(days=1)  # a time already past today means tomorrow
        if at > now:
            print("waiting until", at, flush=True)
            time.sleep((at - now).total_seconds())
    start_mdats = {name: slot_mdat(service) for name, service in SLOTS.items()}
    log("start, %d minutes, slot mdat %s" % (minutes, json.dumps(start_mdats)))
    base = dict(os.environ)
    base.pop("CLAUDE_SECURESTORAGE_CONFIG_DIR", None)
    threads = [
        threading.Thread(target=monitor, args=(start_mdats,)),
        threading.Thread(target=account, args=("personal", HOME / "tmp" / "ais-spike-e1", base)),
        threading.Thread(target=account, args=("work", HOME / "tmp" / "ais-spike-e2",
                                               dict(base, CLAUDE_SECURESTORAGE_CONFIG_DIR=WORK_DIR))),
    ]
    for t in threads:
        t.start()
    stop.wait(minutes * 60)
    stop.set()
    for t in threads:
        t.join(timeout=200)
    log("done %s" % json.dumps(stats))


if __name__ == "__main__":
    main()
