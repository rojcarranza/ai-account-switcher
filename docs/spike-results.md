# Spike results (G-1, G-2, G-3)

Date: 2026-10-16. Claude Code 2.1.301, macOS (Darwin 27). Scripts are in `spike/`; raw output only in `spike/raw/` (git-ignored, checked with `git check-ignore -v spike/raw/x`).
Each "Expected" line was written before the command ran. Emails, org/account IDs and unrelated Keychain entries are redacted.

Status: automatable parts only. Items (a), (c), (d), (e), (b) login, (h) SwiftBar prompt and G-3 are PENDING (user).

## Expectations written before running
- (b) credDir exists and is empty; Keychain has `Claude Code-credentials` and no `-<hash>` service for work yet; the sha256 rule is findable in the installed package.
- (f) version 2.1.301; FR-2.2 list mostly complete, maybe a few additions.
- (g) `pgrep -x claude` finds the same PIDs as `-f` minus helper processes; `lsof` shows a cwd per PID; each under 100 ms.
- (h) `claude auth status` prints a short block; under 2 s; `--json` may exist.
- (i) SwiftBar may not be installed; README documents `name.5m.sh`, `bash=`, `paramN=`, `terminal=`, `disabled=`.
- (j) A marker string such as "usage limit" in some transcript record, in a `message.content` text field.
- G-2: terms do not forbid owning two accounts, but may forbid sharing accounts or circumventing limits.

## (a) `/login` inside a running session — PENDING (user)
Expected: `/login` as Work either keeps the conversation (then scope must be re-decided) or does not. Expected by the plan: it does not switch cleanly, so ais is still needed.
Run: in a live interactive `claude` session on Personal, type `/login`, sign in as Work, then ask "what did we just discuss?". Record whether the conversation continued and which account `claude auth status` reports afterwards.
Failure rule: (a) works -> the user re-decides the MVP scope before building.

## (b) `CLAUDE_SECURESTORAGE_CONFIG_DIR` and Keychain naming — PARTIAL
Commands: `python3 spike/b_keychain.py` (runs `security find-generic-password -s "Claude Code-credentials"` and `security dump-keychain`, keeping only lines containing `svce` / `Claude Code-credentials`; no `-w`, `-g`, `-d`); `python3 spike/h_status.py`; `strings` on the installed binary `~/.local/share/claude/versions/2.1.301` (read-only) to find the hashing code; `python3 spike/b_hash.py`.

State found:
- `~/.claude-accounts/work` exists (drwxr-xr-x) and is empty. `~/.claude-accounts/spike` does not exist (not created: it needs a login).
- Default item: `"svce"<blob>="Claude Code-credentials"` is present.
- `security dump-keychain` lists 8 services of the form `Claude Code-credentials-<8 hex>` (7 unrelated ones redacted here; likely other Claude Switcher / past config dirs, not investigated). One of the 8 equals the expected service for the work credDir (below).

Hashing rule (from the 2.1.301 binary, function `v1`, read from the strings; quoted logic):
```
dir     = CLAUDE_SECURESTORAGE_CONFIG_DIR            (if set, even "")
suffix  = "" if (env var set and empty) or (env var unset and CLAUDE_CONFIG_DIR unset)
          else "-" + sha256(NFC(dir)).hex[:8]        (dir when unset = CLAUDE_CONFIG_DIR value)
service = "Claude Code" + "-credentials" + suffix
```
The string hashed is the variable's value exactly as given, NFC-normalized, UTF-8, no trailing-slash or `~` handling. Test vectors (from `spike/b_hash.py`) for task 5:

| credDir string | expected service |
| --- | --- |
| `/Users/roj/.claude-accounts/work` | `Claude Code-credentials-f9fb4ac6` |
| `/Users/roj/.claude-accounts/work/` (trailing slash) | `Claude Code-credentials-cf3ea493` |
| `/Users/roj/.claude` | `Claude Code-credentials-fb50e6da` |
| `/Users/roj/.claude-accounts/personal` | `Claude Code-credentials-65ac6854` |
| `/Users/roj/.claude-accounts/spike` | `Claude Code-credentials-8cef0543` |

