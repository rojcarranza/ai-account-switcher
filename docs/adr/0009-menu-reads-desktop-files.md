# ADR-0009: Menu reads Claude Desktop's own files, read only
Status: Accepted
Area: other
Depends on: ADR-0007 (SwiftBar menu), ADR-0008 (Desktop per account).

## Context
Next to Claude Switcher, the ais menu showed `(untitled)` titles,
`(unknown)` owners, no times and no usage (rojcarranza/ai-account-switcher#54
to #57). On 2026-10-18 the user approved showing usage and real session
titles (brief non-goal 7 and out-of-scope 7 narrowed). The Mac showed:
- Each Claude Desktop data folder holds `plan-usage-history.json`
  (`{"version": 2, "samples": [{"t", "org", "u": {"fh", "sd"}}]}`), which
  Desktop appends to about every 15 minutes while that instance runs. Both
  the default and the Work folder had samples 5 and 8 minutes old, matching
  Claude Switcher's 9 %/73 % and 11 %/60 %.
- Each data folder holds one `claude-code-sessions/<account uuid>/<org
  uuid>/local_*.json` per Code-tab session, with `cliSessionId` (the
  transcript's session ID), `title`, `cwd`, `lastActivityAt` and
  `isArchived`. The folder's `config.json` names its account in
  `lastKnownAccountUuid`. Older account folders from earlier sign-ins sit
  beside it.
- `~/.claude.json` had no `cachedUsageUtilization` key. When present it covers
  only the account the CLI last signed in to.
- The Work Desktop still runs on Claude Switcher's `Claude-Work`, not
  `Claude-ais-work`.

## Decision
- The menu reads, and never writes, three things per account's Desktop data
  folder: `config.json`'s `lastKnownAccountUuid`, the session records under
  that UUID, and `plan-usage-history.json`. No Keychain read, no network,
  no token. Size and count caps keep a render under NFR-PERF; anything
  missing or malformed is skipped silently, so the menu never fails because
  of Desktop's files.
- Usage shows only the newest saved sample and its age. No reset-time
  estimate and no forecast; that is a separate decision.
- Session owner: ais's own `state.json` record first, then a Desktop record,
  else unknown.
- An extra account may set `desktop_data_dir` in `config.json` (FR-4.21),
  so ais reads and launches the Desktop folder Claude Switcher created.
  The migration guide stays valid; the key only changes which folder is used.
- The file formats are Desktop's private formats. Their parsers live in
  `src/ais/providers/claude.py` (provider-specific code) and are covered by
  fixtures copied from the observed shapes, without real titles.

## Alternatives considered
- **`~/.claude.json` `cachedUsageUtilization`:** absent on the Mac and one
  account at a time; rejected.
- **Fetch usage from Anthropic's API:** needs the OAuth token from the
  Keychain, which NFR-SEC and non-goal 6 forbid; rejected.
- **Estimate reset times and forecast like Claude Switcher:** more useful,
  but a model of the 5 h and weekly windows plus history keeping; deferred
  until the user asks for it.
- **Titles from transcripts only (status quo):** Desktop sessions start with
  tool or system lines, so most show `(untitled)`; kept only as a fallback.

## Consequences
- A Desktop update can change these private formats; the menu then quietly
  shows fewer titles or no usage instead of failing.
- Usage is as fresh as the last time that Desktop instance ran.
- Menu render reads up to 1,000 small JSON files per account; covered by
  the NFR-PERF test.
