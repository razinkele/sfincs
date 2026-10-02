"""Read SFINCS progress from sfincs.log and tail stage logs."""

from __future__ import annotations

import os
import re
from pathlib import Path

FINISHED_LINE = "---------- Simulation finished -----------"
_PROGRESS = re.compile(r"^\s*(\d+)% complete,\s*(-|[\d.]+) s remaining", re.M)


def parse_progress(text: str) -> dict | None:
    matches = _PROGRESS.findall(text)
    if not matches:
        return None
    percent, remaining = matches[-1]
    return {"percent": int(percent), "remaining_s": None if remaining == "-" else float(remaining)}


def tail_lines(path: Path, n: int, max_bytes: int = 256 * 1024) -> str:
    try:
        size = os.path.getsize(path)
        with open(path, "rb") as fh:
            fh.seek(max(0, size - max_bytes))
            chunk = fh.read().decode("utf-8", errors="replace")
    except OSError:
        return ""
    lines = chunk.splitlines(keepends=True)
    if size > max_bytes and lines:
        lines = lines[1:]  # drop the partial first line
    return "".join(lines[-n:])
