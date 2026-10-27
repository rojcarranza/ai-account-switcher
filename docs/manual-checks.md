# Manual checks on the Mac

Run these on the real Mac after `make install`. Fill in each result line as `Pass` or `Fail`, the date, and a note for any failure. Account names below are `primary` (default) and `secondary`.

## M1 Both accounts signed in (FR-1)

1. `ais login primary` and sign in with the Primary account in the browser.
2. `ais login secondary` and sign in with the Secondary account in the browser.
3. `ais status`.

Expected: both lines show `credential present: yes`.

Result: ____ (date ____)

## M2 Switch under 30 s (FR-3, NFR-PERF end to end)

1. In a scratch folder: `ais run primary`, ask something you can recognise later, then `/exit`.
2. Start a stopwatch. Run `ais switch`; answer the one-time prompt if shown.
3. Stop the stopwatch when the Secondary session shows the prior conversation and accepts a prompt.

Expected: the earlier conversation is visible, `ais status` shows `last used secondary`, and the time is under 30 s.

Result: ____ (time ____ s, date ____)

## M3 Menu bar (FR-4)

1. `make install`, then `ais menu install` (needs SwiftBar and its plugin folder set).
2. Open the ais menu in the menu bar.
3. With `claude` running in a session's folder, open the menu again.
4. `/exit` that session, open the menu, click `Resume in Secondary` under it.

Expected: both accounts are listed with `yes`; while open, the session shows the disabled `Quit Claude in <folder> to resume` item; after `/exit`, `Resume in Secondary` opens a Terminal window that resumes the session on Secondary.

Result: ____ (date ____)

## M4 Measurements (NFR-PERF)

1. Do 20 switches (M2 steps 1 and 2, any folders), then print the p95 tool time of the last 20 from the log:

   ```bash
   python3 -c '
   import json, os
   logs = [os.path.expanduser("~/.config/ais/ais.log" + s) for s in (".1", "")]  # .1 = rotated, older
   rows = [json.loads(x) for p in logs if os.path.exists(p) for x in open(p)]
   t = sorted([r["tool_seconds"] for r in rows if r["command"] == "switch" and r["tool_seconds"] is not None][-20:])
   print(len(t), "switches, p95", t[int(0.95 * (len(t) - 1))] if t else "n/a", "s")'
   ```

2. Time 20 menu renders and print the p95:

   ```bash
   python3 -c '
   import subprocess, time
   t = []
   for _ in range(20):
       s = time.monotonic()
       subprocess.run(["ais", "menu", "render"], capture_output=True)
       t.append(time.monotonic() - s)
   print("p95", round(sorted(t)[18], 3), "s")'
   ```

Expected: switch tool time p95 < 1 s; menu render p95 < 2 s.

Record the transcript count with the result (NFR-PERF's render bound holds for up to 5,000 transcript files): `find ~/.claude/projects -mindepth 2 -maxdepth 2 -name '*.jsonl' | wc -l` (top-level transcripts only, the ones ais scans; subagent files sit deeper)

Result: ____ (switch p95 ____ s, render p95 ____ s, transcripts ____, date ____)

## M5 NFD folder and process detection (NFR-COST, until macOS CI runs)

1. Make a folder with a decomposed accent: `mkdir "$HOME/caf$(printf 'e\xcc\x81')"`, `cd` into it, `ais run primary`, ask anything, `/exit`.
2. `ais status` in that folder.
3. Run `claude` in that folder again, and in a second terminal in the same folder run `ais switch secondary` (answer `y` if the one-time transcript prompt appears).

Expected: step 2 shows the session; step 3 refuses with exit 75 and `Claude is still running in <folder> (PID <n>)`, proving `pgrep`/`lsof` parsing works.

Result: ____ (date ____)

## M6 Claude Desktop per account (FR-6)

1. Note the Keychain items' modification times: `security find-generic-password -s "Claude Code-credentials" | grep mdat` and the same for `Claude Code-credentials-f9fb4ac6`.
2. `ais desktop primary` and `ais desktop secondary`: two windows side by side; sign in to Secondary in its window the first time.
3. Cmd+Q the Secondary window, run `ais desktop secondary` again.
4. Run `ais desktop secondary` once more while it is open, then `ps -x -o pid=,args= | grep "Claude-ais-secondary" | grep -v grep`.
5. Repeat step 1.
6. Quit Secondary Desktop, click `Open Secondary Desktop` in the ais menu.
7. Quit Primary Desktop (Cmd+Q). In Secondary Desktop, run "Import Claude Code CLI Sessions…" and confirm. Then, in the ais menu, open a Primary Desktop session and click `Resume in Secondary`.

Expected: Secondary is still signed in after step 3; step 4 prints `Secondary Desktop is already open (PID n)` and `ps` shows one `…/Contents/MacOS/Claude` process for that folder (helpers aside); the `mdat` values are unchanged; step 6 opens Secondary Desktop with no Terminal window; in step 7 the import adds no Primary Desktop session to Secondary Desktop's list (it may add terminal sessions), and `Resume in Secondary` continues the Primary session in Terminal; while it runs the ais menu shows it `open` with "Quit Claude in <folder> to resume".

Result: ____ (date ____)

## M7 SessionStart hook records the account (FR-3.21, FR-5.7, ADR-0010)

1. `ais hook install`, answer `y`; `ls -l ~/.claude/settings.json` still shows a symlink, and `git -C <dotfiles> diff` shows only the added SessionStart group.
2. In `~/tmp/ais-hook`, `CLAUDE_SECURESTORAGE_CONFIG_DIR="$HOME/.claude-accounts/secondary" claude`, type `hi`, `/exit` (not through ais).
3. `ais status` in that folder.
4. In the same folder, plain `claude --resume` on the newest session, `/exit`, then `ais status` again.
5. Start a Code-tab session in Claude Desktop, then check `tail -3 ~/.config/ais/ais.log`.
6. `ais hook uninstall`, answer `y`; the dotfiles diff is empty again.

Expected: step 3 shows the session last used on Secondary; step 4 shows Primary; step 5 has no `record` line for the Desktop session; step 6 leaves the file as it was before step 1.

Result: ____ (date ____)

## M8 `ais default` on the real Keychain (FR-3.22, ADR-0011)

Not covered by tests, which use a fake `security`: the real `security -i` parsing and the Keychain item's access list.

1. `ais login primary` and `ais login secondary` once, then `ais default` (prints `primary`).
2. `ais default secondary`. A Keychain prompt may appear; choose Always Allow.
3. In a plain terminal: `claude auth status`, then a short `claude -p hi`.
4. `ais status`, then `ais run secondary --dry-run` and `ais default primary`.

Expected: step 3 runs on Secondary with no sign-in; step 4 still shows both accounts logged in and the dry run shows no `CLAUDE_SECURESTORAGE_CONFIG_DIR`; the last step restores Primary.

Result: ____ (date ____)
