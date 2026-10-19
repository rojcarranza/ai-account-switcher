# Both Accounts' Sessions in Desktop Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Write down how to see both accounts' sessions in one Claude Desktop using Desktop's own import. Record why ais does not switch accounts inside one Desktop.

**Architecture:** Docs only. No source, test or provider change. ais stays one Desktop instance per account (ADR-0008) and reads Desktop files only (ADR-0009).

**Tech Stack:** Markdown in `docs/`.

**Spec:** `docs/superpowers/specs/2026-10-19-desktop-both-accounts-design.md` (approved by the user 2026-10-19). Evidence: `docs/spike-results.md`, section "Desktop: one app for both accounts".

## Global Constraints

- No change under `src/` or `tests/`. No new ADR: no decision changes.
- No doc may tell the user, or ais, to write, move or delete anything in `~/Library/Application Support/Claude*`, or to touch `oauth:tokenCache`.
- Do not quote real session titles, account or org UUIDs.
- Commits use Roj's git identity only, with no AI attribution or co-author trailer. Use Conventional Commits with a scope.
- Run `git restore graphify-out` before each commit. Never stage `graphify-out/`.
- One PR for the branch, with `Closes #1` in its body.

## Review Focus

- A user imports in both Desktops and then opens one session in both at once. The docs must say to quit it in one Desktop first. Covered in Task 1, by the usage text and the M6 step.
- A user expects the import to sync. Desktop's import is a one-time copy of list entries, and later sessions need a new import (inferred). The usage text must say "run it again for newer sessions". Task 1.
- A user expects one Desktop to switch accounts. The usage text and the narrowed non-goal must say it does not. Tasks 1 and 2.
- Desktop removes or renames the import item. The usage text names it as Desktop's own feature, so a missing item is not read as an ais bug. Task 1.
- Archived sessions: the spec does not cover whether the import brings archived sessions over. Left unstated; not claimed in the docs.

---

### Task 1: User-facing steps and the manual check

**Files:**
- Modify: `docs/usage.md` (after the paragraph ending "prints `<label> Desktop is already open (PID n)` and starts nothing.", before `## Signing in`)
- Modify: `docs/manual-checks.md` (M6: steps list and Expected line)

**Interfaces:**
- Consumes: the existing menu items `Resume in <account>` (FR-4.8), `Open <label> Desktop` (FR-6.5), and the `open` marker with "Quit Claude in <folder> to resume" (FR-4.13).
- Produces: nothing other tasks depend on.

- [ ] **Step 1: Add a `### Both accounts' sessions in one window` subsection to `docs/usage.md`** with these facts, in this order:
  1. Each Desktop lists only its own account's sessions.
  2. In the Desktop window you want to use, choose Desktop's own "Import Claude Code CLI Sessions…". It adds the other account's sessions and terminal sessions to that window's list. Transcripts are shared in `~/.claude`, so nothing is duplicated. Run it again to pick up newer sessions.
  3. To continue a session on the other account, use one of these:
     - `Resume in <account>` in the ais menu (Terminal), or
     - `Open <label> Desktop`, after importing the session there.
  4. Quit a session in one Desktop before you open it in the other. The ais menu shows it as `open` while it runs.
  5. One Desktop window cannot switch accounts. Use one window per account.

- [ ] **Step 2: Add a step 7 to M6 in `docs/manual-checks.md`.** It reads: in Work Desktop, run "Import Claude Code CLI Sessions…"; open a Personal session from its list and send one message; then check the ais menu. Append to the Expected line: the Personal session appears in Work Desktop's list and continues there, and while it runs the ais menu shows it `open` with "Quit Claude in <folder> to resume".

- [ ] **Step 3: Check the wording.** Run `git grep -n "Import Claude Code CLI Sessions" docs/usage.md docs/manual-checks.md`. Expected: one or more hits in each file.

- [ ] **Step 4: Commit**

```bash
git restore graphify-out
git add docs/usage.md docs/manual-checks.md
git commit -m "docs(desktop): explain both accounts' sessions via Desktop import"
```

