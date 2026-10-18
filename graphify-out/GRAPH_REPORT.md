# Graph Report - graphy-cali-cli-b270a9  (2026-10-18)

## Corpus Check
- 82 files · ~59,027 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 1025 nodes · 2416 edges · 56 communities (35 shown, 21 thin omitted)
- Extraction: 91% EXTRACTED · 9% INFERRED · 0% AMBIGUOUS · INFERRED: 208 edges (avg confidence: 0.91)
- Token cost: 245,029 input · 0 output

## Community Hubs (Navigation)
- CLI Core and Accounts
- Claude Provider Internals
- Test Harness Helpers
- Menu Rendering and Sanitizing
- Menu CLI Tests
- Test Fakes and Runner Plan
- Provider Protocol
- Fake Provider
- Desktop Records Tests
- Setup Tests
- Requirements and Shared Brain
- Run Command Tests
- Open Session Tests
- Architecture and Threat Model
- Menu Render Tests
- Session Cache
- Store and Locking
- Credential State
- Runner and Signals
- Spike and Migration
- Accounts Config Tests
- Desktop Command Tests
- Desktop per Account
- ClaudeProvider Class
- Login Tests
- Menu Render Process Tests
- Billing Risks and Settings
- Snapshot Tests
- Success Metrics and Manual Checks
- Session Discovery
- Status Tests
- Signal Tests
- Desktop ADRs and Config
- Commands and Logging
- Progress and MVP Plan
- Snapshots
- Status and Usage Requirements
- Persistence and Session Handoff
- CI and Build
- Flock Tests
- SwiftBar Menu Plugin
- Project Rules and Gates
- Keychain Slot Split
- CLI Tests
- Hook Tests
- Fake claude
- Fake claude_default_sigint
- Fake claude_trap
- Fake cp
- Fake defaults
- Fake lsof
- Fake open
- Fake pgrep
- Fake ps
- Fake security

## God Nodes (most connected - your core abstractions)
1. `AisError` - 75 edges
2. `Store` - 63 edges
3. `ClaudeProvider` - 52 edges
4. `Requirements v0.4` - 47 edges
5. `SwitchTest` - 41 edges
6. `Provider` - 37 edges
7. `Account` - 34 edges
8. `TempHomeCase` - 34 edges
9. `SwitchCase` - 33 edges
10. `Session` - 31 edges

## Surprising Connections (you probably didn't know these)
- `config.json schema` --references--> `load_config()`  [INFERRED]
  docs/requirements.md → src/ais/accounts.py
- `MVP Task 12: ais login` --references--> `cmd_login()`  [INFERRED]
  docs/superpowers/plans/2026-10-16-ais-mvp.md → src/ais/core.py
- `MENU_RECENT = 30` --references--> `gather_status()`  [INFERRED]
  docs/superpowers/plans/2026-10-18-menu-sessions-usage.md → src/ais/core.py
- `MVP Task 16: ais setup (guided)` --references--> `cmd_setup()`  [INFERRED]
  docs/superpowers/plans/2026-10-16-ais-mvp.md → src/ais/core.py
- `MVP Task 17: ais uninstall and dry-run` --references--> `cmd_uninstall()`  [INFERRED]
  docs/superpowers/plans/2026-10-16-ais-mvp.md → src/ais/core.py

## Import Cycles
- None detected.

