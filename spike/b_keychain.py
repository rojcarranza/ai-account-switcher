"""Spike (b): print only Claude Code credential service names from the Keychain."""
import subprocess


def names(cmd, key):
    out = subprocess.run(cmd, capture_output=True, text=True, timeout=30).stdout
    return [l.strip() for l in out.splitlines() if key in l]


print("find-generic-password:", names(["security", "find-generic-password", "-s", "Claude Code-credentials"], "svce"))
print("dump-keychain:", names(["security", "dump-keychain"], "Claude Code-credentials"))
