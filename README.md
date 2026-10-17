# ais: AI Account Switcher

`ais` keeps two Claude Code accounts signed in side by side on one Mac. When one account hits its usage limit, one command resumes the same session on the other account, with the conversation, memory and project context intact.

macOS only. Python 3.9+ standard library, shipped as one file (a Python zipapp). No services, no secrets read or stored: each account's login stays in the macOS Keychain.

## Status

All commands are built. The build gates (the spike on a real Mac) are done; see [docs/spike-results.md](docs/spike-results.md). The checks that need a real Mac (sign-in, resume timing, menu, Desktop) are listed in [docs/manual-checks.md](docs/manual-checks.md) and are run by hand. Progress: [docs/progress.md](docs/progress.md).

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

## Commands

| Command | What it does |
|---|---|
| `ais setup [--dry-run]` | Guided setup: name the accounts, sign in where needed |
| `ais login <account> [--dry-run]` | Sign in to one account in its own slot |
| `ais switch [account] [--pick] [--session <id>] [--dry-run]` | Resume the newest session in this folder on the other account; `--pick` chooses one of the 5 newest |
| `ais run [account] [--dry-run] [-- claude args]` | Start a new `claude` session on an account (default: the default account) |
| `ais status [--json]` | Accounts, sign-in state, newest session, self-check |
| `ais desktop <account> [--dry-run]` | Open that account's Claude Desktop window |
| `ais menu render` | Print the SwiftBar menu (SwiftBar runs this) |
| `ais menu install [--dry-run]` | Write the optional SwiftBar plugin after a yes |
| `ais menu uninstall [--dry-run]` | Remove that plugin file after a yes |
| `ais uninstall [--dry-run]` | Remove ais's own files; never touches `~/.claude` or the Keychain |

`switch`, `run` and `login` also take `--allow-api-key`, which overrides the refusal to start `claude` when an API key or similar billing setting is set. Exact behaviour and exit codes: [docs/requirements.md](docs/requirements.md).

## Daily use

The short version: `/compact`, `/exit`, then `ais switch`. Details, rules and the Desktop windows: [docs/usage.md](docs/usage.md).

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
- [docs/usage.md](docs/usage.md): daily use
- [docs/restore.md](docs/restore.md): put a snapshot back
- [docs/manual-checks.md](docs/manual-checks.md): checks M1 to M6 to run on the Mac
- [docs/migrate-from-claude-switcher.md](docs/migrate-from-claude-switcher.md): remove Claude Switcher
