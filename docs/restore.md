# Restore a session from a snapshot

Before every `ais switch`, ais copies the session's files to `~/.config/ais/snapshots/<UTC stamp>-<session id>/`, for example `20261017T093000Z-<session id>`. It keeps at most 20 snapshots, 500 MB and 30 days.

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
   Pick the newest one whose name ends in the session ID you want.
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
5. Resume: `ais switch`, or `claude --resume <session id>` in the session's folder.

ais never writes to `~/.claude` itself. This copy is by hand, and it is the only way a snapshot goes back.
