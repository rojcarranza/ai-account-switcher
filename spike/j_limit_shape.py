"""Spike (j): shape of records with error == rate_limit: keys and distinct redacted message texts (<=120 chars)."""
import collections, glob, json, os, re
keys, texts = collections.Counter(), collections.Counter()
for p in glob.glob(os.path.expanduser("~/.claude/projects/*/*.jsonl")):
    for line in open(p, errors="replace"):
        if '"rate_limit"' not in line:
            continue
        try: r = json.loads(line)
        except ValueError: continue
        if r.get("error") != "rate_limit" or not r.get("isApiErrorMessage"):
            continue
        keys[tuple(sorted(r))] += 1
        c = r.get("message", {}).get("content", [])
        t = " ".join(b.get("text", "") for b in c if isinstance(b, dict))
        texts[re.sub(r"\d+", "N", t)[:120]] += 1
for k, n in keys.most_common(2): print(n, k)
for t, n in texts.most_common(8): print(n, repr(t))
