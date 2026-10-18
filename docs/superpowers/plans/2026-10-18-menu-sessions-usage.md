# Menu: sessions per account, titles, running, usage — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the ais SwiftBar menu as organized as Claude Switcher's: sessions grouped per account with real titles and ages, a `Running:` line, and each account's latest usage sample.

**Architecture:** `core.gather_status` gathers more facts (more sessions, owner and title from Desktop records, running Desktops, usage samples); `menu.render` lays them out. Desktop file parsing is provider-specific and lives in `providers/claude.py`. Everything new is read only (ADR-0009).

**Tech Stack:** Python 3.9 stdlib, unittest, SwiftBar plugin text format.

**Spec:** `docs/requirements.md` FR-4.8, FR-4.15 to FR-4.21, FR-6.1, NFR-SEC, NFR-PERF (change 2026-10-18); `docs/adr/0009-menu-reads-desktop-files.md`.

## Global Constraints
- Python 3.9 syntax only; stdlib only; provider-specific code only in `src/ais/providers/claude.py`.
- Untrusted text (titles, folders, labels) is sanitized with `menu.sanitize`, never starts a line with `-`, never enters an action (FR-4.12, FR-4.17).
- Actions carry only a validated UUID and account name (FR-4.8, FR-6.5).
- Desktop files are only read; tests use fixture folders under the temp HOME, never the real `~/Library`.
- `ais menu render` still finishes p95 < 2 s and within 5 s (NFR-PERF, FR-4.11).
- One task = one issue = one PR; hand over to a fresh session after each.

## Review Focus
- A title or folder starting with `-` or holding `|`/newlines: must not nest or inject (test in Task 1).
- `modified` missing (`None`) or in the future: no age / `just now` (Task 1).
- Desktop record naming a session whose transcript is gone, or archived: ignored (Task 2).
- `plan-usage-history.json` with `fh`/`sd` missing, non-numeric, > 100 or samples unsorted (Task 4).
- `desktop_data_dir` pointing outside `~/Library/Application Support` or via a symlink out: exit 78 (Task 2).

---

### Task 1: Per-account groups, ages, short folders and titles (#54)

**Files:**
- Modify: `src/ais/core.py` (`gather_status` gets `recent_count`), `src/ais/menu.py` (`render`, helpers)
- Test: `tests/test_menu.py`
- Docs already in this PR: brief, requirements, ADR-0009, architecture, this plan.

**Interfaces:**
- Produces: `core.MENU_RECENT = 30`; `core.gather_status(ctx, cache_only, open_warnings=None, recent_count=RECENT_COUNT) -> dict` (`recent` holds `recent_count` sessions; `ais status --json` unchanged at 5).
- Produces: `menu.render(status: dict, privacy: bool, ais_path: str, now: Optional[float] = None) -> str` (`now` = epoch seconds, default `time.time()`).
- Produces: `menu._ago(modified: Optional[str], now: float) -> Optional[str]` (ISO `%Y-%m-%dT%H:%M:%SZ`, FR-4.16), `menu._short_folder(folder: str) -> str`, `menu._short_title(title: str) -> str` (FR-4.17).
- Later tasks rely on: a session dict's owner key stays `last_used`; the header is built by one helper `_header(account: dict, label: str) -> List[str]` that Task 4 extends with usage lines.

Layout for the fixture `status()` in `tests/test_menu.py` (now = `2026-10-16T12:00:00Z`; `Second` has `last_used: None`):

```
Personal
---
✓ Personal
Sessions (1)
--Main task · 2 h ago
----/Users/x/proj
----Resume in Work | bash=/opt/ais/ais param1=switch param2=--session param3=<UUID> param4=work terminal=true
---
Work · credential unknown
---
Other sessions (account unknown)
--Second · open
----/Users/x/other
----Quit Claude in /Users/x/other to resume | disabled=true
---
Open Personal Desktop | bash=/opt/ais/ais param1=desktop param2=personal terminal=false
Open Work Desktop | bash=/opt/ais/ais param1=desktop param2=work terminal=false
```
Warnings (`Warning: …`) go after the groups, before the last `---`, as today. Privacy mode keeps the header lines (`✓ Personal`, `Work · credential unknown`) and replaces the groups with today's `recent sessions: N, open: M` line.

