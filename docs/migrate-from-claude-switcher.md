# Moving from Claude Switcher to ais

ais deletes nothing of Claude Switcher's. Every step below is done by you, in this order. Each step says how to check it.

1. **Before removing anything**, check ais works:
   - `ais status` shows both accounts with `credential present: yes`.
   - `ais desktop work` opens a Work Desktop window, and you have signed in there.
2. **Quit Claude Switcher** and its Work Desktop window. Check: `pgrep -fl "Claude Switcher"` prints nothing, and `ps -x -ww -o pid=,args= | grep -iE 'user-data-dir=.*/[C]laude-work( |$)'` prints nothing (the Work Desktop window runs as `Claude`, so the first check cannot see it).
3. **Remove the app**: drag `/Applications/Claude Switcher.app` to the Bin, and remove its login item, if any, in System Settings > General > Login Items. Check: the app is gone from `/Applications` and from Login Items.
4. **Remove its settings**: `rm -r ~/.config/claude-switcher`. Check: `ls ~/.config/claude-switcher` says no such file.
5. **Optional, last**: remove `~/Library/Application Support/Claude-work`, Claude Switcher's Work Desktop data. macOS folder names ignore case, so this is the same folder as `Claude-Work`, and it may show under that name. It is the data of that Work Desktop window: removing it deletes every chat, every Code session and the sign-in in it. Do it only after you have moved your work to the window `ais desktop work` opens; skip it if unsure. ais's Work Desktop uses `Claude-ais-work` instead. Check: `ls -d ~/Library/Application\ Support/Claude-work` says no such file, and `ais desktop work` still opens signed in.
6. **Keep** these, ais uses them:
   - `~/.claude-accounts/work` and the Keychain item `Claude Code-credentials-f9fb4ac6` (the work slot);
   - the Keychain item `Claude Code-credentials` (the default slot);
   - `~/.claude` and `~/.claude.json`.
7. **Other `Claude Code-credentials-<8 hex>` Keychain items.** List the names (no secrets are printed):

   ```bash
   security dump-keychain | grep -o '"Claude Code-credentials[^"]*"' | sort -u
   ```

   Each suffix is the first 8 hex characters of the SHA-256 of a credDir path. Work out the suffix of a folder you know:

   ```bash
   printf '%s' "$HOME/.claude-accounts/work" | shasum -a 256 | cut -c1-8
   ```

   Remove, by hand in Keychain Access, only the items you can identify as unused. Check: `ais status` still shows both accounts signed in.
8. **Remove the spike's throwaway pieces**:
   - the folder `~/Library/Application Support/Claude-ais-spike`;
   - the Keychain item of `~/.claude-accounts/spike` (`Claude Code-credentials-8cef0543`), in Keychain Access;
   - `~/SwiftBarPlugins/ais-probe.1m.sh`.

   Check: none of the three exists, and `ais status` still shows both accounts signed in.
