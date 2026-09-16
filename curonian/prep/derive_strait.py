"""Derive the Klaipeda strait centreline from the model's own active-cell mask.

`prep/make_channels.py`'s strait feature is a hand-digitised, three-point fallback
(OSM has no fairway for it), which interpolated a straight line across the Curonian
Spit for a ~4 km stretch: 42 % of its length landed on inactive (dune) cells, so
`setup_subgrid`'s channel burn silently skipped it there and left a gap in the
dredged bed level. See `.superpowers/sdd/2026-09-16-april-2013-nemunas-flood/
fix-strait-centreline-report.md` for the diagnosis.

This module replaces that guess with a centreline routed through the model's own
active cells. It is legitimate ground truth, not circular: the active mask
(msk > 0) is produced by `setup_dep` + `setup_mask_active` + `setup_mask_bounds`,
all of which `build_model.build()` runs *before* `setup_subgrid`'s channel burn, so
the mask carries no information about `channels.geojson` (see that function).

Method: restrict to the corridor between the lagoon and the sea boundary arc, run
`scipy.ndimage.distance_transform_edt` on the active mask to get each cell's
clearance to the nearest inactive cell, build an 8-neighbour graph over active
cells with edge cost `1/(clearance+1)` (so the cheapest path hugs mid-channel
rather than a bank), and run `scipy.sparse.csgraph.dijkstra` from a lagoon-side
seed to the cheapest reachable `msk==2` boundary cell. The resulting staircase of
grid-cell centres is simplified with Shapely to a clean centreline.

Deliberately separate from `prep/make_channels.py`: that module queries the live
OSM Overpass API and must never be run in this environment. This one only reads an
already-built run's mask (default `runs/xaver_2013`, unaffected by any of this) and
is safe to run offline, repeatedly. `update_channels_geojson()` rewrites *only* the
"strait" feature of `inputs/channels.geojson`, leaving the OSM-derived "atmata" and
"skirvyte" features byte-for-byte untouched.
"""
from __future__ import annotations

from pathlib import Path

import geopandas as gpd
import numpy as np
from scipy import ndimage
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import dijkstra
from shapely.geometry import LineString

import common
from prep.make_channels import CHANNELS

# The corridor between the lagoon proper and the sea boundary arc, in the model's
# northing. Restricting the graph to it keeps the search small and stops "cheapest
# path" from wandering into the open lagoon or the Baltic, where it would no longer
# mean "the strait".
CORRIDOR_Y = (6_166_000.0, 6_183_000.0)

# The lagoon-side end of the pre-fix strait line. It already sits on an active cell
# and burns correctly at z_zmin -12.00 m -- the failure diagnosed in
# .superpowers/sdd/2026-09-16-april-2013-nemunas-flood/fix-strait-centreline-report.md
# is entirely the ~4 km stretch north of it -- so it is a validated anchor to search
# from, not a new guess across the Spit.
SEED_XY = (320_503.0, 6_168_707.0)

# A raw grid-cell staircase (100 m steps) is a poor centreline; simplify to
# roughly the cell size.
SIMPLIFY_TOLERANCE_M = common.DX

STRAIT_RIVWTH, STRAIT_RIVBED = CHANNELS["strait"]
SOURCE_TAG = "thalweg"  # derived from the active mask, not hand-digitised or OSM


def _corridor_slice(ys: np.ndarray) -> tuple[int, int]:
    ja, jb = (int(np.argmin(np.abs(ys - y))) for y in CORRIDOR_Y)
    return min(ja, jb), max(ja, jb)


