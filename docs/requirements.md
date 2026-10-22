# Requirements: AI Account Switcher (v0.4, 2026-10-16)
Status: Approved 2026-10-16

Inputs: `docs/brief.md` (approved 2026-10-16, changed 2026-10-16) and
`docs/superpowers/specs/2026-10-16-ai-account-switcher-design.md`
(approved 2026-10-16). v0.3 applied the architecture review; v0.4 applies
the plan reviews (see Review log).

Terms used below:
- **Default account:** runs with Claude Code's normal Keychain slot
  (`CLAUDE_SECURESTORAGE_CONFIG_DIR` omitted entirely, never "").
- **Extra account:** has its own Keychain slot, chosen by its `credDir`.
- **credDir:** one canonical absolute path string stored in `config.json`
  (no `~`, no trailing slash, NFC). ais passes exactly this string to
  `claude`; realpath is used only to validate it. A different spelling of
  the same folder is a different Keychain slot.
- **Session folder:** the `cwd` recorded in the first transcript line that
  has one.
- **Session ID resolution:** the provider scans top-level `*.jsonl` files
  in every `~/.claude/projects/*/` folder (subfolders such as subagent
  transcripts are excluded), keeps those whose session folder has the same
  realpath as the current folder, and picks the newest by modified time.
  Session folder and title per file are cached in `cache.json`, keyed by
  path, modified time and size. No folder-name encoding is assumed.
- **Last-used account:** the account ais last launched for a session,
  recorded in `~/.config/ais/state.json`. With no record it is **unknown**.
- **Open session:** a session whose session folder is the cwd of a running
  `claude` process (one batched `pgrep` plus `lsof -a -d cwd` per call).
  Conservative: one running `claude` in a folder marks every session of
  that folder open.
- **Switch mutex:** an `fcntl.flock` on `~/.config/ais/switch.lock`, held
  from the open check until `claude` has been started, so two switches
  (for example a double click in the menu) cannot both pass the check.
- **Title:** the first user prompt line of the transcript, cut to 60
  characters and sanitized (FR-4.12).
- **Child environment:** the environment ais passes to `claude`, built by
  the provider's `env_for`.

