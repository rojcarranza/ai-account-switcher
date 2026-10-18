# Restore a session from a snapshot

Before every `ais switch`, ais tries to copy the session's files to `~/.config/ais/snapshots/<UTC stamp>-<session id>/`, for example `20261017T093000Z-<session id>`. It keeps at most 20 snapshots, 500 MB and 30 days.

If the snapshot cannot be made, the switch goes on and ais prints `ais: warning: snapshot failed (...); continuing without one` or `ais: warning: not enough free space for a snapshot; continuing without one`. Then there is nothing to restore for that switch.

A snapshot holds:

- `<session id>.jsonl`, the transcript
- `<session id>/`, the subagent files, only when the session has them

Restoring replaces the live transcript with the saved one. Anything said after the snapshot is lost.

## Steps

1. Close the session first. Type `/exit` in every `claude` running in that folder. Copying over an open transcript can corrupt it.
2. Find the snapshot:
   ```bash
   ls -d ~/.config/ais/snapshots/*
   ```
   Pick the newest one whose name contains the session ID you want.
3. Find where the live transcript sits (the folder name under `projects/` is Claude Code's own encoding of the project folder):
   ```bash
   ls ~/.claude/projects/*/<session id>.jsonl
   ```
4. Copy the snapshot back, with that project folder in place of `<project>`:
   ```bash
   SNAP=~/.config/ais/snapshots/<stamp>-<session id>
   DEST=~/.claude/projects/<project>
   cp -R "$SNAP"/. "$DEST"/
   ```
   This overwrites `<session id>.jsonl` and merges `<session id>/`.
5. Resume on the account you want to continue on: `ais switch <account> --session <session id>` (or `ais switch <account>` in the session's folder, which takes the newest session there). A plain `claude --resume` would run on the default account, whatever the session used last.

ais never writes to `~/.claude` itself. This copy is by hand, and it is the only way a snapshot goes back.
