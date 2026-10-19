# ADR-0008: Claude Desktop per account: one instance per data folder
Status: Accepted
Area: other
Depends on: the Desktop spike in `docs/spike-results.md` (2026-10-16).

## Context
The user wants ais to replace Claude Switcher, including its second Claude
Desktop window for the other account, so Primary and Secondary Desktop run side
by side (brief MVP bullet 1 and non-goal 1, changed 2026-10-16; design
`docs/superpowers/specs/2026-10-16-ais-desktop-design.md`). The spike showed:
- Claude Switcher runs its Secondary Desktop as
  `/Applications/Claude.app/Contents/MacOS/Claude --user-data-dir=<…>/Claude-work`.
- `open -n -a Claude --args --user-data-dir=<new folder>` starts a separate
  instance that keeps its own sign-in across restarts and does not touch the
  terminal Keychain items or `~/.claude.json`.
- Launching again on the same folder while it runs starts a duplicate
  process; Claude.app does not stop it.

## Decision
- `ais desktop <account>`: the default account opens the normal Claude app
  (`open -n -a`, no data-folder flag, unchanged sign-in and history; `-n`
  because plain `open -a` only fronts a running Work instance); every
  other account opens its own instance with
  `--user-data-dir=~/Library/Application Support/Claude-ais-<account>`,
  derived from the account name, not stored in `config.json`.
- Before launching, one `ps` call checks for a running instance on that
  folder; if found, ais prints that it is already open and launches
  nothing.
- All Desktop facts (app paths, flag, folder prefix, process matching) live
  in `providers/claude.py` behind provider methods (FR-5.1).
- ais never signs in for the user, never touches Keychain items or Claude
  Switcher's files, and `ais uninstall` keeps the Desktop folders.
- Removing Claude Switcher is a written guide,
  `docs/migrate-from-claude-switcher.md`, not a command.

## Alternatives considered
- **Reuse Claude Switcher's `Claude-secondary` folder:** keeps the Secondary Desktop
  sign-in and data, but ties ais to another app's folder; the user chose a
  fresh folder.
- **One Desktop that switches accounts and lists both accounts' sessions:**
  explored on 2026-10-19 (`docs/spike-results.md`). Desktop's own import does
  not bring the other account's sessions; switching needs Desktop's
  gated multi-account feature or a swap of Desktop's stored sign-in,
  which NFR-SEC and this ADR's "never signs in for the user" rule out.
  Kept one instance per account; see
  `docs/superpowers/specs/2026-10-19-desktop-both-accounts-design.md`
  (rojcarranza/ai-account-switcher#1).
- **An `ais` cleanup command for Claude Switcher:** one-time, mostly
  permanent deletion of another app's files; a guide the user follows is
  safer and keeps ADR-0002.

## Consequences
- Relies on Claude.app honouring `--user-data-dir` (Electron behaviour,
  undocumented by Anthropic); a Desktop update may break it, which M6
  catches.
- The first open of an extra account's Desktop shows a sign-in screen.
- Each extra account keeps a Desktop data folder of its own that ais never
  deletes.