Expected-but-unverified-until-login: work -> `Claude Code-credentials-f9fb4ac6`. The value was seen in the dump, so an item already exists for that service; whose account it holds is not known (no secret read). Not yet verified against a fresh login.

Does `claude` honour the variable? `CLAUDE_SECURESTORAGE_CONFIG_DIR=/private/tmp/claude-501/ais-nonexistent-credir claude auth status` -> exit 2, `loggedIn: false`, `authMethod: none`, `configDirectory` still `/Users/roj/.claude`. So the variable selects the Keychain slot only, and `auth status` does not create the folder. With `~/.claude-accounts/work` the output has the same keys and `loggedIn` true, i.e. an item exists for that slot; `docs/progress.md` recorded that it showed the same account as default. Open for the user: confirm whether the work slot really holds the Work account (compare the redacted email of both calls by hand), or the Personal one.

Still PENDING (user): does `claude` create the credDir itself on login (use a fresh `~/.claude-accounts/spike`: confirm absent, run `CLAUDE_SECURESTORAGE_CONFIG_DIR="$HOME/.claude-accounts/spike" claude`, `/login`, then `ls -ld`), and that the resulting service equals `Claude Code-credentials-8cef0543`.

Result: Pass (partial). Rule found, variable proven to select a different Keychain slot (logged out for a dir with no item). Full pass needs the login on `spike`.
Failure rule: (b) fails -> build stops until a new ADR; if `claude` does not create the credDir -> ADR-0002 amended so ais creates only the empty folder (0700) after the FR-2.3 yes.

## (c) Resume across accounts — PENDING (user)
Expected: `claude --resume <id>` under Work continues a Personal session, appends to the same `<id>.jsonl`, also works from another folder; a SIGKILLed mid-tool-call transcript resumes; a target at its limit or logged out prints an error or login prompt.
Commands (user): in `~/tmp/ais-spike`, start `claude` on Personal, ask for `sleep 120` via Bash, note the session id (`ls -t ~/.claude/projects/*/ | head`), `pkill -9 -f 'claude'` is NOT to be used broadly: kill that one PID from another terminal (`kill -9 <pid>`), then `CLAUDE_SECURESTORAGE_CONFIG_DIR="$HOME/.claude-accounts/work" claude --resume <id>`; `wc -l` the `.jsonl` before and after, and `ls` the project folder for new files. Repeat from `cd ~`. Then repeat with Work at its limit and with a logged-out dir (`.../spike` before login).
Failure rule: fails -> the build stops until a new ADR picks another mechanism.

## (d) `~/.claude.json` with two accounts — PENDING (user)
Expected: `~/.claude.json` is shared (one file) with `oauthAccount` identity fields rewritten per login, OR per-account depending on the config dir.
Commands (user): `python3 -c "import json;d=json.load(open('$HOME/.claude.json'));print(sorted(d), sorted(d.get('oauthAccount',{})))"` (keys only), before and after each `/login`; `cp ~/.claude.json spike/raw/claude.json.before` and `diff` key lists only.
Failure rule: fails -> the build stops until a new ADR.

## (e) Two accounts at once for 30 minutes — PENDING (user)
Expected: no corruption; `oauthAccount`/`userID` may flip.
Commands (user): two terminals, one per account, different folders; every minute `python3 -c` to print whether `~/.claude.json` and every `~/.claude/**/*.json` parse, and a hash of `oauthAccount` and `userID` (not values). Record all changes.
Failure rule: fails -> plan task 9 (global lock, one running `claude` at a time).

## (f) Version range, billing/account variables and keys — DONE
Command: `claude --version`; `claude --help`; WebFetch of https://code.claude.com/docs/en/env-vars (first 100k chars; second half fetched too) and https://code.claude.com/docs/en/settings; `strings` on the binary to confirm names exist in 2.1.301.
Expected: 2.1.301; a few additions to FR-2.2.
Output: `2.1.301 (Claude Code)`. Tested range = 2.1.301 only, for now.

