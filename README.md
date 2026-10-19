# ais: AI Account Switcher

`ais` keeps two Claude Code accounts signed in side by side on one Mac. When one account hits its usage limit, one command resumes the same session on the other account, with the conversation, memory and project context intact.

macOS only. Python 3.9+ standard library, shipped as one file. ais never reads or stores a secret: each account's login stays in its own macOS Keychain slot, and both accounts share `~/.claude`. The only thing ais writes under `~/.claude` is its own SessionStart hook, and only when you run `ais hook install`.

## Install

```bash
make install
```

This puts `ais` in `~/.local/bin` (the previous version is kept as `ais.prev`). If `ais --version` is not found, add this line to `~/.zshrc`:

```bash
export PATH="$HOME/.local/bin:$PATH"
```

## Set up once

```bash
ais setup
```

Press Enter to take each default:

```
Default account name [personal]:
Label for personal [Personal]:
Extra account name [work]:
Label for work [Work]:
Folder for work (number or path) [/Users/<user>/.claude-accounts/work]:
Setup will create:
  /Users/<user>/.config/ais/config.json
  ...
  /Users/<user>/.claude-accounts/work/ (empty, mode 0700)
Create these? [y/N] y
```

`personal` is your normal `claude` login. Setup then opens the sign-in for any account that is logged out: sign in to the **work** account there. To redo a sign-in later: `ais login work`.

Then two optional steps, both recommended:

```bash
ais hook install                      # record every session's account (see below)
echo 'eval "$(ais shell-init)"' >> ~/.zshrc   # pick the account per terminal window
```

**Naming tip:** you type the account name in every command, so keep it short and about the role, not the email: `personal` / `work`, or `pro` / `max`, or `client-acme`. Names are lowercase letters, digits and `-`, up to 32 characters. Put the detail (such as the email) in the label, which is display-only (`ais status`, prompts, the menu).

## Switch when you hit the limit

1. In the Claude session that hit its limit, type `/exit`.
2. In the same folder, run:

   ```bash
   ais switch
   ```

That resumes the newest session in this folder on the other account. ais knows which account a session last ran on from its own record: `ais run`, `ais switch` and the SessionStart hook (`ais hook install`) write one. A session with no record (started before the hook was installed, or in Claude Desktop) counts as the default account's, and ais says so.

The first switch from one account to the other asks once:

```
ais: the full transcript of session 11587d78-f810-4c64-870f-d7c9c6058ce2 (used under Personal) will be sent under Work.
ais: this is asked once for personal->work.
Continue? [y/N]
```

Not sure what it will do? Add `--dry-run`:

```
$ ais switch work --dry-run
session 11587d78-f810-4c64-870f-d7c9c6058ce2
folder /Users/<user>/Dev/projects/ai-account-switcher
account work
CLAUDE_SECURESTORAGE_CONFIG_DIR=/Users/<user>/.claude-accounts/work claude --resume 11587d78-f810-4c64-870f-d7c9c6058ce2
```

Other ways to pick the session:

```bash
ais switch work                                            # resume on a named account (also after a crash)
ais switch --pick                                          # choose from the 5 newest in this folder
ais switch --session 11587d78-f810-4c64-870f-d7c9c6058ce2  # a specific one
```

## Record every session's account

```bash
ais hook install
```

This adds one SessionStart hook to `~/.claude/settings.json`, writing through the symlink if that file is one (for example into a dotfiles repo). Claude Code then runs `ais record` whenever a terminal session starts or resumes, however you started it: plain `claude`, `claude --resume`, or a slot you exported by hand. `ais record` matches `CLAUDE_SECURESTORAGE_CONFIG_DIR` exactly against each account's folder (unset means the default account) and records nothing for an unknown slot or a Claude Desktop, IDE or SDK session. The hook command is `[ -x "$HOME/.local/bin/ais" ] && "$HOME/.local/bin/ais" record || true`, so it does nothing on a machine without ais. `ais hook uninstall` (or `ais uninstall`) removes only that hook; both take `--dry-run`.

## Pick an account per terminal window

Add this line to `~/.zshrc` once, then open a new terminal:

