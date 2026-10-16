# ADR-0004: Deploy target: local Mac, single-file zipapp
Status: Accepted
Area: deploy target

## Context
One user, one Mac, $0 (brief constraints). No servers.

## Decision
`python3 -m zipapp` builds one executable file `dist/ais`. `make install`
copies it to `~/.local/bin/ais` and keeps the previous one as
`ais.prev`. CI runs tests on GitHub Actions: Linux on Python 3.9 and 3.12 with fakes,
plus one `macos-latest` job on Python 3.9 for path normalization, process
and `lsof` parsing, and menu rendering. (Free-minute limits for private repos could not be
checked from the planning session; The review noted macOS minutes are billed at a higher rate than
Linux for private repos; verify before enabling the macOS job.
Verify on GitHub's billing page before relying on CI.)

## Alternatives considered
- **`pipx` / `uv tool install`:** clean isolation, but needs one more tool
  installed.
- **Homebrew tap:** easy updates, but overkill for a single user and needs
  a second repo.

## Consequences
- Install and rollback are a file copy.
- No auto-update; the user re-runs `make install` after pulling.
