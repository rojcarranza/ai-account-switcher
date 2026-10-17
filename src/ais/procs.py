"""Find running processes by name and their working directories (FR-3.11). Provider-agnostic."""
import os
import signal
import subprocess
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple


def _run(cmd: Sequence[str], timeout: float) -> Tuple[Optional[int], str, Optional[str]]:
    """(returncode, stdout, warning). A timeout kills the whole process group, children included."""
    tool = cmd[0]
    try:
        proc = subprocess.Popen(list(cmd), stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                stderr=subprocess.DEVNULL, universal_newlines=True, errors="replace",
                                start_new_session=True)
    except OSError as e:
        return None, "", "cannot run %s: %s" % (tool, e)
    try:
        out, _ = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except OSError:
            pass
        proc.communicate()  # reap
        return None, "", "%s timed out after %gs" % (tool, timeout)
    return proc.returncode, out, None


def process_cwds(name: str, timeout: float) -> Tuple[Dict[int, Tuple[str, Path]], List[str]]:
    """({pid: (args, cwd)}, warnings) for processes whose name is exactly `name`; ({}, [...]) on failure."""
    rc, out, warn = _run(["pgrep", "-x", name], timeout)
    if warn:
        return {}, [warn]
    if rc == 1:  # pgrep: no match
        return {}, []
    pids = [t for t in out.split() if t.isdigit()]
    if rc != 0 or not pids:
        return {}, ["pgrep -x %s failed (exit %s)" % (name, rc)]
    plist = ",".join(pids)
    rc, ps_out, warn = _run(["ps", "-o", "pid=,args=", "-p", plist], timeout)
    if warn or rc != 0:
        return {}, [warn or "ps failed (exit %s)" % rc]
    rc, ls_out, warn = _run(["lsof", "-a", "-d", "cwd", "-p", plist, "-Fn"], timeout)
    if warn or rc not in (0, 1):  # lsof exits 1 when some pid vanished
        return {}, [warn or "lsof failed (exit %s)" % rc]
    args = {}
    for line in ps_out.splitlines():
        pid, _, rest = line.strip().partition(" ")
        if pid.isdigit():
            args[int(pid)] = rest.strip()
    result = {}  # type: Dict[int, Tuple[str, Path]]
    pid = None  # type: Optional[int]
    for line in ls_out.splitlines():
        if line.startswith("p") and line[1:].isdigit():
            pid = int(line[1:])
        elif line.startswith("n") and pid in args:
            result[pid] = (args[pid], Path(line[1:]))
    return result, []
