# Manual checks M1 to M6

These need the real Mac, the real Keychain and two real accounts, so tests cannot cover them. Run them yourself and fill in the `Result` line of each.

Common setup: `make install` has run, `ais setup` is done, and the accounts are `personal` (default) and `work`. Use a scratch folder, not a real project. Never paste a Keychain password anywhere; none of these steps print one.

## M1 Both accounts have a credential (FR-1)

Purpose: both accounts are signed in side by side.

Prerequisites: `ais login personal` and `ais login work` done, each with its own account.

Steps:
1. `ais status`
2. `ais status --json`

Expected: step 1 prints `credential present: yes` for `personal` and for `work`, and ends with `ais cannot see which account each slot is signed in to; sign in to the matching account in each`. Step 2 shows `"credential_present": "yes"` for both.

Result: ____ (Pass/Fail)  Date: ____

## M2 Personal to Work resume, under 30 s (FR-3, brief metric)

Purpose: a session started on Personal continues on Work with the prior conversation visible, in under 30 seconds.

Prerequisites: a scratch folder, e.g. `mkdir -p ~/ais-m2 && cd ~/ais-m2`; a stopwatch.

Steps:
1. `ais run personal`. Ask Claude a short question, and wait for the answer.
2. Start the stopwatch and type `/exit` in that session.
3. Run `ais switch`. If it asks `Continue? [y/N]`, answer `y`.
4. Stop the stopwatch when the Work session is open and ready for input.
5. Scroll up in the Work session and check that the question and answer from step 1 are there.

Expected: `ais switch` resumes on `work`; the earlier conversation is visible; the time from step 2 to step 4 is under 30 s.

Result: ____ (Pass/Fail)  Time: ____ s  Date: ____

## M3 Menu bar (FR-4)

Purpose: the menu shows both accounts, the disabled quit item while a session is open, and a working Resume in Work.

Prerequisites: SwiftBar installed with a plugin folder chosen; a session in `~/ais-m2` last used on Personal (from M2, or run `ais run personal` once and `/exit`).

Steps:
1. `make install`
2. `ais menu install`. Read the file shown, answer `y` to `Write this file? [y/N]`.
3. Open the SwiftBar menu. Check that both accounts are listed with their credential state.
4. In another terminal, `cd ~/ais-m2` and run `claude` (leave it open). Refresh the SwiftBar menu. Check that the session shows `open` and a disabled item `Quit Claude in ~/ais-m2 to resume` appears instead of resume items.
5. `/exit` the `claude` from step 4 and refresh the menu.
6. Click `Resume in Work` under the session. A Terminal window should open and resume it on Work.

Expected: as listed in each step.

Result: ____ (Pass/Fail)  Date: ____

## M4 Measurements (NFR-PERF)

Purpose: p95 of tool time over 20 switches under 1 s; p95 of `ais menu render` over 20 runs under 2 s.

Prerequisites: a session in a scratch folder. Each switch needs a `/exit` before the next one.

Part A, switch tool time:
1. In the scratch folder, run `ais switch` 20 times, typing `/exit` after each one. Run `ais status` once first to warm the cache.
2. Compute p95 (the 19th smallest of the last 20 values) from the log. Each `ais switch` writes one JSON line to `~/.config/ais/ais.log` with a `tool_seconds` field (time from ais start to the `claude` start):
   ```bash
   python3 -c "import json,os;r=[json.loads(l) for l in open(os.path.expanduser('~/.config/ais/ais.log'))];t=[x['tool_seconds'] for x in r if x['command']=='switch' and x['tool_seconds'] is not None][-20:];print(len(t),'values, p95 =',sorted(t)[18])"
   ```
   If the first number is below 20, run more switches. (The log rotates at 1 MB into `ais.log.1`; this is fine for a short run.)

Expected: `p95 =` is below 1 (seconds).

Part B, menu render:
1. Run once to warm the cache: `ais menu render > /dev/null`
2. Time 20 runs:
   ```bash
   python3 -c "import subprocess as s,time as m;t=sorted((lambda a:(s.run(['ais','menu','render'],stdout=s.DEVNULL),m.monotonic()-a)[1])(m.monotonic()) for _ in range(20));print(len(t),'runs, p95 =',t[18])"
   ```

Expected: `p95 =` is below 2 (seconds).

Result A: ____ s (Pass/Fail)  Result B: ____ s (Pass/Fail)  Date: ____

## M5 NFD folder names and process parsing (until macOS CI is on)

Purpose: Finder-style (NFD) folder names, and the `pgrep`/`lsof` parsing, work on the real Mac. Linux CI cannot check either.

Prerequisites: none beyond the common setup.

Steps:
1. Make a folder whose name has an accent written in decomposed (NFD) form, which is how Finder names it:
   ```bash
   mkdir -p "$HOME/ais-m5-$(python3 -c "import unicodedata;print(unicodedata.normalize('NFD','é'))")"
   cd "$HOME"/ais-m5-*
   ```
2. `ais run personal`, ask one short question, `/exit`.
3. `ais switch --dry-run`. Check it prints `session <id>` and `folder` with this folder (not `nothing to resume`).
4. `ais run personal` again and leave it open. In another terminal, in the same folder, run `ais switch`. Check it refuses with `Claude is still running in` and `Type /exit there, then run `ais switch` again.` (exit code 75: `echo $?`).
5. Look at what ais parses: `pgrep -x claude`, then `lsof -a -d cwd -p <pid> -Fn`. Check that the `n` line is this folder and the PID is the one in the refusal message.
6. `/exit`. Run `ais switch --dry-run` again and check it no longer refuses.
7. Clean up: `cd ~ && rm -r "$HOME"/ais-m5-*` (only after checking `ls -d "$HOME"/ais-m5-*` lists just that folder).

Expected: step 3 finds the session; step 4 refuses with the right PID; step 6 does not refuse.

Result: ____ (Pass/Fail)  Date: ____

## M6 Claude Desktop per account (FR-6)

Purpose: Personal and Work Desktop open side by side; Work keeps its sign-in; no duplicate; terminal credentials untouched; the menu item opens Desktop with no Terminal window.

Prerequisites: Claude Desktop in `/Applications` or `~/Applications`; `make install`, then `ais menu install` done (see M3).

Steps:
1. Record the terminal Keychain items' modification dates (names and dates only, no passwords):
   ```bash
   security find-generic-password -s "Claude Code-credentials" | grep mdat
   security find-generic-password -s "Claude Code-credentials-f9fb4ac6" | grep mdat
   ```
   (For a different credDir, the second name is `Claude Code-credentials-` plus the 8 digits described in [migrate-from-claude-switcher.md](migrate-from-claude-switcher.md) step 7.)
2. `ais desktop personal`, then `ais desktop work`. Check two Claude windows are open. Sign in to each the first time (Work with the work account).
3. Press Cmd+Q in the Work window, then run `ais desktop work` again. Check that it opens already signed in.
4. With Work open, run `ais desktop work` a second time. Check it prints `Work Desktop is already open (PID <n>)` and exits 0.
5. Check no duplicate: `ps -x -ww -o pid=,args= | grep user-data-dir=` shows exactly one `.../Contents/MacOS/Claude` line containing `Claude-ais-work` (lines for `Claude Helper` processes do not count).
6. In the SwiftBar menu, click `Open Work Desktop` with Work closed. Check Work Desktop opens and no Terminal window appears.
7. Repeat the two `mdat` commands from step 1.

Expected: all checks above hold; the `mdat` values in step 7 equal those in step 1.

Result: ____ (Pass/Fail)  Date: ____
