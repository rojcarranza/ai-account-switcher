# ADR-0011: `ais default`: swap which account the machine's default sign-in holds
Status: Accepted
Area: auth
Depends on: ADR-0002 (supersedes its rejection of "swap Keychain entries"), ADR-0003 (state.json).

## Context
Bug (rojcarranza/ai-account-switcher, found 2026-10-27): after a session limit,
`ais switch` does not help Infinitary crewmates and the first mate. They
always run on the machine's default sign-in (Keychain item
`Claude Code-credentials` and the shared `~/.claude.json`); Infinitary
starts every Claude session without `CLAUDE_SECURESTORAGE_CONFIG_DIR`, and
its meter and limit hold read only that item. `ais switch` sets the slot
variable for the one `claude` it starts, so nothing Infinitary uses changes
and its limit hold stays. The only workaround was a browser sign-in of the
default slot as the other account, which also left ais's "primary" holding
the wrong account (reproduction: `ais switch` exit 0, next Infinitary turn
still on the spent account).

ADR-0002 rejected swapping Keychain entries because it "handles secrets,
which the brief forbids". That rejection was right while the only goal was
launching `claude` per account. It cannot serve programs ais does not start.

## Decision
- New command `ais default [<account>]`: make the default sign-in hold
  `<account>`'s login. It swaps (exchanges) the credential of the default slot
  with the credential of `<account>`'s slot, so no login is lost or duplicated
  (Claude rotates refresh tokens, so a copy would go stale).
  Without an argument it prints which account the default sign-in holds.
  `ais default <default account>` swaps back.
- ais records the swap in `state.json` as `default_holds` (the extra account
  whose login now sits in the default slot). When loading the config ais
  exchanges the two accounts' credDirs for that state, so `run`, `login`,
  `switch`, `status`, the menu and the hook keep meaning the same logical
  account. `config.json` is not rewritten.
- The secret is read with `security find-generic-password -s <service> -w`
  into ais's memory only and written back with
  `security -i` (add-generic-password -U ... -X <hex>) from **stdin**, so it is
  never in argv, a log, `state.json` or a snapshot. The item's account
  attribute is read without `-w` and kept. If the second write fails ais
  restores the first item. If either slot has no item, nothing changes (exit 66).
- Identity: Infinitary's login stamp is a digest of `oauthAccount` in the shared
  `~/.claude.json`. `ais login` records the signed-in `oauthAccount` per
  account in `state.json` (profile fields: e-mail, uuids, no token). `ais default`
  writes the new holder's recorded `oauthAccount` into `~/.claude.json`,
  touching no other key (read, replace the one key, atomic rename), so the stamp
  changes and Infinitary clears its limit hold. If no identity is recorded for
  the account, the swap still happens and ais warns to run `ais login <account>`
  once.
- Holds `switch.lock` while swapping. Running `claude` sessions keep the token
  they already loaded.

## Alternatives considered
- **Automate a default-slot sign-in:** still one browser sign-in per switch.
- **Infinitary support for a second account:** outside this repository.
- **Copy instead of swap:** the other account's refresh token is rotated by
  whichever copy refreshes first and the other copy dies.
- **Rewrite `config.json` on swap:** a crash between the Keychain write and the
  config write would leave ais pointing at the wrong slot; `state.json` is
  one atomic file written after the Keychain.

## Consequences
- Amends the "never call `security` with `-w`", "never write the Keychain" and
  "never write `~/.claude.json`" rules for `ais default` only; status, menu and
  every other command keep them (FR-4.2 unchanged). T1 gains a row for this command.
- `~/.claude.json` is rewritten by Claude Code itself; a write by ais in the same
  instant could be lost. The window is one read-replace-rename; a lost write is
  repaired by running the command again.
- A crash after the Keychain swap but before `state.json` is written leaves the
  mapping inverted. The command writes `state.json` last and `ais default` with
  no argument tells the user to run `ais default <account>` again; `ais status`
  shows the credential per slot.
