#!/usr/bin/env python3
"""Generate a minimal SFINCS test model: a plane beach flooded by a rising tide.

Regular grid, ASCII input, water-level boundary on the western edge.
Bed level rises linearly from -5 m (west) to +4.8 m (east); the boundary
water level ramps from 0 to +2 m over 6 hours, so the shoreline should
advance inland to roughly where the bed level equals +2 m.
"""
from pathlib import Path
import numpy as np

here = Path(__file__).resolve().parent

mmax, nmax = 50, 20          # cells in x and y
dx = dy = 100.0              # m
x0 = y0 = 0.0                # origin of the cell edges

# --- bed level (nmax rows, mmax columns; row n=1 first, as the ASCII reader expects)
m = np.arange(mmax)
zb_row = -5.0 + 0.2 * m      # -5.0 ... +4.8
zb = np.tile(zb_row, (nmax, 1))
np.savetxt(here / "sfincs.dep", zb, fmt="%.3f")

# --- mask: 1 = active, 2 = water-level boundary along the western column
msk = np.ones((nmax, mmax), dtype=int)
msk[:, 0] = 2
np.savetxt(here / "sfincs.msk", msk, fmt="%d")

# --- boundary points (cell centres at the SW and NW corners of the western column)
xc = x0 + dx / 2
(here / "sfincs.bnd").write_text(f"{xc:.1f} {y0 + dy/2:.1f}\n{xc:.1f} {y0 + (nmax-0.5)*dy:.1f}\n")

# --- water-level time series: seconds since tref, one column per boundary point
t = np.arange(0, 21600 + 1, 600)
zs = 2.0 * t / 21600.0
np.savetxt(here / "sfincs.bzs", np.column_stack([t, zs, zs]), fmt="%.1f %.4f %.4f")

# --- observation points: offshore (zb=-3), at the initial shoreline (zb=0), inland (zb=+1.4)
obs = [(1050.0, 1050.0, "offshore"), (2550.0, 1050.0, "shoreline"), (3250.0, 1050.0, "inland")]
(here / "sfincs.obs").write_text("".join(f"{x:.1f} {y:.1f} {name}\n" for x, y, name in obs))

# --- main input file
(here / "sfincs.inp").write_text(f"""\
x0              = {x0}
y0              = {y0}
mmax            = {mmax}
nmax            = {nmax}
dx              = {dx}
dy              = {dy}
rotation        = 0

tref            = 20240101 000000
tstart          = 20240101 000000
tstop           = 20240101 060000

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
manning         = 0.04
zsini           = 0.0

dtout           = 1800
dthisout        = 300
dtmaxout        = 21600
""")
print("wrote test model to", here)
