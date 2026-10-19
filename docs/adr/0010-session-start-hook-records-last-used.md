# ADR-0010: A SessionStart hook records last-used for every session
Status: Accepted
Area: persistence
Depends on: ADR-0002 (one Keychain slot per account), ADR-0003 (state.json).

## Context
`ais switch` needs each session's last-used account (FR-3.1). ais records it
only for sessions it starts itself (`ais run`, `ais switch`). Sessions started
any other way have no record, or keep a stale one after a plain
`claude --resume` on another slot. For those, FR-3.1 guesses: the account
`AIS_ACCOUNT` names (#80), else the default account. The `AIS_ACCOUNT` guess
can mislabel a session started in another window, because ais keeps no data
on which window or slot started it (rojcarranza/ai-account-switcher#81).

Claude Code runs `SessionStart` hooks from its settings files when a session
starts or resumes, and passes JSON on stdin with `session_id`,
`transcript_path`, `cwd` and `source`. The hook runs as a child of `claude`.

Seen on the Mac (2026-10-19, Claude Code 2.1.302, from a Bash tool call in a
Desktop Code-tab session; a hook is a sibling child of the same process):
- A Desktop session's children get `CLAUDE_CODE_ENTRYPOINT=claude-desktop`
  and no `CLAUDE_SECURESTORAGE_CONFIG_DIR`, whatever Desktop instance runs
  them. Mapping "unset" to the default account would label every Work
  Desktop session as default, and ais's record wins over the Desktop record
  in FR-4.19.
- `~/.claude/settings.json` is a symlink into the user's dotfiles repo,
  which the Ubuntu laptop and Windows also use. A hook written there reaches
  machines without ais, and a temp-file-plus-rename write would replace the
  symlink with a plain file.
- Not yet seen: a terminal `claude` started with
  `CLAUDE_SECURESTORAGE_CONFIG_DIR` set passing it to its hooks. Child
  processes inherit the environment, so this is expected. Also not seen:
  that a terminal `claude` leaves `CLAUDE_CODE_ENTRYPOINT` unset or sets it
  to `cli`. Manual check M7 confirms both before merge.

## Decision
- New command `ais record`, meant only for the hook. It reads the hook's
  stdin JSON (at most 64 KiB), takes `transcript_path`, and keeps it only if
  it is a `.jsonl` whose realpath is under `~/.claude/projects` and whose
  name is `<session_id>.jsonl` with `session_id` a UUID.
- It maps `CLAUDE_SECURESTORAGE_CONFIG_DIR` to an account by exact string
  match with a stored credDir (ADR-0002: another spelling is another slot).
  Unset means the default account. Set to anything else, empty included,
  means no account: write nothing.
- WHERE `CLAUDE_CODE_ENTRYPOINT` is set and is not `cli`, it writes nothing
  (Desktop, IDE and SDK sessions; their owner comes from FR-4.19 or stays
  unknown).
- It writes the `state.json` record as `ais run` does (same lock, same
  format, FR-5.6), logs one line (NFR-OPS), prints nothing, and always
  exits 0, so a broken ais never blocks or clutters a session.
- ais writes its own hook entry into `~/.claude/settings.json` (user
  approved 2026-10-19, #81). `ais hook install` adds one `SessionStart`
  group, with no matcher, holding one command hook:
  `[ -x "$HOME/.local/bin/ais" ] && "$HOME/.local/bin/ais" record || true`,
  so the dotfiles copy is harmless on machines without ais. That exact
  command string is how ais finds its entry; running install twice adds
  nothing. `ais hook uninstall` and `ais uninstall` remove every command
  hook with exactly that command, then any group, `SessionStart` and
  `hooks` that this left empty. Every other key and hook is kept as read.
- The write goes through the symlink: ais resolves the realpath, requires
  it to be a regular file under the user's home folder (or creates
  `~/.claude/settings.json`, 0600, when nothing is there), writes a temp file
  in the realpath's folder, fsyncs and renames it over the realpath, and
  keeps the file's mode. The symlink itself is never replaced.
- A settings file that is not a JSON object, or whose `hooks` or
  `SessionStart` has the wrong type, is left untouched: ais exits 78 and
  names the path.
- Like `ais menu install`, both commands print what changes, ask for a yes
  and honour `--dry-run` (FR-5.4). `ais setup` prints `ais hook install`
  as a next step. All
  Claude-specific facts (path, keys, hook shape, env names) live in
  `providers/claude.py`.
- This narrows "ais never writes to `~/.claude`" (NFR-OPS, ADR-0003) to:
  ais writes nothing under `~/.claude` except its own hook entry in
  `settings.json`.
- With every session recorded, `ais switch` drops the `AIS_ACCOUNT` guess:
  no record means the default account again (FR-3.1 before #80).

## Alternatives considered
- **ais prints the hook block and the user adds it** (as `ais shell-init`
  does for `~/.zshrc`, #77): keeps "ais never writes to `~/.claude`" whole
  and leaves the dotfiles edit to the user. The user chose one command that
  ais can also undo.
- **Keep the `AIS_ACCOUNT` guess:** no new moving part, but it is a guess
  and misfires across windows (#80 finding 1).
- **Record from the `claude` shell function before it runs `claude`:** only
  covers terminals with the function loaded, and still cannot see which
  transcript the session will use.
- **Ask Claude Desktop records for every session:** they exist only for
  Desktop sessions.

## Consequences
- The hook runs on every session start and resume on the Mac, about 50 ms of
  Python. Resumes refresh the record too, so a plain `claude --resume` on
  another slot no longer leaves a stale owner.
- The record may name a transcript that `claude` has not created yet;
  FR-5.6 pruning removes it later if the session never writes one.
- The hook lands in the dotfiles repo's `claude/settings.json`; the user
  commits it there. Re-serialising may change that file's whitespace once
  (2-space indent, key order kept).
- Claude Code may rewrite `settings.json` itself (`/config`); a write that
  races ais's read-modify-write can lose one of the two changes. ais holds
  its own lock, which Claude Code does not honour.
- Until the hook is installed, sessions ais did not start fall back to the
  default-account assumption.
- A Claude Code update that renames the stdin keys or the entrypoint value
  makes `ais record` write nothing; the default-account assumption covers
  that, and M7 catches it.
