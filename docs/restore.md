# Restoring a session from a snapshot

Before every resume, `ais switch` copies the session's files to `~/.config/ais/snapshots/<UTC time>-<session id>/`: the transcript `<id>.jsonl` and, when it exists, the `<id>/` folder with subagent files. It keeps at most 20 snapshots, 500 MB and 30 days. ais never writes to `~/.claude` itself, so a snapshot is only needed when a resumed session damaged its transcript.

1. Quit Claude in that session (`/exit`).
2. Find the snapshot. The newest for a session is last:

   ```bash
   ls ~/.config/ais/snapshots/ | grep <session-id>
   ```

3. Find where the live transcript is:

   ```bash
   ls ~/.claude/projects/*/<session-id>.jsonl
   ```

4. Keep the damaged copy aside (and, if the session has a `<session-id>/` folder, move it aside the same way first, so the copy does not mix old and new subagent files), then copy the snapshot back into that folder (`<project-folder>` is the folder from step 3):

   ```bash
   mv ~/.claude/projects/<project-folder>/<session-id>.jsonl ~/<session-id>.jsonl.damaged
   cp -R ~/.config/ais/snapshots/<snapshot>/ ~/.claude/projects/<project-folder>/
   ```

5. Resume it: `ais switch --session <session-id> <account>`.

Anything the session did after the snapshot is lost from the conversation (files it changed on disk stay changed).
