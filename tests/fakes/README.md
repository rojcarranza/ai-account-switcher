# Fakes

Fake `claude`, `security`, `pgrep` and `lsof` scripts for tests live here.
Tests put them first on `PATH` and set `HOME` to a temp dir; they never touch the real HOME, Keychain or ~/.claude.

- `claude_default_sigint`: interactive claude with no signal handling; writes `$$` to `$FAKE_READY`, then dies on SIGINT.
- `claude_trap`: ignores SIGINT and SIGQUIT, exits 143 on SIGTERM, writes `$$` to `$FAKE_READY`, exits `$FAKE_RC` once `$FAKE_STOP` exists.
