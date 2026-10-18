# Manual checks on the Mac

Run these on the real Mac after `make install`. Fill in each result line as `Pass` or `Fail`, the date, and a note for any failure. Account names below are `personal` (default) and `work`.

## M1 Both accounts signed in (FR-1)

1. `ais login personal` and sign in with the Personal account in the browser.
2. `ais login work` and sign in with the Work account in the browser.
3. `ais status`.

Expected: both lines show `credential present: yes`.

Result: ____ (date ____)

## M2 Switch under 30 s (FR-3, NFR-PERF end to end)

1. In a scratch folder: `ais run personal`, ask something you can recognise later, then `/exit`.
2. Start a stopwatch. Run `ais switch`; answer the one-time prompt if shown.
3. Stop the stopwatch when the Work session shows the prior conversation and accepts a prompt.

Expected: the earlier conversation is visible, `ais status` shows `last used work`, and the time is under 30 s.

Result: ____ (time ____ s, date ____)

## M3 Menu bar (FR-4)

1. `make install`, then `ais menu install` (needs SwiftBar and its plugin folder set).
2. Open the ais menu in the menu bar.
3. With `claude` running in a session's folder, open the menu again.
4. `/exit` that session, open the menu, click `Resume in Work` under it.

Expected: both accounts are listed with `yes`; while open, the session shows the disabled `Quit Claude in <folder> to resume` item; after `/exit`, `Resume in Work` opens a Terminal window that resumes the session on Work.

Result: ____ (date ____)

## M4 Measurements (NFR-PERF)

1. Do 20 switches (M2 steps 1 and 2, any folders), then print the p95 tool time of the last 20 from the log:

   ```bash
   python3 -c '
   import json, os
   rows = [json.loads(x) for x in open(os.path.expanduser("~/.config/ais/ais.log"))]
   t = sorted(r["tool_seconds"] for r in rows if r["command"] == "switch" and r["tool_seconds"] is not None)[-20:]
   print(len(t), "switches, p95", t[int(0.95 * (len(t) - 1))], "s")'
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

Record the transcript count with the result (NFR-PERF's render bound holds for up to 5,000 transcript files): `find ~/.claude/projects -name '*.jsonl' | wc -l`

Result: ____ (switch p95 ____ s, render p95 ____ s, transcripts ____, date ____)

## M5 NFD folder and process detection (NFR-COST, until macOS CI runs)

1. Make a folder with a decomposed accent: `mkdir "$HOME/caf$(printf 'e\xcc\x81')"`, `cd` into it, `ais run personal`, ask anything, `/exit`.
2. `ais status` in that folder.
3. Run `claude` in that folder again, and in a second terminal in the same folder run `ais switch work` (answer `y` if the one-time transcript prompt appears).

Expected: step 2 shows the session; step 3 refuses with exit 75 and `Claude is still running in <folder> (PID <n>)`, proving `pgrep`/`lsof` parsing works.

Result: ____ (date ____)

## M6 Claude Desktop per account (FR-6)

1. Note the Keychain items' modification times: `security find-generic-password -s "Claude Code-credentials" | grep mdat` and the same for `Claude Code-credentials-f9fb4ac6`.
2. `ais desktop personal` and `ais desktop work`: two windows side by side; sign in to Work in its window the first time.
3. Cmd+Q the Work window, run `ais desktop work` again.
4. Run `ais desktop work` once more while it is open, then `ps -x -o pid=,args= | grep "Claude-ais-work" | grep -v grep`.
5. Repeat step 1.
6. Quit Work Desktop, click `Open Work Desktop` in the ais menu.

Expected: Work is still signed in after step 3; step 4 prints `Work Desktop is already open (PID n)` and `ps` shows one `…/Contents/MacOS/Claude` process for that folder (helpers aside); the `mdat` values are unchanged; step 6 opens Work Desktop with no Terminal window.

Result: ____ (date ____)
