"""Spike (j): find usage-limit text in transcripts. Read-only; prints only redacted <=120 char snippets,
the JSON field path and counts. No conversation content beyond the marker snippet."""
import collections, glob, json, os, re

PAT = re.compile(r"(usage limit|limit reached|hit your limit|resets? (at|in)|rate.?limit)", re.I)
paths = glob.glob(os.path.expanduser("~/.claude/projects/*/*.jsonl"))
hits = collections.Counter()
examples = {}


def walk(o, path):
    if isinstance(o, dict):
        for k, v in o.items():
            yield from walk(v, f"{path}.{k}")
    elif isinstance(o, list):
        for v in o:
            yield from walk(v, f"{path}[]")
    elif isinstance(o, str):
        yield path, o


for p in paths:
    with open(p, errors="replace") as f:
        for line in f:
            if not PAT.search(line):
                continue
            try:
                rec = json.loads(line)
            except ValueError:
                continue
            for fp, s in walk(rec, "$"):
                m = PAT.search(s)
                # only short strings, to skip conversation prose / code listings
                if m and len(s) <= 300:
                    key = (rec.get("type"), fp, bool(rec.get("isApiErrorMessage")))
                    hits[key] += 1
                    snip = s[max(0, m.start() - 40): m.end() + 60].replace("\n", " ")
                    snip = re.sub(r"[\w.+-]+@[\w.-]+", "<email>", snip)
                    examples.setdefault(key, snip[:120])

print(len(paths), "transcripts scanned")
for key, n in hits.most_common(15):
    print(n, key, "|", examples[key])
