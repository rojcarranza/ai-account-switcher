# Fakes

Fake `claude`, `security`, `pgrep` and `lsof` scripts for tests live here.
Tests put them first on `PATH` and set `HOME` to a temp dir; they never touch the real HOME, Keychain or ~/.claude.