FR-2.2 today (requirements.md:123): env `ANTHROPIC_API_KEY`, `ANTHROPIC_AUTH_TOKEN`, `ANTHROPIC_BASE_URL`, `CLAUDE_CODE_OAUTH_TOKEN`, `CLAUDE_CODE_USE_BEDROCK`, `CLAUDE_CODE_USE_VERTEX`; settings `apiKeyHelper`; flag `--settings`.

Additions found (all present in the 2.1.301 binary strings; the first group is also in the public env-vars page):
- Provider switches: `CLAUDE_CODE_USE_FOUNDRY`, `CLAUDE_CODE_USE_MANTLE`, `CLAUDE_CODE_USE_ANTHROPIC_AWS`; (binary only: `CLAUDE_CODE_USE_GATEWAY`, `CLAUDE_CODE_USE_ANTHROPIC_GOOGLE_CLOUD`).
- Credentials: `CLAUDE_CODE_OAUTH_REFRESH_TOKEN`, `CLAUDE_CODE_OAUTH_SCOPES`, `ANTHROPIC_FOUNDRY_API_KEY`, `ANTHROPIC_FOUNDRY_AUTH_TOKEN`, `ANTHROPIC_AWS_API_KEY`, `AWS_BEARER_TOKEN_BEDROCK`, `ANTHROPIC_CUSTOM_HEADERS` (can set Authorization), `ANTHROPIC_PROFILE`, `ANTHROPIC_FEDERATION_RULE_ID`, `ANTHROPIC_ORGANIZATION_ID`, `ANTHROPIC_WORKSPACE_ID`; (binary only: `CLAUDE_CODE_OAUTH_TOKEN_FILE_DESCRIPTOR`, `CLAUDE_CODE_API_KEY_FILE_DESCRIPTOR`, `ANTHROPIC_IDENTITY_TOKEN`, `ANTHROPIC_IDENTITY_TOKEN_FILE`, `CLAUDE_CODE_ACCOUNT_UUID`, `CLAUDE_CODE_ORGANIZATION_UUID`).
- Endpoints that reroute billing: `ANTHROPIC_BEDROCK_BASE_URL`, `ANTHROPIC_VERTEX_BASE_URL`, `ANTHROPIC_FOUNDRY_BASE_URL`, `ANTHROPIC_FOUNDRY_RESOURCE`, `ANTHROPIC_AWS_BASE_URL`, `ANTHROPIC_BEDROCK_MANTLE_BASE_URL`.
- Storage slot: `CLAUDE_CONFIG_DIR` (already handled by FR-2.1), `ANTHROPIC_CONFIG_DIR` (binary only; purpose not checked), `CLAUDE_CODE_PROVIDER_MANAGED_BY_HOST`.
- Settings keys present in the binary: `apiKeyHelper`, `awsAuthRefresh`, `awsCredentialExport`, `gcpAuthRefresh`, `forceLoginMethod`, `forceLoginOrgUUID` (not yet in FR-2.2). The `settings` docs page was fetched but the key table was not in the portion returned; names confirmed only from the binary. Flags: `--bare` (API key only), `--settings` (already listed), `--setting-sources`.
- Not billing but account-adjacent, not proposed: `claude setup-token`, `claude auth` subcommands.

Result: Pass (list recorded). The proposal for FR-2.2 is the first four bullets plus `forceLoginMethod`, `forceLoginOrgUUID`, `awsAuthRefresh`, `awsCredentialExport`, `gcpAuthRefresh`; the controller decides what to add. Binary-only names are unverified against public docs.
Failure rule: none stated for (f).