```bash
eval "$(ais shell-init)"
```

In any terminal app, `ais use work` sets that window to the work account and starts `claude` on it. After that, `claude` in the same window runs on work too, through `ais run`. Other windows keep their own account; a window you never set uses the default account. `ais use` on its own prints the window's account. `ais use --copy work` puts `ais use work` on the clipboard (the menu's `Copy "ais use work"` item does the same).

## Everyday commands

| Command | Example |
|---|---|
| Start a new session on an account (args after `--` go to `claude`) | `ais run work -- --model opus` |
| Set this terminal window's account and start `claude` | `ais use work` |
| Check both accounts and the newest session here (`--json` for scripts) | `ais status` |
| Sign an account in again | `ais login work` |
| Open Claude Desktop as an account, side by side with the other | `ais desktop work` |
| Record every session's account through a Claude Code hook | `ais hook install` / `ais hook uninstall` |
| SwiftBar menu bar status and one-click resume (needs SwiftBar) | `ais menu install` / `ais menu uninstall` |
| Remove ais's files and its hook (never the rest of `~/.claude`, or the Keychain) | `ais uninstall` |

`ais status` prints:

```
  personal (Personal): credential present: yes
  work (Work): credential present: yes
session 11587d78-f810-4c64-870f-d7c9c6058ce2: last used personal, not open
self-check: ok
```

Every command that changes something takes `--dry-run`.

## Menu bar

`ais menu install` writes a SwiftBar plugin (install SwiftBar first: `brew install --cask swiftbar`). The menu shows:

- `Running: <label>, …` for each account whose Claude Desktop is open.
- Per account: its label and credential state, its latest usage (5-hour and weekly, from that account's Claude Desktop) and a `Sessions (n)` list of its 10 newest sessions, each with title or folder and age, or `open`.
- Under each closed session, `Resume in <other account>`, which runs `ais switch --session <id> <account>` in a new Terminal window; an open session shows `Quit Claude in <folder> to resume` instead.
- `Open <label> Desktop`, `Open <label> Terminal` (runs `ais run <account>`) and `Copy "ais use <account>"` for each account.

Set `"menu_privacy": true` in `~/.config/ais/config.json` to show only labels, credential states and session counts. If your Work Desktop already lives in another folder (for example Claude Switcher's `Claude-Work`), set `"desktop_data_dir"` on that account to its absolute path.

## Good to know

- `ais` cannot tell which email a slot is signed in to. Sign in to the right account in each slot.
- Sign in to an extra account only with `ais login <account>`. A `/login` inside a plain `claude` session replaces the default account's login.
- Do not set `CLAUDE_CONFIG_DIR`: it splits the shared `~/.claude`, and `ais switch` stops finding sessions.
- If Claude is still running the session, `ais switch` stops with exit 75: type `/exit` there first.
- `ais` refuses to start `claude` when the environment or Claude settings would bill an API key instead of your subscription (for example `ANTHROPIC_API_KEY` or `ANTHROPIC_BASE_URL` set). `--allow-api-key` overrides.
- Shared memory, `CLAUDE.md` and settings in `~/.claude` go with every session on either account.
- Claude Desktop sessions are never recorded by the hook (they carry no slot variable); the menu takes their account from Claude Desktop's own files.

Exit codes and exact behaviour: [docs/requirements.md](docs/requirements.md).

More: [daily flow](docs/usage.md), [restore a session from a snapshot](docs/restore.md), [move from Claude Switcher](docs/migrate-from-claude-switcher.md), [manual checks on the Mac](docs/manual-checks.md).

## Development

```bash
make lint test build
```

- Single test: `python3 -m unittest tests.test_cli.CliTest.test_version`
- Run from source: `PYTHONPATH=src python3 -m ais status`
- Python 3.9 syntax only. Rules: [CLAUDE.md](CLAUDE.md). Scope: [docs/brief.md](docs/brief.md). Design: [docs/architecture.md](docs/architecture.md), [docs/adr/](docs/adr/). Build status: [docs/progress.md](docs/progress.md), [docs/spike-results.md](docs/spike-results.md).
