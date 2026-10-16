"""G-1(e) spike: two accounts running sessions at the same time for 30 minutes.

Throwaway; never imported by src/. Usage: python3 spike/e_concurrent.py [HH:MM start, local] [minutes]
Each account resumes its own session every 2 minutes with `claude -p` (a simulation of interactive use).
Every 30 s it checks that ~/.claude.json and every ~/.claude/**/*.json parse, and logs a hash of
`oauthAccount` and `userID` (never the values). Log: spike/raw/e.log.
"""
import datetime
import hashlib
import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

HOME = Path.home()
LOG = Path(__file__).resolve().parent / "raw" / "e.log"
WORK_DIR = str(HOME / ".claude-accounts" / "work")
lock = threading.Lock()
stop = threading.Event()
stats = {"parse_fail": 0, "transient": 0, "identity_changes": 0, "personal_ok": 0, "work_ok": 0,
         "personal_err": 0, "work_err": 0}


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
            stats["transient"] += 1
            return data
        except (ValueError, OSError) as e:
            stats["parse_fail"] += 1
            log("PARSE FAIL %s: %s" % (path, type(e).__name__))
            return None


def monitor():
    last = None
    while not stop.is_set():
        d = load(HOME / ".claude.json") or {}
        ident = (h(d.get("oauthAccount")), h(d.get("userID")))
        if ident != last:
            if last is not None:
                stats["identity_changes"] += 1
            log("identity oauthAccount=%s userID=%s" % ident)
            last = ident
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
            stats[name + ("_ok" if ok else "_err")] += 1
            log("%s #%d exit=%d session=%s result=%r" % (name, n, r.returncode, (session or "-")[:8], str(out.get("result"))[:60]))
        except (subprocess.TimeoutExpired, ValueError) as e:
            stats[name + "_err"] += 1
            log("%s #%d error %s" % (name, n, type(e).__name__))
        stop.wait(120)


def main():
    start = sys.argv[1] if len(sys.argv) > 1 else None
    minutes = int(sys.argv[2]) if len(sys.argv) > 2 else 30
    if start:
        hh, mm = map(int, start.split(":"))
        now = datetime.datetime.now()
        at = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
        if at > now:
            print("waiting until", at, flush=True)
            time.sleep((at - now).total_seconds())
    log("start, %d minutes" % minutes)
    base = dict(os.environ)
    base.pop("CLAUDE_SECURESTORAGE_CONFIG_DIR", None)
    threads = [
        threading.Thread(target=monitor),
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