## (g) Detecting a running `claude` and its cwd — DONE with caveats
Command: `zsh spike/g_detect.sh` (`pgrep -lx claude`, `pgrep -fl claude`, `lsof -a -d cwd -p <pids> -Fn`, each under `time`).
Expected: same PIDs as `-f` minus helpers; cwd per PID; under 100 ms.
Output (home paths kept):
- `pgrep -lx claude`: 4 PIDs. 50923 (the background daemon, `claude daemon run`, cwd `/Users/roj`) and three desktop-app-embedded sessions (72681, 73156, 73294, binaries under `~/Library/Application Support/Claude*/claude-code/2.1.299/.../claude`, with cwd `/Users/roj/Dev/projects/bam-cli/.claude/worktrees/...`, `/Users/roj/Dev/projects/agent-skills`, `/Users/roj/Dev/projects/.dotfiles`).
- `pgrep -fl claude`: 30+ PIDs, mostly `Claude.app` Electron helpers, `Claude Switcher.app`, `claude bg-pty-host`, `claude bg-spare`; unusable without filtering.
- Timings: `pgrep -x` 0.026 s; `pgrep -f` 0.026 s; `lsof -a -d cwd -p` 4 PIDs 0.056 s.
- No terminal-started `claude` was running during the spike (all `-x` hits are the daemon and desktop-app sessions), so the common case, a terminal CLI, was not exercised. Note `pgrep -l` showed the daemon's name as `2.1.301` (the versioned binary name) while `-x claude` matched it, so the match depends on how the process was exec'd; the terminal CLI case must be checked.
Findings for task design: `-x claude` also matches the daemon (cwd `/Users/roj`) and desktop-app sessions; ais must filter on argv (exclude `daemon`, `bg-*`) and decide whether desktop-app sessions count as "open".
Result: Pass on mechanism and timing (under 60 ms); PENDING (user) the terminal case: open `claude` in two terminals, then rerun `zsh spike/g_detect.sh`.
Failure rule: fails -> FR-3.11 becomes a yes/no question and the menu shows no open badge.

## (h) `claude auth status` — PARTIAL
Command: `python3 spike/h_status.py` (3 runs each, default and with `CLAUDE_SECURESTORAGE_CONFIG_DIR=$HOME/.claude-accounts/work`); `claude auth status --help`.
Expected: short block; under 2 s; `--json` exists.
Output format (keys only, values redacted): JSON object, exit 0:
`loggedIn` (bool), `authMethod`, `apiProvider`, `analyticsDisabled`, `projectsDirectory`, `configDirectory`, `email`, `orgId`, `orgName`, `subscriptionType`.
Flags: `--json` (default) and `--text`. Logged-out case (nonexistent credDir): exit 2, keys include `loggedIn: false`, `authMethod: none`, `apiProvider`, `analyticsDisabled`, `projectsDirectory`, `configDirectory`; no email.
Latency: 0.12 s on every one of 6 runs (default and work).
Network: `nettop` not run (needs sudo; skipped). Not checked whether it calls the network; 0.12 s suggests a local read.
Keychain prompt from SwiftBar: PENDING (user); SwiftBar is not installed (see (i)).
Result: Pass (format, latency, flags). Keychain-prompt part PENDING.
Failure rule: fails -> the menu uses only the Keychain existence check.

## (i) SwiftBar — DONE (README only), plugin behaviour PENDING
Command: `defaults read com.ameba.SwiftBar PluginDirectory`; `ls -d /Applications/SwiftBar.app`; WebFetch of https://raw.githubusercontent.com/swiftbar/SwiftBar/main/README.md.
Expected: not installed; README documents the names and parameters.
Output: `Domain 'com.ameba.SwiftBar' not found.` and no `/Applications/SwiftBar.app` -> SwiftBar not installed.
From the README:
- Refresh interval: file name `{name}.{time}.{ext}`, `{time}` = number + unit `ms`, `s`, `m`, `h` or `d`, e.g. `date.1m.sh`; interval optional; cron-style `<swiftbar.schedule>` metadata is an alternative.
- Plugin folder: chosen by the user at first launch; every file in it is a plugin; hidden folders ignored, nested folders and symlinks traversed; `.swiftbarignore` excludes files.
- Menu parameters: `bash=` absolute path of the script to run; `paramN=` arguments (`param0=`, `param1=`, ...); `terminal=` `false` runs in the background instead of opening Terminal (so `terminal=true` opens Terminal); `refresh=true` re-runs the plugin after click.
- `disabled=`: not covered by the README text returned. PENDING: check the SwiftBar wiki or the installed app.
- Plugin PATH: not stated. README lists env vars set for plugins (`SWIFTBAR_PLUGIN_PATH`, `SWIFTBAR_PLUGIN_DATA_PATH`, `OS_APPEARANCE`) and `<swiftbar.environment>[var=default]</swiftbar.environment>` for custom ones. PENDING (user): after installing SwiftBar, make a plugin that prints `echo $PATH` and record it; ais should use an absolute path to `~/.local/bin/ais`.
Result: PENDING for live checks; docs-based answers recorded.
Failure rule: (i) fails -> the user decides whether the menu tasks stay in the MVP.

