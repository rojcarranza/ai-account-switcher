# ais Desktop instances per account: design
Status: Approved 2026-10-16 (scope change to the MVP)
Related: `docs/brief.md` non-goal 1, `docs/adr/0002-auth-account-split.md`,
`docs/adr/0007-menu-bar-swiftbar-plugin.md`, `docs/spike-results.md`
("Desktop spike"), rojcarranza/ai-account-switcher#1 (part 2, next release).

## Intent
The user runs two personal Claude Pro accounts ("Personal" and "Work"; the
labels are only names). Today Claude Switcher gives them two things: a
terminal login per account and a second Claude Desktop window for the other
account. The user wants ais to replace Claude Switcher completely and then
uninstall it. ais already covers the terminal side. This change adds the
Desktop side: open the Claude Desktop app for an account, so that Personal
and Work Desktop windows run side by side for parallel work on different
projects.

## Goals
1. `ais desktop <account>` opens the Claude Desktop app for that account.
   - Default account (Personal): the normal Claude app, launched without a
     data-folder flag, exactly as the user opens it today.
   - Any other account: a separate Claude.app instance started with
     `--user-data-dir=<home>/Library/Application Support/Claude-ais-<account>`
     (folder name: controller's call; see "Decided by the controller").
   - If that account's Desktop instance is already running, ais must not
     start a second one (see Constraints, "No duplicate instance").
2. The SwiftBar menu gets one item per account, `Open <label> Desktop`, that
   runs `ais desktop <account>` (no Terminal window).
3. A written guide, `docs/migrate-from-claude-switcher.md`, takes the user
   through removing Claude Switcher once ais works: what to keep, what to
   remove, in which order, and how to check each step.
4. `ais desktop` supports `--dry-run` (prints the command it would run).

## Non-goals
- One Desktop app that switches accounts and lists both accounts' sessions
  (part 2): deferred to rojcarranza/ai-account-switcher#1.
- Moving or copying sessions between Desktop instances, or from Claude
  Switcher's `Claude-work` folder. The user chose a fresh folder.
- Signing in for the user. The first time an account's Desktop opens, the
  user signs in in that window; ais does nothing with Desktop credentials.
- An `ais` command that removes Claude Switcher. The cleanup is a guide the
  user follows (see "Decided by the controller").
- claude.ai web chat.

## Anti-goals (a failure even if it works)
- ais deletes anything of Claude Switcher's, or any Desktop data folder,
  without the user doing it by hand.
- Opening a Desktop instance changes a terminal login, a Keychain item,
  `~/.claude` or `~/.claude.json`.
- Two instances run on the same data folder.
- The Personal Desktop moves to a new data folder and loses its sign-in or
  history.

## Evidence (from `docs/spike-results.md`, 2026-10-16)
- Claude Switcher runs its Work Desktop as
  `/Applications/Claude.app/Contents/MacOS/Claude --user-data-dir=<…>/Claude-work`.
- `open -n -a Claude --args --user-data-dir=<new folder>` created the folder
  and ran a third instance next to the other two. A sign-in there changed no
  terminal Keychain item and not `~/.claude.json`. After Cmd+Q, the same
  command reopened it already signed in.
- Running the same command while that instance was open started a duplicate
  process on the same folder. Claude.app does not prevent it.

## Constraints
- Everything from the MVP stays: Python 3.9 stdlib only, one zipapp, exit
  codes 64 to 78, every subprocess with a `timeout=`, tests with a temp HOME
  and fake tools on `PATH`, never `CLAUDE_CONFIG_DIR`, never `security -w/-g`.
- Claude-specific facts (app path `/Applications/Claude.app`, the
  `--user-data-dir` flag, the folder prefix, how to spot a running instance)
  live only in `src/ais/providers/claude.py`, behind new provider methods.
- No duplicate instance: before launching, look for a running
  `…/Claude.app/Contents/MacOS/Claude` process whose arguments contain
  exactly `--user-data-dir=<this account's folder>` (one `ps` call). For the
  default account, look for that process with no `--user-data-dir`. If one is
  running, do not launch; bring it to the front if that can be done without a
  permission prompt, otherwise print `<label> Desktop is already open
  (PID n)` and exit 0.
- ADR-0002 stands: ais never reads or writes Claude Switcher's files. The
  migration guide is a document, not code.
- `ais uninstall` leaves the Desktop data folders in place (they hold the
  user's Desktop sign-in and data) and lists them under the manual steps.

## Decided by the controller (the user can override)
- Command name `ais desktop <account>`; menu item text `Open <label> Desktop`.
- Data folder `~/Library/Application Support/Claude-ais-<account>`, derived
  from the account name, not stored in `config.json`. The `ais-` part keeps
  it apart from Claude Switcher's `Claude-<id>` folders.
- The cleanup is a guide rather than a command, because it is a one-time,
  mostly permanent deletion that the user should see and confirm, and
  because ADR-0002 keeps ais out of Claude Switcher's files.
- Exit code when Claude.app is missing: 69 (see builder-check answer 5).

## Migration guide contents (`docs/migrate-from-claude-switcher.md`)
Order matters; each step says how to check it.
1. Before removing anything: `ais status` shows both terminal accounts
   signed in, and `ais desktop work` opens a Work Desktop where the user has
   signed in.
2. Quit Claude Switcher and its Work Desktop window.
3. Remove the app (`/Applications/Claude Switcher.app`) and its login item,
   if any.
4. Remove `~/.config/claude-switcher/`.
5. Optional, last: remove `~/Library/Application Support/Claude-work` (Claude
   Switcher's Work Desktop data). Say plainly that this deletes that
   window's local data and sign-in.
6. Keep: `~/.claude-accounts/work` and Keychain item
   `Claude Code-credentials-f9fb4ac6` (ais uses them), the default
   `Claude Code-credentials` item, `~/.claude`, `~/.claude.json`.
7. Other `Claude Code-credentials-<8 hex>` Keychain items: how to list them
   (names only) and match each against the known credDir hashes; remove
   only those the user can identify as unused, by hand in Keychain Access.
8. Remove the spike's throwaway pieces: `~/Library/Application Support/Claude-ais-spike`,
   `~/.claude-accounts/spike` Keychain item (`…-8cef0543`), `~/SwiftBarPlugins/ais-probe.1m.sh`.

## Documents this change touches
- `docs/brief.md`: non-goal 1 becomes "No claude.ai web chat; Claude Desktop
  only as one separate instance per account (no shared Desktop session
  list)"; MVP bullet 4 or a new bullet mentions the Desktop instances.
- `docs/requirements.md`: new FRs for `ais desktop` (launch, duplicate rule,
  missing app, dry-run), the menu items, and the migration guide; FR-5.3 and
  FR-5.4 updated; Review log entry.
- New ADR-0008: Desktop instances via `--user-data-dir`.
- ADR-0002: amendment for the credDir finding (`claude` does not create it
  and does not need it).
- `docs/architecture.md`: the new provider methods and command.
- The plan: new tasks after the CLI is complete and before or with the menu
  tasks.

## Builder-check answers (2026-10-16; controller's calls unless marked)
1. Which account is "default": the account with `Account.is_default`, the one
   `config.json` `default` names, whose credDir is null (FR-1.2, ADR-0002).
   Only that account launches without `--user-data-dir`. Every other account,
   including one renamed later, gets `Claude-ais-<account>`.
2. Default launch: `open -n -a <app>` with no `--user-data-dir` (code review,
   PR #5: without `-n`, macOS only fronts an already-running Work instance,
   so Personal would never open). Detection for the default: a `…/Contents/MacOS/Claude` process whose
   args have no `--user-data-dir`. `Claude Helper…` processes never match.
   Tests use a `ps` fixture with helpers, Claude Switcher's instance and
   ais instances mixed.
3. `ps` parsing: one `ps -x -ww -o pid=,args=` call (`-x`: Desktop has no terminal, plain `ps` omits it). The data folder is the
   text after `--user-data-dir=` up to the next ` --` or the end of the line
   (paths contain spaces). Compare it with the account's folder exactly.
4. `--dry-run`: runs the read-only duplicate check, then prints either the
   launch command or the "already open" message. Never launches.
5. App location: use the first of `/Applications/Claude.app` and
   `~/Applications/Claude.app` that exists, and launch by that path. Neither
   exists: exit 69, `Claude Desktop not found in <roots searched, joined by
   " or ">`.
6. Menu: one `Open <label> Desktop` item per account, always shown, action
   `bash=<ais path> param1=desktop param2=<account> terminal=false`. Only the
   validated account name goes into the action (FR-4.12 holds). The command
   itself handles "already open" and "app missing".
7. Exit codes: unknown account 64 (existing rule); `open` fails or times out
   (10 s): 69 with `open`'s stderr; already open: 0.
8. Order: the user approves this document first. Then the brief,
   requirements, ADR-0008, ADR-0002 amendment and architecture changes, then
   the plan tasks, then code. (Answered by the repo rules.)

## Left to the builder
- How to bring an already-running instance to the front without a
  permission prompt, or whether to only print the message.
- Exact provider method names and the `ps` parsing.
- Where the new tasks sit in the plan and how they split.
