"""G-1(c) spike: SIGKILL claude while a Bash tool call has no result yet.

Throwaway; never imported by src/. Raw output goes to spike/raw/.
Kills as soon as the transcript holds a tool_use without a matching tool_result.
"""
import json
import os
import signal
import subprocess
import time
from pathlib import Path

RAW = Path(__file__).resolve().parent / "raw"
FOLDER = Path.home() / "tmp" / "ais-spike-k2"
FOLDER.mkdir(parents=True, exist_ok=True)
PROJ = Path.home() / ".claude" / "projects" / "-Users-roj-tmp-ais-spike-k2"
env = dict(os.environ, CLAUDE_SECURESTORAGE_CONFIG_DIR=str(Path.home() / ".claude-accounts" / "work"))
prompt = "Use the Bash tool to run exactly: sleep 20 && echo DONE (run it in the foreground, not in the background). Then tell me the output."


def open_tool_use():
    for f in PROJ.glob("*.jsonl"):
        uses, results = set(), set()
        for line in f.read_text().splitlines():
            try:
                m = json.loads(line).get("message") or {}
            except ValueError:
                continue
            for b in (m.get("content") if isinstance(m, dict) and isinstance(m.get("content"), list) else []):
                if isinstance(b, dict) and b.get("type") == "tool_use":
                    uses.add(b["id"])
                if isinstance(b, dict) and b.get("type") == "tool_result":
                    results.add(b.get("tool_use_id"))
        if uses - results:
            return f
    return None


with open(RAW / "k2.json", "w") as out:
    p = subprocess.Popen(
        ["claude", "-p", prompt, "--allowedTools", "Bash(sleep:*)", "--output-format", "json"],
        cwd=FOLDER, env=env, stdout=out, stderr=subprocess.STDOUT,
    )
    deadline = time.time() + 60
    hit = None
    while time.time() < deadline and p.poll() is None and not hit:
        hit = open_tool_use()
        time.sleep(0.2)
    time.sleep(2)  # let the tool start running
    if p.poll() is None:
        p.send_signal(signal.SIGKILL)
    print("claude pid", p.pid, "returncode", p.wait(timeout=10), "open tool_use seen:", bool(hit))
for f in sorted(PROJ.glob("*.jsonl")):
    print(f.name, len(f.read_text().splitlines()), "lines; open tool_use now:", open_tool_use() is not None)
