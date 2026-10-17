# Daily use

Account names below are the ones from `ais setup`: `personal` (the default account) and `work`.

## Switch a session to the other account

1. In the Claude session that hit its limit, run `/compact`. A resumed long session uses part of the other account's limit straight away, so a shorter conversation costs less (NFR-COST).
2. Type `/exit`. Claude prints `claude --resume <session-id>`. ais refuses to switch while Claude is still running in that folder (exit 75).
3. In the same folder, run:
   ```bash
   ais switch
   ```
   It resumes the newest session of this folder on the account that did not run it last. If ais does not know which account ran it, it exits 64 and asks for `ais switch <account>`.

Other forms:

- `ais switch work` resumes on a named account.
- `ais switch --pick` lists the 5 newest sessions of this folder and asks for a number.
- `ais switch --dry-run` prints the session, folder, account and command and starts nothing.

The first time a transcript moves from one account to the other, ais asks `Continue? [y/N]`. It is asked once for each direction (personal to work, and work to personal).

Before each resume, ais copies the session's files to `~/.config/ais/snapshots/`. To undo a damaged session, see [restore.md](restore.md).

## Start a new session on an account

```bash
ais run work
ais run work -- <claude arguments>
```

Everything after `--` goes to `claude`. `ais run` does not take `--resume` or `--continue`; use `ais switch`.

## Claude Desktop

```bash
ais desktop personal
ais desktop work
```

Each opens its own Claude Desktop window. Sign in inside the window the first time. If that account's Desktop is already open, ais prints `<label> Desktop is already open (PID n)` and starts nothing.

## Rules

- Sign in to an extra account only with `ais login <account>`. A `/login` inside a plain `claude` session replaces the default account's credential.
- Never set `CLAUDE_CONFIG_DIR`. It splits the shared `~/.claude`, and sessions can no longer be resumed on the other account.
- `ais status` shows whether each account has a credential. It cannot see which email each slot holds; sign in to the matching account in each.
- ais refuses to start `claude` when an API key or similar billing setting is present (exit 77). `--allow-api-key` overrides it on purpose.

## Menu bar (optional)

`ais menu install` writes a SwiftBar plugin after `Write this file? [y/N]`. `ais menu uninstall` removes only that file after `Remove it? [y/N]`. SwiftBar must already be installed (`brew install --cask swiftbar`).
