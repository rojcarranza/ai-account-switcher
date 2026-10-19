# Using ais day to day

Setup and the full command list are in the [README](../README.md). This page is the daily flow.

## When an account hits its limit

1. Optional but recommended: type `/compact` in the session first. A resumed session sends its whole transcript to the other account, so a long one uses part of that account's limit straight away.
2. Type `/exit`. `ais switch` refuses while Claude still runs in the folder (exit 75).
3. In the same folder:

   ```bash
   ais switch
   ```

   It resumes the newest session in this folder on the other account. A session started with plain `claude` counts as last used on the default account, except a plain `claude` with no arguments in a window set by `ais use` (see below), which is recorded on that window's account. The first switch between two accounts asks once before sending the transcript.

To go back later, run `ais switch` again. To pick an older session: `ais switch --pick`.

## Start new work on a given account

```bash
ais run work
```

Arguments after `--` go to `claude`: `ais run work -- --model opus`.

## Pick an account per terminal window

Add this line to `~/.zshrc` once, then open a new terminal:

```bash
eval "$(ais shell-init)"
```

In any terminal app (Terminal, Ghostty, Orca), `ais use work` sets that window to the work account and starts `claude` on it. After that, a plain `claude` in the same window uses work too. Other windows keep their own account. `ais use` on its own prints the account of the window. A window you never set uses the default account.

## Claude Desktop per account

```bash
ais desktop personal
ais desktop work
```

Each opens its own Desktop window, signed in separately. Running it again for an account that is already open prints `<label> Desktop is already open (PID n)` and starts nothing.

### The other account's sessions

Each Desktop lists only its own account's Code-tab sessions, and one Desktop window cannot switch accounts. Desktop's own "Import Claude Code CLI Sessions…" does not change that: it adds terminal sessions and sessions from another data folder signed in to the same account, but not the other account's Desktop sessions (checked 2026-10-19).

To continue a session on the other account, use `Resume in <account>` in the ais menu. It opens the session in Terminal under that account. Quit the Desktop that has it open first (Cmd+Q): the menu shows a session as `open` only while its `claude` process runs, and Desktop can stop that process while a session sits idle.

## Signing in

Sign in to an extra account only with `ais login <account>`. A `/login` inside a plain `claude` session replaces the **default** account's login, and you would have to sign in to it again.
