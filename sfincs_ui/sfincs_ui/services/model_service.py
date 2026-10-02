"""Per-run files the UI owns: settings.json, the sfincs.inp override rewrite and overrides.diff.

Overrides are applied after the builder writes sfincs.inp (spec section 3) so
the step is a pure text transformation. The pristine file is kept as
sfincs.inp.orig so the recorded diff is always original -> final and a
re-application after an interrupted build is idempotent.
"""

from __future__ import annotations

import difflib
import json
import re
from pathlib import Path

SETTINGS_FILE = "settings.json"
OVERRIDES_DIFF = "overrides.diff"
ORIG_INP = "sfincs.inp.orig"
_LINE = re.compile(r"^(\s*)([A-Za-z_][A-Za-z0-9_]*)(\s*=\s*)(.*?)(\s*)$")


def write_settings(run_dir: Path, settings: dict) -> Path:
    run_dir.mkdir(parents=True, exist_ok=True)
    path = run_dir / SETTINGS_FILE
    path.write_text(json.dumps(settings, indent=2, sort_keys=True))
    return path


def read_settings(run_dir: Path) -> dict:
    return json.loads((run_dir / SETTINGS_FILE).read_text())


def _rewrite(text: str, overrides: dict[str, str]) -> str:
    remaining = dict(overrides)
    out = []
    for line in text.splitlines(keepends=True):
        m = _LINE.match(line.rstrip("\n"))
        if m and m.group(2) in remaining:
            value = remaining.pop(m.group(2))
            out.append(f"{m.group(1)}{m.group(2)}{m.group(3)}{value}\n")
        else:
            out.append(line)
    if remaining:
        if out and not out[-1].endswith("\n"):
            out[-1] += "\n"
        for key, value in remaining.items():
            out.append(f"{key:<15} = {value}\n")
    return "".join(out)


def apply_overrides(inp_path: Path, overrides: dict[str, str]) -> str:
    old = inp_path.read_text()
    new = _rewrite(old, overrides)
    if new == old:
        return ""
    inp_path.write_text(new)
    return "".join(difflib.unified_diff(old.splitlines(keepends=True), new.splitlines(keepends=True),
                                        fromfile="sfincs.inp (built)", tofile="sfincs.inp (overrides applied)"))


def write_overrides(run_dir: Path, overrides: dict[str, str]) -> Path:
    """Apply overrides to run_dir/sfincs.inp from its pristine copy and write overrides.diff last."""
    inp, orig = run_dir / "sfincs.inp", run_dir / ORIG_INP
    if not orig.exists():
        orig.write_text(inp.read_text())
    inp.write_text(orig.read_text())
    diff = apply_overrides(inp, overrides)
    path = run_dir / OVERRIDES_DIFF
    path.write_text(diff)
    return path