## (j) Usage-limit text in transcripts — DONE
Command: `python3 spike/j_limit_text.py` and `python3 spike/j_limit_shape.py` over `~/.claude/projects/*/*.jsonl` (381 files; read-only; only marker snippets printed).
Expected: a marker string in a message text field.
Output: 77 records match one marker:
- Record: `type: "assistant"`, `isApiErrorMessage: true`, `error: "rate_limit"` (JSON path `$.error`), also `apiError`, `apiErrorStatus`, `apiErrorParams`, `quotaLimits`, `sessionId`, `timestamp`, `cwd`.
- Text, at `$.message.content[].text`: `You've hit your session limit · resets N:Npm (Europe/Amsterdam)` (digits normalised to N; the reset time is in that text with a time-zone name).
- The other matches ("Concurrent subagent limit reached") are not account limits. Weekly or other limit wordings were not seen, only the "session limit" form.
Result: Pass (a marker exists). Marker for FR-3.14: `isApiErrorMessage == true and error == "rate_limit"`, text begins "You've hit your session limit".
Failure rule: no marker -> FR-3.14's end-to-end time is measured only by manual check M2 (not triggered).

## G-2 Terms — DONE
Sources: https://www.anthropic.com/legal/consumer-terms (effective October 8, 2025 as returned) and https://www.anthropic.com/legal/aup (effective date returned as November 12, 2026; reported as read). Fetched 2026-10-16.
Findings:
- No clause limits how many accounts one person holds, and none addresses switching between one's own accounts.
- Consumer Terms forbid making an account available to others (Section 2: "make your Account available to anyone else"); resuming one's own session under one's own other account is not that.
- No clause expressly prohibits working around usage limits. Section 3 does bar "bypassing any of our systems or protective measures" in general; whether a limit-driven switch counts is not addressed. Section 4 describes technical limitations without prohibiting circumvention.
- Usage Policy (paraphrase): bans opening extra accounts to avoid detection or get around guardrails, and evading a ban with another account. Does not address usage limits.
- Automated access is barred except through an API key or where Anthropic permits it; ais drives the official `claude` CLI, not an extraction path.
Result: Pass with a caveat (reading is from a summarising fetch tool, not a human legal read; "protective measures" wording is ambiguous for limit evasion). Recommend the user confirms before the build proceeds.
Failure rule: terms forbid it -> the build stops. Not triggered on this reading.

Draft Review-log line (not yet added to `docs/requirements.md`):
`2026-10-16 G-2: Consumer Terms (https://www.anthropic.com/legal/consumer-terms, effective 2025-10-08) do not restrict holding or switching between two own accounts; they bar sharing an account with others and "bypassing any of our systems or protective measures" (limit evasion not named). Usage Policy (https://www.anthropic.com/legal/aup) bars extra accounts to evade detection/bans only. Build may proceed; user to confirm.`

## G-3 Work account plan — PENDING (user)
Expected: the Work plan is Team or Enterprise (from `subscriptionType`), which triggers the terms and employer-policy check.
Commands (user): `CLAUDE_SECURESTORAGE_CONFIG_DIR="$HOME/.claude-accounts/work" claude auth status --json` after a Work login, read only `subscriptionType`. If Team or Enterprise: read the commercial terms and the employer data policy; record whether moving transcripts between accounts is allowed.
Failure rule: Team/Enterprise and either forbids moving data between accounts -> the build stops.
