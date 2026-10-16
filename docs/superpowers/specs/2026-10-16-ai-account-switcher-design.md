# AI Account Switcher Design
Status: Approved 2026-10-16

Source brief: `docs/brief.md` (approved 2026-10-16). The user skipped the
brainstorming questions, so every "how" choice below is marked
**(Claude's call)** unless the brief already decided it. Each call is
open to change at this gate.

## Intent and why

One person, one Mac, two Claude Pro accounts. When one account hits its
usage limit mid-task, the agent's work should continue on the other
account within 30 seconds, in the same session, with nothing to
re-explain. The tool is the glue between "limit hit" and "same session,
other account".

## Goals

- Both accounts stay signed in at the same time; switching never logs
  anything out.
- Both accounts read and write one shared `~/.claude`, so sessions,
  memory, CLAUDE.md, skills, subagents and settings are the same whichever
  account runs.
- One command resumes the current project's latest session under the
  other account.
- One command shows which account is active and whether each is signed in.
- Adding a second AI provider later means adding one module, not
  reworking the tool.

## Non-goals

As in the brief: no desktop app or web chat, no auto-switch, no second
provider implemented, no GUI, no cross-machine sync, no handling of
secrets, no usage meter, no more than 2 accounts tested.

## Anti-goals (a failure even if it technically works)

- **Losing or corrupting `~/.claude`.** Any install, switch or uninstall
  that can damage transcripts or memory is a failure.
- **Touching secrets.** The tool must never read, print, copy or write a
  token or Keychain secret.
- **Running on the wrong account silently.** The user must always be able
  to see which account a running session uses.
- **Hidden global changes.** Nothing changes in the user's shell or
  `~/.claude` without being listed and undoable.

## Constraints

- macOS, zsh, Claude Code CLI (native install), $0, local only.
- Stays within Anthropic's terms (brief open question 1 must be answered
  before building).
- Work-account data policies apply to shared memory.

## How it works

### The core mechanism

Claude Code keeps two kinds of state:

| State | Where | Per account? |
|---|---|---|
| Login credential | macOS Keychain | **Yes**: one Keychain slot per account |
| Sessions, memory, CLAUDE.md, skills, agents, settings | `~/.claude/` | **No**: shared |

Following kevinchau/claude-switcher, the tool never sets
`CLAUDE_CONFIG_DIR` (that would split `~/.claude` and defeat sharing).
Instead the second account gets its own Keychain slot through
`CLAUDE_SECURESTORAGE_CONFIG_DIR`, and the default account runs with that
variable **unset**. This variable comes from that project's README and is
not in Anthropic's public docs, so the first build task is a spike that
proves it on the user's Mac (brief open questions 2 to 4). If the spike
fails, the design falls back to an ADR choosing another split (decided in
phase 4), and the commands below stay the same.

### Accounts

- `personal` is the **default account**: Claude Code's normal Keychain
  slot, no extra environment.
- `work` is an **extra account**: its own Keychain slot keyed by
  `~/.config/ais/accounts/work/`.
- Labels and the default are set in `~/.config/ais/config.json`
  **(Claude's call: JSON, so the tool needs only the Python standard
  library)**. Email addresses are stored only as labels for `status`,
  never used for login.

### Commands (CLI name `ais`, Claude's call)

| Command | Does |
|---|---|
| `ais setup` | Lists every change it will make, asks yes, backs up `~/.claude` to a timestamped `.tar.gz`, writes `~/.config/ais/`, prints the line to add to `~/.zshrc` (never edits it itself). |
| `ais login <account>` | Opens the official `claude` login flow with that account's environment. The user signs in in the browser. |
| `ais run [account]` | Starts `claude` under an account (default: the active one), records it as active. Passes extra arguments through to `claude`. |
| `ais switch [account]` | Finds the newest session for the current folder in the shared `~/.claude`, then runs `claude --resume <session-id>` under the other account (or the one named). Warns and asks if a `claude` process for that session is still running. |
| `ais status` | Active account; for each account, signed in or not (checked by whether its Keychain item **exists**, never reading it); newest session for the current folder. |
| `ais uninstall` | Removes `~/.config/ais/` and the zsh line it told the user to add; leaves `~/.claude` and Keychain items untouched and tells the user how to remove the extra Keychain item by hand. |

The typical flow when a limit hits: exit Claude (or it stops by itself),
type `ais switch`, and the same conversation reopens on the other account.

### Which session is "current"

The newest transcript file (by modified time) under
`~/.claude/projects/<folder-key>/` for the current working folder, where
`<folder-key>` is Claude Code's own encoding of the path. `ais switch
--pick` lists the 5 newest so the user can choose **(Claude's call)**.

### Making the account visible

`ais run` and `ais switch` print the account label before starting
Claude, and set the terminal tab title to `claude (<label>)`
**(Claude's call)**.

### Providers (room for other AIs)

A provider is one Python module with a small, fixed set of functions:

- `env_for(account)`: the environment that selects an account
- `newest_session(folder)` and `list_sessions(folder)`
- `resume_command(session_id)` and `start_command(args)`
- `is_signed_in(account)` (existence check only)
- `login_command()`

Only `claude` exists in the MVP. A second provider (brief open question 5)
adds one module and registers its name. Sharing context *between*
different providers is out of scope.

### Language and packaging (Claude's call)

Python 3.9+ standard library only, because it ships with Apple's
command-line developer tools, needs no dependencies and is easy to test.
One package, installed as a single `ais` command into `~/.local/bin`.

### Safety rules

- Only `ais setup` and `ais uninstall` write outside `~/.config/ais/`, and
  only after a yes.
- The tool never calls `security` with flags that print a secret.
- Every command that changes state supports `--dry-run`.

### Testing

`unittest` with a fake `HOME`, and fake `claude` and `security` programs
on `PATH`, so tests never touch the real Keychain or `~/.claude`. A short
manual checklist covers the real two-account handoff on the Mac.

## Left to the builder

- Exact Keychain service name derivation for the existence check (read
  from Claude Code's behaviour in the spike).
- Exact folder-key encoding (read from real `~/.claude/projects/` names).
- Output wording and colours.

## Risks

- `CLAUDE_SECURESTORAGE_CONFIG_DIR` is undocumented and could change in a
  Claude Code update. The spike and a `status` self-check catch it.
- Two accounts writing the same session at once could corrupt a
  transcript. `switch` refuses to resume a session that is still open
  unless the user confirms.
- `~/.claude.json` (outside `~/.claude`) holds cached account info; the
  spike decides whether it needs a split (brief open question 3).
