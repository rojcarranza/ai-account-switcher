# ais: AI Account Switcher

`ais` keeps two Claude Code accounts signed in side by side on one Mac. When one account hits its usage limit, one command resumes the same session on the other account, with the conversation, memory and project context intact.

macOS only. Python 3.9+ standard library, shipped as one file (a Python zipapp). No services, no secrets read or stored: each account's login stays in the macOS Keychain.

## Status

All MVP commands are built and tested (see [docs/progress.md](docs/progress.md)). The manual checks and measurements on a real Mac are still open ([#41](https://github.com/rojcarranza/ai-account-switcher/issues/41)). The SwiftBar menu has a known bug ([#42](https://github.com/rojcarranza/ai-account-switcher/issues/42)).

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

## Use

Set up once. `ais setup` lists what it will create and asks before writing anything. It names the accounts (`personal` on Claude Code's normal login, `work` in its own Keychain slot), reuses any `~/.claude-accounts/*` folder, and opens the sign-in only for an account that is not signed in yet:

```bash
ais setup
```

When an account hits its usage limit, type `/exit` in Claude, then in the same folder:

```bash
ais switch
```

That resumes the newest session in this folder on the other account. A session started with plain `claude` counts as last used on the default account, so this works the first time too. Run `/compact` before switching to send less.

| Command | What it does |
|---|---|
| `ais setup` | Guided setup: name the accounts, sign in where needed |
| `ais login <account>` | Sign in to one account in its own slot |
| `ais switch [account]` | Resume the newest session in this folder on the other (or named) account |
| `ais switch --pick` | Choose one of the 5 most recent sessions |
| `ais switch --session <id> [account]` | Resume one session by ID, from any folder |
| `ais run [account] [-- claude args]` | Start a new `claude` session on an account |
| `ais status` | Accounts, sign-in state, newest session |
| `ais desktop <account>` | Open that account's Claude Desktop window |
| `ais menu install` | Optional SwiftBar menu bar status and one-click resume |
| `ais uninstall` | Remove ais's own files; never touches `~/.claude` or the Keychain |

Most commands take `--dry-run` to show what they would do. Exact behaviour and exit codes: [docs/requirements.md](docs/requirements.md).

Do not run `/login` for the other account inside a plain `claude` session: that replaces the default account's login. Use `ais login <account>`. `claude auth status` shows the same email for both slots (it reads the shared `~/.claude.json`), so it cannot tell you which account a slot holds.

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
