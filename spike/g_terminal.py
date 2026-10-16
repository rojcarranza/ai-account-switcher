"""G-1(g) spike: is a terminal-started claude found by `pgrep -x claude`, with the right cwd?

Throwaway; never imported by src/. Starts one short claude -p run on the work slot.
"""
import os
import subprocess
import time
from pathlib import Path

FOLDER = Path.home() / "tmp" / "ais-spike g ünï"  # space and non-ASCII on purpose
FOLDER.mkdir(parents=True, exist_ok=True)
env = dict(os.environ, CLAUDE_SECURESTORAGE_CONFIG_DIR=str(Path.home() / ".claude-accounts" / "work"))
p = subprocess.Popen(
    ["claude", "-p", "Use the Bash tool to run exactly: sleep 15 && echo DONE. Then reply DONE.",
     "--allowedTools", "Bash(sleep:*)"],
    cwd=FOLDER, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
)
time.sleep(6)
t = time.time()
pids = subprocess.run(["pgrep", "-x", "claude"], capture_output=True, text=True, timeout=5).stdout.split()
t_pgrep = time.time() - t
print("our pid", p.pid, "found by pgrep -x claude:", str(p.pid) in pids, "(%d pids, %.3fs)" % (len(pids), t_pgrep))
t = time.time()
out = subprocess.run(["lsof", "-a", "-d", "cwd", "-p", ",".join(pids), "-Fn"],
                     capture_output=True, text=True, timeout=5).stdout
t_lsof = time.time() - t
cur, cwds = None, {}
for line in out.splitlines():
    if line.startswith("p"):
        cur = line[1:]
    elif line.startswith("n") and cur:
        cwds[cur] = line[1:]
got = cwds.get(str(p.pid))
print("lsof cwd for our pid:", repr(got), "(%.3fs)" % t_lsof)
print("equals realpath(folder):", got == os.path.realpath(FOLDER))
print("equals after NFC/NFD compare:", got is not None and __import__("unicodedata").normalize("NFC", got) == __import__("unicodedata").normalize("NFC", os.path.realpath(FOLDER)))
args = subprocess.run(["ps", "-o", "args=", "-p", str(p.pid)], capture_output=True, text=True, timeout=5).stdout.strip()
print("argv of our pid:", args[:120])
p.wait(timeout=60)
