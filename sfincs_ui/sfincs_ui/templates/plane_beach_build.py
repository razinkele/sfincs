#!/usr/bin/env python3
"""Write a plane-beach SFINCS model directory from settings.json.

Standalone on purpose: launched as a subprocess by absolute path, it must
import nothing from the UI package (tests never install it). Mirrors
test_model/make_test_model.py with the cell size, duration and boundary level
taken from the settings. The three solver override keys are always written at
their defaults; the UI rewrites them afterwards and records overrides.diff.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

DOMAIN_X_M, DOMAIN_Y_M = 5000.0, 2000.0
ZB_WEST, ZB_EAST = -5.0, 4.8
RESOLUTIONS = (100, 50, 20, 10, 5)
STATIONS = ((1050.0, 1050.0, "offshore"), (2550.0, 1050.0, "shoreline"), (3250.0, 1050.0, "inland"))


def parse_settings(raw: dict) -> dict:
    try:
        res = int(float(raw.get("resolution_m", 100)))
        hours = int(float(raw.get("duration_hours", 6)))
        level = float(raw.get("boundary_level_m", 2.0))
        manning = float(raw.get("manning", 0.04))
    except (TypeError, ValueError) as exc:
        raise SystemExit(f"settings: {exc}")
    if res not in RESOLUTIONS:
        raise SystemExit(f"resolution_m must be one of {RESOLUTIONS}, got {res}")
    if not 1 <= hours <= 24:
        raise SystemExit(f"duration_hours must be 1..24, got {hours}")
    if not 0.5 <= level <= 4.0:
        raise SystemExit(f"boundary_level_m must be 0.5..4.0, got {level}")
    if not 0.01 <= manning <= 0.10:
        raise SystemExit(f"manning must be 0.01..0.10, got {manning}")
    return {"resolution_m": res, "duration_hours": hours, "boundary_level_m": level, "manning": manning}


def write_model(run_dir: Path, s: dict) -> None:
    dx = dy = float(s["resolution_m"])
    mmax, nmax = int(DOMAIN_X_M / dx), int(DOMAIN_Y_M / dy)
    tstop_s = s["duration_hours"] * 3600
    run_dir.mkdir(parents=True, exist_ok=True)

    x_centres = (np.arange(mmax) + 0.5) * dx
    zb_row = ZB_WEST + (ZB_EAST - ZB_WEST) * (x_centres - dx / 2) / (DOMAIN_X_M - dx)
    np.savetxt(run_dir / "sfincs.dep", np.tile(zb_row, (nmax, 1)), fmt="%.3f")

    msk = np.ones((nmax, mmax), dtype=int)
    msk[:, 0] = 2
    np.savetxt(run_dir / "sfincs.msk", msk, fmt="%d")

    xc = dx / 2
    (run_dir / "sfincs.bnd").write_text(f"{xc:.1f} {dy / 2:.1f}\n{xc:.1f} {(nmax - 0.5) * dy:.1f}\n")

    t = np.arange(0, tstop_s + 1, 600)
    zs = s["boundary_level_m"] * t / tstop_s
    np.savetxt(run_dir / "sfincs.bzs", np.column_stack([t, zs, zs]), fmt="%.1f %.4f %.4f")

    (run_dir / "sfincs.obs").write_text("".join(f"{x:.1f} {y:.1f} {name}\n" for x, y, name in STATIONS))

    (run_dir / "sfincs.inp").write_text(f"""\
x0              = 0.0
y0              = 0.0
mmax            = {mmax}
nmax            = {nmax}
dx              = {dx}
dy              = {dy}
rotation        = 0

tref            = 20240101 000000
tstart          = 20240101 000000
tstop           = 20240101 {s['duration_hours']:02d}0000

inputformat     = asc
outputformat    = net

depfile         = sfincs.dep
mskfile         = sfincs.msk
bndfile         = sfincs.bnd
bzsfile         = sfincs.bzs
obsfile         = sfincs.obs

advection       = 1
alpha           = 0.5
huthresh        = 0.05
manning         = {s['manning']}
zsini           = 0.0

dtout           = 1800
dthisout        = 300
dtmaxout        = {tstop_s}
""")


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="write a plane-beach SFINCS model")
    p.add_argument("--run-dir", required=True, type=Path)
    p.add_argument("--settings", required=True, type=Path)
    args = p.parse_args(argv)
    try:
        raw = json.loads(args.settings.read_text())
    except (OSError, ValueError) as exc:
        print(f"cannot read settings: {exc}", file=sys.stderr)
        return 2
    try:
        s = parse_settings(raw)
    except SystemExit as exc:
        print(str(exc), file=sys.stderr)
        return 2
    write_model(args.run_dir, s)
    print(f"wrote plane beach ({s['resolution_m']} m cells, {s['duration_hours']} h) to {args.run_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
