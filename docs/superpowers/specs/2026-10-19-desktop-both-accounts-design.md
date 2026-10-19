# Design: both accounts' sessions in Claude Desktop (rojcarranza/ai-account-switcher#1)

Status: Approved 2026-10-19 by the user; amended the same day after M6 step 7 showed Desktop's import does not bring the other account's Desktop sessions (user approved the rewrite). Issue #1 stays open.
Evidence: `docs/spike-results.md`, section "Desktop: one app for both accounts".
The user skipped the design questions and asked for a draft from the findings, so every decision below is the author's call unless marked as the user's.

## Intent
Issue #1 asks for one Claude Desktop that switches between Personal and Work and shows both accounts' sessions, so all history is in one place and any session can continue on either account.

## What the exploration changed
- **One Desktop cannot list the other account's Desktop sessions.** Desktop keeps one session list per data folder and account; each record points at a transcript in the shared `~/.claude`. Desktop's own "Import Claude Code CLI Sessions…" adds terminal sessions and same-account sibling sessions only (checked in the app, `docs/spike-results.md`).
- **Switching accounts inside one Desktop cannot be done by ais.** Desktop keeps one sign-in per data folder (`oauth:tokenCache` in `config.json`). Desktop has a native `multiAccount` feature, but it is behind a server-side gate that is off for this user (inferred from the flag cache). The only ais route is to swap Desktop's stored sign-in. That reads and writes a credential, which NFR-SEC and ADR-0008 forbid.

## Decision (author's call)
1. Keep one Desktop instance per account (ADR-0008). Do not build an account switcher inside one Desktop.
2. Both accounts' sessions are seen together only in the ais menu (FR-4.15). ais does not copy, write or delete any Desktop record (ADR-0009 stays read-only).
3. To continue a session on the other account, the user uses the menu's existing `Resume in <account>` item (terminal, FR-4.8).
4. Before continuing a session on the other account, the user quits the Desktop that has it open. Desktop only stops two loaded sessions writing one transcript inside a single instance, not across instances. The menu already marks such a session `open` and shows "Quit Claude in <folder> to resume" (FR-4.13), because Desktop's embedded `claude` has the folder as its cwd (spike (g)). No new detection is needed.
5. Revisit when Desktop's native multi-account switching is available to the user. ADR-0008's deferred alternative now points at this design.

## Goals
- `docs/usage.md` says plainly that one Desktop shows one account's sessions and how to continue on the other account.
- The user can continue any session on either account through ways that already exist.
- The written record (requirements, brief, ADR-0008) matches what ais does and does not do.

## Non-goals
- No ais command that imports, copies or links sessions between Desktop data folders.
- No Desktop sign-in swap, and no reading of `oauth:tokenCache` or any credential.
- No detection of Desktop's `multiAccount` gate. The flag cache is a private format, and a gate change shows up in Desktop's own UI.
- No `claude://code/…` deep links from the menu. With two instances running, macOS chooses which one receives the URL, so the link might open the wrong account (inferred, not tested).

## Anti-goals (failure even if it works)
- Any write into `~/Library/Application Support/Claude*`. A Desktop update could then corrupt a session list that ais filled.
- Any handling of Desktop's sign-in tokens.
- Two Desktop processes writing one transcript because ais suggested opening it in both.

## Changes
Docs only. No code, tests or provider methods change.
- `docs/usage.md`, under "Claude Desktop per account": a short "Both accounts' sessions in one window" part with:
  - that each Desktop lists only its own account's sessions, and what the Import menu item does and does not add,
  - `Resume in <account>` as the way to continue on the other account,
  - the rule "quit the Desktop that has it open first".
- `docs/manual-checks.md` M6: one added step. Import in the Work Desktop, then check that a Personal session appears, opens and continues. Then check that the menu shows it `open` while it runs.
- `docs/requirements.md`:
  - narrow Out of scope item 1 to "no single Desktop that switches accounts; listing both accounts' sessions uses Desktop's own import (#1)",
  - add a Review log entry.
- `docs/brief.md`: the same narrowing in non-goal 1, plus a Change log line.
- `docs/adr/0008-desktop-instance-per-account.md`: the "One Desktop that switches accounts…" alternative is updated to record the finding and point at this design. This changes no decision, so it needs no new ADR.
- `docs/spike-results.md`: the findings section (already written).

## Left to the builder
- Exact wording and placement inside each doc.
- Whether the M6 step is a new numbered step or an extension of an existing one.

## Open risk
- Desktop's import and its record format are private. A Desktop update can change or remove the menu item. Then the docs are wrong, but no ais behaviour breaks.
