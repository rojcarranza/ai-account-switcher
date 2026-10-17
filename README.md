# ais: AI Account Switcher

`ais` keeps two Claude Code accounts signed in side by side on one Mac. When one account hits its usage limit, one command resumes the same session on the other account, with the conversation, memory and project context intact.

macOS only. Python 3.9+ standard library, shipped as one file. ais never reads or stores a secret: each account's login stays in its own macOS Keychain slot, and both accounts share `~/.claude`.

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

**Naming tip:** you type the account name in every command, so keep it short and about the role, not the email: `personal` / `work`, or `pro` / `max`, or `client-acme`. Names are lowercase letters, digits and `-`, up to 32 characters. Put the detail (such as the email) in the label, which is display-only (`ais status`, prompts, the menu).

## Switch when you hit the limit

1. In the Claude session that hit its limit, type `/exit`.
2. In the same folder, run:

   ```bash
   ais switch
   ```

That resumes the newest session in this folder on the other account. The first switch between two accounts asks once:

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
ais switch --pick                                          # choose from the 5 newest in this folder
ais switch --session 11587d78-f810-4c64-870f-d7c9c6058ce2  # a specific one
```

## Everyday commands

| Command | Example |
|---|---|
| Start a new session on an account (args after `--` go to `claude`) | `ais run work -- --model opus` |
| Check both accounts and the newest session here | `ais status` |
| Open Claude Desktop as the other account | `ais desktop work` |
| SwiftBar menu bar status and one-click resume (needs SwiftBar) | `ais menu install` / `ais menu uninstall` |
| Remove ais's files (never `~/.claude` or the Keychain) | `ais uninstall` |

`ais status` prints:

```
  personal (Personal): credential present: yes
  work (Work): credential present: yes
session 11587d78-f810-4c64-870f-d7c9c6058ce2: last used personal, not open
self-check: ok
```

Every command that changes something takes `--dry-run`.

## Good to know

- `ais` cannot tell which email a slot is signed in to. Sign in to the right account in each slot.
- If Claude is still running the session, `ais switch` stops with exit 75: type `/exit` there first.
- `ais` refuses to start `claude` when the environment or Claude settings would bill an API key instead of your subscription (for example `ANTHROPIC_API_KEY` or `ANTHROPIC_BASE_URL` set). `--allow-api-key` overrides.
- Shared memory, `CLAUDE.md` and settings in `~/.claude` go with every session on either account.

Exit codes and exact behaviour: [docs/requirements.md](docs/requirements.md).

## Development

```bash
make lint test build
```

- Single test: `python3 -m unittest tests.test_cli.CliTest.test_version`
- Run from source: `PYTHONPATH=src python3 -m ais status`
- Python 3.9 syntax only. Rules: [CLAUDE.md](CLAUDE.md). Design: [docs/architecture.md](docs/architecture.md), [docs/adr/](docs/adr/).