### Task 2: Record the decision

**Files:**
- Modify: `docs/requirements.md` (Out of scope item 1; new entry at the end of `## Review log`)
- Modify: `docs/brief.md` (Non-goals item 1; new line at the end of `## Change log`)
- Modify: `docs/adr/0008-desktop-instance-per-account.md` (the "**One Desktop that switches accounts and lists both accounts' sessions:**" bullet under Alternatives considered)
- Modify: `docs/superpowers/specs/2026-10-19-desktop-both-accounts-design.md` (Status line)
- Add (already written): `docs/spike-results.md` findings section

**Interfaces:**
- Consumes: Task 1's subsection title `Both accounts' sessions in one window`. The new text points readers to it.
- Produces: nothing.

- [ ] **Step 1: Replace Out of scope item 1 in `docs/requirements.md`** with: `1. No claude.ai web chat. Claude Desktop only as one separate instance per account (FR-6); no single Desktop that switches accounts. Listing both accounts' sessions in one window uses Desktop's own "Import Claude Code CLI Sessions…" (docs/usage.md; rojcarranza/ai-account-switcher#1, design docs/superpowers/specs/2026-10-19-desktop-both-accounts-design.md).`

- [ ] **Step 2: Append a Review log entry to `docs/requirements.md`:** `Change 2026-10-19 (user approved, rojcarranza/ai-account-switcher#1):` then two bullets:
  - Out of scope 1 is narrowed: Desktop's own import lists both accounts' sessions. ais adds no code and never writes Desktop files.
  - Switching accounts inside one Desktop is rejected for now. It would need ais to swap Desktop's stored sign-in (NFR-SEC, FR-6.4). Desktop's native multi-account feature is gated off for the user (`docs/spike-results.md`).

- [ ] **Step 3: Make the same narrowing in `docs/brief.md` non-goal 1.** Add a Change log line: `- 2026-10-19: non-goal 1 narrowed: both accounts' sessions show in one Desktop through Desktop's own import; one Desktop still does not switch accounts (user approved; rojcarranza/ai-account-switcher#1, design docs/superpowers/specs/2026-10-19-desktop-both-accounts-design.md).`

- [ ] **Step 4: Rewrite the ADR-0008 alternative bullet.** It now says:
  - **One Desktop that switches accounts and lists both accounts' sessions:** explored on 2026-10-19 (`docs/spike-results.md`).
  - Listing both accounts' sessions works through Desktop's own import.
  - Switching needs Desktop's gated multi-account feature, or a sign-in swap that NFR-SEC and ADR-0008 rule out.
  - Kept one instance per account; see `docs/superpowers/specs/2026-10-19-desktop-both-accounts-design.md`.

  The Decision section stays unchanged.

- [ ] **Step 5: Set the spec's Status line** to `Approved 2026-10-19 by the user.`

- [ ] **Step 6: Verify nothing else broke.** Run `python3 -m unittest discover -s tests -t .`. Expected: `OK`, with the same test count as on main. Then run `git grep -n "no single Desktop that lists both" docs`. Expected: no hits.

- [ ] **Step 7: Commit**

```bash
git restore graphify-out
git add docs/requirements.md docs/brief.md docs/adr/0008-desktop-instance-per-account.md docs/spike-results.md docs/superpowers/specs/2026-10-19-desktop-both-accounts-design.md docs/superpowers/plans/2026-10-19-desktop-both-accounts.md
git commit -m "docs(desktop): record issue #1 findings and narrow the Desktop non-goal"
```

### Task 3: PR and review

- [ ] **Step 1:** Run `/graphify . --update` (repo rule after doc changes), then `git restore graphify-out`.
- [ ] **Step 2:** Push the branch. Open a PR against `main` with `Closes #1` in the body. Run `/code-review` on it and fix the findings. If fixing one would mean editing a test, ask first. Re-run the review until it is clean.
- [ ] **Step 3:** No install is needed: no code or plugin changed, so skip `make install` and `ais menu install`.
