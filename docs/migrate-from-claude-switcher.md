# Move from Claude Switcher to ais

This is a guide. ais deletes nothing of Claude Switcher's: every removal below is done by you, by hand. Do the steps in order. Each says how to check it.

## 1. Check that ais works

Run:

```bash
ais status
ais desktop work
```

Check: `ais status` shows `credential present: yes` for both accounts, and the Work Desktop window opened by `ais desktop work` is signed in (sign in inside it if it is not). Do not go on until both are true.

## 2. Quit Claude Switcher

Quit Claude Switcher and its Work Desktop window (Cmd+Q on each).

Check: Activity Monitor cannot tell Desktop instances apart (all are called `Claude`), so use:

```bash
ps -x -ww -o pid=,args= | grep -i 'user-data-dir=.*Claude-work'
```

It should print no `.../Contents/MacOS/Claude` line. Claude Switcher's own app process should be gone too.

## 3. Remove the app

Move `/Applications/Claude Switcher.app` to the Trash. If it is a login item, remove it in System Settings, General, Login Items.

Check: the app is gone from `/Applications`, and not in the Login Items list.

## 4. Remove its settings folder

Remove `~/.config/claude-switcher/`.

Check: `ls ~/.config/claude-switcher` says there is no such file or folder.

## 5. Optional, last: remove its Work Desktop data

Remove `~/Library/Application Support/Claude-work`. macOS folder names ignore case, so this is the same folder as `Claude-Work`, and it may appear under that name. It is the data folder of the Work Desktop you run today. Removing it deletes every chat, every Code session and the sign-in of that Desktop. Do it only after you have moved your work to the window opened by `ais desktop work`. Skip it if unsure; it only takes disk space. ais uses `Claude-ais-work`, a different folder.

Check: `ls -d ~/Library/Application\ Support/Claude-work` says no such file or directory, and `ls -d ~/Library/Application\ Support/Claude-ais-work` still prints the folder.

## 6. Keep these

Do not remove:

- `~/.claude-accounts/work` and the Keychain item `Claude Code-credentials-f9fb4ac6`: ais uses both for the Work terminal account.
- the Keychain item `Claude Code-credentials` (the default account)
- `~/.claude`
- `~/.claude.json`

Check: `ais status` still shows both accounts with `credential present: yes`.

## 7. Other Claude Code Keychain items

List the item names only (this does not print any password):

```bash
security dump-keychain | grep 'Claude Code-credentials'
```

Each extra item is named `Claude Code-credentials-<8 hex digits>`. The 8 digits are the first 8 characters of the SHA-256 of an account's credDir path. To get the digits for a folder, run:

```bash
python3 -c "import hashlib,sys;print(hashlib.sha256(sys.argv[1].encode()).hexdigest()[:8])" "$HOME/.claude-accounts/work"
```

Match each listed name against the folders you know. Remove only an item you can identify as unused, by hand in Keychain Access. When in doubt, leave it.

Check: the list still has `Claude Code-credentials` and `Claude Code-credentials-f9fb4ac6`.

## 8. Remove the spike's leftovers

If you ran the build spike, remove:

- `~/Library/Application Support/Claude-ais-spike`
- the Keychain item `Claude Code-credentials-8cef0543` (the `~/.claude-accounts/spike` slot), in Keychain Access
- `~/SwiftBarPlugins/ais-probe.1m.sh`

Check: none of the three exists any more; `ais status` is unchanged.
