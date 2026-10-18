# AI Account Switcher (ais)
Status: Approved 2026-10-16
Stack: Python 3.9+ standard library only, one zipapp CLI for macOS. See
docs/architecture.md and docs/adr/. Requirements: docs/requirements.md.

## Commands
- Test: `python3 -m unittest discover -s tests -t .`
- Single test: `python3 -m unittest tests.test_switch.SwitchTest.test_resume_other_account`
- Lint (stdlib only): `python3 -m compileall -q src tests`
- Build: `python3 -m zipapp src -m "ais.__main__:run" -p "/usr/bin/env python3" -o dist/ais`
- Run from source: `PYTHONPATH=src python3 -m ais status`
- Install: `make install` (copies dist/ais to ~/.local/bin/ais, keeps ais.prev)

## Rules
- TDD: failing test first. Never edit a test to pass without asking.
- Follow docs/adr/. No new dependency, service or datastore without an ADR.
- Small commits. Work only on the current plan task.
- Build gates G-1 to G-3 in docs/requirements.md come before any FR work.
- Python 3.9 syntax only: no `match`, no runtime `X | Y` unions, no `tomllib`.
- Provider-specific code and constants live only in `src/ais/providers/<name>.py`.
- Exit codes: ais's own are 64 to 78 (see requirements); after `claude`
  runs, pass its exit code through.

## Workflow
- Every piece of work is tracked by a GitHub issue (user story) in
  rojcarranza/ai-account-switcher. Find it, or create it first.
- Every change lands through a pull request that links its issue
  (`Closes #N`, or `Refs #N` when the PR does only part of it). No direct
  pushes to main.
- After opening a PR, run `/code-review` on it, fix every finding, and run
  it again until it is clean before asking to merge. If fixing a finding
  would mean editing a test to make it pass, ask first.

## Gotchas
- Tests never touch the real HOME, Keychain or ~/.claude: set `HOME` to a
  temp dir and put fake `claude`, `security`, `pgrep`, `lsof`, `ps` and
  `open` scripts first on `PATH`; inject app roots, never the host's
  `/Applications`.
- `CLAUDE_SECURESTORAGE_CONFIG_DIR` is omitted entirely for the default
  account, never "". A stored credDir is passed exactly as stored: a
  different spelling is a different Keychain slot.
- Never set `CLAUDE_CONFIG_DIR`; it would split the shared ~/.claude.
- Transcript text (titles, folders) is untrusted: sanitize before the
  SwiftBar menu, never put it in an action.
- macOS ships `/usr/bin/python3` 3.9 with the Command Line Tools; CI also
  runs 3.12.

## graphify
- Before answering a question about the codebase or reading files to find
  something, check `graphify-out/GRAPH_REPORT.md` and use
  `graphify query "<question>"` if `graphify-out/graph.json` exists.
- No graph yet: build it with `/graphify .` first.
- After changing code, run `graphify update .` to refresh the graph (AST only,
  no LLM). After changing docs, run `/graphify . --update`.
- `graphify-out/` is generated output; never commit it.

## When compacting
- Keep: current task, modified files, test commands, open G-1 findings.
