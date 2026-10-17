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
    label = "".join(c for c in label if c >= " " and c != "\x7f")
    print("ais: %s" % label, file=sys.stderr, flush=True)
    try:
        if sys.stdout.isatty():
            sys.stdout.write("\033]0;claude (%s)\007" % label)
            sys.stdout.flush()
    except (OSError, ValueError):
        pass  # tab title is best effort

    child = None
    pending = []  # SIGHUP/SIGTERM that arrived before the child existed

    def forward(signum, _frame):
        if child is None:
            pending.append(signum)
            return
        try:
            child.send_signal(signum)
        except ProcessLookupError:
            pass

    saved = {}
    try:
        # Caught (not ignored) handlers during the spawn: execve resets them to SIG_DFL in the child,
        # while ais can no longer be killed or interrupted in the window before the wait.
        for sig, handler in ((signal.SIGINT, _noop), (signal.SIGQUIT, _noop),
                             (signal.SIGHUP, forward), (signal.SIGTERM, forward)):
            saved[sig] = signal.signal(sig, handler)
        try:
            # No new session: the child must stay in the foreground group so Ctrl-C reaches it directly.
            child = subprocess.Popen(cmd, env=env, cwd=str(cwd))
        except BaseException as e:
            try:
                on_started()
            finally:  # the spawn error stays primary even if on_started raises
                raise _spawn_error(cmd, cwd, e) if isinstance(e, OSError) else e
        try:
            on_started()
        finally:  # wait even if on_started raised, so the child is never orphaned
            signal.signal(signal.SIGINT, signal.SIG_IGN)
            signal.signal(signal.SIGQUIT, signal.SIG_IGN)
            for sig in pending:
                forward(sig, None)
            rc = child.wait()  # PEP 475: retried after a handler runs
    finally:
        for sig, handler in saved.items():
            signal.signal(sig, handler)
    return rc if rc >= 0 else 128 - rc


def _noop(_signum, _frame):
    pass


def _spawn_error(cmd: List[str], cwd: Path, e: OSError) -> AisError:
    if isinstance(e, FileNotFoundError) and e.filename != str(cwd):
        return AisError(69, "%s is not on PATH" % cmd[0])
    return AisError(69, "cannot start %s: %s" % (cmd[0], e))