## Hyperedges (group relationships)
- **ais review subagents (architecture, security, tests)** — _claude_agents_architecture_guardian_architecture_guardian, _claude_agents_security_reviewer_security_reviewer, _claude_agents_test_auditor_test_auditor [INFERRED 0.85]
- **~/.config/ais persisted files** — docs_adr_0002_auth_account_split_ais_config_json, docs_adr_0003_persistence_json_files_state_json, docs_adr_0005_observability_local_log_ais_log, docs_adr_0003_persistence_json_files_flock_lock, docs_adr_0003_persistence_json_files_switch_mutex [INFERRED 0.85]
- **Menu render data sources** — docs_adr_0007_menu_bar_swiftbar_plugin_menu_render_sanitize, docs_adr_0009_menu_reads_desktop_files_plan_usage_history, docs_adr_0009_menu_reads_desktop_files_desktop_session_records, docs_adr_0009_menu_reads_desktop_files_last_known_account_uuid, docs_adr_0003_persistence_json_files_state_json, docs_adr_0002_auth_account_split_claude_auth_status_check [INFERRED 0.85]
- **G-1 spike evidence driving requirements** — docs_requirements_g_1_spike, docs_spike_results_g1_b_keychain_hashing, docs_spike_results_g1_g_process_detection, docs_spike_results_g1_h_auth_status, docs_spike_results_g1_f_billing_env, docs_requirements_fr_4_2, docs_requirements_fr_2_2 [INFERRED 0.85]
- **Menu sessions/usage feature (FR-4.15 to FR-4.21)** — docs_requirements_fr_4_15, docs_requirements_fr_4_16, docs_requirements_fr_4_17, docs_requirements_fr_4_18, docs_requirements_fr_4_19, docs_requirements_fr_4_20, docs_requirements_fr_4_21, docs_superpowers_plans_2026_10_18_menu_sessions_usage_task_1_per_account_groups, docs_superpowers_plans_2026_10_18_menu_sessions_usage_task_2_desktop_records, docs_superpowers_plans_2026_10_18_menu_sessions_usage_task_3_running_line, docs_superpowers_plans_2026_10_18_menu_sessions_usage_task_4_usage_lines [EXTRACTED 1.00]
- **Claude Desktop per account (FR-6)** — docs_requirements_fr_6, docs_requirements_fr_6_2, docs_superpowers_specs_2026_10_16_ais_desktop_design_user_data_dir_per_account, docs_superpowers_specs_2026_10_16_ais_desktop_design_no_duplicate_instance, docs_spike_results_desktop_spike, docs_superpowers_plans_2026_10_16_ais_mvp_task_17b, tests_fixtures_ps_desktop, docs_manual_checks_m6_check [INFERRED 0.95]

## Communities (56 total, 21 thin omitted)

### Community 0 - "CLI Core and Accounts"
Cohesion: 0.06
Nodes (78): ArgumentParser, Collection, MVP Task 1: Walking skeleton, MVP Task 15: ais status, MVP Task 4: Accounts and config validation, MVP Task 6: Guards: apply risks, path checks, Account, _check_cred_dir() (+70 more)

### Community 1 - "Claude Provider Internals"
Cohesion: 0.09
Nodes (24): datetime, _parse_time(), Everything Claude Code specific (FR-5.1). Constants come from docs/spike-…, (object, UTC seconds) for a transcript line with a zoned ISO timestamp, else…, _timed_line(), Temp HOME, tests/fakes first on PATH; env restored on cleanup., TempHomeCase, AckTest (+16 more)

### Community 2 - "Test Harness Helpers"
Cohesion: 0.11
Nodes (3): line(), limit_time with pre-launch lines `pre` and lines appended after the launch…, SwitchTest

