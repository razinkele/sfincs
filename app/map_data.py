"""Data layer of the viewer's Map tab: frames, images, cell series, stations,
overlays. No Shiny imports -- map_ui.py owns the UI.

Frames are read one at a time from sfincs_map.nc; the per-run cache written by
curonian/prep/export_map_cache.py supplies cell time series, the change
baseline, the web-map warp and colour ranges. Without a valid cache the tab
still works: those are computed here (about a second) and a click reads the
map file directly (~4 s).
Spec: docs/superpowers/specs/2026-09-27-sfincs-map-viewer-design.md
"""
from __future__ import annotations

import base64
import io
import json
import time
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import netCDF4 as nc
import numpy as np
import pandas as pd
from matplotlib import colormaps
from PIL import Image

import map_core as mc
import sfincs_data as sd

QUANTITIES = ("level", "change")
# The uncached click read goes through sfincs_map.nc a few frames at a time,
# releasing NC_LOCK between blocks, so a playing session's frame reads wait at
# most one block (~0.1 s) instead of the whole ~4 s column read.
SLOW_BLOCK = 4
CMAPS = {"level": "viridis", "change": "RdBu_r"}
IMAGE_LRU = 512


@dataclass(frozen=True, eq=False)
class RunMaps:
    run: str
    map_nc: Path
    grid: mc.Grid
    warp: mc.Warp
    baseline: np.ndarray
    ranges: dict
    labels: list
    times: pd.DatetimeIndex
    series: np.ndarray | None        # memmap (n_active, n_time) when the cache is valid
    active_flat: np.ndarray
    cached: bool


def map_available(run: str) -> bool:
    return sd.run_path(run, "sfincs_map.nc").is_file()


def _stat_key(path: Path) -> tuple:
    st = path.stat()
    return (str(path), st.st_mtime_ns, st.st_ino, st.st_size)


def load_run(run: str) -> RunMaps:
    """Keyed on the stat of every file involved, so a re-export or re-run is
    picked up, and a replaced file is reopened rather than read through a map
    of the old one (which stays valid for readers still holding it)."""
    run_dir = sd.RUNS_DIR / run
    files = [run_dir / "sfincs_map.nc"] + [run_dir / f for f in mc.CACHE_FILES if (run_dir / f).is_file()]
    return _load_run(run, str(run_dir), tuple(_stat_key(p) for p in files))


@lru_cache(maxsize=8)
def _load_run(run: str, run_dir: str, _key: tuple) -> RunMaps:
    run_dir = Path(run_dir)
    map_nc = run_dir / "sfincs_map.nc"
    grid = mc.read_grid(map_nc)
    active_flat = np.flatnonzero(grid.active.ravel())
    if mc.cache_valid(run_dir):
        meta = json.loads((run_dir / "map_meta.json").read_text())
        series = np.load(run_dir / "zs_series.npy", mmap_mode="r")
        baseline = np.load(run_dir / "map_baseline.npy")
        with np.load(run_dir / "map_warp.npz") as w:
            warp = mc.Warp(index=w["index"], bounds=tuple(float(b) for b in w["bounds"]))
        ranges = {k: tuple(v) for k, v in meta["ranges"].items()}
        labels, cached = list(meta["hours"]), True
    else:
        baseline = mc.compute_baseline(mc.read_frame(map_nc, 0), grid.active)
        warp = mc.compute_warp(grid)
        level_hist, change_hist = mc.RangeHistogram(), mc.RangeHistogram()
        nt = len(grid.times)
        for t in sorted({0, nt // 2, nt - 1}):      # first, middle, last only (spec)
            zs = mc.read_frame(map_nc, t)
            level_hist.add(zs[grid.active])
            change_hist.add(np.abs(zs - baseline)[grid.active])
        ranges = {k: tuple(v) for k, v in mc.colour_ranges(level_hist, change_hist).items()}
        series, labels, cached = None, mc.hour_labels(grid.times), False
    return RunMaps(run=run, map_nc=map_nc, grid=grid, warp=warp, baseline=baseline, ranges=ranges,
                   labels=labels, times=pd.DatetimeIndex(grid.times), series=series,
                   active_flat=active_flat, cached=cached)


@lru_cache(maxsize=8)
def _zsmax(rm: RunMaps) -> np.ndarray:
    return mc.read_zsmax(rm.map_nc)


def frame(rm: RunMaps, when, quantity: str) -> np.ndarray:
    zs = _zsmax(rm) if when == "max" else mc.read_frame(rm.map_nc, int(when))
    return zs if quantity == "level" else zs - rm.baseline


def render_png(values: np.ndarray, warp: mc.Warp, quantity: str, vmin: float, vmax: float) -> str:
    """Warp, colour and PNG-encode one frame; NaN (dry or outside) is transparent."""
    flat = values.ravel()
    idx = warp.index
    img = np.full(idx.shape, np.nan)
    ok = idx >= 0
    img[ok] = flat[idx[ok]]
    norm = np.clip((img - vmin) / (vmax - vmin), 0.0, 1.0)
    rgba = (colormaps[CMAPS[quantity]](norm) * 255).astype(np.uint8)
    rgba[~np.isfinite(img)] = 0
    buf = io.BytesIO()
    Image.fromarray(rgba, "RGBA").save(buf, "PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("ascii")


def frame_image(rm: RunMaps, when, quantity: str) -> str:
    return _frame_image(rm, when, quantity)


@lru_cache(maxsize=IMAGE_LRU)
def _frame_image(rm: RunMaps, when, quantity: str) -> str:
    # Keyed on the RunMaps object itself (identity): a new export or run yields
    # a new object, and with it new ranges and a new map mtime.
    vmin, vmax = rm.ranges[quantity]
    return render_png(frame(rm, when, quantity), rm.warp, quantity, vmin, vmax)


def locate(rm: RunMaps, lon: float, lat: float) -> tuple[int, int] | None:
    x, y = mc.from_lonlat(lon, lat)
    g = rm.grid
    col = int(np.rint((float(x) - g.x0) / g.dx))
    row = int(np.rint((float(y) - g.y0) / g.dy))
    n, m = g.shape
    if not (0 <= row < n and 0 <= col < m) or not g.active[row, col]:
        return None
    return row, col


@dataclass
class CellSeries:
    row: int
    col: int
    x: float
    y: float
    zb: float
    zsmax: float
    series: pd.Series
    slow: bool


def cell_series(rm: RunMaps, lon: float, lat: float) -> CellSeries | None:
    rc = locate(rm, lon, lat)
    if rc is None:
        return None
    row, col = rc
    m = rm.grid.shape[1]
    if rm.series is not None:
        k = int(np.searchsorted(rm.active_flat, row * m + col))
        values, slow = np.asarray(rm.series[k], dtype=np.float64), False
    else:
        nt = len(rm.times)
        values = np.empty(nt, dtype=np.float64)
        for t0 in range(0, nt, SLOW_BLOCK):
            with mc.NC_LOCK, nc.Dataset(rm.map_nc) as d:
                values[t0:t0 + SLOW_BLOCK] = np.ma.filled(d["zs"][t0:t0 + SLOW_BLOCK, row, col], np.nan)
            time.sleep(0.005)          # let a waiting frame read take the lock
        slow = True
    g = rm.grid
    return CellSeries(row=row, col=col, x=g.x0 + col * g.dx, y=g.y0 + row * g.dy,
                      zb=float(g.zb[row, col]), zsmax=float(_zsmax(rm)[row, col]),
                      series=pd.Series(values, index=rm.times, name="zs"), slow=slow)
