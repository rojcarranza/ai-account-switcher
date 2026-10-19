# Using ais day to day

Setup and the full command list are in the [README](../README.md). This page is the daily flow.

## When an account hits its limit

1. Optional but recommended: type `/compact` in the session first. A resumed session sends its whole transcript to the other account, so a long one uses part of that account's limit straight away.
2. Type `/exit`. `ais switch` refuses while Claude still runs in the folder (exit 75).
3. In the same folder:

   ```bash
   ais switch
   ```

   It resumes the newest session in this folder on the other account. A session started with plain `claude` counts as last used on the default account. The first switch between two accounts asks once before sending the transcript.

To go back later, run `ais switch` again. To pick an older session: `ais switch --pick`.

## Start new work on a given account

```bash
ais run work
```

Arguments after `--` go to `claude`: `ais run work -- --model opus`.

## Claude Desktop per account

```bash
ais desktop personal
ais desktop work
```

Each opens its own Desktop window, signed in separately. Running it again for an account that is already open prints `<label> Desktop is already open (PID n)` and starts nothing.

### Both accounts' sessions in one window

Each Desktop lists only its own account's sessions. To see the other account's sessions too, choose Desktop's own "Import Claude Code CLI Sessions…" in the window you want to use. It adds the other account's Code-tab sessions and your terminal sessions to that window's list. It adds a list entry only; the transcript stays the shared one in `~/.claude`. Run it again to pick up newer sessions. (Read from Desktop's code and files, not yet tried in the app; manual check M6 step 7 confirms it.) This is a Desktop feature, not an ais one; if a Desktop update removes it, ais keeps working.

To continue a session on the other account, use `Resume in <account>` in the ais menu (Terminal), or `Open <label> Desktop` after importing the session there. Before you continue a session in the other Desktop, quit the Desktop that last had it open (Cmd+Q): two Desktops would otherwise write the same transcript. The ais menu shows a session as `open` only while its `claude` process runs, and Desktop can stop that process while a session sits idle, so a missing `open` does not mean the other Desktop has let go of it.

One Desktop window cannot switch accounts. Use one window per account (`ais desktop <account>`).

## Signing in

Sign in to an extra account only with `ais login <account>`. A `/login` inside a plain `claude` session replaces the **default** account's login, and you would have to sign in to it again.
