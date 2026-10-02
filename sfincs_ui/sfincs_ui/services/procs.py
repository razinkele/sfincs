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
        with open(f"/proc/{pid}/stat") as fh:
            stat = fh.read()
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


def _group_alive(pgid: int) -> bool:
    """True when any non-zombie process in process group pgid still exists (scan of /proc)."""
    for entry in os.listdir("/proc"):
        if not entry.isdigit():
            continue
        try:
            with open(f"/proc/{entry}/stat") as fh:
                rest = fh.read().rsplit(")", 1)[1].split()
        except (OSError, IndexError):
            continue
        # after the comm: field 3 = state (index 0), field 5 = pgrp (index 2)
        if len(rest) > 2 and rest[2] == str(pgid) and rest[0] != "Z":
            return True
    return False


def killpg_graceful(pid: int, grace_s: float = 30.0, sleep=time.sleep) -> str:
    """SIGTERM the whole process group, wait up to grace_s for every member to go, then SIGKILL the group.

    Returns "gone" (nothing to signal), "terminated" (the group emptied within the grace period)
    or "killed" (SIGKILL was needed). Refuses pids that would address our own or every group.
    """
    if pid <= 1:
        raise ValueError(f"refusing to signal process group {pid}")
    try:
        os.killpg(pid, signal.SIGTERM)
    except ProcessLookupError:
        return "gone"
    deadline = time.monotonic() + grace_s
    while time.monotonic() < deadline:
        if not _group_alive(pid):
            return "terminated"
        sleep(0.2)
    try:
        os.killpg(pid, signal.SIGKILL)
    except ProcessLookupError:
        return "terminated"
    return "killed"


def _is_zombie(pid: int) -> bool:
    try:
        with open(f"/proc/{pid}/stat") as fh:
            return fh.read().rsplit(")", 1)[1].split()[0] == "Z"
    except (OSError, IndexError):
        return True
