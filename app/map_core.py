"""Numerics shared by the offline export and the viewer's Map tab.

Imported by curonian/prep/export_map_cache.py (hydromt-sfincs env, via
sys.path) and by app/map_data.py (shiny env), so it depends only on the
standard library, numpy, scipy, pyproj and netCDF4.
Spec: docs/superpowers/specs/2026-09-27-sfincs-map-viewer-design.md
"""
from __future__ import annotations

import json
import os
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import netCDF4 as nc
import numpy as np
from pyproj import Transformer
from scipy import ndimage

MODEL_CRS = 3346
PIXEL_M = 176.0        # web-map pixel in EPSG:3857 metres: ~100 m on the ground at 55.3 N
HIST_LO, HIST_HI, HIST_BIN = -2.0, 10.0, 0.001
MIN_RANGE_M = 0.01
CACHE_FILES = ("zs_series.npy", "map_baseline.npy", "map_warp.npz", "map_meta.json")
# netcdf-c is not thread-safe ("expect segfaults if a netcdf file is opened on
# multiple threads"): the app reads frames on the event loop and clicked cells in
# a worker thread, so every netCDF open/read in the viewer holds this lock.
NC_LOCK = threading.Lock()

_TO_WEB = Transformer.from_crs(MODEL_CRS, 3857, always_xy=True)
_FROM_WEB = Transformer.from_crs(3857, MODEL_CRS, always_xy=True)
_WEB_TO_LONLAT = Transformer.from_crs(3857, 4326, always_xy=True)
_TO_LONLAT = Transformer.from_crs(MODEL_CRS, 4326, always_xy=True)
_FROM_LONLAT = Transformer.from_crs(4326, MODEL_CRS, always_xy=True)


def _nan(data) -> np.ndarray:
    return np.ma.filled(data, np.nan).astype(np.float64)


@dataclass(frozen=True, eq=False)
class Grid:
    x0: float              # centre of cell (row 0, col 0), EPSG:3346
    y0: float
    dx: float
    dy: float
    active: np.ndarray     # bool (n, m): msk > 0
    zb: np.ndarray         # float (n, m): subgrid bed MINIMUM (z_zmin), NaN where none
    times: np.ndarray      # datetime64[s], one per map frame

    @property
    def shape(self) -> tuple[int, int]:
        return self.active.shape


def read_grid(map_nc: Path) -> Grid:
    with NC_LOCK, nc.Dataset(map_nc) as d:
        x, y = _nan(d["x"][:]), _nan(d["y"][:])
        msk = np.ma.filled(d["msk"][:], 0)
        zb = _nan(d["zb"][:])
        tvar = d["time"]
        times = np.array(
            nc.num2date(tvar[:], tvar.units, only_use_cftime_datetimes=False,
                        only_use_python_datetimes=True),
            dtype="datetime64[s]")
    if not (np.allclose(x, x[:1, :]) and np.allclose(y, y[:, :1])):
        raise ValueError(f"{map_nc}: grid is rotated or irregular; the Map tab assumes an unrotated regular grid")
    return Grid(x0=float(x[0, 0]), y0=float(y[0, 0]), dx=float(x[0, 1] - x[0, 0]),
                dy=float(y[1, 0] - y[0, 0]), active=msk > 0, zb=zb, times=times)


def read_frame(map_nc: Path, hour: int) -> np.ndarray:
    with NC_LOCK, nc.Dataset(map_nc) as d:
        return _nan(d["zs"][int(hour)])


def read_zsmax(map_nc: Path) -> np.ndarray:
    with NC_LOCK, nc.Dataset(map_nc) as d:
        z = d["zsmax"][:]
    return _nan(z[0] if z.ndim == 3 else z)


def hour_labels(times: np.ndarray) -> list[str]:
    return [s.replace("T", " ") for s in np.datetime_as_string(times, unit="m")]


def read_points(path: Path) -> list[tuple[float, float, str | None]]:
    """SFINCS point files (sfincs.obs / .bnd / .src): 'x y ["name"]' per line."""
    out = []
    for line in Path(path).read_text(encoding="utf-8", errors="replace").splitlines():
        parts = line.split(maxsplit=2)
        if len(parts) < 2:
            continue
        name = parts[2].strip().strip("\"'") if len(parts) == 3 else None
        out.append((float(parts[0]), float(parts[1]), name))
    return out


