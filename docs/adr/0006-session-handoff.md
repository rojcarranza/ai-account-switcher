# ADR-0006: Session handoff: ais resolves the session, Claude Code resumes it
Status: Accepted
Area: other
Depends on: G-1 spike (requirements); a failed check means a superseding ADR.

## Context
The core job is to continue the same session on the other account
(requirements FR-3). Transcripts live in the shared `~/.claude`. The
first version of this ADR used `claude --continue` and Claude's own
picker; the architecture review showed that leaves ais without a session
ID to lock, snapshot, check or attribute (blocker B1).

## Decision
- The provider resolves the session ID: top-level `*.jsonl` files in every
  `~/.claude/projects/*/` folder (subagent folders excluded) whose first
  recorded `cwd` has the same realpath as the current folder, newest by
  modified time, with folder and title cached by path, mtime and size. No
  folder-name encoding is assumed (changed in the plan review).
- ais always launches `claude --resume <id>` under the target account,
  from the session folder. Never bare `--continue` or Claude's picker.
- `ais switch --pick` is ais's own numbered list of the 5 newest sessions.
- `ais run` (new session) attributes the new transcript after `claude`
  exits, and refuses resume flags so it cannot bypass these checks.
- Before resuming, under the switch mutex, ais refuses if a `claude`
  process's cwd is the session folder (telling the user to `/exit` first),
  then snapshots the paths the provider names.

## Alternatives considered
- **`claude --continue` / Claude's picker:** least coupling, but ais
  cannot know which session it launched (rejected after review).
- **Copy the session to a new ID (Claude Switcher's Desktop approach):**
  needed for the Desktop Code tab's per-account list; the terminal CLI has
  no per-account list, so a copy only adds files and splits history.
- **Always require the account name:** removes last-used tracking, but
  is less intuitive; rejected by the user's preference for "switch to the
  other one".

## Consequences
- ais depends on the transcript layout (recorded in the spike, checked by
  the self-check and the tested version range); G-1(c) must show that
  `--resume` keeps appending to the same `<id>.jsonl`.
- Snapshots and last-used records always name the right session.
- The open check is conservative: any `claude` in a folder marks all its
  sessions open.