Exit codes (ais's own, from the sysexits range to make clashes with
`claude`'s unlikely): 0 ok; 64 bad input; 65 declined by the user; 66
nothing to resume or session not found; 69 `claude` not found; 71 SwiftBar
missing; 73 cannot write a file; 75 session open; 77 billing guard; 78
config error. After `claude` runs, ais exits with `claude`'s own exit
code, or 128+N when `claude` was killed by signal N.

## Build gates (before any FR work)

- G-1 **Spike.** A throwaway spike on the user's Mac SHALL prove, and
  record in `docs/spike-results.md` (emails, organisation and account IDs
  and unrelated Keychain entries redacted; raw output kept out of git):
  - (a) whether `/login` inside a running session switches accounts and
    keeps the conversation;
  - (b) that `CLAUDE_SECURESTORAGE_CONFIG_DIR` gives an extra account its
    own Keychain item, the exact string form Claude Code hashes, the
    resulting service name, and whether `claude` creates the credDir
    folder itself;
  - (c) that `claude --resume <id>` under the other account continues a
    session started by the first and keeps appending to the same
    `<id>.jsonl` (no new file); including a transcript cut off
    mid-tool-call (simulated by SIGKILL of `claude` during a long Bash
    tool call); whether `--resume` finds sessions from another folder; and
    what interactive `claude` does when the target account is at its limit
    or logged out;
  - (d) how `~/.claude.json` behaves with two accounts (shared vs per
    account);
  - (e) whether two accounts running different sessions at once corrupt
    any shared file, or overwrite each other's identity fields
    (`oauthAccount`, `userID`) in `~/.claude.json`, checked by diffing
    during and after 30 minutes of concurrent use;
  - (f) the tested Claude Code version range, and the environment
    variables and settings keys that change billing or the account in
    that range;
  - (g) how to detect a running `claude` and its cwd (`pgrep`,
    `lsof -a -d cwd -p`), with timings;
  - (h) `claude auth status`: output format, latency, network use, and
    whether it triggers a Keychain prompt when run from SwiftBar;
  - (i) SwiftBar: plugin folder lookup, refresh-interval file naming,
    Terminal action parameters, and the `PATH` plugins get;
  - (j) the text of the usage-limit message in transcripts, if any.

  What a failed item means:
  - (a) works: the user re-decides the MVP scope before building.
  - (b), (c) or (d) fails: the build stops until a new ADR picks another
    mechanism. IF (b) shows `claude` does not create the credDir THEN
    ADR-0002 is amended to let ais create only the empty folder (0700)
    after the FR-2.3 yes.
  - (e) fails: ais enforces one running `claude` at a time across all
    accounts (plan task 9, global lock).
  - (g) fails: ais cannot detect open sessions; FR-3.11 becomes a yes/no
    question ("Is Claude still running in <folder>?") and the menu shows no
    open badge.
  - (h) fails: the menu uses only the Keychain existence check.
  - (i) fails: the user decides whether the menu tasks stay in the MVP.
  - (j) has no marker: FR-3.14's end-to-end time is measured only by the
    manual check M2.
- G-2 **Terms.** The answer to brief open question 1 (Anthropic's Consumer
  Terms on switching between two personal accounts when a limit hits)
  SHALL be recorded, with the source link and date, in this file's Review
  log before FR work starts. IF the terms forbid it THEN the build SHALL
  stop.
- G-3 **Secondary account.** The secondary account's plan type SHALL be recorded in
  `docs/spike-results.md`. IF it is Team or Enterprise THEN the commercial
  terms and the employer's data policy SHALL be checked and recorded
  before FR work starts, and IF either forbids moving data between the
  accounts THEN the build SHALL stop.

## Functional requirements

### FR-1 Two accounts signed in side by side
User story: As a developer with two Claude Pro accounts, I want both signed in on my Mac at the same time so that switching never means logging out.
- FR-1.1 WHEN the user runs `ais login <account>` THE SYSTEM SHALL start the official `claude` login flow with that account's child environment.
- FR-1.2 WHEN building the child environment for an extra account THE SYSTEM SHALL set `CLAUDE_SECURESTORAGE_CONFIG_DIR` to the account's credDir string exactly as stored, default `/Users/<user>/.claude-accounts/<account>` (the convention Claude Switcher also uses, so its terminal logins are reused when the account name equals its lowercased label).
- FR-1.3 WHEN building the child environment for the default account THE SYSTEM SHALL remove `CLAUDE_SECURESTORAGE_CONFIG_DIR` if inherited, and print a one-line warning that it was removed.
- FR-1.4 WHEN one account signs in THE SYSTEM SHALL leave the other account's Keychain item unchanged.
- FR-1.5 IF `<account>` is not defined in `~/.config/ais/config.json`, or does not match `^[a-z][a-z0-9-]{0,31}$`, THEN THE SYSTEM SHALL exit with code 64, print the defined account names, and not start `claude`.
- FR-1.6 IF the `claude` command is not on `PATH` THEN THE SYSTEM SHALL exit with code 69 and print how to install Claude Code.
- FR-1.7 IF a credDir in `config.json` is not absolute, contains `~`, ends with `/`, is not NFC, or resolves outside the user's home folder, or `config.json` has an unknown `version`, THEN THE SYSTEM SHALL exit with code 78 and name the account and the rule.
Verification: `python3 -m unittest tests.test_accounts tests.test_providers` passes, including an NFD-path test; manual check M1 in `docs/manual-checks.md` (both accounts show a credential present after logging in to each).

### FR-2 One shared brain, set up safely
User story: As a developer, I want both accounts to use the same `~/.claude` so that sessions, memory, CLAUDE.md, skills, subagents and settings are identical whichever account runs.
- FR-2.1 WHEN the tool starts `claude` under any account THE SYSTEM SHALL leave `CLAUDE_CONFIG_DIR` unset in the child environment; IF it is inherited THEN THE SYSTEM SHALL remove it and print a one-line warning.
- FR-2.2 IF any billing or account risk the provider reports is present THEN THE SYSTEM SHALL refuse to start `claude` (exit code 77) and name the setting, unless `--allow-api-key` is passed. For Claude the risks are: `ANTHROPIC_API_KEY`, `ANTHROPIC_AUTH_TOKEN`, `ANTHROPIC_BASE_URL`, `CLAUDE_CODE_OAUTH_TOKEN`, `CLAUDE_CODE_USE_BEDROCK`, `CLAUDE_CODE_USE_VERTEX`, the other provider switches (`CLAUDE_CODE_USE_FOUNDRY`, `CLAUDE_CODE_USE_MANTLE`, `CLAUDE_CODE_USE_ANTHROPIC_AWS`, `CLAUDE_CODE_USE_GATEWAY`, `CLAUDE_CODE_USE_ANTHROPIC_GOOGLE_CLOUD`), credential variables (`CLAUDE_CODE_OAUTH_REFRESH_TOKEN`, `CLAUDE_CODE_OAUTH_SCOPES`, `ANTHROPIC_FOUNDRY_API_KEY`, `ANTHROPIC_FOUNDRY_AUTH_TOKEN`, `ANTHROPIC_AWS_API_KEY`, `AWS_BEARER_TOKEN_BEDROCK`, `ANTHROPIC_CUSTOM_HEADERS`, `ANTHROPIC_PROFILE`, `ANTHROPIC_FEDERATION_RULE_ID`, `ANTHROPIC_ORGANIZATION_ID`, `ANTHROPIC_WORKSPACE_ID`, `CLAUDE_CODE_OAUTH_TOKEN_FILE_DESCRIPTOR`, `CLAUDE_CODE_API_KEY_FILE_DESCRIPTOR`, `ANTHROPIC_IDENTITY_TOKEN`, `ANTHROPIC_IDENTITY_TOKEN_FILE`, `CLAUDE_CODE_ACCOUNT_UUID`, `CLAUDE_CODE_ORGANIZATION_UUID`), endpoints (`ANTHROPIC_BEDROCK_BASE_URL`, `ANTHROPIC_VERTEX_BASE_URL`, `ANTHROPIC_FOUNDRY_BASE_URL`, `ANTHROPIC_FOUNDRY_RESOURCE`, `ANTHROPIC_AWS_BASE_URL`, `ANTHROPIC_BEDROCK_MANTLE_BASE_URL`) or `ANTHROPIC_CONFIG_DIR`, `CLAUDE_CODE_PROVIDER_MANAGED_BY_HOST` in the environment; `apiKeyHelper`, `forceLoginMethod`, `forceLoginOrgUUID`, `awsAuthRefresh`, `awsCredentialExport`, `gcpAuthRefresh` or one of those variables in an `env` block of any settings scope (`~/.claude/settings.json`, `~/.claude/settings.local.json`, `<folder>/.claude/settings.json`, `<folder>/.claude/settings.local.json`, the `.claude/settings.local.json` of the nearest ancestor holding `.git`, found from the folder as given and from its realpath (skipped when it is the folder itself), plus that of the main checkout when that `.git` is a worktree file, `/Library/Application Support/ClaudeCode/managed-settings.json`, every `/Library/Application Support/ClaudeCode/managed-settings.d/*.json`, the managed preferences profile `com.anthropic.claudecode`); a non-null `primaryApiKey` in `~/.claude.json`; and `--settings`, `--settings=<file>` or `--bare` in passed-through arguments; a settings file that cannot be read or parsed is also reported. The settings roots are injectable for tests.
- FR-2.3 WHEN the user runs `ais setup` THE SYSTEM SHALL list every file and folder it will create, and ask for a yes before writing anything; IF the answer is not yes THEN it SHALL write nothing and exit with code 65.
- FR-2.4 WHEN setup runs THE SYSTEM SHALL guide the user step by step: offer any existing `~/.claude-accounts/*` folders as credDirs, ask for the account names and labels (recommended `primary` as the default account, `secondary` as extra), check each with `claude auth status` under its environment, start the sign-in only for accounts that are not logged in, and write `config.json` (schema below).
- FR-2.5 WHEN setup finishes THE SYSTEM SHALL print, only if `~/.local/bin` is not on `PATH`, the line `export PATH="$HOME/.local/bin:$PATH"` for `~/.zshrc` with what it does; it SHALL NOT edit `~/.zshrc` and SHALL NOT suggest exporting any account variable.
- FR-2.6 WHEN ais creates `~/.config/ais/` or any file in it THE SYSTEM SHALL use mode 0700 for directories and 0600 for files.
- FR-2.7 WHEN setup finishes THE SYSTEM SHALL state that shared memory, CLAUDE.md and settings are sent with every session on either account, not only on resume.
- FR-2.8 WHEN ais is about to resume a session on a different account than its last-used account, for an account pair with no acknowledgement yet, THE SYSTEM SHALL show that the full transcript will be sent under the other account, ask for a yes (without holding any lock), and record the acknowledgement for that pair in `config.json`; IF the answer is not yes THEN it SHALL exit with code 65.
- FR-2.9 IF a write to `~/.config/ais/` fails THEN THE SYSTEM SHALL remove any partial file, print the path and the error, and exit with code 73.
Verification: `python3 -m unittest tests.test_env tests.test_setup tests.test_ack` passes.

Config schema (`config.json`): `{"version": 1, "default": "<account>", "accounts": {"<account>": {"label": "<text>", "provider": "claude", "credDir": "<canonical absolute path, or null for the default account>"}}, "cross_account_ack": {"<from>-><to>": "<ISO date>"}, "menu_privacy": false}`. A third account is added by adding one entry under `accounts`.

### FR-3 One-command switch, resume and run
User story: As a developer who just hit a usage limit, I want one command to reopen the same session on my other account so that the agent keeps going without me re-explaining.
- FR-3.1 WHEN the user runs `ais switch` in a folder with exactly 2 accounts configured THE SYSTEM SHALL resolve the newest session ID for that folder and run `claude --resume <id>` under the account that is not the session's last-used account; IF the last-used account is unknown (with the FR-3.21 hook installed, only a session started before the hook, from Claude Desktop or an IDE, or on a slot no account uses) THEN it SHALL treat the default account as last-used (a plain `claude` runs on the default account) (amended 2026-10-19, #81: the #79 `AIS_ACCOUNT` assumption is removed, it could name the account of another window), print a one-line note saying so, and resume under the other account; the FR-2.8 prompt then applies as for a recorded default account.
- FR-3.2 WHEN the user runs `ais switch <account>` THE SYSTEM SHALL resolve the session the same way and resume it under the named account, treating an unknown last-used account as in FR-3.1 (the note is printed only when the FR-2.8 prompt can follow); IF that is the session's last-used account THEN it SHALL resume there (useful after a crash) without the FR-2.8 prompt.
- FR-3.3 WHEN the user runs `ais switch --pick [account]` THE SYSTEM SHALL list the 5 newest sessions for the folder (number, time, title, last-used account, open or not), read a number, and resume that session; IF the input is not a listed number THEN it SHALL exit with code 64.
- FR-3.4 WHEN the user runs `ais switch --session <id> [account]` THE SYSTEM SHALL find that session's transcript, validate its session folder (realpath, existing directory, not a symlink escape), change into it, and resume; IF `<id>` is not a UUID THEN it SHALL exit with code 64, and IF the transcript or folder is not found THEN with code 66.
- FR-3.5 WHEN the user runs `ais run [account] [-- args]` THE SYSTEM SHALL start a new `claude` session with the args under the named account (default: the default account), and after `claude` exits record the account as last-used for the transcript in that folder created after the launch time.
- FR-3.6 WHEN ais starts `claude` for a switch THE SYSTEM SHALL hold the switch mutex from the open check until `claude` has started, record the account as last-used for the session, print the account label, and set the terminal tab title to `claude (<label>)` (best effort; not tested).
- FR-3.7 WHEN ais resumes a session THE SYSTEM SHALL first snapshot the files the provider names for it (transcript and its `<id>/` folder) into `~/.config/ais/snapshots/`, as an APFS clone (`cp -c`) where possible and a plain copy otherwise, keeping at most 20 snapshots, 500 MB in total and 30 days; IF free disk space is below twice the size of a plain copy and cloning is unavailable THEN it SHALL warn and continue without the snapshot.
- FR-3.8 WHILE `claude` runs THE SYSTEM SHALL start `claude` with default signal handlers, then ignore SIGINT and SIGQUIT in ais only, forward SIGHUP and SIGTERM to `claude`, and release any held lock when `claude` exits or ais is terminated.
- FR-3.9 IF more than 2 accounts are configured and no account is named THEN THE SYSTEM SHALL exit with code 64 and list the accounts.
- FR-3.10 IF no session exists for the folder THEN THE SYSTEM SHALL exit with code 66 and print that there is nothing to resume, without starting `claude`.
- FR-3.11 IF the target session is open THEN THE SYSTEM SHALL refuse with exit code 75 and print "Claude is still running in <folder> (PID <n>). Type /exit there, then run `ais switch` again.", without starting `claude`. The daemon (`claude daemon`) and `bg-*` helpers are ignored (judged by argv), and a Claude Desktop embedded session in the folder counts as open.
- FR-3.12 IF the target account is logged out THEN THE SYSTEM SHALL still start `claude` and let Claude Code's own login appear; `switch` and `run` SHALL NOT run a credential check.
- FR-3.13 IF the Claude Code version is outside the tested range (a constant in `providers/claude.py`) THEN THE SYSTEM SHALL print a one-line warning and continue.
- FR-3.14 WHEN a switch starts `claude` THE SYSTEM SHALL log the tool time (from ais start to the `claude` spawn); WHERE G-1(j) found a usage-limit marker THE SYSTEM SHALL also log, after `claude` exits, the end-to-end time from the last limit message before the launch to the first line appended after it.
- FR-3.15 IF `ais run` is given `--resume`, `-r`, `--continue`, `-c`, `--settings` or `--settings=<file>` among the passed-through arguments THEN THE SYSTEM SHALL exit with code 64 and point to `ais switch`, unless `--allow-api-key` is passed for `--settings`.
- FR-3.16 (added 2026-10-19, #77) WHEN the user runs `ais shell-init` THE SYSTEM SHALL print a snippet for zsh and bash, meant for `eval "$(ais shell-init)"` in `~/.zshrc`, that removes any `ais` or `claude` alias (an alias would win over the function) and defines two shell functions: `ais`, which for `ais use <account>` runs `ais use --shell <account>`, and only if that exits 0 evals its output in the current shell and then runs `ais run <account>`, returning its exit code (any other `ais` command runs unchanged); and `claude`, which WHILE `AIS_ACCOUNT` is set and no arguments are given runs `ais run "$AIS_ACCOUNT"`, WHILE `AIS_ACCOUNT` is set and `ais run --dry-run "$AIS_ACCOUNT" -- <args>` exits 0 or 77 (FR-2.2 billing refusal, which `ais run` then prints) runs `ais run "$AIS_ACCOUNT" -- <args>` so last-used is recorded (amended 2026-10-19, #79), and otherwise runs `claude` with its arguments unchanged (its session is then recorded by the FR-3.21 hook).
- FR-3.17 (added 2026-10-19, #77) WHEN the user runs `ais use --shell <account>` THE SYSTEM SHALL print to stdout the shell commands that make the current environment match that account's child environment (FR-1.2, FR-1.3): `export NAME=value` for each variable it sets or changes, `unset NAME` for each it removes, values shell-quoted, then `export AIS_ACCOUNT=<account>`; and print `This terminal: <label>` to stderr. IF the account is unknown THEN it SHALL exit 64 and print nothing to stdout. Only the shell that evals the output changes; other terminal windows keep their own setting.
- FR-3.18 (added 2026-10-19, #77) WHEN the user runs `ais use <account>` without `--shell` (the FR-3.16 function is not loaded) THE SYSTEM SHALL print a one-line warning that this terminal was not set and that `eval "$(ais shell-init)"` in `~/.zshrc` sets it, then behave as `ais run <account>`.
- FR-3.19 (added 2026-10-19, #77) WHEN the user runs `ais use` with no account THE SYSTEM SHALL print `This terminal: <label>` for the account named by `AIS_ACCOUNT`, or `This terminal: <default label> (default)` when `AIS_ACCOUNT` is unset or names no configured account.
- FR-3.20 (added 2026-10-19, #77) WHEN the user runs `ais use --copy <account>` THE SYSTEM SHALL put the text `ais use <account>` on the clipboard with `pbcopy` and start nothing; IF the account is unknown THEN it SHALL exit 64.
- FR-3.21 (added 2026-10-19, #81, ADR-0010) WHEN Claude Code's SessionStart hook (FR-5.7) runs `ais record` THE SYSTEM SHALL read the hook's stdin JSON (at most 64 KiB), and WHERE `CLAUDE_CODE_ENTRYPOINT` is unset or `cli`, `session_id` is a lowercase UUID and `transcript_path` is `<session_id>.jsonl` in a folder whose realpath is directly under `~/.claude/projects`, record as the session's last-used account the configured account whose stored credDir equals `CLAUDE_SECURESTORAGE_CONFIG_DIR` exactly, or the default account when that variable is unset, and log one line; in every other case (another entrypoint such as `claude-desktop`, a credDir no account uses, `""`, bad input, no or broken config) it SHALL record nothing. It SHALL print nothing and exit 0 in all cases.
Verification: `python3 -m unittest tests.test_switch tests.test_run tests.test_open tests.test_signals tests.test_snapshots` passes, including an open session started without ais, a fake `claude` that relies on the default SIGINT handler, and both `--settings` forms; manual check M2 in `docs/manual-checks.md` (session started on primary continues on secondary with the prior conversation visible, under 30 seconds end to end, timed by hand).

### FR-4 Status at a glance
User story: As a developer, I want one command and a menu bar item that show which account a session last used and whether each account has a credential so that I never run on the wrong account by surprise.
- FR-4.1 WHEN the user runs `ais status` THE SYSTEM SHALL print each account with `credential present: yes|no|unknown`, the newest session for the current folder with its last-used account (or `unknown`) and whether it is open, and the result of the provider self-check, plus one line: `ais cannot see which account each slot is signed in to; sign in to the matching account in each` (G-1(h): no tool output tells two slots on the same account apart).
- FR-4.2 WHEN `ais status` checks for a credential THE SYSTEM SHALL use only the `loggedIn` field and exit code of `claude auth status` under the account's environment, never its `email`, `orgId`, `orgName` or `subscriptionType` (those come from the shared `~/.claude.json` and follow the last `/login`, G-1(h)), cached for 10 minutes in `cache.json` (cache owned by `core.py`); IF that command is missing, exits non-zero or takes longer than 10 s THEN it SHALL fall back to testing whether the account's Keychain item exists (service-name formula is a constant in `providers/claude.py`); it SHALL NOT call `security` with any flag that prints a secret (`-w`, `-g`).
- FR-4.3 WHEN printing `credential present` THE SYSTEM SHALL state that it is not a validity check when it came from the Keychain fallback.
- FR-4.4 IF the Keychain check fails for a reason other than "item not found" THEN THE SYSTEM SHALL print `unknown` and the error for that account, and exit with code 0.
- FR-4.5 IF the self-check finds the Claude Code version outside the tested range, or an extra account's credDir failing FR-1.7, THEN THE SYSTEM SHALL print a warning naming each problem.
- FR-4.6 WHERE `--json` is passed THE SYSTEM SHALL print `{"accounts": [{"name", "label", "credential_present"}], "session": {"id", "last_used", "open"} | null, "recent": [{"id", "folder", "title", "last_used", "open", "modified"}], "self_check": {"ok", "messages"}}`, where `recent` lists the 5 newest sessions across all folders.
- FR-4.7 WHEN the user runs `ais menu install` THE SYSTEM SHALL show the plugin file it will write into SwiftBar's plugin folder, ask for a yes, write `ais.1m.sh` (a script that sets an explicit `PATH` of `~/.local/bin`, the folder of `claude`, `/usr/bin`, `/bin`, `/usr/sbin` and `/sbin`, so `lsof`, `pgrep` and `ps` are found, then runs `exec ais menu render`, with SwiftBar metadata lines `hideLastUpdated`, `hideRunInTerminal`, `hideDisablePlugin`, `hideAbout` and `hideSwiftBar` set to `true` so SwiftBar adds none of its own menu items (amended 2026-10-18, #71)), and record the install in `state.json`; `ais menu uninstall` SHALL remove only that file after a yes.
- FR-4.8 WHEN SwiftBar runs `ais menu render` THE SYSTEM SHALL print in SwiftBar's format: in the menu bar, only the SF Symbol `gauge.medium` (amended 2026-10-18, #57: was the label of the account that last ran the newest session, or `ais` when none); in the menu, the account groups of FR-4.15, and under each closed session one `Resume in <account>` item per other account whose action runs, in a new Terminal window, `ais switch --session <id> <account>` with only the validated UUID and account name as arguments. (Amended 2026-10-18: was a flat list of the 5 recent sessions with folder, title, last-used account and an `open` badge.)
- FR-4.9 WHEN `ais menu render` checks credentials THE SYSTEM SHALL use only the cached `claude auth status` result or the Keychain existence check, never start a sign-in, and never prompt.
- FR-4.10 IF SwiftBar is not installed or its plugin folder is not set THEN `ais menu install` SHALL exit with code 71, print `brew install --cask swiftbar` and how to pick a plugin folder, and install nothing (ais never installs SwiftBar).
- FR-4.11 WHEN `ais menu render` runs THE SYSTEM SHALL give every subprocess an explicit timeout, kill its process group on timeout, finish within 5 s, and on any failure or timeout print `ais ⚠` in the menu bar with the error line and no switch actions, then exit without waiting for leftover work.
- FR-4.12 WHEN rendering any value taken from a transcript or the file system (title, folder) THE SYSTEM SHALL remove `|`, newlines and all control characters, and SHALL NOT place it in any action parameter.
- FR-4.13 WHERE a session is open THE SYSTEM SHALL show, instead of resume items, one disabled item "Quit Claude in <folder> to resume".
- FR-4.14 WHERE `menu_privacy` is true in `config.json` THE SYSTEM SHALL show only account labels, credential states and session counts, without folders or titles; the counts cover only sessions with a configured owner, as FR-4.15 shows (amended 2026-10-18, #71).
- FR-4.15 (added 2026-10-18, #54) WHEN `ais menu render` prints the menu with `menu_privacy` off THE SYSTEM SHALL take the 30 newest sessions across all folders and group them by owning account (FR-4.19; until then the last-used account): per account, in `config.json` order, a header line `<label>` when its credential is `yes`, else `<label> · credential no` or `<label> · credential unknown`, followed by ` · updated <relative time>` when FR-4.20 shows usage bars, then a `Sessions (<n>)` item whose submenu lists that account's up to 10 newest sessions; sessions with no known owner are not shown; a group with no sessions prints its header but no `Sessions` item. (Amended 2026-10-18, #71: was `✓ <label>`, and unknown-owner sessions went under an `Other sessions (account unknown)` item.) Each session item reads `<title> · open` or `<title> · <relative time>` (FR-4.16), where `<title>` is the session's title or, without one, its shortened folder (FR-4.17); its submenu holds the shortened folder as a plain line with no action, then the Resume items (FR-4.8) or the disabled Quit item (FR-4.13).
- FR-4.16 (added 2026-10-18, #54) WHEN showing a session's age THE SYSTEM SHALL use its transcript's modified time against the render time: `just now` under 1 minute or in the future, `<n> min ago` under 60 minutes, `<n> h ago` under 48 hours, else `<n> d ago`, with `n` rounded down; a missing time shows no age (`<title>` alone).
- FR-4.17 (added 2026-10-18, #54) WHEN showing a folder or title in the menu THE SYSTEM SHALL sanitize it (FR-4.12), show a folder under the home folder as `~/…`, shorten a folder longer than 48 characters that has at least one component between its first and last to `<first component>/…/<last component>` (for example `~/…/ais-task-20-docs-ee1c1a`), cut a title longer than 50 characters to 49 and add `…`, and strip leading `-` from any untrusted text that starts a menu item.
- FR-4.18 (added 2026-10-18, #56) WHEN at least one account's Claude Desktop instance is running (FR-6.2 detection, from the same single `ps` call) THE SYSTEM SHALL print `Running: <label>, <label>` in config order as the first menu line; with none running it prints no such line, and IF the `ps` call fails THEN it prints no such line and adds no warning.
- FR-4.19 (added 2026-10-18, #55) WHEN `ais menu render` lists sessions THE SYSTEM SHALL read, for each account whose Desktop data folder (FR-6.1, FR-4.21) exists, the account UUID from that folder's `config.json` key `lastKnownAccountUuid` and the session records `claude-code-sessions/<that UUID>/*/local_*.json` (at most 1,000 files, each at most 1 MB); a record whose `cliSessionId` equals a listed session's ID and whose `isArchived` is not `true` makes that account the session's owner and its `title` the session's title, sanitized (FR-4.12). An ais record in `state.json` wins over a Desktop record for the owner; when two accounts' records name the same session, the one with the newer `lastActivityAt` wins. IF a folder, `config.json` or record is missing, unreadable, too large or not the expected JSON THEN THE SYSTEM SHALL skip it without a warning. These files are only read, never written.
- FR-4.20 (added 2026-10-18, #57) WHERE an account's Desktop data folder holds `plan-usage-history.json` (at most 2 MB, `{"version": 2, "samples": [{"t": <ms>, "org": <uuid>, "u": {"fh": <0-100>, "sd": <0-100>}}]}`) THE SYSTEM SHALL show under that account's header the newest sample (largest `t`) as two items `5h  <fh>%` and `week  <sd>%`, each with a drawn bar as its SwiftBar `image` (a base64 PNG 120 × 8 points, stored at 2× with 144 dpi: a gray track filled from the left in proportion to the value, blue below 80, orange from 80, red from 90), values clamped to 0 to 100, with the header line ending in ` · updated <relative time>` (FR-4.16; amended 2026-10-18, #71: was a line of its own after the bars); a missing key shows `?` and an empty bar. (Amended 2026-10-18: was a 10-cell `█░` text bar and `as of`; red was at 100 only, now from 90 to follow Claude Desktop's menu, red at 92 and not at 85.) IF the newest sample is older than 24 hours THEN it SHALL show `usage: no sample in the last 24 h` instead; IF the file is missing, too large or not the expected JSON THEN it SHALL show nothing for usage. The usage lines are also shown when `menu_privacy` is true. ais SHALL NOT estimate reset times or forecast usage, and SHALL NOT fetch usage itself.
- FR-4.21 (added 2026-10-18, #55) WHERE an extra account in `config.json` has `desktop_data_dir` (an absolute path, no `~`, whose realpath is a folder directly under `~/Library/Application Support`) THE SYSTEM SHALL use exactly that string, instead of the derived `Claude-ais-<account>` folder, for `ais desktop` (FR-6.1, FR-6.2) and FR-4.18 to FR-4.20. IF it is set on the default account, or fails that check THEN THE SYSTEM SHALL exit 78 naming the account and the key. This lets ais use the Work Desktop that Claude Switcher created (`Claude-Work`) before or instead of the migration guide.
- FR-4.22 (added 2026-10-18, #57) WHEN `ais menu render` prints the menu THE SYSTEM SHALL give these items an SF Symbol icon through SwiftBar's `sfimage`: each account header `person.crop.circle`, each `Sessions` item `list.bullet`, each `Resume in` item `play.fill`, each `Open … Desktop` item `desktopcomputer` (amended 2026-10-19, #83: dropped `terminal` with the `Open … Terminal` item). Icon names are fixed strings, never built from untrusted text.
- FR-4.23 (added 2026-10-18, #71; removed 2026-10-19, #83: the FR-4.24 Copy item replaces it) ~~WHEN `ais menu render` prints the menu THE SYSTEM SHALL add, after the `Open <label> Desktop` items (FR-6.5), one `Open <label> Terminal` item per account whose action is `bash=<ais path> param1=run param2=<account> terminal=true`, with only the validated account name as an argument; SwiftBar opens it in a new Terminal window in the home folder.~~
- FR-4.24 (added 2026-10-19, #77) WHEN `ais menu render` prints the menu THE SYSTEM SHALL add, after the `Open <label> Desktop` items (amended 2026-10-19, #83: was after the `Open <label> Terminal` items), one `Copy "ais use <account>"` item per account with SF Symbol `doc.on.clipboard`, whose action is `bash=<ais path> param1=use param2=--copy param3=<account> terminal=false` (FR-3.20), with only the validated account name in the title and as an argument.
Verification: `python3 -m unittest tests.test_status tests.test_menu` passes, including a test that fails if any `security` call includes `-w` or `-g`, a render test from a fixed status, a test with a malicious title and folder (`| bash=/bin/sh`, newlines), a fake `lsof` that sleeps forever, and the privacy mode; manual check M3 in `docs/manual-checks.md` (menu shows both accounts and a working `Resume in Secondary`).

### FR-5 Built for more AIs, reversible install
User story: As a developer who may add another AI tool later, I want providers to be pluggable and the install to be fully undoable so that growth is cheap and trying it is safe.
- FR-5.1 WHEN any command needs provider behaviour THE SYSTEM SHALL call it only through the provider interface: `env_for`, `billing_risks`, `resume_command`, `start_command`, `login_command`, `newest_session`, `recent_sessions`, `find_session`, `open_session_pid`, `has_credential`, `snapshot_paths`, `self_check`, `limit_time`, for FR-3.21 and FR-5.7 `hook_session`, `hook_settings_path`, `add_start_hook`, `remove_start_hook`, and for FR-6 `desktop_data_dir`, `desktop_launch_command`, `desktop_running_pid`.
- FR-5.2 WHEN loading providers THE SYSTEM SHALL use a static name-to-module table in code; IF a provider name in `config.json` is not in the table THEN it SHALL exit with code 78 and list the registered providers.
- FR-5.3 WHEN the user runs `ais uninstall` THE SYSTEM SHALL list what it will remove, ask for a yes, remove `~/.config/ais/` (asking separately whether to delete `snapshots/`, and printing their location and size when kept), remove the SwiftBar plugin file if `state.json` records that ais installed it, remove ais's SessionStart hook as `ais hook uninstall` does (FR-5.8; amended 2026-10-19, #81), leave the rest of `~/.claude`, `~/.claude.json`, `~/.claude-accounts/` and all Keychain items untouched, and print the manual steps to remove `~/.local/bin/ais` and `~/.local/bin/ais.prev`, `~/.claude-accounts/<account>`, the extra Keychain item and the `~/.zshrc` line, and list the Desktop data folders `~/Library/Application Support/Claude-ais-<account>` (kept: they hold the Desktop sign-in).
- FR-5.4 WHERE `--dry-run` is passed to `setup`, `switch`, `run`, `login`, `desktop`, `menu install`, `menu uninstall`, `hook install`, `hook uninstall` or `uninstall` THE SYSTEM SHALL print what it would do and change nothing (`desktop` still runs its read-only running-instance check).
- FR-5.5 IF uninstall cannot remove a file THEN THE SYSTEM SHALL stop, print the path and the error, leave the remaining files in place, and exit with code 73.
- FR-5.6 WHEN ais reads, changes and writes `state.json`, `config.json` or `cache.json`, or rotates `ais.log`, THE SYSTEM SHALL hold an `fcntl.flock` on `~/.config/ais/.lock` for the whole operation, never while waiting for user input, and SHALL drop `state.json` entries whose transcript no longer exists, except entries written less than 24 hours ago (amended 2026-10-19, #81: `ais record` writes before Claude Code creates the transcript).
- FR-5.7 (added 2026-10-19, #81, ADR-0010) WHEN the user runs `ais hook install` THE SYSTEM SHALL print the target file and the hook command `[ -x "$HOME/.local/bin/ais" ] && "$HOME/.local/bin/ais" record || true`, ask for a yes, and add one SessionStart group with no matcher holding that one command hook to `~/.claude/settings.json`, keeping every other key, hook and the key order; it SHALL write through a symlink to the file's realpath (temp file in that folder, fsync, rename, mode kept; a new file is 0600), never replacing the symlink; IF the hook is already there THEN it SHALL print so and change nothing; IF the realpath is outside the user's home folder or not a regular file THEN it SHALL exit 73, and IF the file is not a JSON object or its `hooks` or `hooks.SessionStart` has the wrong type THEN with code 78, changing nothing; IF the answer is not yes THEN it SHALL exit 65. `ais setup` prints `ais hook install` as a next step.
- FR-5.8 (added 2026-10-19, #81) WHEN the user runs `ais hook uninstall` THE SYSTEM SHALL remove, after a yes, every command hook whose command is exactly the FR-5.7 command, then any SessionStart group, `hooks.SessionStart` and `hooks` that this left empty, writing as FR-5.7 does; IF no such hook is there THEN it SHALL print so and change nothing.
Verification: `python3 -m unittest tests.test_providers tests.test_uninstall tests.test_dry_run tests.test_flock` passes; a fake second provider in the tests is added by one module plus one table entry.

### FR-6 Claude Desktop per account (added 2026-10-16, design `docs/superpowers/specs/2026-10-16-ais-desktop-design.md`, ADR-0008)
User story: As a user with two accounts, I want to open the Claude Desktop app for either account and keep both open side by side so that I can work on different projects in parallel and stop using Claude Switcher.
- FR-6.1 (amended 2026-10-18 by FR-4.21: `desktop_data_dir`, when set, replaces the derived folder) WHEN the user runs `ais desktop <account>` for the default account THE SYSTEM SHALL launch a new Claude Desktop instance with `open -n -a <app>` and no `--user-data-dir` (`-n` is required: without it macOS only brings an already-running instance, such as Work, to the front); for any other account it SHALL launch a new instance with `open -n -a <app> --args --user-data-dir=<home>/Library/Application Support/Claude-ais-<account>`, the folder derived from the account name and not stored in `config.json`.
- FR-6.2 IF a `…/Contents/MacOS/Claude` process (never a `Claude Helper` process) is already running for that account (args contain exactly `--user-data-dir=<that folder>`, or, for the default account, no `--user-data-dir`) THEN THE SYSTEM SHALL NOT launch a second instance, SHALL print `<label> Desktop is already open (PID n)`, and exit 0. Detection uses one `ps -x -ww -o pid=,args=` call (`-x`: Desktop has no terminal, and plain `ps` omits it); the folder is the text after `--user-data-dir=` up to the next ` --` or the end of the line.
- FR-6.3 IF `Claude.app` exists in none of the app roots (default `/Applications`, `~/Applications`) THEN THE SYSTEM SHALL exit 69 with `Claude Desktop not found in <the roots searched, joined by " or ">`; IF `open` fails or does not finish in 10 s THEN it SHALL exit 69 with `open`'s error text.
- FR-6.4 WHEN opening a Desktop instance THE SYSTEM SHALL NOT read, write or delete any Keychain item, `~/.claude`, `~/.claude.json`, `~/.claude-accounts/` or Claude Switcher's files; the user signs in inside the Desktop window. `ais desktop` changes no ais state, so it writes no log line (NFR-OPS).
- FR-6.5 WHEN `ais menu render` prints the menu THE SYSTEM SHALL add one `Open <label> Desktop` item per account whose action is `bash=<ais path> param1=desktop param2=<account> terminal=false`, with only the validated account name as an argument.
- FR-6.6 THE SYSTEM SHALL ship `docs/migrate-from-claude-switcher.md`, a step-by-step guide (no code) to remove Claude Switcher after ais works, in the order and with the keep list given in the design document.
Verification: `python3 -m unittest tests.test_desktop tests.test_menu tests.test_dry_run` passes, including a `ps` fixture with helper processes, Claude Switcher's instance and an ais instance whose path has spaces; manual check M6 in `docs/manual-checks.md` (Primary and Secondary Desktop side by side, a second `ais desktop secondary` does not start a duplicate).

## Non-functional requirements
- NFR-PERF: `ais switch` reaches the `claude` spawn in p95 < 1 s with a warm `cache.json` and APFS cloning, measured on the Mac in plan task 20 and logged as tool time (FR-3.14); `ais menu render` finishes in p95 < 2 s with up to 5,000 transcript files, run once a minute, measured on the Mac in task 20 (from 2026-10-18 also with up to 1,000 Desktop session records per account); end to end, a switch takes under 30 s (brief metric), timed by hand in M2.
- NFR-SEC: authn by Claude Code's own login flow only; authz: runs as the current macOS user, never `sudo`; input validated at the CLI boundary (account names `^[a-z][a-z0-9-]{0,31}$`, session IDs are UUIDs); allowed roots per path kind, checked with realpath: ais state under `~/.config/ais`, transcripts and session folders read under `~/.claude` and the user's home folder, credDir under the user's home folder, Claude Desktop data folders read only under `~/Library/Application Support` (only `config.json`'s `lastKnownAccountUuid`, `claude-code-sessions/<uuid>/*/local_*.json` and `plan-usage-history.json`, FR-4.19 to FR-4.21), the plugin file only in SwiftBar's configured plugin folder, the Claude Code user settings file written only at a realpath under the user's home folder (FR-5.7); secrets from macOS Keychain, never read, printed, logged or copied; files 0600, directories 0700; transcript and file-system text sanitized before it reaches the menu (FR-4.12); cross-account transcript sending only after the FR-2.8 acknowledgement; `ais run` cannot resume a session (FR-3.15).
- NFR-OPS: each state-changing command appends one line with `O_APPEND` (ISO 8601 UTC time, command name, account, session ID, result, tool time and end-to-end time when known; never passed-through arguments) to `~/.config/ais/ais.log`, rotated at 1 MB keeping 2 files under the FR-5.6 lock; `state.json` written by temp file plus rename under the same lock; metrics: tool time and end-to-end time per FR-3.14; RTO 5 minutes for a damaged session (restore its snapshot by following `docs/restore.md`); RPO: the last snapshot for a resumed session; ais writes nothing under `~/.claude` except its own SessionStart hook in `settings.json` (FR-5.7, FR-5.8; amended 2026-10-19, #81), so it adds no other data-loss risk; a `/config` change Claude Code writes at the same moment as `ais hook install` can be lost (ADR-0010).
- NFR-COST: $0 per month beyond the two existing Claude Pro subscriptions (checks run locally through the no-mistakes gate, no GitHub Actions; task 20's manual checks cover NFD paths and `pgrep`/`lsof` parsing; amended 2026-10-22, #90). `docs/usage.md` tells the user to run `/compact` before switching, because a resumed long session uses part of the other account's limit straight away.

Documents created by the plan: `docs/spike-results.md` (G-1 to G-3 answers),
`docs/manual-checks.md` (M1 to M6 step lists with expected results),
`docs/restore.md` (copy a snapshot back into `~/.claude/projects/`),
`docs/usage.md` (daily use: `/exit`, then `ais switch`; `/compact` advice).

## Out of scope
1. No claude.ai web chat. Claude Desktop only as one separate instance per account (FR-6); no single Desktop that switches accounts or lists both accounts' sessions; the ais menu lists both and `Resume in <account>` continues across accounts (`docs/usage.md`; rojcarranza/ai-account-switcher#1 stays open, design `docs/superpowers/specs/2026-10-19-desktop-both-accounts-design.md`).
2. No automatic switching when a limit hits; the user runs the switch command.
3. No second AI provider implemented; only the plug-in shape exists.
4. No native menu bar or GUI app; an optional SwiftBar plugin shows status and switch actions.
5. No sync across machines; one Mac, local files only.
6. No storing, reading or copying of passwords or tokens; logins stay in macOS Keychain and the official `claude` login flow.
7. No usage or limit forecasting or reset-time estimates, and no usage fetched by ais itself; the menu only shows the latest usage sample Claude Desktop saved (FR-4.20, changed 2026-10-18).
8. No more than 2 accounts tested in the MVP; the design must not block a third.

## Traceability: requirement -> task -> test
Plan: `docs/superpowers/plans/2026-10-16-ais-mvp.md`.

| Requirement | Task | Test |
|---|---|---|
| G-1, G-2, G-3 | 2 (fallback for G-1(e): 9) | `docs/spike-results.md`; `tests.test_global_lock` |
| FR-1.1, FR-1.4, FR-1.6 | 12 | `tests.test_login` |
| FR-1.2, FR-1.3, FR-2.1 | 5 | `tests.test_providers` |
| FR-1.5, FR-1.7 | 4 | `tests.test_accounts` |
| FR-2.2 | 5, 6 | `tests.test_providers`, `tests.test_env` |
| FR-2.3, FR-2.4, FR-2.5, FR-2.7 | 16 | `tests.test_setup` |
| FR-2.6, FR-2.9 | 3 | `tests.test_store` |
| FR-2.8 | 14 | `tests.test_ack` |
| FR-3.1 to FR-3.4, FR-3.6, FR-3.9 to FR-3.12, FR-3.14 | 14 (lookup 7, open check 8) | `tests.test_switch`, `tests.test_sessions`, `tests.test_open` |
| FR-3.5, FR-3.15 | 13 | `tests.test_run` |
| FR-3.16 to FR-3.20, FR-4.24 | #77 | `tests.test_use`, `tests.test_menu` |
| FR-3.21 | #81 | `tests.test_record` |
| FR-3.7 | 14 | `tests.test_snapshots` |
| FR-3.8 | 11 | `tests.test_signals` |
| FR-3.13 | 5 | `tests.test_providers` |
| FR-4.1, FR-4.5, FR-4.6 | 15 | `tests.test_status` |
| FR-4.2, FR-4.3, FR-4.4 | 10 | `tests.test_credentials` |
| FR-4.7, FR-4.10 | 19 | `tests.test_menu_install` |
| FR-4.8, FR-4.9, FR-4.11 to FR-4.14 | 18 | `tests.test_menu` |
| FR-4.15 to FR-4.22 | menu plan 1 to 4, #71 | `tests.test_menu`, `tests.test_desktop_records`, `tests.test_desktop` |
| FR-5.1, FR-5.2 | 5 | `tests.test_providers` |
| FR-5.3, FR-5.4, FR-5.5 | 17, 17b, 19 | `tests.test_uninstall`, `tests.test_dry_run` |
| FR-5.7, FR-5.8 | #81 | `tests.test_session_hook`; manual check M7 |
| FR-5.6 | 3 | `tests.test_flock` |
| FR-6.1 to FR-6.4 | 17b | `tests.test_desktop`, `tests.test_dry_run` |
| FR-6.5 | 18 | `tests.test_menu` |
| FR-6.6 | 20 | `docs/migrate-from-claude-switcher.md`, M6 |
| NFR-PERF | 18, 20 | `test_render_under_2s_with_5000_cached_transcripts`, M4 |
| NFR-SEC | 5, 6, 10, 13, 18 | `tests.test_providers`, `tests.test_env`, `test_never_calls_security_with_w_or_g`, `test_run_rejects_resume_and_continue_flags`, `test_malicious_title_and_folder_sanitized_not_in_action` |
| NFR-OPS | 3, 14 | `tests.test_store`, `test_tool_time_logged` |
| NFR-COST | 1, 20 | CI config, `docs/usage.md`, M5 |
| Manual M1 to M5 | 20 | `docs/manual-checks.md` |

## Review log
Fresh-context review 2026-10-16 (red-team subagent, files only). The user accepted the recommendations as a set.
- [blocker] B1 "SHALL set `CLAUDE_SECURESTORAGE_CONFIG_DIR`" (unproven) → accepted: build gate G-1 spike; Keychain service name recorded; FR-4.5 self-check.
- [blocker] B2 `ais run` never specified → accepted: FR-3.5 to FR-3.8; last-used account defined.
- [blocker] N1 no terms-of-service gate → accepted: build gate G-2.
- [blocker] N2 work data crosses accounts → accepted: FR-2.8 one-time acknowledgement; G-3 records the secondary plan type.
- [major] M1 process check misses sessions started without `--resume` → accepted: lock file plus `lsof` (open session definition, FR-3.11).
- [major] M2 "newest session" underspecified → accepted with A1: Claude Code's own `--continue` / `--resume` picker.
- [major] M3 one global "active" account → accepted: last-used account per session.
- [major] M4 "signed in" means only an item exists → accepted: renamed `credential present`, FR-4.3.
- [major] C1 uninstall vs `~/.zshrc` → accepted: setup prints the line (FR-2.5), uninstall prints removal steps.
- [major] C2 RPO 0 is wrong → accepted: honest RPO; FR-3.7 transcript snapshot before each switch.
- [major] C3 "the account that is not active" assumes 2 → accepted: FR-3.9.
- [major] C4 interface missing open-session and self-check → accepted: FR-5.1.
- [major] N3 concurrent use of `~/.claude` → accepted: G-1(e), open-session refusal, atomic state writes.
- [major] N4 `~/.claude.json` not handled → accepted: G-1(d), included in backup, untouched by uninstall.
- [major] N5 backups unprotected → accepted: modes, free-space check, keep 5, uninstall prints size.
- [major] N6 other billing routes → accepted: FR-2.2 full list including `settings.json`.
- [major] N7 inherited Keychain variable → accepted: FR-1.3.
- [major] R1 resume uses the other account's limit → accepted: `/compact` guidance in NFR-COST and `docs/usage.md`.
- [major] R2 Claude Code updates break internals → accepted: G-1(f) version range, FR-3.13 warning.
- [major] A1 use `--continue` / `--resume` → accepted: FR-3.1 to FR-3.4.
- [major] A2 `/login` in a running session may be enough → accepted: G-1(a), user re-decides scope if it works.
- [minor] m1 pick errors, exit codes, JSON schema, tab title → accepted: picker delegated to Claude Code, FR-3.8 exit code passthrough, FR-4.6 schema, tab title best effort.
- [minor] m2 metric not measurable → accepted: switch times in `ais.log`.
- [minor] C5 backup writes into `~/.config/ais` → accepted: temp file, fsync, rename, partial deleted.
- [minor] C6 switching to the same account → accepted: plain resume (FR-3.2).
- [minor] N8 log can capture prompts → accepted: no passed-through arguments logged.
- [minor] N9 symlinks and dynamic provider import → accepted: realpath containment, static provider table.
- [minor] N10 no config schema or permissions → accepted: schema under FR-2, FR-2.6 modes.
- [minor] R3 transcript cut off mid-tool-call → accepted: G-1(c).
- [minor] A3 defer the provider plug-in shape → rejected: the approved brief puts it in the MVP.
- [minor] A4 shell-script MVP → rejected: the approved design chose Python; the spike may be shell.

Change 2026-10-16 (from ADR-0002, user approved):
- FR-1.2 credential directory default changed to `~/.claude-accounts/<account>`; `credDir` added to the config schema.
- FR-2.5 setup became a guided flow using `claude auth status`.
- FR-4.2 credential check uses `claude auth status`, Keychain existence check as fallback.

Change 2026-10-16 (brief MVP bullet 4 and non-goal 4, user approved):
- FR-4.6 adds `recent`; FR-4.7 to FR-4.11 add the optional SwiftBar plugin; `recent_sessions` added to the provider interface; NFR-PERF covers the once-a-minute status call.

Architecture review 2026-10-16 (red-team subagent, files only; also recorded in `docs/architecture.md`). Requirement changes in v0.3:
- B1 → session ID resolved by the provider; always `claude --resume <id>`; `--pick` is ais's own list; `ais run` locks by PID and folder and links the session after exit (FR-3.1 to FR-3.5).
- B2 → FR-4.8 actions carry only UUID and account; FR-4.12 sanitizing; FR-3.4 validates the folder.
- M1 → service-name formula and version range are code constants (FR-3.13, FR-4.2, FR-4.5).
- M2 → canonical credDir string, FR-1.7, per-kind path roots in NFR-SEC, name-equals-label note in FR-1.2.
- M3 → open-session definition by process cwd plus `O_EXCL` lock with start time (FR-3.6); G-1(g).
- M4 → FR-3.8 signal handling.
- M5 → FR-3.14 switch time from the transcript.
- M6 → FR-4.7 one-line plugin with explicit `PATH`; FR-4.11 deadline inside Python.
- M7 → FR-4.2 cache, FR-4.9 menu never prompts; G-1(h).
- M8 → FR-2.2 adds `CLAUDE_CODE_OAUTH_TOKEN`, all settings scopes, `--settings`.
- M9 → G-3 decision rule; FR-2.8 per account pair; FR-2.7 shared-memory statement.
- M10 (in part) → G-1(g) to (j) added; (e) fallback pre-decided; ADRs keep Accepted with "Depends on: G-1".
- M11 + alternative 3 → full `~/.claude` backup dropped; per-switch snapshots include subagent files (FR-3.7); NFR-OPS RTO/RPO restated.
- M12 → NFR-COST CI note.
- m1 → FR-2.5 PATH-only line. m2 → FR-4.8 tri-state. m3 → exit codes 64 to 78. m4 → FR-5.6 flock. m5 → FR-3.4 changes into the session folder. m6 → title, "unavailable", plain resume and documents defined. m7 → uninstall uses `state.json`, lists `~/.claude-accounts/`. m8 → log rotation in NFR-OPS.
- Rejected: alternative 1 (shell-function MVP), alternative 2 (always name the account), alternative 4 (postpone the menu); reasons in `docs/architecture.md`.

Superseded by v0.3/v0.4 (kept for history): M2 and m1 above ("Claude Code's own `--continue` / `--resume` picker") → ais resolves the ID and has its own picker; N4 "included in backup" and N5 "keep 5" → the full backup was dropped; FR-3.12 credential refusal → dropped from switch in v0.4.

Plan reviews 2026-10-16 (red-team subagent and architecture-guardian, files only; full log in the plan). The user accepted the recommendations as a set. Requirement changes in v0.4:
- [blocker] zipapp drops `main()`'s return code → plan task 1 entry point calls `sys.exit(main())`; test runs the built binary.
- [major] unknown last-used account → FR-3.1 exits 64 with a hint.
- [major] switch-time metric measured human delay → FR-3.14 tool time plus end-to-end where G-1(j) allows; M2 timed by hand.
- [major] `unknown` credential on switch, and p95 vs credential check → FR-3.12: no credential check on switch or run (alternative a).
- [major] global-lock fallback unbuilt, G-1 items without failure rules → failure rules per item; plan task 9.
- [major] Claude-specific env and billing logic outside the provider (both reviewers) → `env_for`, `billing_risks` in the provider (FR-2.2, FR-5.1).
- [major] `ais run` passthrough bypasses safeguards → FR-3.15.
- [major] main flow blocked while the limited session is open → FR-3.11 message, FR-4.13 disabled menu item, `docs/usage.md`.
- [major] menu deadline cannot stop subprocesses → FR-4.11.
- [major] concurrent identity overwrite in `~/.claude.json` → G-1(e).
- [major] snapshot growth → FR-3.7 clones and caps; FR-5.3 asks about snapshots (alternative d).
- [major] `--resume` may fork the ID → G-1(c).
- [major] session lookup fragile → session folder from the first line with `cwd`, realpath both sides, scan without folder encoding, cache (alternative c).
- [major] open detection too slow → one batched `pgrep`/`lsof` per call; measured on the Mac.
- [major] SIGINT ignored before spawn leaks into the child → FR-3.8.
- [major] PID lock files → dropped for process-cwd detection plus the switch mutex (alternative b).
- [minor] all accepted: G-1(c) simulation defined; signal deaths 128+N; "never collide" softened; stale log lines marked superseded; spike redaction; billing-guard roots injectable and managed profile; flock covers rotation, no prompts under lock, state pruning; setup offers existing `~/.claude-accounts/*`; uninstall lists `~/.local/bin/ais`; unknown config version exits 78; `menu_privacy`; manual checks cover NFD and `pgrep`/`lsof` until macOS CI is on.
- [minor, architecture-guardian] cache owned by `core.py` (FR-4.2); snapshot paths from the provider (FR-3.7); who creates the credDir → G-1(b) rule.
- Rejected: shipping the SwiftBar menu later (alternative e); instead the plan finishes and proves the CLI before the two menu tasks.

Build gates 2026-10-16 (plan task 2, details in `docs/spike-results.md`):
- G-2: the Consumer Terms (https://www.anthropic.com/legal/consumer-terms) and Usage Policy (https://www.anthropic.com/legal/aup), read 2026-10-16 through a summarising fetch tool (not a legal read), found nothing against holding or switching between two of one's own accounts. They bar sharing an account and "bypassing any of our systems or protective measures"; whether switching after a usage limit counts as that is ambiguous. The Usage Policy bars extra accounts used to evade detection or bans. The fetched Usage Policy showed an effective date after 2026-10-16, so that read may be unreliable. The user read the Consumer Terms clause and accepted the risk on 2026-10-16. Build may proceed.
- G-3: both accounts are the user's own personal Pro subscriptions; no Team, Enterprise or employer policy applies.
- G-1(a) works: `/login` in a running session switches the account and keeps the conversation, but one slot holds one account, so every switch is a browser login and the accounts cannot run side by side. The user re-decided and kept the MVP scope unchanged (2026-10-16).
- G-1(b): `claude` does not create the credDir and does not need it (hash input only) → ADR-0002 amended.

Change 2026-10-16 (Desktop per account, user approved the design `docs/superpowers/specs/2026-10-16-ais-desktop-design.md`):
- FR-6.1 to FR-6.6 added (ADR-0008); FR-5.1 provider methods, FR-5.3 lists Desktop folders, FR-5.4 adds `desktop`; out-of-scope 1 and brief non-goal 1 narrowed; part 2 deferred to rojcarranza/ai-account-switcher#1.

Change 2026-10-17 (user approved, rojcarranza/ai-account-switcher#41):
- FR-3.1: an unknown last-used account now defaults to the default account instead of exiting 64, so `ais switch` works right after a plain `claude` session hits its limit. Supersedes the 2026-10-16 "[major] unknown last-used account" resolution.

Change 2026-10-18 (user approved the scope change and the menu layout, rojcarranza/ai-account-switcher#54 to #57, ADR-0009, plan `docs/superpowers/plans/2026-10-18-menu-sessions-usage.md`):
- Out-of-scope 7 and brief non-goal 7 narrowed: the menu shows the usage sample Claude Desktop saved; no forecasting, no reset estimates, no fetch by ais.
- FR-4.8 amended to the per-account layout; FR-4.15 to FR-4.21 added; FR-6.1 amended by FR-4.21; NFR-SEC adds read-only Desktop data folders; NFR-PERF covers Desktop records.
- Later the same day (user approved drawn bars and icons, #57): FR-4.20 shows drawn bar images instead of `█░` text bars; FR-4.22 adds SF Symbol icons.
- `~/.claude.json` `cachedUsageUtilization` was considered and rejected: it was absent on the Mac on 2026-10-18 and covers only the account the CLI last signed in to (ADR-0009).

Change 2026-10-18 (user approved, rojcarranza/ai-account-switcher#62):
- FR-3.2: a named account on a session with no record also treats the default account as last-used, so the FR-2.8 prompt applies to the menu's `Resume in <label>` click (which always names the account), as NFR-SEC requires. Naming the default account still resumes without the prompt. Narrows the 2026-10-17 change, which left the named-account case unchanged.

Change 2026-10-19 (user approved, rojcarranza/ai-account-switcher#77):
- FR-3.16 to FR-3.20: `ais use <account>` picks the account per terminal window in any terminal app and starts `claude`; a plain `claude` in that window then runs through `ais run` on the same account, so last-used is still recorded and `ais switch` keeps working. Needs one `eval "$(ais shell-init)"` line in `~/.zshrc`, which ais prints but never writes.

Change 2026-10-19 (user approved, rojcarranza/ai-account-switcher#79):
- FR-3.1, FR-3.2: a session with no record is assumed to have last run on the account `AIS_ACCOUNT` names, when it names a configured account, else on the default account. `claude <args>` in an `ais use` terminal bypasses `ais run`, so without this `ais switch` there resumed on the account that had just hit its limit. `ais switch` outside that terminal (the menu's Resume) still assumes the default account.
- FR-3.16: `claude <args>` in an `ais use` terminal now goes through `ais run` whenever `ais run --dry-run` accepts the args, so its session gets a last-used record and the menu and `ais status` show the right account. Args `ais run` refuses (FR-3.15: resume flags, `--settings`) still run `claude` directly, as before; a billing risk (FR-2.2) now refuses `claude <args>` as it refuses a plain `claude`. Costs one extra `ais` start per `claude <args>`.

Change 2026-10-19 (user approved ADR-0010 with ais writing its own hook, rojcarranza/ai-account-switcher#81):
- FR-3.21, FR-5.7, FR-5.8: a Claude Code SessionStart hook that ais installs runs `ais record`, which records each terminal session's account from its Keychain slot when it starts or resumes, however it was launched. Desktop, IDE and SDK sessions are skipped: they carry no slot variable.
- FR-3.1, FR-3.2: the #79 `AIS_ACCOUNT` assumption is removed; it could name the account of another window (#80 finding 1). An unrecorded session again counts as the default account's.
- FR-5.1, FR-5.3, FR-5.4, NFR-SEC, NFR-OPS: provider methods for the hook; uninstall removes it; `hook install` and `hook uninstall` take `--dry-run`; ais now writes one thing under `~/.claude`, its own hook entry, through any symlink.

Change 2026-10-19 (user approved, rojcarranza/ai-account-switcher#1):
- Out of scope 1 reworded: one Desktop shows only its own account's sessions; Desktop's own import does not bring the other account's Desktop sessions (checked in the app, M6 step 7). ais adds no code and never writes Desktop files; issue #1 stays open.
- Switching accounts inside one Desktop is rejected for now: it would need ais to swap Desktop's stored sign-in (NFR-SEC, FR-6.4), and Desktop's native multi-account feature is gated off for the user (`docs/spike-results.md`).

Change 2026-10-19 (user approved, rojcarranza/ai-account-switcher#83):
- FR-4.23 removed, FR-4.22 and FR-4.24 amended: the menu no longer has `Open <label> Terminal`. It ran `ais run <account>` once in a new Terminal.app window in the home folder, and the window did not stay on that account. The `Copy "ais use <account>"` item does the same in any terminal app, in the folder you are already in, and keeps the window on that account.
