# Progress: AI Account Switcher
Plan: `docs/superpowers/plans/2026-10-16-ais-mvp.md` (approved 2026-10-16).

## Build gates (tick only when recorded in docs/spike-results.md)
- [x] G-1 spike (a) to (j) with failure rules applied (task 2)
- [x] G-2 terms answer recorded in docs/requirements.md Review log (task 2)
- [x] G-3 work plan type recorded (task 2)
- [x] Global lock fallback (task 9): skipped, G-1(e) passed with two accounts

## Feature checklist (tick only when verification passes)
- [ ] FR-1 Two accounts signed in side by side (verify: `python3 -m unittest tests.test_accounts tests.test_providers` passes; manual check M1)
- [ ] FR-2 One shared brain, set up safely (verify: `python3 -m unittest tests.test_env tests.test_setup tests.test_ack` passes)
- [ ] FR-3 One-command switch, resume and run (verify: `python3 -m unittest tests.test_switch tests.test_run tests.test_open tests.test_signals tests.test_snapshots` passes; manual check M2 under 30 s)
- [ ] FR-4 Status at a glance (verify: `python3 -m unittest tests.test_status tests.test_menu` passes; manual check M3)
- [ ] FR-5 Built for more AIs, reversible install (verify: `python3 -m unittest tests.test_providers tests.test_uninstall tests.test_dry_run tests.test_flock` passes)
- [ ] FR-6 Claude Desktop per account (verify: `python3 -m unittest tests.test_desktop` passes; manual check M6)
- [ ] NFR-PERF measured on the Mac (verify: manual check M4)

## Log
- 2026-10-16 planning: phases 0 to 6 approved; next Task 1 (walking skeleton); blockers: none (docs pushed to the repo).
- 2026-10-16 task 1 Mac checks (walking skeleton built, tests green): `python3` on PATH is 3.14.6 (Homebrew), system `/usr/bin/python3` is 3.9.6; `claude` 2.1.301; default account logged in (claude.ai, pro; email and org ID redacted). OPEN INPUT for task 2 G-1(b): `CLAUDE_SECURESTORAGE_CONFIG_DIR="$HOME/.claude-accounts/work" claude auth status` returned the same account and `configDirectory /Users/roj/.claude` as the default call. Possible causes, not investigated: `~/.claude-accounts/work` is absent or not logged in, or the variable is ignored.
- 2026-10-16 task 2 (#3): all gates have a result except the (e) rerun, see `docs/spike-results.md`. The first (e) run likely had WORK in both slots; PERSONAL was restored in the default slot at 22:22. The open input above is resolved: `auth status` prints the shared `~/.claude.json` identity, not the slot's (G-1(h)); the slots hold separate credentials (G-1(b), (c)). (a) works, and the user kept the MVP scope. Desktop per account added as FR-6 (#4).
- 2026-10-16 task 2 done (#3): the (e) rerun (23:21 to 23:51) passed with PERSONAL and WORK at the same time, 15/15 rounds each, no slot or identity change, no broken file. Task 9 skipped. Next: task 3.