### Community 3 - "Menu Rendering and Sanitizing"
Cohesion: 0.08
Nodes (39): T6 menu injection threat, FR-4.12 sanitize transcript/file-system text, FR-4.15 per-account session groups in menu, FR-4.16 relative session age, FR-4.17 short folders and titles, MVP Task 18: ais menu render, Menu Task 1: per-account groups, ages, short folders (#54), _ago() (+31 more)

### Community 4 - "Menu CLI Tests"
Cohesion: 0.09
Nodes (5): MenuCliTest, MenuInstallCase, MenuInstallTest, MenuUninstallTest, #42: SwiftBar runs the plugin with only its own PATH; lsof is /usr/sbin/lsof on…

### Community 5 - "Test Fakes and Runner Plan"
Cohesion: 0.10
Nodes (10): MVP Task 11: Runner: spawn, signals, exit codes, keychain_service(), Test fakes README, claude_default_sigint fake, claude_trap fake, defaults fake, open fake, security fake (+2 more)

### Community 6 - "Provider Protocol"
Cohesion: 0.07
Nodes (14): Protocol, Provider, Any, Path, Everything provider-specific goes through this interface (FR-5.1)., Shell-quoted `NAME=value ` prefix for the per-account variables in env, or ""., Newest first; only sessions of that folder when one is given., Whether the session belongs to that folder (the rule newest_session uses). (+6 more)

### Community 7 - "Fake Provider"
Cohesion: 0.08
Nodes (3): FakeProvider, Minimal provider for registry tests., ProvidersTest

### Community 8 - "Desktop Records Tests"
Cohesion: 0.24
Nodes (4): DesktopFixture, record(), RecordsTest, StatusTest

### Community 10 - "Requirements and Shared Brain"
Cohesion: 0.11
Nodes (27): Concurrency: fcntl.flock, switch mutex, process-cwd open detection, One shared brain (~/.claude shared by both accounts), Requirements v0.4, config.json schema, Exit codes 64-78 (sysexits) and claude passthrough / 128+N, FR-2 One shared brain, set up safely, FR-2.2 billing guard (exit 77), FR-2.8 per-pair cross-account acknowledgement (+19 more)

### Community 13 - "Architecture and Threat Model"
Cohesion: 0.11
Nodes (23): Architecture, C4 system context (ais, SwiftBar, Claude Code, Desktop, Keychain, ~/.claude), Data model and ownership table, Deployment: zipapp, make install, ais.prev rollback, GitHub Actions CI, Provider interface (typing.Protocol), Architecture fresh-context review (B1, B2, M1-M12), Rules for agents: no new dependency/service without ADR, T2 billing/account routing via inherited env or settings (+15 more)

### Community 15 - "Session Cache"
Cohesion: 0.11
Nodes (5): MVP Task 7: Session resolution with cache, Cache, Per-file (folder, title) cache in cache.json, keyed by path and valid for the…, With on_error, a failed read or save is reported there and the cache starts…, SessionsTest

### Community 16 - "Store and Locking"
Cohesion: 0.17
Nodes (5): OSError, Store, _sync(), mode(), StoreTest

### Community 17 - "Credential State"
Cohesion: 0.14
Nodes (3): credential_state(), (state, source, error); `auth status` results are cached 10 minutes, Keychain…, CredentialsTest

### Community 18 - "Runner and Signals"
Cohesion: 0.15
Nodes (10): ais container view (cli, core, menu, accounts, guards, store, runner, providers), Runner signal handling (ignore SIGINT/SIGQUIT, forward SIGHUP/SIGTERM, 128+N), _noop(), Path, Start the interactive child, wait for it and pass its exit code through…, Run cmd in the terminal's foreground group; return its exit code, or 128+N if…, run_claude(), _spawn_error() (+2 more)

### Community 19 - "Spike and Migration"
Cohesion: 0.17
Nodes (20): Open questions (terms, session handoff, ~/.claude.json, concurrency, next provider), Moving from Claude Switcher to ais, Migration keep list (work credDir, f9fb4ac6 and default Keychain items, ~/.claude), credDir (canonical path string selecting a Keychain slot), Build gate G-1 spike (a)-(j), Build gate G-2 terms of service, Spike results (G-1, G-2, G-3), Coexistence with Claude Switcher (shared f9fb4ac6 slot) (+12 more)

### Community 22 - "Desktop per Account"
Cohesion: 0.16
Nodes (15): FR-4.18 Running: line, FR-6 Claude Desktop per account, FR-6.2 no duplicate Desktop instance (ps detection), Desktop spike: --user-data-dir instances, duplicate launch caveat, MVP Task 17b: ais desktop, Menu Task 3: Running: line (#56), ais Desktop instances per account design, Builder-check answers 1-8 (+7 more)

### Community 23 - "ClaudeProvider Class"
Cohesion: 0.13
Nodes (4): ClaudeProvider, FR-3.14 end-to-end seconds: from the LIMIT_MARKER line the session stopped at…, FR-4.19: session ID -> (title, lastActivityAt ms) from Desktop's records; every…, Existence check by exit code only: no -w/-g, stdout discarded, so no secret is…

### Community 25 - "Menu Render Process Tests"
Cohesion: 0.20
Nodes (3): `ais menu render` as SwiftBar runs it: a process, with a stdin pipe that is…, Interpreter and import time, subtracted from the 5 s bound so a slow CI box…, RenderProcessTest

### Community 26 - "Billing Risks and Settings"
Cohesion: 0.19
Nodes (15): default_settings_roots(), _global_risks(), _main_checkout(), _prompt_title(), Any, Path, For a worktree's `.git` file ("gitdir: <X>/.git/worktrees/<name>"), return <X>., Repo root and, for a worktree, the main checkout; claude reads their local… (+7 more)

### Community 28 - "Success Metrics and Manual Checks"
Cohesion: 0.15
Nodes (15): Success metrics: 95% switches < 30 s, zero context loss, Manual checks on the Mac, M1 Both accounts signed in, M2 Switch under 30 s, M3 Menu bar, M4 Measurements (p95), M5 NFD folder and process detection, M6 Claude Desktop per account (+7 more)

### Community 29 - "Session Discovery"
Cohesion: 0.25
Nodes (6): End-to-end seconds from the limit hit to the first transcript line appended…, Session, _nfc_real(), Sessions from projects/*/*.jsonl (top level only: subagent transcripts live…, Lowest PID of a claude with cwd in the session folder; the daemon and bg-*…, _same_folder()

### Community 32 - "Desktop ADRs and Config"
Cohesion: 0.20
Nodes (12): Provider-specific code only in src/ais/providers/<name>.py, ~/.config/ais/config.json account list, ADR-0008 Claude Desktop instance per data folder, migrate-from-claude-switcher guide, providers/claude.py Desktop facts, Desktop instance via --user-data-dir=Claude-ais-<account>, ADR-0009 Menu reads Desktop files read-only, desktop_data_dir config override (FR-4.21) (+4 more)

### Community 33 - "Commands and Logging"
Cohesion: 0.22
Nodes (11): ADR-0005 Local append-only log, ~/.config/ais/ais.log (O_APPEND, 1MB rotation), Switch-time success metric, ais login command, ais README, ais run command, ais status command, ais switch command (+3 more)

### Community 34 - "Progress and MVP Plan"
Cohesion: 0.20
Nodes (11): Progress: AI Account Switcher, Progress build-gate and feature checklist, Traceability requirement -> task -> test, ais MVP Implementation Plan, Global constraints (Python 3.9, exit codes, flock, timeouts, fakes), Review Focus (unicode paths, open session, hung tools, duplicate Desktop), MVP Task 12: ais login, MVP Task 16: ais setup (guided) (+3 more)

### Community 35 - "Snapshots"
Cohesion: 0.27
Nodes (6): _entry_time(), _NoSpace, Exception, Path, Copy paths into snapshots/<UTC stamp>-<id>/ (APFS clone, else plain copy); None…, _restrict()

### Community 36 - "Status and Usage Requirements"
Cohesion: 0.24
Nodes (10): FR-4 Status at a glance, FR-4.19 owners/titles from Desktop session records, FR-4.2 credential check via claude auth status loggedIn, Keychain fallback, FR-4.20 usage lines from plan-usage-history.json, FR-4.21 desktop_data_dir override, MVP Task 10: Credential check and cache, Menu sessions/usage Implementation Plan, MENU_RECENT = 30 (+2 more)

### Community 37 - "Persistence and Session Handoff"
Cohesion: 0.28
Nodes (9): architecture-guardian agent, ADR-0003 JSON files in ~/.config/ais, fcntl.flock on ~/.config/ais/.lock with atomic rename, Session snapshots (APFS clones, 20/500MB/30d cap), switch.lock mutex from open check to spawn, ADR-0006 ais resolves session, Claude resumes it, claude --resume <id> under target account, Open-session check via claude process cwd (+1 more)

### Community 38 - "CI and Build"
Cohesion: 0.25
Nodes (9): CI workflow (ci.yml), CI linux job (Python 3.9/3.12 matrix), CI macos job (gated by RUN_MACOS_CI), Tests use temp HOME and fake claude/security/pgrep/lsof/ps/open on PATH, ADR-0001 Python 3.9+ stdlib runtime, Python 3.9 stdlib-only constraint, ADR-0004 Local single-file zipapp, make install to ~/.local/bin with ais.prev (+1 more)

### Community 39 - "Flock Tests"
Cohesion: 0.39
Nodes (3): finish(), FlockTest, run_py()

### Community 40 - "SwiftBar Menu Plugin"
Cohesion: 0.29
Nodes (7): security-reviewer agent, Transcript text is untrusted: sanitize for SwiftBar menu, ~/.config/ais/state.json, ADR-0007 Optional SwiftBar menu plugin, menu.py rendering with sanitized transcript fields, SwiftBar plugin ais.1m.sh (exec ais menu render), ais menu install/uninstall

### Community 41 - "Project Rules and Gates"
Cohesion: 0.29
Nodes (7): test-auditor agent, Build gates G-1 to G-3, ais exit codes 64-78 with claude passthrough, Never set CLAUDE_CONFIG_DIR, Issue-linked PR workflow with /code-review, AIS project rules (CLAUDE.md), TDD: failing test first

### Community 42 - "Keychain Slot Split"
Cohesion: 0.38
Nodes (7): CLAUDE_SECURESTORAGE_CONFIG_DIR handling, ADR-0002 Per-account Keychain slot, own setup, Credential check via claude auth status (10-min cache), Claude Switcher (kevinchau/claude-switcher), Keychain service name = Claude Code-credentials-<sha256(NFC(dir))[:8]>, Keychain slot split via CLAUDE_SECURESTORAGE_CONFIG_DIR, ais setup command

### Community 44 - "Hook Tests"
Cohesion: 0.53
Nodes (3): bash_hook(), BashHookTest, blocked()

## Ambiguous Edges - Review These
- `process_cwds()` → `MVP Task 8: Open-session detection`  [AMBIGUOUS]
  docs/superpowers/plans/2026-10-16-ais-mvp.md · relation: references

## Knowledge Gaps
- **31 isolated node(s):** `security-reviewer agent`, `test-auditor agent`, `Build gates G-1 to G-3`, `ais exit codes 64-78 with claude passthrough`, `Issue-linked PR workflow with /code-review` (+26 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **21 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **What is the exact relationship between `process_cwds()` and `MVP Task 8: Open-session detection`?**
  _Edge tagged AMBIGUOUS (relation: references) - confidence is low._
- **Why does `ClaudeProvider` connect `ClaudeProvider Class` to `CLI Core and Accounts`, `Claude Provider Internals`, `Test Harness Helpers`, `Test Fakes and Runner Plan`, `Fake Provider`, `Desktop Records Tests`, `Setup Tests`, `Requirements and Shared Brain`, `Run Command Tests`, `Open Session Tests`, `Session Cache`, `Credential State`, `Runner and Signals`, `Desktop per Account`, `Login Tests`, `Billing Risks and Settings`, `Snapshot Tests`, `Session Discovery`, `Status Tests`, `Status and Usage Requirements`?**
  _High betweenness centrality (0.204) - this node is a cross-community bridge._
- **Why does `AisError` connect `CLI Core and Accounts` to `Claude Provider Internals`, `Snapshots`, `Menu CLI Tests`, `Fake Provider`, `Setup Tests`, `Requirements and Shared Brain`, `Run Command Tests`, `Session Cache`, `Store and Locking`, `Credential State`, `Runner and Signals`, `Accounts Config Tests`, `Desktop per Account`, `ClaudeProvider Class`, `Login Tests`, `Snapshot Tests`?**
  _High betweenness centrality (0.187) - this node is a cross-community bridge._
- **Why does `SwitchCase` connect `Claude Provider Internals` to `Test Harness Helpers`, `Menu CLI Tests`, `Desktop Records Tests`, `Menu Render Tests`, `Desktop Command Tests`, `ClaudeProvider Class`, `Menu Render Process Tests`, `Status Tests`?**
  _High betweenness centrality (0.119) - this node is a cross-community bridge._
- **Are the 26 inferred relationships involving `AisError` (e.g. with `Exit codes 64-78 (sysexits) and claude passthrough / 128+N` and `MVP Task 3: Store: files, flock, switch mutex, log`) actually correct?**
  _`AisError` has 26 INFERRED edges - model-reasoned connections that need verification._
- **Are the 19 inferred relationships involving `Store` (e.g. with `FR-5.6 flock on ~/.config/ais/.lock` and `MVP Task 3: Store: files, flock, switch mutex, log`) actually correct?**
  _`Store` has 19 INFERRED edges - model-reasoned connections that need verification._
- **Are the 16 inferred relationships involving `ClaudeProvider` (e.g. with `MVP Task 5: Provider interface, registry and Claude environment` and `Account`) actually correct?**
  _`ClaudeProvider` has 16 INFERRED edges - model-reasoned connections that need verification._