"""Spike (b)/(h): run `claude auth status` with/without the env var, time it, print keys only."""
import os, re, subprocess, sys, time

work = os.path.expanduser("~/.claude-accounts/work")
for label, extra in (("default", {}), ("work", {"CLAUDE_SECURESTORAGE_CONFIG_DIR": work})):
    for i in range(3):
        t = time.time()
        p = subprocess.run(["claude", "auth", "status"], capture_output=True, text=True, env={**os.environ, **extra}, timeout=30)
        dt = time.time() - t
        out = p.stdout + p.stderr
        if i == 0:
            # redact values: keep `key:` / JSON keys, replace the rest
            red = re.sub(r'("?[A-Za-z]+"?\s*[:=]\s*)("?)[^\n",]*', r'\1<redacted>', out)
            print(f"[{label}] exit={p.returncode} format:\n{red}")
        print(f"[{label}] run{i} {dt:.2f}s")
