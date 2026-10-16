# Progress: AI Account Switcher
Plan: `docs/superpowers/plans/2026-10-16-ais-mvp.md` (approved 2026-10-16).

## Build gates (tick only when recorded in docs/spike-results.md)
- [ ] G-1 spike (a) to (j) with failure rules applied (task 2)
- [ ] G-2 terms answer recorded in docs/requirements.md Review log (task 2)
- [ ] G-3 work plan type recorded (task 2)
- [ ] Global lock fallback (task 9): needed / skipped per G-1(e)

## Feature checklist (tick only when verification passes)
- [ ] FR-1 Two accounts signed in side by side (verify: `python3 -m unittest tests.test_accounts tests.test_providers` passes; manual check M1)
- [ ] FR-2 One shared brain, set up safely (verify: `python3 -m unittest tests.test_env tests.test_setup tests.test_ack` passes)
- [ ] FR-3 One-command switch, resume and run (verify: `python3 -m unittest tests.test_switch tests.test_run tests.test_open tests.test_signals tests.test_snapshots` passes; manual check M2 under 30 s)
- [ ] FR-4 Status at a glance (verify: `python3 -m unittest tests.test_status tests.test_menu` passes; manual check M3)
- [ ] FR-5 Built for more AIs, reversible install (verify: `python3 -m unittest tests.test_providers tests.test_uninstall tests.test_dry_run tests.test_flock` passes)
- [ ] NFR-PERF measured on the Mac (verify: manual check M4)

## Log
- 2026-10-16 planning: phases 0 to 6 approved; next Task 1 (walking skeleton); blockers: repo not yet attached, docs staged outside it.
