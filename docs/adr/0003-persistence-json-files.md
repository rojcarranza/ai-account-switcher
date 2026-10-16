# ADR-0003: Persistence: JSON files in ~/.config/ais
Status: Accepted
Area: persistence

## Context
ais stores a few small records: its config, last-used account per session,
a cache, a log and session snapshots (architecture data model). One user,
one Mac, a handful of writes per day.

## Decision
Plain files under `~/.config/ais/` (0700). JSON for `config.json` and
`state.json`, written to a temp file, fsynced and renamed, with every
read-modify-write under one `fcntl.flock` on `~/.config/ais/.lock`. A switch mutex (`switch.lock`, flock) held from the open check to the
spawn; no per-session PID lock files (dropped in the plan review: open
sessions are detected from `claude` process cwd). Append-only text log. Session snapshots of the
paths the provider names, as APFS clones where possible, capped at 20,
500 MB and 30 days. No full `~/.claude` backup (dropped
in the architecture review: ais never writes there).

## Alternatives considered
- **SQLite (stdlib `sqlite3`):** safe concurrent writes, but opaque to the
  user and more than this data needs.
- **macOS `defaults` (plist):** native, but awkward from Python and on
  Linux CI.

## Consequences
- Files are readable and fixable by hand.
- Concurrency relies on flock, atomic rename and the switch mutex, not
  transactions.
