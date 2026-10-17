"""Start the interactive child, wait for it and pass its exit code through (FR-3.8). Provider-agnostic."""
import signal
import subprocess
import sys
from pathlib import Path
from typing import Callable, Dict, List

from ais.errors import AisError


def run_claude(cmd: List[str], env: Dict[str, str], cwd: Path, label: str, on_started: Callable[[], None]) -> int:
    """Run cmd in the terminal's foreground group; return its exit code, or 128+N if signal N killed it.

    on_started is called exactly once, after the spawn succeeded or failed.
    """
    print("ais: %s" % label, file=sys.stderr, flush=True)
    try:
        if sys.stdout.isatty():
            sys.stdout.write("\033]0;claude (%s)\007" % label)
            sys.stdout.flush()
    except (OSError, ValueError):
        pass  # tab title is best effort
    try:
        # No new session: the child must stay in the foreground group so Ctrl-C reaches it directly.
        # Handlers are still the defaults here, so the child starts with them.
        child = subprocess.Popen(cmd, env=env, cwd=str(cwd))
    except FileNotFoundError as e:
        if e.filename == str(cwd):
            raise AisError(69, "cannot start %s: %s" % (cmd[0], e)) from None
        raise AisError(69, "%s is not on PATH" % cmd[0]) from None
    except OSError as e:
        raise AisError(69, "cannot start %s: %s" % (cmd[0], e)) from None
    finally:
        on_started()

    def forward(signum, _frame):
        try:
            child.send_signal(signum)
        except ProcessLookupError:
            pass

    saved = {}
    try:
        for sig, handler in ((signal.SIGINT, signal.SIG_IGN), (signal.SIGQUIT, signal.SIG_IGN),
                             (signal.SIGHUP, forward), (signal.SIGTERM, forward)):
            saved[sig] = signal.signal(sig, handler)
        rc = child.wait()  # PEP 475: retried after a handler runs
    finally:
        for sig, handler in saved.items():
            signal.signal(sig, handler)
    return rc if rc >= 0 else 128 - rc
