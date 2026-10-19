# ADR-0002: Auth and account split: per-account Keychain slot, own setup
Status: Accepted
Area: auth
Depends on: G-1 spike (requirements); a failed check means a superseding ADR.

## Context
Each account needs its own login while both share `~/.claude`. The user
already runs Claude Switcher (kevinchau/claude-switcher) and wants it used
as a guide, not a dependency: ais should have its own setup that is
simpler and easier. Facts from Claude Switcher's README (read 2026-10-16):
- It never sets `CLAUDE_CONFIG_DIR`; all accounts share `~/.claude`.
- The terminal CLI account is chosen by `CLAUDE_SECURESTORAGE_CONFIG_DIR`,
  omitted entirely for the default account and never set to "".
  Verified there with `claude auth status` (`loggedIn: false` for a fresh
  directory).
- Its convention for an extra account's credential directory is
  `~/.claude-accounts/<id>`, with `<id>` the lowercased label.
- The Keychain service name is `Claude Code-credentials` for the default
  slot, else `Claude Code-credentials-` + the first 8 lowercase hex chars
  of `sha256(NFC(<dir>))`. So the same directory path means the same
  Keychain item, whichever tool sets it.
- It relies on undocumented behaviour that a Claude Code update may change.

## Decision
- Account split by Keychain slot via `CLAUDE_SECURESTORAGE_CONFIG_DIR`,
  never `CLAUDE_CONFIG_DIR`.
- ais owns its account list in `~/.config/ais/config.json` and never
  reads or writes Claude Switcher's files at runtime.
- An extra account's credential directory defaults to
  `~/.claude-accounts/<id>`, stored as one canonical absolute string (no
  `~`, no trailing slash, NFC) and passed to `claude` exactly as stored,
  because the Keychain service name hashes the string; the same convention Claude Switcher uses, so
  terminal logins made with either tool are found by the other with no
  import and no second sign-in, as long as the ais account name equals
  Claude Switcher's lowercased label.
- `ais setup` is a guided flow: name the accounts (default `primary`
  as the default account, `secondary` as extra), check each with `claude auth
  status`, and start the sign-in only for accounts that are not logged in.
- Credential check: `claude auth status` under the account's environment
  (no secret printed), cached 10 minutes; the menu uses only the cache or
  the Keychain existence check; fallback to a Keychain existence check on the
  derived service name, never with `-w` or `-g`.

## Alternatives considered
- **Read Claude Switcher's config at runtime:** reuses its account list
  directly, but ties ais to another app's file format and makes ais
  depend on it being installed.
- **ais-only directories (`~/.config/ais/accounts/<id>`):** fully separate,
  but users of both tools sign in twice and keep duplicate Keychain items.
- **Separate `CLAUDE_CONFIG_DIR` per account plus symlinks
  (MelkonTech style):** documented variable, but splits the shared brain.
- **Swap Keychain entries on switch:** one slot, but handles secrets,
  which the brief forbids.

## Consequences
- No runtime dependency on Claude Switcher; works with or without it.
- Existing Claude Switcher terminal logins are reused automatically.
- Requirements change: FR-1.2 (directory path), FR-2.5 (guided setup),
  FR-4.2 (credential check by `claude auth status`). Logged in
  `docs/requirements.md` when approved.
- If G-1(b) shows `claude` does not create the credDir folder itself, this
  ADR is amended to let ais create only that empty folder (0700) after the
  setup yes, never writing inside it.

## Amendment 2026-10-16 (G-1(b) result)
G-1(b) showed `claude` neither creates nor needs the credDir folder: the
path is only hashed into the Keychain service name, and a login with a
missing folder worked (`docs/spike-results.md`). `ais setup` creates the
empty folder (0700) after the setup yes, so the account has a visible home
on disk, and never writes inside it. The spike also confirmed Claude
Switcher's Work profile uses `~/.claude-accounts/work`, so its terminal login
is reused as designed.
