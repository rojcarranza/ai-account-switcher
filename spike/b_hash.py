"""Spike (b): expected Keychain service for a credDir, per v2.1.301 function v1()."""
import hashlib, os, sys, unicodedata

def service(cred_dir):
    d = unicodedata.normalize("NFC", cred_dir)
    return "Claude Code-credentials-" + hashlib.sha256(d.encode()).hexdigest()[:8]

if __name__ == "__main__":
    for d in sys.argv[1:] or [os.path.expanduser("~/.claude-accounts/work"), os.path.expanduser("~/.claude")]:
        print(d, "->", service(d))
