# ais: AI Account Switcher

`ais` keeps two Claude Code accounts signed in side by side on one Mac. When one account hits its usage limit, one command resumes the same session on the other account, with the conversation, memory and project context intact.

macOS only. Python 3.9+ standard library, shipped as one file (a Python zipapp). No services, no secrets read or stored: each account's login stays in the macOS Keychain.

## Status

Early. Only the walking skeleton is built: `ais --version` works and every other command exits 64. The build gates (the spike on a real Mac) are done; see [docs/spike-results.md](docs/spike-results.md). The commands below under "Planned" come next, task by task, from [the plan](docs/superpowers/plans/2026-10-16-ais-mvp.md).

## Install

```bash
make install
```

This builds `dist/ais` and copies it to `~/.local/bin/ais`. A different previous version is kept as `~/.local/bin/ais.prev`. Check it:

```bash
ais --version
```

It prints `ais 0.1.0`. If the shell cannot find `ais`, add `~/.local/bin` to `PATH` in `~/.zshrc`:

```bash
export PATH="$HOME/.local/bin:$PATH"
```

## Switching accounts by hand (works today)

The spike proved the mechanism `ais` will automate. Each account has its own Keychain slot, chosen by the `CLAUDE_SECURESTORAGE_CONFIG_DIR` variable. Every account shares `~/.claude`, so any account can resume any session.

1. Sign in to the second account once, in its own slot:
   ```bash
   CLAUDE_SECURESTORAGE_CONFIG_DIR="$HOME/.claude-accounts/work" claude
   ```
   Type `/login`, sign in with the second account, then `/exit`. Your normal `claude` keeps the first account.
2. When the first account hits its limit, type `/exit`. Claude prints `claude --resume <session-id>`.
3. In the same folder, resume that session on the other account:
   ```bash
   CLAUDE_SECURESTORAGE_CONFIG_DIR="$HOME/.claude-accounts/work" claude --resume <session-id>
   ```

Do not run `/login` for the second account inside a plain `claude` session: that replaces the first account's login. Do not set `CLAUDE_CONFIG_DIR`: it splits the shared `~/.claude`. `claude auth status` shows the same email for both slots (it reads the shared `~/.claude.json`), so it cannot tell you which account a slot holds.

To open a second Claude Desktop window for the other account:

```bash
open -n -a Claude --args --user-data-dir="$HOME/Library/Application Support/Claude-ais-work"
```

Sign in with the second account the first time. Run it only once: a second launch on the same folder starts a duplicate copy.

## Planned commands

| Command | What it will do |
|---|---|
| `ais setup` | Guided setup: name the accounts, sign in where needed |
| `ais login <account>` | Sign in to one account in its own slot |
| `ais switch [account]` | Resume the newest session in this folder on the other account |
| `ais switch --pick` | Choose one of the 5 most recent sessions |
| `ais run [account] [claude args]` | Start a new `claude` session on an account |
| `ais status` | Accounts, sign-in state, newest session |
| `ais desktop <account>` | Open that account's Claude Desktop window |
| `ais menu install` | Optional SwiftBar menu bar status and one-click resume |
| `ais uninstall` | Remove ais's own files; never touches `~/.claude` or the Keychain |

Exact behaviour and exit codes: [docs/requirements.md](docs/requirements.md).

## Development

```bash
make lint test build
```

- Tests: `python3 -m unittest discover -s tests -t .` (single test: `python3 -m unittest tests.test_cli.CliTest.test_version`).
- Run from source: `PYTHONPATH=src python3 -m ais --version`.
- Python 3.9 syntax only; CI runs 3.9 and 3.12 on Linux.
- Every change is tracked by a GitHub issue and lands through a pull request; rules in [CLAUDE.md](CLAUDE.md).

## Documents

- [docs/brief.md](docs/brief.md): the problem, scope and non-goals
- [docs/requirements.md](docs/requirements.md): what ais must do
- [docs/architecture.md](docs/architecture.md) and [docs/adr/](docs/adr/): how, and why
- [docs/spike-results.md](docs/spike-results.md): what was proven on a real Mac
- [docs/progress.md](docs/progress.md): where the build stands
