"""Process identity and termination through /proc and process groups."""

from __future__ import annotations

import os
import signal
import time


def proc_starttime(pid: int) -> int | None:
    """Field 22 of /proc/<pid>/stat (clock ticks since boot). None when the pid is gone.

    The comm field (2) may contain spaces and parentheses, so split after the
    LAST ')' and count fields from there: field 22 is index 19 of the remainder.
    """
    try:
        stat = open(f"/proc/{pid}/stat").read()
    except (FileNotFoundError, ProcessLookupError, PermissionError):
        return None
    try:
        return int(stat.rsplit(")", 1)[1].split()[19])
    except (IndexError, ValueError):
        return None


def is_alive(pid: int, starttime: int | None) -> bool:
    """Exists, is not a zombie, and (when known) still has the recorded start time.

    A finished child of this process is a zombie until reaped; /proc still
    lists it, so without the state check a monitor would never see it end.
    """
    current = proc_starttime(pid)
    if current is None or _is_zombie(pid):
        return False
    return starttime is None or current == starttime


def killpg_graceful(pid: int, grace_s: float = 30.0, sleep=time.sleep) -> str:
    """SIGTERM the process group, wait up to grace_s, then SIGKILL. Returns what happened."""
    try:
        os.killpg(pid, signal.SIGTERM)
    except ProcessLookupError:
        return "gone"
    deadline = time.monotonic() + grace_s
    while time.monotonic() < deadline:
        if proc_starttime(pid) is None or _is_zombie(pid):
            return "terminated"
        sleep(0.2)
    try:
        os.killpg(pid, signal.SIGKILL)
    except ProcessLookupError:
        return "terminated"
    return "killed"


def _is_zombie(pid: int) -> bool:
    try:
        return open(f"/proc/{pid}/stat").read().rsplit(")", 1)[1].split()[0] == "Z"
    except (OSError, IndexError):
        return True