def _clearance_graph(act: np.ndarray):
    """8-neighbour graph over active cells `act`; edge cost favours mid-channel cells.

    Returns (graph, idx, clearance) where idx maps (row, col) -> graph node id
    (-1 where inactive) and clearance is the EDT in grid cells.
    """
    clearance = ndimage.distance_transform_edt(act)
    ny, nx = act.shape
    idx = -np.ones(act.shape, dtype=int)
    idx[act] = np.arange(int(act.sum()))
    cost = 1.0 / (clearance + 1.0)

    rows, cols, vals = [], [], []
    for dj in (-1, 0, 1):
        for di in (-1, 0, 1):
            if dj == 0 and di == 0:
                continue
            ja0, ja1 = max(0, -dj), ny - max(0, dj)
            ia0, ia1 = max(0, -di), nx - max(0, di)
            a = act[ja0:ja1, ia0:ia1]
            b = act[ja0 + dj:ja1 + dj, ia0 + di:ia1 + di]
            both = a & b
            if not both.any():
                continue
            rows.append(idx[ja0:ja1, ia0:ia1][both])
            cols.append(idx[ja0 + dj:ja1 + dj, ia0 + di:ia1 + di][both])
            vals.append(cost[ja0 + dj:ja1 + dj, ia0 + di:ia1 + di][both] * np.hypot(dj, di))

    n = int(act.sum())
    graph = coo_matrix(
        (np.concatenate(vals), (np.concatenate(rows), np.concatenate(cols))), shape=(n, n)
    ).tocsr()
    return graph, idx, clearance


def thalweg(run_dir: Path = common.RUN_XAVER) -> tuple[LineString, dict]:
    """The mid-channel path from `SEED_XY` to the nearest sea boundary cell.

    Returns the simplified centreline and a stats dict (cells, lengths, minimum
    clearance, reachability) for reporting and verification.
    """
    msk, xs, ys = common.read_active_mask(run_dir)
    j0, j1 = _corridor_slice(ys)
    sub = msk[j0:j1 + 1]
    act = sub > 0
    graph, idx, clearance = _clearance_graph(act)

    js = int(np.argmin(np.abs(ys - SEED_XY[1]))) - j0
    is_ = int(np.argmin(np.abs(xs - SEED_XY[0])))
    src = int(idx[js, is_])
    if src < 0:
        raise ValueError(f"seed {SEED_XY} is not on an active cell in {run_dir}")

    targets = idx[sub == 2]
    targets = targets[targets >= 0]
    if len(targets) == 0:
        raise ValueError(f"no msk==2 (waterlevel boundary) cells found in the corridor {CORRIDOR_Y}")

    dist, pred = dijkstra(graph, indices=src, return_predecessors=True)
    best = int(targets[np.argmin(dist[targets])])
    if not np.isfinite(dist[best]):
        raise ValueError("no active-cell path from the lagoon seed to a sea boundary cell")

    path = []
    k = best
    while k != src and k >= 0:
        path.append(k)
        k = int(pred[k])
    path.append(src)
    path.reverse()

    ij = np.argwhere(act)
    coords = [(float(xs[ij[p][1]]), float(ys[j0 + ij[p][0]])) for p in path]
    clearances_m = [float(clearance[ij[p][0], ij[p][1]]) * common.DX for p in path]

    raw = LineString(coords)
    simplified = raw.simplify(SIMPLIFY_TOLERANCE_M, preserve_topology=False)
    stats = {
        "cells": len(coords),
        "raw_length_m": raw.length,
        "simplified_length_m": simplified.length,
        "simplified_vertices": len(simplified.coords),
        "min_clearance_m": min(clearances_m),
        "reachable": True,
    }
    return simplified, stats


def update_channels_geojson(run_dir: Path = common.RUN_XAVER,
                             out: Path = common.INPUTS / "channels.geojson") -> gpd.GeoDataFrame:
    """Rewrite only the "strait" feature of `out`; "atmata" and "skirvyte" are untouched."""
    line, stats = thalweg(run_dir)
    gdf = gpd.read_file(out)
    is_strait = gdf["name"] == "strait"
    if is_strait.sum() != 1:
        raise ValueError(f"expected exactly one 'strait' feature in {out}, found {is_strait.sum()}")

    gdf.loc[is_strait, "geometry"] = [line]
    gdf.loc[is_strait, "rivwth"] = STRAIT_RIVWTH
    gdf.loc[is_strait, "rivbed"] = STRAIT_RIVBED
    gdf.loc[is_strait, "source"] = SOURCE_TAG

    common.write_geojson(gdf, out)
    print(f"wrote {out}: strait centreline {stats['simplified_vertices']} vertices, "
          f"{stats['simplified_length_m']:.0f} m (raw {stats['cells']} cells, "
          f"{stats['raw_length_m']:.0f} m), min clearance {stats['min_clearance_m']:.0f} m, "
          f"from run {run_dir}")
    return gdf


if __name__ == "__main__":
    update_channels_geojson()