def to_lonlat(x, y):
    return _TO_LONLAT.transform(x, y)


def from_lonlat(lon, lat):
    return _FROM_LONLAT.transform(lon, lat)


@dataclass(frozen=True, eq=False)
class Warp:
    index: np.ndarray                              # int32 (H, W): flat model-cell index, -1 = none
    bounds: tuple[float, float, float, float]      # west, south, east, north: lon/lat of outer pixel edges


def compute_warp(grid: Grid, pixel_m: float = PIXEL_M) -> Warp:
    """North-up EPSG:3857 raster covering the grid; each pixel takes the nearest
    active model cell of its centre. deck.gl's BitmapLayer (LNGLAT bounds) reads
    image rows as evenly spaced in Mercator y, which this raster is."""
    n, m = grid.shape
    xs = np.linspace(grid.x0 - grid.dx / 2, grid.x0 + (m - 0.5) * grid.dx, 200)
    ys = np.linspace(grid.y0 - grid.dy / 2, grid.y0 + (n - 0.5) * grid.dy, 200)
    edge_x = np.concatenate([xs, xs, np.full(ys.size, xs[0]), np.full(ys.size, xs[-1])])
    edge_y = np.concatenate([np.full(xs.size, ys[0]), np.full(xs.size, ys[-1]), ys, ys])
    wx, wy = _TO_WEB.transform(edge_x, edge_y)
    west, south = float(wx.min()), float(wy.min())
    width = int(np.ceil((wx.max() - west) / pixel_m))
    height = int(np.ceil((wy.max() - south) / pixel_m))
    east, north = west + width * pixel_m, south + height * pixel_m
    gx, gy = np.meshgrid(west + (np.arange(width) + 0.5) * pixel_m,
                         north - (np.arange(height) + 0.5) * pixel_m)   # row 0 = north
    mx, my = _FROM_WEB.transform(gx, gy)
    col = np.rint((mx - grid.x0) / grid.dx).astype(np.int64)
    row = np.rint((my - grid.y0) / grid.dy).astype(np.int64)
    inside = (col >= 0) & (col < m) & (row >= 0) & (row < n)
    index = np.full(gx.shape, -1, np.int32)
    r, c = row[inside], col[inside]
    index[inside] = np.where(grid.active[r, c], r * m + c, -1)
    lon0, lat0 = _WEB_TO_LONLAT.transform(west, south)
    lon1, lat1 = _WEB_TO_LONLAT.transform(east, north)
    return Warp(index=index, bounds=(float(lon0), float(lat0), float(lon1), float(lat1)))


def compute_baseline(zs0: np.ndarray, active: np.ndarray) -> np.ndarray:
    """Change-from-start baseline, continuous across the starting shoreline:
    zs[0] where wet at the start, else zs[0] of the nearest wet-at-start cell.
    No clip to zb -- every newly wet real cell has its bed minimum above the
    nearby starting level, so a clip would restore the step (spec, measured)."""
    wet0 = active & np.isfinite(zs0)
    if not wet0.any():
        raise ValueError("no wet cell in the first frame: change from start is undefined")
    _, (ii, jj) = ndimage.distance_transform_edt(~wet0, return_indices=True)
    base = zs0[ii, jj].astype(np.float32)
    base[~active] = np.nan
    return base


class RangeHistogram:
    """Streamed percentiles on fixed 1 mm bins over HIST_LO..HIST_HI (clamped),
    so a whole run's ranges never need every value in memory at once."""

    def __init__(self) -> None:
        self.counts = np.zeros(int(round((HIST_HI - HIST_LO) / HIST_BIN)), np.int64)

    def add(self, values) -> None:
        v = np.asarray(values, dtype=np.float64).ravel()
        v = v[np.isfinite(v)]
        if v.size == 0:
            return
        k = np.clip(np.floor((v - HIST_LO) / HIST_BIN).astype(np.int64), 0, self.counts.size - 1)
        self.counts += np.bincount(k, minlength=self.counts.size)

    def percentile(self, q: float) -> float:
        total = int(self.counts.sum())
        if total == 0:
            raise ValueError("no values in the histogram")
        k = int(np.searchsorted(np.cumsum(self.counts), q / 100.0 * total))
        return HIST_LO + (k + 0.5) * HIST_BIN


