# ADR-0007: Menu bar status: optional SwiftBar plugin
Status: Accepted
Area: other
Depends on: G-1 spike (requirements); a failed check means a superseding ADR.

## Context
The user wants menu bar status like Claude Switcher's, while keeping ais
simple, robust and easy to set up (brief MVP bullet 4 and non-goal 4,
changed 2026-10-16). The architecture review found that a shell plugin
would need `jq` and `timeout` (not on macOS) and that transcript text
could inject menu actions (B2, M6).

## Decision
- An optional plugin for SwiftBar (open-source macOS menu bar app that
  shows the output of scripts; the user installs it with
  `brew install --cask swiftbar`). ais never installs SwiftBar.
- The plugin `ais.1m.sh` is one line plus an explicit `PATH`:
  `exec ais menu render`. All logic, the 5 s deadline and sanitizing live
  in `menu.py`.
- Every transcript-derived field (title, folder) has `|`, newlines and
  control characters removed and never appears in an action. Actions run
  `ais switch --session <uuid> <account>` in a new Terminal window; ais
  looks up and validates the folder itself.
- The menu never prompts: credentials come from the 10-minute
  `claude auth status` cache or the Keychain existence check.
- `ais menu install` / `uninstall` write or remove only that file after a
  yes and record it in `state.json`.
- SwiftBar's plugin folder lookup, refresh file naming, Terminal action
  parameters and plugin `PATH` are verified in G-1(i).

## Alternatives considered
- **Native Swift menu bar app (like Claude Switcher):** most polished, but
  needs Xcode, signing and a second codebase.
- **xbar:** same plugin idea, older project; SwiftBar is the more actively
  maintained of the two (verify at spike time).
- **No menu (CLI only):** simplest, but misses the at-a-glance status the
  user asked for.

## Consequences
- One optional third-party app, installed by the user; ais works without
  it.
- Menu rendering runs every minute, so it must stay under 2 s (NFR-PERF).
- Menu actions open Terminal because `claude` is interactive.