- [ ] **Step 1: Replace the old-layout tests** (user approved replacing them on 2026-10-18): `test_render_from_fixed_status` asserts the layout above exactly; `test_malicious_title_and_folder_sanitized_not_in_action`, `test_open_session_shows_disabled_quit_item` (`----Quit Claude in /Users/x/other to resume | disabled=true`), `test_privacy_mode_hides_folders_and_titles`, `test_label_leading_dashes_stripped`, `test_render_end_to_end` (`✓ Personal` present, `--Main task · ` line present) keep their intent with the new line shapes. Add:
  - `test_age_buckets`: `_ago` gives `just now` (30 s, and +5 min future), `59 min ago`, `47 h ago`, `2 d ago` (49 h), `None` for `None`.
  - `test_short_folder_and_title`: `/Users/x/` + 60-char path → `/Users/…/<last>`; home-relative → `~/…/<last>`; 60-char title → 49 chars + `…`.
  - `test_dash_title_does_not_nest`: title `--Evil` renders `--Evil · 2 h ago`'s text as `Evil` (line `--Evil · …` exactly one level).
  - `test_ten_per_group_newest_first`: 12 sessions of `personal` → `Sessions (10)` and 10 items.
  - `test_menu_uses_30_recent_status_json_keeps_5`: `cmd_menu_render` path passes `MENU_RECENT`; `ais status --json` still lists 5.
- [ ] **Step 2: Run** `python3 -m unittest tests.test_menu` — expect failures in the new and replaced tests.
- [ ] **Step 3: Implement** per the interfaces. `Sessions (n)` counts the shown items (≤ 10). Untitled session → shortened folder as title.
- [ ] **Step 4: Run** `python3 -m unittest discover -s tests -t .` on `python3` and `/usr/bin/python3` — all pass; `python3 -m compileall -q src tests` clean.
- [ ] **Step 5: Commit** `feat(menu): group sessions per account with ages and short folders`.

### Task 2: Titles and owners from Desktop records; `desktop_data_dir` (#55)

**Files:** `src/ais/providers/base.py`, `src/ais/providers/claude.py`, `src/ais/accounts.py` (config key), `src/ais/core.py`; tests `tests/test_desktop_records.py`, `tests/test_desktop.py`, `tests/test_accounts.py`.

**Interfaces:**
- `Account.desktop_data_dir: Optional[str]` (loaded from `config.json`; validated per FR-4.21, else `AisError` exit 78).
- `ClaudeProvider.desktop_data_dir(account, home)` returns `Path(account.desktop_data_dir)` when set.
- `Provider.desktop_records(data_dir: Optional[Path], home: Path) -> Dict[str, Tuple[str, int]]` — session ID → (title, lastActivityAt ms), FR-4.19 caps and skips.
- `gather_status`: each `recent` entry gets `owner` filled from state.json, else the record with the newest `lastActivityAt`; `title` replaced by the record's title when present. Keep the key `last_used` for the owner so `menu.render` is unchanged.
- Tests: fixture records shaped like ADR-0009 (no real titles); archived, oversized, wrong-UUID-folder and malformed records skipped; state.json beats Desktop; `ais desktop work` launches with the override.

### Task 3: `Running:` line (#56)

**Interfaces:** `gather_status` adds `"running": [account names]` using one `ps -x -ww -o pid=,args=` call and the existing `_desktop_pid` parser per account data dir; `render` prints `Running: <labels>` first when non-empty (also in privacy mode). Tests: none running → no line; ps failure → no line, no warning; ais-launched and override folders both detected.

### Task 4: Usage lines (#57)

**Interfaces:** `Provider.desktop_usage(data_dir, home) -> Optional[dict]` returning `{"t": ms, "fh": Optional[int], "sd": Optional[int]}` from the newest sample (FR-4.20 caps); `gather_status` adds `usage` per account; `menu._header` appends `5h  N% | image=<png>`, `week  N% | image=<png>`, `updated <age>` or `usage: no sample in the last 24 h`; icons per FR-4.22. Tests: bar fill width and colour (blue, orange from 80, red at 100), clamping, missing key → `?`, 25 h old → no-sample line, missing file → nothing, privacy shows usage.

### After each task
Open the PR (`Closes #N`), run `/code-review` until clean, CI green, build the zipapp and run `ais menu render` with a scratch HOME (copied fixtures, real Desktop files only copied read only), leave a hand-over note in the shared notes folder, and hand over to a fresh session. Never merge without the user's approval.