def colour_ranges(level: RangeHistogram, change: RangeHistogram) -> dict[str, list[float]]:
    lo, hi = level.percentile(2), level.percentile(98)
    if hi - lo < MIN_RANGE_M:
        mid = (lo + hi) / 2
        lo, hi = mid - MIN_RANGE_M / 2, mid + MIN_RANGE_M / 2
    top = max(change.percentile(98), MIN_RANGE_M / 2)
    return {"level": [round(lo, 4), round(hi, 4)], "change": [-round(top, 4), round(top, 4)]}


def source_stamp(map_nc: Path) -> dict:
    st = Path(map_nc).stat()
    return {"size": st.st_size, "mtime_ns": st.st_mtime_ns}


def cache_valid(run_dir: Path) -> bool:
    """A cache is valid only if every file exists and map_meta.json records the
    current sfincs_map.nc size and mtime. Missing or stale meta invalidates all."""
    run_dir = Path(run_dir)
    map_nc = run_dir / "sfincs_map.nc"
    if not map_nc.is_file() or not all((run_dir / f).is_file() for f in CACHE_FILES):
        return False
    try:
        recorded = json.loads((run_dir / "map_meta.json").read_text())["source"]
    except (OSError, ValueError, KeyError):
        return False
    return recorded == source_stamp(map_nc)


def atomic_save(path: Path, writer: Callable[[Path], None]) -> None:
    """writer(tmp) writes a temporary file next to `path`, which then replaces
    `path` in one step, so a live reader (a memmap in the app) never sees a
    truncated file. The temp name keeps the suffix, so np.save/np.savez do not
    append another one."""
    path = Path(path)
    tmp = path.with_name(f".tmp-{os.getpid()}-{path.name}")
    try:
        writer(tmp)
        os.chmod(tmp, 0o644)
        os.replace(tmp, path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


def export_cache(run_dir: Path) -> dict:
    """Write zs_series.npy, map_baseline.npy, map_warp.npz and, last,
    map_meta.json for one run. Returns the meta dict."""
    run_dir = Path(run_dir)
    map_nc = run_dir / "sfincs_map.nc"
    stamp = source_stamp(map_nc)             # taken first: a file changed mid-export stays invalid
    grid = read_grid(map_nc)
    active_flat = np.flatnonzero(grid.active.ravel())
    nt = len(grid.times)
    baseline = compute_baseline(read_frame(map_nc, 0), grid.active)
    by_time = np.empty((nt, active_flat.size), np.float16)
    level_hist, change_hist = RangeHistogram(), RangeHistogram()
    with NC_LOCK, nc.Dataset(map_nc) as d:
        for t in range(nt):
            zs = _nan(d["zs"][t])
            by_time[t] = zs.ravel()[active_flat]
            level_hist.add(zs[grid.active])
            change_hist.add(np.abs(zs - baseline)[grid.active])
    series = np.ascontiguousarray(by_time.T)     # one cell's series = one contiguous row
    del by_time
    warp = compute_warp(grid)
    meta = {
        "run": run_dir.name,
        "source": stamp,
        "shape": list(grid.shape),
        "n_active": int(active_flat.size),
        "hours": hour_labels(grid.times),
        "ranges": colour_ranges(level_hist, change_hist),
    }
    atomic_save(run_dir / "zs_series.npy", lambda p: np.save(p, series))
    atomic_save(run_dir / "map_baseline.npy", lambda p: np.save(p, baseline))
    atomic_save(run_dir / "map_warp.npz",
                lambda p: np.savez(p, index=warp.index, bounds=np.asarray(warp.bounds)))
    atomic_save(run_dir / "map_meta.json", lambda p: p.write_text(json.dumps(meta, indent=1)))
    return meta
