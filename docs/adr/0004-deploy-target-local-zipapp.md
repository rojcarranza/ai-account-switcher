# ADR-0004: Deploy target: local Mac, single-file zipapp
Status: Accepted
Area: deploy target

## Context
One user, one Mac, $0 (brief constraints). No servers.

## Decision
`python3 -m zipapp` builds one executable file `dist/ais`. `make install`
copies it to `~/.local/bin/ais` and keeps the previous one as
`ais.prev`. Checks run locally through the no-mistakes gate
(`.no-mistakes.yaml`): `full-suite` runs `make lint test build`,
`full-suite-py312` runs the same under uv Python 3.12, and `no_ci: true`
is set. GitHub Actions is removed.

Amended 2026-10-22 (#90): GitHub Actions CI replaced by the no-mistakes gate.

## Alternatives considered
- **`pipx` / `uv tool install`:** clean isolation, but needs one more tool
  installed.
- **Homebrew tap:** easy updates, but overkill for a single user and needs
  a second repo.

## Consequences
- Install and rollback are a file copy.
- No auto-update; the user re-runs `make install` after pulling.
