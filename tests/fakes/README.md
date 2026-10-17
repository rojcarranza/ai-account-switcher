# Fakes

Fake `claude`, `security`, `pgrep`, `lsof`, `ps`, `open` and `defaults` scripts for tests live here.
Tests put them first on `PATH` and set `HOME` to a temp dir; they never touch the real HOME, Keychain or ~/.claude.

- `claude_default_sigint`: interactive claude with no signal handling; writes `$$` to `$FAKE_READY`, then dies on SIGINT.
- `claude_trap`: ignores SIGINT and SIGQUIT, exits 143 on SIGTERM, writes `$$` to `$FAKE_READY`, exits `$FAKE_RC` once `$FAKE_STOP` exists.
- `ps`: prints `$FAKE_PS_OUT`, or the file `$FAKE_PS_FILE` when set (e.g. `tests/fixtures/ps_desktop.txt`); `$FAKE_PS_ERR` goes to stderr, exits `$FAKE_PS_RC`.
- `open`: logs its argv to `$FAKE_CALL_LOG`; with `$FAKE_OPEN_FORBID` set it logs `FORBIDDEN` and exits 99; else sleeps `$FAKE_OPEN_SLEEP` seconds when set, prints `$FAKE_OPEN_ERR` to stderr and exits `$FAKE_OPEN_RC`.
- `security`: with `$FAKE_SECURITY_SLEEP` set it leaves a `sleep` child (pid in `$FAKE_SECURITY_CHILD_FILE`) and hangs that many seconds before its normal reply.
- `defaults`: logs its argv to `$FAKE_CALL_LOG`; prints `$FAKE_SWIFTBAR_DIR` when set, else exits 1 with `Domain com.ameba.SwiftBar does not exist`.
