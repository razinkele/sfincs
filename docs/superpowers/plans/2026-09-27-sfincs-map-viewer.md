# SFINCS Viewer Map Tab Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a **Map** tab to the SFINCS results viewer that plays a completed run hour by hour on a WebGL map (water level or change from start, plus a max view), compares stations with gauges in place, draws each run's structural geometry, and plots any clicked cell's time series.

**Architecture:** An offline export (`curonian/prep/export_map_cache.py`, `hydromt-sfincs` env) writes a per-run cache next to each run (`zs_series.npy`, `map_baseline.npy`, `map_warp.npz`, `map_meta.json`) and `results/<run>/gauge_obs.csv`. The numerics are shared by the export and the app through `app/map_core.py`, which depends only on numpy/scipy/pyproj/netCDF4 so it imports in both envs. The app's `app/map_data.py` renders frames on demand (read one frame, warp to a north-up Web-Mercator image, colour, PNG data URI) and `app/map_ui.py` holds the tab, the deck.gl layers and a server-side playback loop gated by a client acknowledgement (`app/www/map_ack.js`).

**Tech Stack:** Python 3.11 (model env) / 3.13 (shiny env), Shiny for Python 1.8, shiny_deckgl 1.9.2 (deck.gl `BitmapLayer`, `ScatterplotLayer`, `GeoJsonLayer`), numpy, scipy 1.17, pyproj 3.7, netCDF4, Pillow 12.2, matplotlib, pandas, pytest, pytest-playwright (Chromium already installed in `~/.cache/ms-playwright`).

**Spec:** `docs/superpowers/specs/2026-09-27-sfincs-map-viewer-design.md` (revision 2 + the baseline correction in commit `53ae5d3`). Read it before starting any task.

## Global Constraints

- Two environments, not interchangeable. App code and app tests: `micromamba run -n shiny python -m pytest app/ -q` from the repo root `/home/razinka/sfincs`. Model code and model tests: `cd curonian && micromamba run -n hydromt-sfincs python -m pytest tests -q`.
- `app/map_core.py` may import only the standard library, numpy, scipy, pyproj and netCDF4 (it is imported from both envs).
- `app/map_data.py` must not import `shiny` or `shiny_deckgl`; `app/map_ui.py` is the only new module that does.
- Web-map image: north-up EPSG:3857, square pixels of **176 m** (`map_core.PIXEL_M`); ≈ 1040 × 1138 px for the real grid.
- Change baseline: `zs[0]` where wet in the first frame, else `zs[0]` of the nearest wet-at-start cell (`scipy.ndimage.distance_transform_edt(~wet0, return_indices=True)`). **No clip to `zb`.**
- Dry cells are exactly the cells SFINCS left without a `zs` value (fill → NaN); never apply a depth threshold.
- Gauge comparison: a scored gauge is coloured only when a reading lies **within 30 min (inclusive)** of the frame time; ties go to the earlier reading; the error is `model at the reading's time − reading`. Error colour: RdBu_r on `model − gauge`, clipped at **±0.20 m**.
- Colour ranges: fixed 1 mm histogram bins over −2…10 m; `level` = 2nd–98th percentile of wet `zs`; `change` = ±(98th percentile of |zs − baseline|); minimum width 0.01 m.
- Every cache file is written to a temporary name in the same directory and `os.replace`d; `map_meta.json` is written last and is what makes a cache valid (its recorded `sfincs_map.nc` size and `mtime_ns` must match the file).
- Playback step 0.25 s; stop at the last frame (no loop); Play at the last frame restarts from hour 0.
- The frame image LRU holds 512 entries.
- Every netCDF open/read in the viewer (`map_core`, `map_data`, `sfincs_data._station_frame`) holds `map_core.NC_LOCK`: netcdf-c is not thread-safe and the click read runs in a worker thread. The uncached click read takes the lock per block of `map_data.SLOW_BLOCK = 4` frames.
- Never run `prep.make_channels` (live Overpass data). Never modify `~/curonian/curonian_db.gpkg`.
- Every commit message ends with these two lines:
  `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`
  `Claude-Session: https://claude.ai/code/session_01KRu4KRMkzuo3KBx1pDy9mh`

**Four deliberate refinements of the spec, applied throughout this plan:**
1. *Frame dropping.* The spec's literal rule ("a tick is skipped while the last sent frame is unacknowledged") would make the shown hour fall behind wall-clock time on a slow link — the lag it exists to prevent. Here the hour **always advances on schedule**, and a frame is **sent** only when the previous one has been acknowledged; the latest hour is sent as soon as the ack arrives. Frames are dropped, time is not.
2. *Acceptance timing.* "Median step ≤ 250 ms" is measured as the interval between consecutive acknowledgements in the browser, which includes the 250 ms timer, so the bound is **median ≤ 300 ms, no interval > 1000 ms** over 100 steps. The station-hover check is covered by unit tests of the tooltip text plus a manual Playwright screenshot, because deck.gl picking is not reachable from a page script.
3. *Slow-link simulation.* Chromium's network throttling does not slow WebSocket messages, and all Shiny traffic is WebSocket, so the acceptance test simulates a slow link by delaying each frame acknowledgement 800 ms through a test hook (`window.__mapAckDelay` in `map_ack.js`) instead of throttling to 1 Mbit/s.
4. *Fallback load inline.* Loading a run without a valid cache (baseline, warp, three-frame ranges) measured 0.5–0.9 s on April and runs inline in a `reactive.calc`; the spec is amended accordingly (commit alongside this plan fix).

## Review Focus

1. **Run switch while a frame is in flight** — an acknowledgement for the old run arriving after the switch must neither stall nor prematurely unlock the new run → Task 6, `test_stale_ack_from_previous_run_is_ignored`.
2. **Re-run without re-export** (cache written for an older `sfincs_map.nc`) — the tab must still play, from `sfincs_map.nc`, and cell clicks must take the slow path, never read the stale series → Task 4, `test_stale_cache_falls_back_to_the_map_file`.
3. **Clicks that are not on an active cell** — just outside the grid edge, or on an inactive cell inside the grid's bounding box → `None`, no exception → Task 4, `test_locate_rejects_outside_and_inactive`.
4. **Gauge readings exactly 30 min away, and two readings equidistant from the frame** — inclusive bound; the earlier reading wins → Task 5, `test_thirty_minute_bound_is_inclusive_and_ties_take_the_earlier_reading`.
5. **Play pressed again after playback stopped at the last frame** — restarts from hour 0 instead of doing nothing → Task 6, `test_play_at_the_end_restarts_from_zero`.

---

## File Structure

| file | status | responsibility |
|---|---|---|
| `app/map_core.py` | create | grid/frame reading, warp, baseline, colour-range histogram, cache validity, atomic writes, the cache export itself (`export_cache`) |
| `app/map_fixture.py` | create | a 20 × 30 synthetic SFINCS run (map, his, obs/bnd/src, inputs, validation.md, gauge csv) for tests in both envs |
| `app/conftest.py` | create | `synthetic` pytest fixture pointing `sfincs_data` at a temp data dir |
| `app/test_map_core.py` | create | tests for `map_core` |
| `curonian/prep/export_map_cache.py` | create | CLI: run name → event, `map_core.export_cache`, `gauge_obs.csv` |
| `curonian/tests/test_export_map_cache.py` | create | event resolution, gauge csv, CLI end to end on the synthetic run |
| `app/map_data.py` | create | `load_run`, frames, PNG rendering + LRU, click → cell series, station records, overlays, legend |
| `app/test_map_data.py` | create | tests for `map_data` (synthetic) + one real-April integration test |
| `app/map_ui.py` | create | Map tab UI, deck.gl layer specs, `Playback` state machine, server function |
| `app/www/map_ack.js` | create | frame acknowledgement handler (+ timing log for the acceptance test) |
| `app/test_map_ui.py` | create | `Playback` tests, layer-spec and UI smoke tests |
| `app/app.py` | modify | `head_includes()`, Map `nav_panel`, `map_server(...)` call, `/www` static route |
| `app/sfincs_data.py` | modify | docstring: the viewer now reads `sfincs_map.nc` (via `map_data`) |
| `app/e2e/test_map_playback.py` | create | Playwright acceptance test (opt-in, `SFINCS_E2E=1`) |
| `curonian/README.md` | modify | export step in the run sequence; Map tab paragraph |
| `curonian/results/<run>/gauge_obs.csv` × 6 | create | committed gauge readings per run |

---

### Task 1: Shared grid, frame and warp numerics (`map_core`, part 1) + synthetic run

**Files:**
- Create: `app/map_core.py`
- Create: `app/map_fixture.py`
- Create: `app/conftest.py`
- Test: `app/test_map_core.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `map_core.PIXEL_M: float = 176.0`, `map_core.CACHE_FILES: tuple[str, ...]`, `map_core.NC_LOCK: threading.Lock` (held by every netCDF read in the viewer)
  - `@dataclass(frozen=True, eq=False) class Grid: x0: float; y0: float; dx: float; dy: float; active: np.ndarray (bool n×m); zb: np.ndarray (float n×m, NaN where none); times: np.ndarray (datetime64[s]); shape -> tuple[int, int]` (property)
  - `read_grid(map_nc: Path) -> Grid`
  - `read_frame(map_nc: Path, hour: int) -> np.ndarray` (float64 n×m, NaN = dry/inactive)
  - `read_zsmax(map_nc: Path) -> np.ndarray` (float64 n×m)
  - `hour_labels(times: np.ndarray) -> list[str]` (`"2013-04-05 00:00"`)
  - `read_points(path: Path) -> list[tuple[float, float, str | None]]`
  - `to_lonlat(x, y) -> tuple[np.ndarray, np.ndarray]`, `from_lonlat(lon, lat) -> tuple[np.ndarray, np.ndarray]`
  - `@dataclass(frozen=True, eq=False) class Warp: index: np.ndarray (int32 H×W, flat model index or −1); bounds: tuple[float, float, float, float]` (west, south, east, north lon/lat)
  - `compute_warp(grid: Grid, pixel_m: float = PIXEL_M) -> Warp`
  - `map_fixture.make_run(run_dir: Path) -> Path`, `map_fixture.write_inputs(inputs_dir: Path)`, `map_fixture.write_validation(results_dir: Path)`, `map_fixture.write_gauge_obs(path: Path, rows: list[tuple[str, str, float]])`, `map_fixture.level(hours) -> float`, constants `N=20, M=30, HOURS=6, X0, Y0, D=100.0, T0, STATIONS`
  - pytest fixture `synthetic` (in `app/conftest.py`) → run name `"synthetic_2013"`, with `sfincs_data.RUNS_DIR`, `RESULTS_DIR`, `DATA_DIR` monkeypatched to a temp dir.

- [ ] **Step 1: Write the synthetic run builder**

Create `app/map_fixture.py`:

```python
"""A tiny synthetic SFINCS run for the Map tab's tests (app/ and curonian/tests/).

20 x 30 cells of 100 m in EPSG:3346 and six hourly map frames:

- columns 0-9: bed -2.0 m (always wet); columns 10-29: bed rises 0.05 m per
  column from -0.25 m, so column 19 sits at +0.20 m;
- rows 0-2 x columns 25-29 are inactive (msk 0); column 0 is the sea boundary
  (msk 2);
- the water level is uniform, level(t) = -0.30 + 0.10 t for hour t = 0..5, and a
  cell is wet where its bed is below that level: the shoreline advances one
  column per hour from column 10, and column 19 never floods;
- zsmax = level(5) + 0.05 = 0.25 wherever the cell was ever wet.

Station output (sfincs_his.nc) every 10 min follows level(t) at every station.
"""
from __future__ import annotations

import json
from pathlib import Path

import netCDF4 as nc
import numpy as np

N, M, HOURS = 20, 30, 6
X0, Y0, D = 330_050.0, 6_120_050.0, 100.0      # centre of cell (row 0, col 0)
T0 = "2013-04-05 00:00:00"
FILL = -99999.0
# (name, row, col). Names match real stations so the Rusne note is exercised.
STATIONS = [("Klaipeda", 10, 5), ("Rusne", 10, 15), ("Silute", 10, 25)]


def level(hours):
    return -0.30 + 0.10 * np.asarray(hours, dtype=float)


def bed() -> np.ndarray:
    zb = np.full((N, M), -2.0)
    zb[:, 10:] = -0.25 + 0.05 * (np.arange(10, M) - 10)
    return zb


def mask() -> np.ndarray:
    msk = np.ones((N, M))
    msk[0:3, 25:30] = 0
    msk[:, 0] = 2
    return msk


def cell_xy(row: int, col: int) -> tuple[float, float]:
    return X0 + D * col, Y0 + D * row


def make_run(run_dir: Path) -> Path:
    run_dir = Path(run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    zb, msk = bed(), mask()
    active = msk > 0
    xx, yy = np.meshgrid(X0 + D * np.arange(M), Y0 + D * np.arange(N))

    with nc.Dataset(run_dir / "sfincs_map.nc", "w") as d:
        d.createDimension("n", N)
        d.createDimension("m", M)
        d.createDimension("time", HOURS)
        d.createDimension("timemax", 1)

        def var(name, dims, data):
            v = d.createVariable(name, "f4", dims, fill_value=FILL)
            v[:] = data
            return v

        var("x", ("n", "m"), xx)
        var("y", ("n", "m"), yy)
        var("msk", ("n", "m"), msk)
        var("zb", ("n", "m"), np.where(active, zb, FILL))
        t = d.createVariable("time", "f4", ("time",))
        t.units = f"seconds since {T0}"
        t[:] = np.arange(HOURS) * 3600.0
        tm = d.createVariable("timemax", "f4", ("timemax",))
        tm.units = t.units
        tm[:] = [(HOURS - 1) * 3600.0]
        zs = np.full((HOURS, N, M), FILL)
        for h in range(HOURS):
            zs[h][active & (zb < level(h))] = level(h)
        var("zs", ("time", "n", "m"), zs)
        ever = active & (zb < level(HOURS - 1))
        var("zsmax", ("timemax", "n", "m"), np.where(ever, level(HOURS - 1) + 0.05, FILL)[None])

    his_t = np.arange(0, (HOURS - 1) * 3600 + 1, 600, dtype=float)
    with nc.Dataset(run_dir / "sfincs_his.nc", "w") as d:
        d.createDimension("time", his_t.size)
        d.createDimension("stations", len(STATIONS))
        t = d.createVariable("time", "f4", ("time",))
        t.units = f"seconds since {T0}"
        t[:] = his_t
        pz = d.createVariable("point_zs", "f4", ("time", "stations"), fill_value=FILL)
        pz[:] = np.stack([level(his_t / 3600.0)] * len(STATIONS), axis=1)

    (run_dir / "sfincs.obs").write_text(
        "".join(f'{cell_xy(r, c)[0]:.1f} {cell_xy(r, c)[1]:.1f} "{name}"\n' for name, r, c in STATIONS))
    (run_dir / "sfincs.bnd").write_text(
        f"{X0:.1f} {Y0 + 5 * D:.1f}\n{X0:.1f} {Y0 + 15 * D:.1f}\n")
    (run_dir / "sfincs.src").write_text(f"{X0 + 12 * D:.1f} {Y0 + 10 * D:.1f}\n")
    return run_dir


def write_inputs(inputs_dir: Path) -> None:
    """active_region.geojson and channels.geojson in EPSG:3346, like curonian/inputs/."""
    inputs_dir = Path(inputs_dir)
    inputs_dir.mkdir(parents=True, exist_ok=True)
    crs = {"type": "name", "properties": {"name": "urn:ogc:def:crs:EPSG::3346"}}
    w, s, e, n = X0 - D / 2, Y0 + 2.5 * D, X0 + (M - 0.5) * D, Y0 + (N - 0.5) * D
    region = {"type": "FeatureCollection", "crs": crs, "features": [{
        "type": "Feature", "properties": {},
        "geometry": {"type": "Polygon", "coordinates": [[[w, s], [e, s], [e, n], [w, n], [w, s]]]}}]}
    channels = {"type": "FeatureCollection", "crs": crs, "features": [{
        "type": "Feature", "properties": {"name": "test_channel"},
        "geometry": {"type": "LineString", "coordinates": [list(cell_xy(10, 12)), list(cell_xy(10, 20))]}}]}
    (inputs_dir / "active_region.geojson").write_text(json.dumps(region))
    (inputs_dir / "channels.geojson").write_text(json.dumps(channels))


def write_validation(results_dir: Path) -> None:
    """Just enough of a validation.md for sfincs_data.periods() / scored_window_name()."""
    results_dir = Path(results_dir)
    results_dir.mkdir(parents=True, exist_ok=True)
    (results_dir / "validation.md").write_text(
        "# Synthetic validation\n\n"
        "Whole period: 2013-04-05 00:00 to 2013-04-05 05:00\n\n"
        "Scoring window: 2013-04-05 00:00 to 2013-04-05 05:00\n")


def write_gauge_obs(path: Path, rows: list[tuple[str, str, float]]) -> None:
    """rows: (site, 'YYYY-mm-dd HH:MM:SS', level_m) -> the export's gauge_obs.csv layout."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("site,time,level_m\n" + "".join(f"{s},{t},{v}\n" for s, t, v in rows))
```

- [ ] **Step 2: Write the shared `synthetic` fixture**

Create `app/conftest.py`:

```python
"""Shared fixtures for the viewer's tests. `synthetic` builds the 20 x 30 run
from map_fixture.py in a temp data dir and points sfincs_data at it."""
import pytest

import map_fixture
import sfincs_data as sd

SYNTHETIC_RUN = "synthetic_2013"


@pytest.fixture
def synthetic(tmp_path, monkeypatch):
    runs, results = tmp_path / "runs", tmp_path / "results"
    map_fixture.make_run(runs / SYNTHETIC_RUN)
    map_fixture.write_validation(results / SYNTHETIC_RUN)
    map_fixture.write_inputs(tmp_path / "inputs")
    monkeypatch.setattr(sd, "DATA_DIR", tmp_path)
    monkeypatch.setattr(sd, "RUNS_DIR", runs)
    monkeypatch.setattr(sd, "RESULTS_DIR", results)
    return SYNTHETIC_RUN
```

- [ ] **Step 3: Write the failing tests**

Create `app/test_map_core.py`:

```python
"""map_core: the numerics shared by the export and the Map tab."""
import numpy as np
import pytest
from pyproj import Transformer

import map_core as mc
import map_fixture as fx
import sfincs_data as sd


def _map_nc(run):
    return sd.RUNS_DIR / run / "sfincs_map.nc"


def test_read_grid_matches_the_fixture(synthetic):
    g = mc.read_grid(_map_nc(synthetic))
    assert g.shape == (fx.N, fx.M)
    assert (g.x0, g.y0, g.dx, g.dy) == (fx.X0, fx.Y0, fx.D, fx.D)
    assert g.active.sum() == fx.N * fx.M - 15
    assert np.isnan(g.zb[1, 27]) and g.zb[4, 12] == pytest.approx(-0.15)
    assert mc.hour_labels(g.times) == [f"2013-04-05 0{h}:00" for h in range(fx.HOURS)]


def test_read_frame_is_nan_where_sfincs_wrote_no_level(synthetic):
    f0 = mc.read_frame(_map_nc(synthetic), 0)
    assert f0[10, 9] == pytest.approx(-0.30)
    assert np.isnan(f0[10, 10])            # bed -0.25 above the starting level
    f5 = mc.read_frame(_map_nc(synthetic), 5)
    assert f5[10, 18] == pytest.approx(0.20) and np.isnan(f5[10, 19])
    zmax = mc.read_zsmax(_map_nc(synthetic))
    assert zmax[10, 18] == pytest.approx(0.25) and np.isnan(zmax[10, 19])


def test_read_points_parses_names_and_bare_points(synthetic):
    obs = mc.read_points(sd.RUNS_DIR / synthetic / "sfincs.obs")
    assert [p[2] for p in obs] == ["Klaipeda", "Rusne", "Silute"]
    bnd = mc.read_points(sd.RUNS_DIR / synthetic / "sfincs.bnd")
    assert len(bnd) == 2 and bnd[0][2] is None


def test_lonlat_round_trip():
    lon, lat = mc.to_lonlat(fx.X0, fx.Y0)
    x, y = mc.from_lonlat(lon, lat)
    assert (float(x), float(y)) == pytest.approx((fx.X0, fx.Y0), abs=1e-3)


def test_warp_maps_each_pixel_to_its_nearest_cell_north_up(synthetic):
    g = mc.read_grid(_map_nc(synthetic))
    w = mc.compute_warp(g)
    to_web = Transformer.from_crs(4326, 3857, always_xy=True)
    west, south = to_web.transform(w.bounds[0], w.bounds[1])
    east, north = to_web.transform(w.bounds[2], w.bounds[3])
    height, width = w.index.shape
    assert width == pytest.approx((east - west) / mc.PIXEL_M, abs=1e-6)
    assert height == pytest.approx((north - south) / mc.PIXEL_M, abs=1e-6)
    from_web = Transformer.from_crs(3857, 3346, always_xy=True)
    checked = 0
    for i in range(height):
        for j in range(width):
            k = int(w.index[i, j])
            if k < 0:
                continue
            row, col = divmod(k, fx.M)
            mx, my = from_web.transform(west + (j + 0.5) * mc.PIXEL_M, north - (i + 0.5) * mc.PIXEL_M)
            assert abs(mx - (fx.X0 + col * fx.D)) <= fx.D / 2 + 1e-6
            assert abs(my - (fx.Y0 + row * fx.D)) <= fx.D / 2 + 1e-6
            checked += 1
    assert checked > 100
    # ceil() pads the raster by up to one pixel at the north and east edges, so
    # compare the first and last image rows that actually hold an active cell.
    covered = [i for i in range(height) if (w.index[i] >= 0).any()]
    rows_top = [int(k) // fx.M for k in w.index[covered[0]] if k >= 0]
    rows_bottom = [int(k) // fx.M for k in w.index[covered[-1]] if k >= 0]
    assert min(rows_top) > max(rows_bottom), "image row 0 must be the northern edge"


def test_warp_marks_inactive_cells_minus_one(synthetic):
    g = mc.read_grid(_map_nc(synthetic))
    w = mc.compute_warp(g)
    flat = set(int(k) for k in w.index.ravel() if k >= 0)
    assert 1 * fx.M + 27 not in flat          # inactive corner cell
    assert 10 * fx.M + 12 in flat


def test_map_reads_wait_for_the_netcdf_lock(synthetic):
    """netcdf-c is not thread-safe: a click reads in a worker thread while the
    event loop reads frames, so every read must hold map_core.NC_LOCK."""
    import threading
    done = threading.Event()
    with mc.NC_LOCK:
        t = threading.Thread(target=lambda: (mc.read_frame(_map_nc(synthetic), 0), done.set()))
        t.start()
        assert not done.wait(0.3), "read_frame ran while another thread held NC_LOCK"
    t.join(5)
    assert done.is_set()
```

- [ ] **Step 4: Run the tests to verify they fail**

Run: `cd /home/razinka/sfincs && micromamba run -n shiny python -m pytest app/test_map_core.py -q`
Expected: FAIL / ERROR with `ModuleNotFoundError: No module named 'map_core'`.

- [ ] **Step 5: Implement `map_core` part 1**

Create `app/map_core.py`:

```python
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
```

(`json`, `os`, `Callable` and `ndimage` are used by Task 2's additions to this file; keep the imports.)

- [ ] **Step 6: Run the tests to verify they pass**

Run: `cd /home/razinka/sfincs && micromamba run -n shiny python -m pytest app/test_map_core.py -q`
Expected: 7 passed. Also run `micromamba run -n shiny python -m pytest app/ -q` — the existing 17 app tests still pass.

- [ ] **Step 7: Commit**

```bash
cd /home/razinka/sfincs
git add app/map_core.py app/map_fixture.py app/conftest.py app/test_map_core.py
git commit -m "Map tab: shared grid, frame and warp numerics with a synthetic run

<trailer lines from Global Constraints>"
```

---

### Task 2: Baseline, colour ranges, cache validity, atomic writes, `export_cache` (`map_core`, part 2)

**Files:**
- Modify: `app/map_core.py` (append)
- Test: `app/test_map_core.py` (append)

**Interfaces:**
- Consumes: Task 1's `Grid`, `read_grid`, `read_frame`, `compute_warp`, `hour_labels`, `Warp`.
- Produces:
  - `compute_baseline(zs0: np.ndarray, active: np.ndarray) -> np.ndarray` (float32 n×m, NaN outside active)
  - `class RangeHistogram: add(values) -> None; percentile(q: float) -> float`
  - `colour_ranges(level: RangeHistogram, change: RangeHistogram) -> dict[str, list[float]]` (`{"level": [lo, hi], "change": [-t, t]}`)
  - `source_stamp(map_nc: Path) -> dict` (`{"size": int, "mtime_ns": int}`)
  - `cache_valid(run_dir: Path) -> bool`
  - `atomic_save(path: Path, writer: Callable[[Path], None]) -> None`
  - `export_cache(run_dir: Path) -> dict` (writes the four `CACHE_FILES`, returns the meta dict: keys `run, source, shape, n_active, hours, ranges`)

- [ ] **Step 1: Write the failing tests**

Append to `app/test_map_core.py`:

```python
import json
import os


def test_baseline_is_continuous_across_the_starting_shoreline(synthetic):
    g = mc.read_grid(_map_nc(synthetic))
    base = mc.compute_baseline(mc.read_frame(_map_nc(synthetic), 0), g.active)
    f5 = mc.read_frame(_map_nc(synthetic), 5)
    change = f5 - base
    # (10, 9) was wet at the start; (10, 10) was dry with its bed ABOVE the
    # starting level. Same water surface at hour 5 -> same change, no step.
    assert change[10, 9] == pytest.approx(0.5)
    assert change[10, 10] == pytest.approx(change[10, 9])
    assert base[10, 10] == pytest.approx(-0.30)       # nearest wet-at-start level, not zb (-0.25)
    assert np.isnan(base[1, 27])                       # inactive


def test_baseline_needs_a_wet_first_frame():
    with pytest.raises(ValueError, match="no wet cell"):
        mc.compute_baseline(np.full((3, 3), np.nan), np.ones((3, 3), bool))


def test_histogram_percentiles_match_numpy_within_one_bin():
    rng = np.random.default_rng(1)
    values = rng.normal(0.4, 0.3, 50_000)
    h = mc.RangeHistogram()
    for chunk in np.array_split(values, 7):
        h.add(np.append(chunk, np.nan))
    for q in (2, 50, 98):
        assert h.percentile(q) == pytest.approx(np.percentile(values, q), abs=2e-3)


def test_colour_ranges_are_centred_and_never_zero_width():
    flat = mc.RangeHistogram()
    flat.add(np.full(100, 0.5))
    r = mc.colour_ranges(flat, flat)
    assert r["level"][1] - r["level"][0] >= mc.MIN_RANGE_M - 1e-9      # ends rounded to 4 dp
    assert r["change"][0] == -r["change"][1] and r["change"][1] >= mc.MIN_RANGE_M / 2 - 1e-9


def test_atomic_save_leaves_nothing_on_failure(tmp_path):
    target = tmp_path / "zs_series.npy"

    def boom(p):
        p.write_bytes(b"partial")
        raise RuntimeError("disk full")

    with pytest.raises(RuntimeError):
        mc.atomic_save(target, boom)
    assert not target.exists()
    assert list(tmp_path.iterdir()) == []


def test_export_cache_writes_a_valid_cache(synthetic):
    run_dir = sd.RUNS_DIR / synthetic
    assert not mc.cache_valid(run_dir)
    meta = mc.export_cache(run_dir)
    assert mc.cache_valid(run_dir)
    assert meta["hours"][0] == "2013-04-05 00:00" and len(meta["hours"]) == fx.HOURS
    assert meta["n_active"] == fx.N * fx.M - 15
    series = np.load(run_dir / "zs_series.npy", mmap_mode="r")
    assert series.dtype == np.float16 and series.shape == (meta["n_active"], fx.HOURS)
    active_flat = np.flatnonzero(mc.read_grid(run_dir / "sfincs_map.nc").active.ravel())
    k = int(np.searchsorted(active_flat, 10 * fx.M + 12))   # bed -0.15: wet from hour 2
    np.testing.assert_allclose(np.asarray(series[k], float),
                               [np.nan, np.nan, -0.1, 0.0, 0.1, 0.2], atol=2e-3)
    assert json.loads((run_dir / "map_meta.json").read_text())["ranges"] == meta["ranges"]


def test_cache_goes_stale_when_the_map_file_changes_or_meta_is_missing(synthetic):
    run_dir = sd.RUNS_DIR / synthetic
    mc.export_cache(run_dir)
    st = (run_dir / "sfincs_map.nc").stat()
    os.utime(run_dir / "sfincs_map.nc", ns=(st.st_atime_ns, st.st_mtime_ns + 1_000_000_000))
    assert not mc.cache_valid(run_dir)
    mc.export_cache(run_dir)
    (run_dir / "map_meta.json").unlink()
    assert not mc.cache_valid(run_dir)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd /home/razinka/sfincs && micromamba run -n shiny python -m pytest app/test_map_core.py -q`
Expected: the 7 new tests FAIL with `AttributeError: module 'map_core' has no attribute ...`; the 7 Task 1 tests pass.

- [ ] **Step 3: Implement**

Append to `app/map_core.py`:

```python
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
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd /home/razinka/sfincs && micromamba run -n shiny python -m pytest app/test_map_core.py -q`
Expected: 14 passed.

- [ ] **Step 5: Commit**

```bash
git add app/map_core.py app/test_map_core.py
git commit -m "Map tab: change baseline, streamed colour ranges and the atomic cache export

<trailer lines from Global Constraints>"
```

---

### Task 3: The export CLI (`curonian/prep/export_map_cache.py`)

**Files:**
- Create: `curonian/prep/export_map_cache.py`
- Test: `curonian/tests/test_export_map_cache.py`

**Interfaces:**
- Consumes: `map_core.export_cache`, `map_core.atomic_save` (Task 2); `common.EVENTS`, `common.event`, `common.RUNS`, `common.ROOT`, `common.REPO`; `validate.GAUGES`; `prep.make_forcing.load_gauge_levels(site, event) -> pd.Series` (index = reading time, values = level in m).
- Produces:
  - `event_for_run(run: str) -> common.Event` (longest event name equal to the run name or followed by `_`; `SystemExit` if none)
  - `gauge_obs(event) -> pd.DataFrame` (columns `site, time, level_m`)
  - `write_gauge_obs(event, results_dir: Path) -> Path`
  - `main(run: str, runs_dir: Path = common.RUNS, results_root: Path = common.ROOT / "results") -> dict`
  - CLI `python -m prep.export_map_cache --run <name>` (from `curonian/`).

- [ ] **Step 1: Write the failing tests**

Create `curonian/tests/test_export_map_cache.py`:

```python
"""The Map tab's offline export: event resolution, gauge readings, end to end."""
import sys

import pandas as pd
import pytest

import common

sys.path.insert(0, str(common.REPO / "app"))
import map_core as mc  # noqa: E402
import map_fixture as fx  # noqa: E402

from prep import export_map_cache as emc  # noqa: E402


@pytest.mark.parametrize("run, event", [
    ("april_2013", "april_2013"),
    ("april_2013_gridwind_pressure", "april_2013"),
    ("xaver_2013_gridwind", "xaver_2013"),
])
def test_event_is_the_longest_matching_prefix(run, event):
    assert emc.event_for_run(run).name == event


@pytest.mark.parametrize("run", ["april", "april_2013x", "baseline"])
def test_unknown_run_names_fail_instead_of_defaulting(run):
    with pytest.raises(SystemExit, match="no event matches"):
        emc.event_for_run(run)


def test_main_writes_the_cache_and_the_gauge_csv(tmp_path, monkeypatch):
    runs, results = tmp_path / "runs", tmp_path / "results"
    fx.make_run(runs / "april_2013_synthetic")
    fake = pd.DataFrame({"site": ["Klaipeda"], "time": [pd.Timestamp("2013-04-05 06:00")], "level_m": [0.12]})
    monkeypatch.setattr(emc, "gauge_obs", lambda event: fake)
    meta = emc.main("april_2013_synthetic", runs_dir=runs, results_root=results)
    assert mc.cache_valid(runs / "april_2013_synthetic")
    assert meta["n_active"] == fx.N * fx.M - 15
    csv = pd.read_csv(results / "april_2013_synthetic" / "gauge_obs.csv", parse_dates=["time"])
    assert csv.to_dict("records") == [{"site": "Klaipeda", "time": pd.Timestamp("2013-04-05 06:00"), "level_m": 0.12}]


@pytest.mark.integration
def test_gauge_obs_equals_what_validate_scores():
    import validate
    from prep.make_forcing import load_gauge_levels
    event = common.event("april_2013")
    frame = emc.gauge_obs(event)
    assert set(frame["site"]) == set(validate.GAUGES)
    for site in validate.GAUGES:
        ours = frame[frame["site"] == site].set_index("time")["level_m"]
        theirs = load_gauge_levels(site, event)
        pd.testing.assert_series_equal(ours, theirs, check_names=False, check_index_type=False)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd /home/razinka/sfincs/curonian && micromamba run -n hydromt-sfincs python -m pytest tests/test_export_map_cache.py -q`
Expected: ERROR `cannot import name 'export_map_cache' from 'prep'`.

- [ ] **Step 3: Implement**

Create `curonian/prep/export_map_cache.py`:

```python
"""Per-run cache for the viewer's Map tab.

    python -m prep.export_map_cache --run april_2013_gridwind

Writes runs/<run>/{zs_series.npy, map_baseline.npy, map_warp.npz,
map_meta.json} (git-ignored; see app/map_core.export_cache) and
results/<run>/gauge_obs.csv (committed), the gauge readings validate.py scores,
so the viewer never reads curonian_db.gpkg. The event is the longest event name
the run name starts with -- validate.py takes --event separately and defaults to
Xaver, which would give an April run Xaver's gauge window.
Spec: docs/superpowers/specs/2026-09-27-sfincs-map-viewer-design.md
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

import common

if str(common.REPO / "app") not in sys.path:
    sys.path.insert(0, str(common.REPO / "app"))
import map_core as mc  # noqa: E402  -- shared with the viewer


def event_for_run(run: str) -> common.Event:
    matches = [name for name in common.EVENTS if run == name or run.startswith(name + "_")]
    if not matches:
        raise SystemExit(f"no event matches run {run!r}; known events: {', '.join(sorted(common.EVENTS))}")
    return common.event(max(matches, key=len))


def gauge_obs(event: common.Event) -> pd.DataFrame:
    import validate
    from prep.make_forcing import load_gauge_levels
    rows = [(site, t, float(v))
            for site in validate.GAUGES
            for t, v in load_gauge_levels(site, event).items()]
    return pd.DataFrame(rows, columns=["site", "time", "level_m"])


def write_gauge_obs(event: common.Event, results_dir: Path) -> Path:
    results_dir.mkdir(parents=True, exist_ok=True)
    out = results_dir / "gauge_obs.csv"
    frame = gauge_obs(event)
    mc.atomic_save(out, lambda p: frame.to_csv(p, index=False, date_format="%Y-%m-%d %H:%M:%S"))
    return out


def main(run: str, runs_dir: Path = common.RUNS, results_root: Path = common.ROOT / "results") -> dict:
    event = event_for_run(run)
    meta = mc.export_cache(runs_dir / run)
    write_gauge_obs(event, results_root / run)
    print(f"{run} ({event.name}): {meta['n_active']} cells x {len(meta['hours'])} hours, "
          f"ranges {meta['ranges']}")
    return meta


def parse_args(argv=None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--run", required=True, help="runs/<name> to export")
    return p.parse_args(argv)


if __name__ == "__main__":
    main(parse_args().run)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd /home/razinka/sfincs/curonian && micromamba run -n hydromt-sfincs python -m pytest tests/test_export_map_cache.py -q`
Expected: 8 passed (the integration test reads the local database read-only). Then the full suite: `micromamba run -n hydromt-sfincs python -m pytest tests -q` → all pass (142 + 8).

- [ ] **Step 5: Commit**

```bash
cd /home/razinka/sfincs
git add curonian/prep/export_map_cache.py curonian/tests/test_export_map_cache.py
git commit -m "Map tab: export CLI with explicit run-to-event resolution and gauge readings

<trailer lines from Global Constraints>"
```

---

### Task 4: Loading a run, rendering frames, click → cell series (`map_data`, part 1)

**Files:**
- Create: `app/map_data.py`
- Modify: `app/sfincs_data.py:1-8` (docstring)
- Test: `app/test_map_data.py`

**Interfaces:**
- Consumes: `map_core` (Tasks 1–2); `sfincs_data.RUNS_DIR`, `run_path`.
- Produces:
  - `QUANTITIES = ("level", "change")`, `SLOW_BLOCK = 4`
  - `@dataclass(frozen=True, eq=False) class RunMaps: run: str; map_nc: Path; grid: mc.Grid; warp: mc.Warp; baseline: np.ndarray; ranges: dict[str, tuple[float, float]]; labels: list[str]; times: pd.DatetimeIndex; series: np.ndarray | None; active_flat: np.ndarray; cached: bool`
  - `map_available(run: str) -> bool`
  - `load_run(run: str) -> RunMaps`
  - `frame(rm: RunMaps, when: int | str, quantity: str) -> np.ndarray` (`when` is an hour index or `"max"`)
  - `render_png(values: np.ndarray, warp: mc.Warp, quantity: str, vmin: float, vmax: float) -> str` (a `data:image/png;base64,` URI)
  - `frame_image(rm: RunMaps, when: int | str, quantity: str) -> str` (LRU of 512)
  - `locate(rm: RunMaps, lon: float, lat: float) -> tuple[int, int] | None`
  - `@dataclass class CellSeries: row: int; col: int; x: float; y: float; zb: float; zsmax: float; series: pd.Series; slow: bool`
  - `cell_series(rm: RunMaps, lon: float, lat: float) -> CellSeries | None`

- [ ] **Step 1: Write the failing tests**

Create `app/test_map_data.py`:

```python
"""map_data: the Map tab's data layer (no Shiny)."""
import base64
import io
import os

import numpy as np
import pytest
from PIL import Image

import map_core as mc
import map_data as md
import map_fixture as fx
import sfincs_data as sd


def _decode(uri: str) -> np.ndarray:
    assert uri.startswith("data:image/png;base64,")
    return np.asarray(Image.open(io.BytesIO(base64.b64decode(uri.split(",", 1)[1]))))


def _lonlat(row, col):
    lon, lat = mc.to_lonlat(*fx.cell_xy(row, col))
    return float(lon), float(lat)


def test_load_run_uses_the_cache_when_valid(synthetic):
    mc.export_cache(sd.RUNS_DIR / synthetic)
    rm = md.load_run(synthetic)
    assert rm.cached and rm.series is not None
    assert rm.labels[0] == "2013-04-05 00:00" and len(rm.times) == fx.HOURS


def test_stale_cache_falls_back_to_the_map_file(synthetic):
    run_dir = sd.RUNS_DIR / synthetic
    mc.export_cache(run_dir)
    st = (run_dir / "sfincs_map.nc").stat()
    os.utime(run_dir / "sfincs_map.nc", ns=(st.st_atime_ns, st.st_mtime_ns + 1_000_000_000))
    rm = md.load_run(synthetic)
    assert not rm.cached and rm.series is None
    assert len(rm.labels) == fx.HOURS                      # still plays
    cs = md.cell_series(rm, *_lonlat(10, 12))
    assert cs.slow                                         # never the stale series


def test_a_re_export_is_picked_up(synthetic):
    run_dir = sd.RUNS_DIR / synthetic
    mc.export_cache(run_dir)
    first = md.load_run(synthetic)
    mc.export_cache(run_dir)
    assert md.load_run(synthetic) is not first


def test_frame_level_and_change(synthetic):
    rm = md.load_run(synthetic)
    assert md.frame(rm, 3, "level")[10, 12] == pytest.approx(0.0)
    assert md.frame(rm, 3, "change")[10, 12] == pytest.approx(0.3)
    assert md.frame(rm, "max", "level")[10, 18] == pytest.approx(0.25)
    assert md.frame(rm, "max", "change")[10, 18] == pytest.approx(0.55)


def test_render_png_shape_and_transparency(synthetic):
    rm = md.load_run(synthetic)
    img = _decode(md.frame_image(rm, 0, "level"))
    assert img.shape == rm.warp.index.shape + (4,)
    values = md.frame(rm, 0, "level").ravel()
    idx = rm.warp.index
    wet = np.zeros(idx.shape, bool)
    wet[idx >= 0] = np.isfinite(values[idx[idx >= 0]])
    assert (img[..., 3][~wet] == 0).all()
    assert (img[..., 3][wet] == 255).all() and wet.any()


def test_frame_images_are_memoised(synthetic):
    rm = md.load_run(synthetic)
    assert md.frame_image(rm, 2, "change") is md.frame_image(rm, 2, "change")


def test_cell_series_cached_and_slow_paths_agree(synthetic):
    rm_slow = md.load_run(synthetic)
    slow = md.cell_series(rm_slow, *_lonlat(10, 12))
    mc.export_cache(sd.RUNS_DIR / synthetic)
    fast = md.cell_series(md.load_run(synthetic), *_lonlat(10, 12))
    assert slow.slow and not fast.slow
    assert (fast.row, fast.col) == (10, 12)
    np.testing.assert_allclose(fast.series.values, slow.series.values, atol=2e-3)
    assert fast.zb == pytest.approx(-0.15) and fast.zsmax == pytest.approx(0.25)


def test_locate_rejects_outside_and_inactive(synthetic):
    rm = md.load_run(synthetic)
    assert md.locate(rm, *_lonlat(1, 27)) is None             # inactive, inside the bbox
    lon, lat = mc.to_lonlat(fx.X0 - 0.6 * fx.D, fx.Y0 + 5 * fx.D)
    assert md.locate(rm, float(lon), float(lat)) is None      # just west of the grid edge
    lon, lat = mc.to_lonlat(fx.X0 - 0.4 * fx.D, fx.Y0 + 5 * fx.D)
    assert md.locate(rm, float(lon), float(lat)) == (5, 0)    # still inside cell (5, 0)
    assert md.cell_series(rm, *_lonlat(1, 27)) is None


def test_slow_read_releases_the_lock_between_blocks(synthetic, monkeypatch):
    import threading

    class Counting:
        def __init__(self):
            self.n, self._lock = 0, threading.Lock()

        def __enter__(self):
            self.n += 1
            self._lock.acquire()

        def __exit__(self, *exc):
            self._lock.release()

    rm = md.load_run(synthetic)                  # no cache: the slow path
    md.frame(rm, "max", "level")                 # warm zsmax so only the column read counts
    counting = Counting()
    monkeypatch.setattr(mc, "NC_LOCK", counting)
    monkeypatch.setattr(md, "SLOW_BLOCK", 2)
    cs = md.cell_series(rm, *_lonlat(10, 12))
    assert cs.slow and counting.n == 3           # 6 frames in blocks of 2
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd /home/razinka/sfincs && micromamba run -n shiny python -m pytest app/test_map_data.py -q`
Expected: ERROR `No module named 'map_data'`.

- [ ] **Step 3: Implement**

Create `app/map_data.py`:

```python
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
```

Edit `app/sfincs_data.py` lines 3–4 of the docstring from:

```
The viewer never writes to the model tree and never opens ``sfincs_map.nc``
(~190 MB per run); station time series come from the small ``sfincs_his.nc``.
```

to:

```
The viewer never writes to the model tree. This module reads only the small
files (reports, ``sfincs_his.nc``); the Map tab reads single frames of
``sfincs_map.nc`` through ``map_data.py``.
```

and in `_station_frame` (same file) take the shared netCDF lock, because the Map tab reads netCDF from a worker thread while this runs on the event loop — change

```python
    with xr.open_dataset(run_path(variant, "sfincs_his.nc")) as ds:
```

to

```python
    from map_core import NC_LOCK     # netcdf-c is not thread-safe; see map_core.NC_LOCK

    with NC_LOCK, xr.open_dataset(run_path(variant, "sfincs_his.nc")) as ds:
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd /home/razinka/sfincs && micromamba run -n shiny python -m pytest app/test_map_data.py -q`
Expected: 9 passed. Then `micromamba run -n shiny python -m pytest app/ -q` → all pass.

- [ ] **Step 5: Measure the fallback load on the real April run**

Run:
```bash
cd /home/razinka/sfincs && SFINCS_DATA_DIR=/home/razinka/sfincs/curonian micromamba run -n shiny python -c "
import time, map_data as md
t=time.time(); rm=md.load_run('april_2013'); print('load', round(time.time()-t,2), 's cached=', rm.cached)
t=time.time(); md.frame_image(rm, 300, 'level'); print('frame', round(time.time()-t,3), 's')"
```
(run with `app/` on the path: prefix `cd app &&` if the import fails.) Expected: `cached=False` (no export yet), load ≲ 2 s, frame ≲ 0.2 s. If load exceeds 2 s, note it in the task report — the spec runs this fallback inline because it measured 0.5–0.9 s; a longer one needs moving into a background task.

- [ ] **Step 6: Commit**

```bash
git add app/map_data.py app/test_map_data.py app/sfincs_data.py
git commit -m "Map tab: load runs, render warped frames, and read clicked cells' series

<trailer lines from Global Constraints>"
```

---

### Task 5: Station records, overlays and legend (`map_data`, part 2)

**Files:**
- Modify: `app/map_data.py` (append)
- Test: `app/test_map_data.py` (append)

**Interfaces:**
- Consumes: Task 4's `RunMaps`, `load_run`; `sfincs_data.station_levels(run) -> pd.DataFrame` (index = time, one column per station name), `sd.periods(run) -> dict[str, str]`, `sd.scored_window_name(run) -> str`, `sd.results_path`, `sd.DATA_DIR`; `map_core.read_points`, `to_lonlat`.
- Produces:
  - `PAIR_TOLERANCE = pd.Timedelta("30min")`, `ERROR_CLIP_M = 0.20`, `RELATIVE_ONLY = {"Rusne": "gauge zero unknown"}`
  - `gauge_obs(run: str) -> pd.DataFrame` (`site, time, level_m`; empty frame when the csv is absent)
  - `stations_at(run: str, when: pd.Timestamp | str) -> list[dict]` — each dict: `name: str, position: [lon, lat], kind: "gauge" | "no_reading" | "modelled", error: float | None, fill: [r, g, b, a], line: [r, g, b, a], text: str`
  - `overlays(run: str) -> dict` — keys `outline` (GeoJSON dict, EPSG:4326), `channels` (GeoJSON dict), `boundary` (list of `{"position": [lon, lat]}`), `inflows` (same), `missing` (list of file names)
  - `legend(rm: RunMaps, quantity: str, is_max: bool) -> dict` — keys `title, vmin, vmax, colors (list of 9 hex strings), notes (list[str])`

- [ ] **Step 1: Write the failing tests**

Append to `app/test_map_data.py`:

```python
import pandas as pd


def _write_obs(run, rows):
    fx.write_gauge_obs(sd.results_path(run, "gauge_obs.csv"), rows)


def _by_name(records):
    return {r["name"]: r for r in records}


def test_gauge_error_only_within_thirty_minutes_of_a_reading(synthetic):
    _write_obs(synthetic, [("Klaipeda", "2013-04-05 01:40:00", -0.16)])
    at2 = _by_name(md.stations_at(synthetic, pd.Timestamp("2013-04-05 02:00")))
    k = at2["Klaipeda"]
    assert k["kind"] == "gauge"
    # model at the READING's time (01:40 -> -0.1333) minus the reading
    assert k["error"] == pytest.approx(fx.level(100 / 60) - (-0.16), abs=1e-3)
    assert "01:40" in k["text"] and "+0.03" in k["text"]
    at4 = _by_name(md.stations_at(synthetic, pd.Timestamp("2013-04-05 04:00")))
    assert at4["Klaipeda"]["kind"] == "no_reading" and at4["Klaipeda"]["error"] is None
    assert "no reading this hour" in at4["Klaipeda"]["text"]


def test_thirty_minute_bound_is_inclusive_and_ties_take_the_earlier_reading(synthetic):
    _write_obs(synthetic, [("Klaipeda", "2013-04-05 01:30:00", -0.20),
                           ("Klaipeda", "2013-04-05 02:30:00", -0.05)])
    k = _by_name(md.stations_at(synthetic, pd.Timestamp("2013-04-05 02:00")))["Klaipeda"]
    assert k["kind"] == "gauge" and "01:30" in k["text"]


def test_modelled_only_stations_are_hollow_and_rusne_is_flagged(synthetic):
    _write_obs(synthetic, [("Klaipeda", "2013-04-05 02:00:00", -0.10)])
    at = _by_name(md.stations_at(synthetic, pd.Timestamp("2013-04-05 02:00")))
    assert at["Rusne"]["kind"] == "modelled" and "gauge zero unknown" in at["Rusne"]["text"]
    assert at["Silute"]["kind"] == "modelled" and at["Silute"]["fill"][3] == 0
    assert at["Klaipeda"]["fill"][3] == 255


def test_error_colour_is_signed_and_clipped(synthetic):
    _write_obs(synthetic, [("Klaipeda", "2013-04-05 02:00:00", -1.0)])   # model 0.9 m too high
    k = _by_name(md.stations_at(synthetic, pd.Timestamp("2013-04-05 02:00")))["Klaipeda"]
    red = k["fill"]
    _write_obs(synthetic, [("Klaipeda", "2013-04-05 02:00:00", 1.0)])    # model far too low
    blue = _by_name(md.stations_at(synthetic, pd.Timestamp("2013-04-05 02:00")))["Klaipeda"]["fill"]
    assert red[0] > red[2] and blue[2] > blue[0]
    _write_obs(synthetic, [("Klaipeda", "2013-04-05 02:00:00", -0.35)])  # +0.25, past the clip
    clipped = _by_name(md.stations_at(synthetic, pd.Timestamp("2013-04-05 02:00")))["Klaipeda"]["fill"]
    assert clipped == red


def test_max_view_compares_maxima_in_the_scoring_window(synthetic):
    _write_obs(synthetic, [("Klaipeda", "2013-04-05 01:40:00", -0.16),
                           ("Klaipeda", "2013-04-05 03:00:00", -0.02)])
    k = _by_name(md.stations_at(synthetic, "max"))["Klaipeda"]
    assert k["kind"] == "gauge"
    assert k["error"] == pytest.approx(fx.level(5) - (-0.02), abs=1e-3)
    assert "05:00" in k["text"] and "03:00" in k["text"]


def test_no_gauge_csv_means_every_station_is_modelled_only(synthetic):
    kinds = {r["kind"] for r in md.stations_at(synthetic, pd.Timestamp("2013-04-05 02:00"))}
    assert kinds == {"modelled"}


def test_overlays_come_from_the_run_and_inputs_in_lonlat(synthetic):
    ov = md.overlays(synthetic)
    assert ov["missing"] == []
    assert len(ov["boundary"]) == 2 and len(ov["inflows"]) == 1
    lon, lat = ov["inflows"][0]["position"]
    assert 20.0 < lon < 23.0 and 54.0 < lat < 57.0
    ring = ov["outline"]["features"][0]["geometry"]["coordinates"][0]
    assert all(20.0 < p[0] < 23.0 and 54.0 < p[1] < 57.0 for p in ring)
    assert "crs" not in ov["outline"]


def test_a_missing_overlay_is_reported_not_fatal(synthetic):
    (sd.DATA_DIR / "inputs" / "channels.geojson").unlink()
    (sd.RUNS_DIR / synthetic / "sfincs.src").unlink()
    ov = md.overlays(synthetic)
    assert set(ov["missing"]) == {"channels.geojson", "sfincs.src"}
    assert ov["channels"]["features"] == [] and ov["inflows"] == []


def test_legend_titles_and_max_note(synthetic):
    rm = md.load_run(synthetic)
    lg = md.legend(rm, "change", is_max=True)
    assert lg["title"].startswith("Change from start")
    assert lg["vmin"] == -lg["vmax"] and len(lg["colors"]) == 9
    assert any("clipped" in n for n in lg["notes"])
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd /home/razinka/sfincs && micromamba run -n shiny python -m pytest app/test_map_data.py -q`
Expected: the 9 new tests FAIL with `AttributeError: module 'map_data' has no attribute 'stations_at'` (etc.).

- [ ] **Step 3: Implement**

Append to `app/map_data.py`:

```python
from matplotlib.colors import to_hex
from pyproj import Transformer

PAIR_TOLERANCE = pd.Timedelta("30min")
ERROR_CLIP_M = 0.20
RELATIVE_ONLY = {"Rusne": "gauge zero unknown"}
GREY = [160, 160, 160, 230]
DARK = [40, 40, 40, 255]
CLEAR = [0, 0, 0, 0]
_GEOJSON_TO_LONLAT = Transformer.from_crs(3346, 4326, always_xy=True)
EMPTY_FC = {"type": "FeatureCollection", "features": []}


def gauge_obs(run: str) -> pd.DataFrame:
    path = sd.results_path(run, "gauge_obs.csv")
    if not path.is_file():
        return pd.DataFrame(columns=["site", "time", "level_m"])
    return _gauge_obs(str(path), path.stat().st_mtime_ns)


@lru_cache(maxsize=16)
def _gauge_obs(path: str, _mtime: int) -> pd.DataFrame:
    return pd.read_csv(path, parse_dates=["time"]).sort_values(["site", "time"], kind="stable")


def _model_at(series: pd.Series, t: pd.Timestamp) -> float:
    s = series.dropna()
    return float(np.interp(pd.Timestamp(t).value, s.index.asi8, s.values)) if len(s) else float("nan")


def error_colour(err: float) -> list[int]:
    x = (np.clip(err, -ERROR_CLIP_M, ERROR_CLIP_M) + ERROR_CLIP_M) / (2 * ERROR_CLIP_M)
    r, g, b, _ = colormaps["RdBu_r"](x)
    return [int(r * 255), int(g * 255), int(b * 255), 255]


def _score_window(run: str) -> tuple[pd.Timestamp, pd.Timestamp] | None:
    span = sd.periods(run).get(sd.scored_window_name(run), "")
    start, _, stop = span.partition(" to ")
    return (pd.Timestamp(start.strip()), pd.Timestamp(stop.strip())) if start and stop else None


def stations_at(run: str, when) -> list[dict]:
    """One record per station in the run's sfincs.obs, for the frame at `when`
    (a Timestamp) or for the max view (`when == "max"`)."""
    points = mc.read_points(sd.run_path(run, "sfincs.obs"))
    his = sd.station_levels(run)
    obs = gauge_obs(run)
    scored = set(obs["site"])
    out = []
    for x, y, name in points:
        lon, lat = mc.to_lonlat(x, y)
        model = his[name] if name in his.columns else pd.Series(dtype=float)
        rec = {"name": name, "position": [float(lon), float(lat)], "kind": "modelled",
               "error": None, "fill": CLEAR, "line": DARK}
        if when == "max":
            level = float(model.max()) if len(model) else float("nan")
            t_model = model.idxmax() if len(model) else None
            text = (f"max model {level:.2f} m at {t_model:%d %b %H:%M}" if t_model is not None
                    else "model: n/a")
        else:
            level = _model_at(model, when)
            text = f"model {level:.2f} m"
        if name in scored:
            readings = obs.loc[obs["site"] == name].set_index("time")["level_m"]
            if when == "max":
                win = _score_window(run)
                inside = readings.loc[win[0]:win[1]] if win else readings.iloc[0:0]
                if len(inside) and np.isfinite(level):
                    g, tg = float(inside.max()), inside.idxmax()
                    err = level - g
                    rec.update(kind="gauge", error=err, fill=error_colour(err))
                    text += f"; max gauge {g:.2f} m at {tg:%d %b %H:%M}; error {err:+.2f} m"
                else:
                    rec.update(kind="no_reading", fill=GREY)
                    text += "; no gauge reading in the scoring window"
            else:
                gaps = np.abs((readings.index - pd.Timestamp(when)).total_seconds())
                i = int(np.argmin(gaps)) if len(gaps) else -1     # argmin: first of equal gaps = earlier
                if i >= 0 and gaps[i] <= PAIR_TOLERANCE.total_seconds():
                    tg, g = readings.index[i], float(readings.iloc[i])
                    m_at = _model_at(model, tg)
                    err = m_at - g
                    rec.update(kind="gauge", error=err, fill=error_colour(err))
                    text = f"model {m_at:.2f} m vs gauge {g:.2f} m at {tg:%H:%M}; error {err:+.2f} m"
                else:
                    rec.update(kind="no_reading", fill=GREY)
                    text += "; gauge: no reading this hour"
        else:
            text += "; modelled only"
            if name in RELATIVE_ONLY:
                text += f" ({RELATIVE_ONLY[name]})"
        rec["text"] = text
        out.append(rec)
    return out


def _reproject(coords):
    if coords and isinstance(coords[0], (int, float)):
        lon, lat = _GEOJSON_TO_LONLAT.transform(coords[0], coords[1])
        return [float(lon), float(lat)]
    return [_reproject(c) for c in coords]


def _geojson_lonlat(path: Path) -> dict:
    data = json.loads(path.read_text())
    data.pop("crs", None)
    for feature in data.get("features", []):
        geom = feature.get("geometry")
        if geom:
            geom["coordinates"] = _reproject(geom["coordinates"])
    return data


def overlays(run: str) -> dict:
    """Stations/boundary/inflows from the run's own files; the active-area
    outline and channel centrelines from the shared inputs/ (labelled
    "current inputs" in the UI, since a run directory has no copy)."""
    out: dict = {"missing": []}
    for key, fname in (("boundary", "sfincs.bnd"), ("inflows", "sfincs.src")):
        path = sd.run_path(run, fname)
        if path.is_file():
            pts = mc.read_points(path)
            lon, lat = mc.to_lonlat([p[0] for p in pts], [p[1] for p in pts])
            out[key] = [{"position": [float(a), float(b)]} for a, b in zip(np.atleast_1d(lon), np.atleast_1d(lat))]
        else:
            out[key] = []
            out["missing"].append(fname)
    inputs = Path(sd.DATA_DIR) / "inputs"
    for key, fname in (("outline", "active_region.geojson"), ("channels", "channels.geojson")):
        path = inputs / fname
        if path.is_file():
            out[key] = _geojson_lonlat(path)
        else:
            out[key] = dict(EMPTY_FC)
            out["missing"].append(fname)
    return out


TITLES = {"level": "Water level (m, model datum)",
          "change": "Change from start (m), relative to the starting water level nearby"}


def legend(rm: RunMaps, quantity: str, is_max: bool) -> dict:
    vmin, vmax = rm.ranges[quantity]
    cmap = colormaps[CMAPS[quantity]]
    notes = ["blank = dry (SFINCS's own wet/dry)"]
    if is_max:
        notes.insert(0, "maximum over the run, clipped to the playback range")
    if not rm.cached:
        notes.append("colour range from three frames: run the export for this run")
    return {"title": TITLES[quantity], "vmin": float(vmin), "vmax": float(vmax),
            "colors": [to_hex(cmap(i / 8)) for i in range(9)], "notes": notes}
```

(Move the two new imports, `from matplotlib.colors import to_hex` and `from pyproj import Transformer`, up into the module's import block.)

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd /home/razinka/sfincs && micromamba run -n shiny python -m pytest app/test_map_data.py -q`
Expected: 18 passed.

- [ ] **Step 5: Commit**

```bash
git add app/map_data.py app/test_map_data.py
git commit -m "Map tab: station records against gauges, run-specific overlays and legend

<trailer lines from Global Constraints>"
```

---

### Task 6: The Map tab — layers, playback with acknowledgement, click plot, app wiring

**Files:**
- Create: `app/map_ui.py`
- Create: `app/www/map_ack.js`
- Modify: `app/app.py` (imports; `app_ui`: `head_includes()`, `map_ui.map_panel()`; `server`: `map_ui.map_server(...)`; `App(..., static_assets=...)`)
- Test: `app/test_map_ui.py`

**Interfaces:**
- Consumes: `map_data` (Tasks 4–5): `map_available`, `load_run`, `frame_image`, `stations_at`, `overlays`, `legend`, `cell_series`, `RunMaps`, `CellSeries`; `shiny_deckgl`: `MapWidget`, `head_includes`, `CARTO_POSITRON`, `bitmap_layer`, `geojson_layer`, `scatterplot_layer`; `MapWidget.update(session, layers)`, `partial_update(session, layers)`, `set_layer_visibility(session, {id: bool})`, `map_click_input_id` (→ `"map_map_click"`, payload `{"longitude": float, "latitude": float, ...}`).
- Produces:
  - `map_ui.MAP: MapWidget` (id `"map"`), `map_ui.OVERLAYS: dict[str, str]`, `map_ui.STEP_S = 0.25`
  - `@dataclass class Playback: run: str = ""; hour: int = 0; playing: bool = False; sent: int = 0; acked: int = 0; pending: bool = False` with `switch(run: str) -> None`, `play(n_frames: int) -> None`, `pause() -> None`, `tick(n_frames: int) -> bool`, `claim_send() -> int | None`, `ack(run: str, seq: int) -> bool`
  - `map_layers(rm: RunMaps, ov: dict, image: str) -> list[dict]` (layer ids: `water, outline, channels, boundary, inflows, stations`)
  - `map_panel() -> NavPanel`, `map_server(input, output, session, variant: Callable[[], str]) -> None`
  - Browser: custom message `map_frame_seq` (`{"run": str, "seq": int}`) → input `map_frame_ack` (same payload); `window.__mapAcks` = list of `{run, seq, t}` (for Task 8).

- [ ] **Step 1: Write the failing tests**

Create `app/test_map_ui.py`:

```python
"""map_ui: the playback state machine, layer specs and the tab's UI."""
import pytest

import map_data as md
import map_ui as mu
import sfincs_data as sd


def test_ticks_advance_on_schedule_and_stop_at_the_end():
    pb = mu.Playback()
    pb.switch("a")
    pb.play(3)
    assert pb.tick(3) and pb.hour == 1
    assert pb.tick(3) and pb.hour == 2
    assert not pb.tick(3) and not pb.playing and pb.hour == 2


def test_play_at_the_end_restarts_from_zero():
    pb = mu.Playback()
    pb.switch("a")
    pb.hour = 2
    pb.play(3)
    assert pb.playing and pb.hour == 0


def test_an_unacknowledged_frame_defers_sending_but_not_time():
    pb = mu.Playback()
    pb.switch("a")
    pb.play(10)
    assert pb.claim_send() == 1
    assert pb.tick(10) and pb.hour == 1            # time moves on regardless
    assert pb.claim_send() is None and pb.pending  # frame 1 not acked yet: hold
    assert pb.tick(10) and pb.hour == 2
    assert pb.ack("a", 1) is True                  # ack arrives: send the latest hour now
    assert pb.claim_send() == 2 and not pb.pending


def test_stale_ack_from_previous_run_is_ignored():
    pb = mu.Playback()
    pb.switch("april")
    assert pb.claim_send() == 1                    # april frame in flight
    pb.switch("xaver")                             # switch resets the gate
    assert pb.claim_send() == 2                    # xaver's first frame goes straight out
    assert pb.claim_send() is None                 # ...and gates the next one
    assert pb.ack("april", 1) is False             # late april ack: must not unlock xaver
    assert pb.claim_send() is None
    assert pb.ack("xaver", 2) is True
    assert pb.claim_send() == 3


def test_switch_stops_and_rewinds():
    pb = mu.Playback()
    pb.switch("a")
    pb.play(5)
    pb.tick(5)
    pb.switch("b")
    assert (pb.run, pb.hour, pb.playing) == ("b", 0, False)


def test_layers_build_for_the_synthetic_run(synthetic):
    rm = md.load_run(synthetic)
    layers = mu.map_layers(rm, md.overlays(synthetic), md.frame_image(rm, 0, "level"))
    assert [l["id"] for l in layers] == ["water", "outline", "channels", "boundary", "inflows", "stations"]
    water = layers[0]
    assert water["bounds"] == list(rm.warp.bounds)
    assert all(l.get("pickable") is False for l in layers if l["id"] != "stations")
    assert layers[-1]["pickable"] is True


def test_panel_builds():
    from shiny import ui
    # a nav_panel only renders inside a navset, and a NavSet has no HTML __str__
    html = str(ui.TagList(ui.navset_tab(mu.map_panel())))
    for element in ("map_play", "map_hour", "map_quantity", "map_cell_plot", "map_cell_caption",
                    "www/map_ack.js"):
        assert element in html


@pytest.mark.parametrize("variant", sd.list_variants())
def test_layers_build_for_every_published_variant(variant):
    if not md.map_available(variant):
        pytest.skip(f"no sfincs_map.nc for {variant}")
    rm = md.load_run(variant)
    layers = mu.map_layers(rm, md.overlays(variant), "data:image/png;base64,")
    assert layers[0]["id"] == "water"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd /home/razinka/sfincs && micromamba run -n shiny python -m pytest app/test_map_ui.py -q`
Expected: ERROR `No module named 'map_ui'`.

- [ ] **Step 3: Write the acknowledgement script**

Create `app/www/map_ack.js`:

```javascript
// Map tab frame acknowledgement (see app/map_ui.py, Playback).
// The server sends "map_frame_seq" right after each frame's layer patch; custom
// messages are handled in order, so answering it means the frame has reached
// this browser. window.__mapAcks keeps arrival times for the acceptance test.
(function () {
  window.__mapAcks = [];
  // Test hook: the acceptance test sets this (ms) to stand in for a slow link,
  // because Chromium's network throttling does not slow WebSocket messages.
  window.__mapAckDelay = 0;
  function register() {
    Shiny.addCustomMessageHandler("map_frame_seq", function (msg) {
      window.__mapAcks.push({ run: msg.run, seq: msg.seq, t: performance.now() });
      if (window.__mapAcks.length > 5000) window.__mapAcks.shift();
      setTimeout(function () {
        Shiny.setInputValue("map_frame_ack", msg, { priority: "event" });
      }, window.__mapAckDelay || 0);
    });
  }
  if (window.Shiny && Shiny.addCustomMessageHandler) register();
  else document.addEventListener("shiny:connected", register, { once: true });
})();
```

- [ ] **Step 4: Implement `map_ui.py`**

Create `app/map_ui.py`:

```python
"""The viewer's Map tab: UI, deck.gl layers and the playback loop.

Playback is the app's own (shiny_deckgl's timeline helpers fix their labels at
build time and cannot follow the run selector). The hour lives on the server and
advances every STEP_S; a frame is sent only once the browser has acknowledged
the previous one (app/www/map_ack.js), and the latest hour is sent as soon as
that acknowledgement arrives -- so a slow link drops frames, not time.
Spec: docs/superpowers/specs/2026-09-27-sfincs-map-viewer-design.md
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass

import matplotlib.pyplot as plt
from shiny import reactive, render, ui
from shiny_deckgl import (CARTO_POSITRON, MapWidget, bitmap_layer, geojson_layer,
                          scatterplot_layer)

import map_data as md

STEP_S = 0.25
MAP = MapWidget(
    "map",
    view_state={"longitude": 21.25, "latitude": 55.40, "zoom": 8.4},
    style=CARTO_POSITRON,
    tooltip={"html": "<b>{name}</b><br/>{text}"},
)
OVERLAYS = {
    "outline": "Active area (current inputs)",
    "channels": "Channels (current inputs)",
    "boundary": "Sea boundary",
    "inflows": "River inflows",
    "stations": "Stations",
}


@dataclass
class Playback:
    run: str = ""
    hour: int = 0
    playing: bool = False
    sent: int = 0
    acked: int = 0
    pending: bool = False

    def switch(self, run: str) -> None:
        self.run, self.hour, self.playing = run, 0, False
        self.acked, self.pending = self.sent, False     # nothing of the old run can gate the new one

    def play(self, n_frames: int) -> None:
        if self.hour >= n_frames - 1:
            self.hour = 0
        self.playing = True

    def pause(self) -> None:
        self.playing = False

    def tick(self, n_frames: int) -> bool:
        if not self.playing:
            return False
        if self.hour + 1 >= n_frames:
            self.playing = False
            return False
        self.hour += 1
        return True

    def claim_send(self) -> int | None:
        if self.sent > self.acked:
            self.pending = True
            return None
        self.sent += 1
        self.pending = False
        return self.sent

    def ack(self, run: str, seq: int) -> bool:
        """Record an acknowledgement; True if a held frame should now be sent."""
        if run != self.run:
            return False
        self.acked = max(self.acked, seq)
        return self.pending and self.acked >= self.sent


def map_layers(rm: md.RunMaps, ov: dict, image: str) -> list[dict]:
    """Bottom to top. Only the stations are pickable: the tooltip is one
    widget-wide template and would pop up blank over any other pickable layer."""
    return [
        bitmap_layer("water", image, list(rm.warp.bounds), opacity=0.85, pickable=False),
        geojson_layer("outline", ov["outline"], stroked=True, filled=False,
                      getLineColor=[60, 60, 60, 200], lineWidthMinPixels=1, pickable=False),
        geojson_layer("channels", ov["channels"], stroked=True, filled=False,
                      getLineColor=[230, 120, 0, 230], lineWidthMinPixels=2, pickable=False),
        scatterplot_layer("boundary", ov["boundary"], getPosition="@@=d.position",
                          getFillColor=[0, 90, 200, 220], radiusMinPixels=4, pickable=False),
        scatterplot_layer("inflows", ov["inflows"], getPosition="@@=d.position",
                          getFillColor=[0, 160, 80, 220], radiusMinPixels=5, pickable=False),
        scatterplot_layer("stations", [], getPosition="@@=d.position", getFillColor="@@=d.fill",
                          getLineColor="@@=d.line", stroked=True, lineWidthMinPixels=2,
                          radiusMinPixels=7, pickable=True),
    ]


def map_panel():
    return ui.nav_panel(
        "Map",
        ui.layout_columns(
            ui.input_radio_buttons("map_quantity", None,
                                   {"level": "Water level", "change": "Change from start"}, inline=True),
            ui.input_switch("map_max", "Maximum over the run", value=False),
            col_widths=(8, 4),
        ),
        ui.input_checkbox_group("map_overlays", None, OVERLAYS, selected=list(OVERLAYS), inline=True),
        ui.layout_columns(
            ui.input_action_button("map_play", "Play", class_="btn-sm"),
            ui.input_slider("map_hour", None, min=0, max=1, value=0, step=1, ticks=False, width="100%"),
            ui.output_text("map_time"),
            col_widths=(1, 8, 3),
        ),
        MAP.ui(height="600px"),
        ui.output_ui("map_legend"),
        ui.output_ui("map_status"),
        ui.output_plot("map_cell_plot", height="300px"),
        ui.output_text("map_cell_caption"),
        ui.tags.script(src="www/map_ack.js"),
    )


def map_server(input, output, session, variant) -> None:
    pb = Playback()
    hour = reactive.value(0)
    playing = reactive.value(False)
    resend = reactive.value(0)

    @reactive.calc
    def run_maps():
        v = variant()
        return md.load_run(v) if md.map_available(v) else None

    def _n_frames() -> int:
        rm = run_maps()
        return len(rm.labels) if rm is not None else 1

    def _set_playing(on: bool) -> None:
        playing.set(on)
        ui.update_action_button("map_play", label="Pause" if on else "Play")

    @reactive.effect(priority=20)
    async def _on_run():
        rm = run_maps()
        pb.switch(variant())
        hour.set(0)
        _set_playing(False)
        ui.update_slider("map_hour", min=0, max=max(_n_frames() - 1, 1), value=0)
        if rm is None:
            return
        with reactive.isolate():
            q = input.map_quantity()
        await MAP.update(session, map_layers(rm, md.overlays(rm.run), md.frame_image(rm, 0, q)))

    @reactive.effect(priority=10)
    async def _visibility():
        run_maps()
        chosen = set(input.map_overlays() or [])
        await MAP.set_layer_visibility(session, {k: k in chosen for k in OVERLAYS})

    @reactive.effect
    @reactive.event(input.map_play)
    def _play():
        if input.map_max():
            return
        if pb.playing:
            pb.pause()
        else:
            pb.play(_n_frames())
            hour.set(pb.hour)
        _set_playing(pb.playing)

    @reactive.effect
    def _tick():
        if not playing():
            return
        reactive.invalidate_later(STEP_S)
        with reactive.isolate():
            if pb.tick(_n_frames()):
                hour.set(pb.hour)
                ui.update_slider("map_hour", value=pb.hour)
            if not pb.playing:
                _set_playing(False)

    @reactive.effect
    @reactive.event(input.map_hour)
    def _scrub():
        if pb.playing:
            return                     # while playing the slider only displays
        pb.hour = min(int(input.map_hour()), _n_frames() - 1)
        hour.set(pb.hour)

    @reactive.effect
    @reactive.event(input.map_max)
    def _max():
        if input.map_max() and pb.playing:
            pb.pause()
            _set_playing(False)

    @reactive.effect
    async def _send_frame():
        rm = run_maps()
        resend()
        if rm is None:
            return
        is_max = input.map_max()
        when = "max" if is_max else min(hour(), len(rm.labels) - 1)
        q = input.map_quantity()
        seq = pb.claim_send()
        if seq is None:
            return                     # previous frame unacknowledged: _ack re-triggers us
        image = md.frame_image(rm, when, q)
        stations = md.stations_at(rm.run, "max" if is_max else rm.times[when])
        await MAP.partial_update(session, [{"id": "water", "image": image},
                                           {"id": "stations", "data": stations}])
        await session.send_custom_message("map_frame_seq", {"run": rm.run, "seq": seq})

    @reactive.effect
    @reactive.event(input.map_frame_ack)
    def _ack():
        msg = input.map_frame_ack()
        if msg and pb.ack(str(msg.get("run")), int(msg.get("seq", 0))):
            with reactive.isolate():
                resend.set(resend() + 1)

    @render.text
    def map_time():
        rm = run_maps()
        if rm is None:
            return ""
        if input.map_max():
            return "maximum over the run"
        h = min(hour(), len(rm.labels) - 1)
        return f"{rm.labels[h]} UTC  ({h + 1}/{len(rm.labels)})"

    @render.ui
    def map_legend():
        rm = run_maps()
        if rm is None:
            return None
        lg = md.legend(rm, input.map_quantity(), input.map_max())
        gradient = ", ".join(lg["colors"])
        return ui.div(
            ui.tags.small(ui.tags.b(lg["title"])),
            ui.div(style=f"height:12px;background:linear-gradient(to right, {gradient});"),
            ui.div(ui.tags.small(f"{lg['vmin']:.2f}"), ui.tags.small(f"{lg['vmax']:.2f}"),
                   style="display:flex;justify-content:space-between;"),
            ui.tags.small(" · ".join(lg["notes"]
                                     + ["stations: blue = model low, red = model high, clipped at "
                                        f"±{md.ERROR_CLIP_M:.2f} m; grey = no gauge reading this hour; "
                                        "hollow = modelled only"]),
                          class_="text-muted"),
            class_="mt-2",
        )

    @render.ui
    def map_status():
        v = variant()
        if not md.map_available(v):
            return ui.markdown("_This run has no `sfincs_map.nc`; the map is unavailable._")
        notes = []
        rm = run_maps()
        if not rm.cached:
            notes.append("No valid map cache for this run: run "
                         f"`python -m prep.export_map_cache --run {v}` — clicks read the map file (~4 s).")
        if md.gauge_obs(v).empty:
            notes.append("No `gauge_obs.csv` for this run: stations show modelled levels only.")
        missing = md.overlays(v)["missing"]
        if missing:
            notes.append("Missing overlay files: " + ", ".join(missing) + ".")
        return ui.tags.small(ui.markdown("  \n".join(notes)), class_="text-warning") if notes else None

    @reactive.extended_task
    async def _series_task(rm, lon, lat):
        return await asyncio.to_thread(md.cell_series, rm, lon, lat)

    @reactive.effect
    @reactive.event(input[MAP.map_click_input_id])
    def _click():
        rm = run_maps()
        c = input[MAP.map_click_input_id]()
        if rm is None or not c:
            return
        _series_task(rm, float(c["longitude"]), float(c["latitude"]))

    @render.text
    def map_cell_caption():
        """Names the plotted cell once a series is drawn; empty for messages
        (lets the acceptance test tell a real plot from the placeholder)."""
        if _series_task.status() != "success":
            return ""
        cs = _series_task.result()
        if cs is None or cs.series.isna().all():
            return ""
        return f"cell row {cs.row}, col {cs.col}"

    @render.plot
    def map_cell_plot():
        fig, ax = plt.subplots(figsize=(10, 3))
        status = _series_task.status()
        rm = run_maps()

        def message(text):
            ax.text(0.5, 0.5, text, ha="center", va="center", transform=ax.transAxes, color="#666")
            ax.set_axis_off()
            return fig

        if status == "initial":
            return message("Click the map to plot a cell's water level through the run.")
        if status == "running":
            return message("Reading from the map file (~4 s)…" if rm is not None and not rm.cached
                           else "Reading…")
        if status == "error":
            return message("Could not read this cell.")
        cs = _series_task.result()
        if cs is None:
            return message("That point is outside the model's active area.")
        if cs.series.isna().all():
            return message(f"Cell {cs.row},{cs.col} is dry for the whole run.")
        ax.plot(cs.series.index, cs.series.values, linewidth=1.2, label="water level")
        ax.axhline(cs.zb, linestyle="--", color="#8a6d3b", linewidth=1, label="bed minimum (subgrid)")
        if input.map_max():
            ax.axhline(cs.zsmax, color="#c0392b", linewidth=1, label="max")
        elif rm is not None:
            ax.axvline(rm.times[min(hour(), len(rm.times) - 1)], color="#c0392b", linewidth=1)
        ax.set_title(f"cell row {cs.row}, col {cs.col}  (x {cs.x:.0f}, y {cs.y:.0f}, EPSG:3346)"
                     + ("  — read from the map file" if cs.slow else ""), fontsize="small")
        ax.set_ylabel("m")
        ax.grid(alpha=0.3)
        ax.legend(loc="upper left", frameon=False, fontsize="small")
        fig.autofmt_xdate()
        fig.tight_layout()
        return fig
```

- [ ] **Step 5: Wire the tab into `app.py`**

In `app/app.py`:

1. After `import sfincs_data as sd` add:
```python
from pathlib import Path

from shiny_deckgl import head_includes

import map_ui
```
2. In `app_ui = ui.page_sidebar(`, add `head_includes(),` as the first argument after the `ui.sidebar(...)` argument (it must be a direct child of the page).
3. In `ui.navset_card_tab(`, add `map_ui.map_panel(),` immediately after the `"Figures"` `nav_panel`.
4. At the start of `def server(input, output, session):`'s body, after the `variant` calc is defined, add:
```python
    map_ui.map_server(input, output, session, variant)
```
5. Replace the last line with:
```python
app = App(app_ui, server, static_assets={
    "/figures": sd.RESULTS_DIR,
    "/www": Path(__file__).parent / "www",
})
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `cd /home/razinka/sfincs && micromamba run -n shiny python -m pytest app/ -q`
Expected: all pass (17 existing + 14 map_core + 18 map_data + 13 map_ui = 62; the per-variant layer test runs for the six real runs, which have `sfincs_map.nc`).

- [ ] **Step 7: Run the app and look at it**

Run: `cd /home/razinka/sfincs/app && SFINCS_DATA_DIR=/home/razinka/sfincs/curonian micromamba run -n shiny python -m shiny run --port 8765 app.py` (background), open `http://127.0.0.1:8765/` with the Playwright MCP browser, select *April 2013 — Nemunas freshet*, open the Map tab: the water image sits on the lagoon (not shifted or flipped — compare the outline overlay against the image edge), Play advances the time label, Change from start shows no colour step along the starting shoreline, clicking the lagoon draws a series (after ~4 s — no cache yet), hovering Klaipėda shows its tooltip. Take a screenshot. Stop the server.

- [ ] **Step 8: Commit**

```bash
git add app/map_ui.py app/www/map_ack.js app/test_map_ui.py app/app.py
git commit -m "Map tab: deck.gl layers, acknowledged playback, click-a-cell plot

<trailer lines from Global Constraints>"
```

---

### Task 7: Export the six runs, commit gauge readings, real-data check, README

**Files:**
- Create: `curonian/results/{april_2013,april_2013_gridwind,april_2013_gridwind_pressure,xaver_2013,xaver_2013_gridwind,xaver_2013_gridwind_pressure}/gauge_obs.csv` (generated)
- Modify: `curonian/README.md` (run sequence; viewer notes)
- Test: `app/test_map_data.py` (append one integration test)

**Interfaces:**
- Consumes: the CLI from Task 3; `map_data.load_run`, `frame_image`, `cell_series` (Task 4).
- Produces: valid caches for all six runs; six committed `gauge_obs.csv`.

- [ ] **Step 1: Write the failing integration test**

Append to `app/test_map_data.py`:

```python
import netCDF4 as nc
from pathlib import Path

REAL = Path("/home/razinka/sfincs/curonian/runs/april_2013")


@pytest.mark.skipif(not mc.cache_valid(REAL), reason="april_2013 map cache not exported on this machine")
def test_real_april_frame_and_cached_series(monkeypatch):
    monkeypatch.setattr(sd, "RUNS_DIR", REAL.parent)
    rm = md.load_run("april_2013")
    img = _decode(md.frame_image(rm, 300, "level"))
    assert img.shape[:2] == rm.warp.index.shape
    assert 1000 <= img.shape[1] <= 1080 and 1100 <= img.shape[0] <= 1180    # ~1040 x 1138 at 176 m
    assert (img[..., 3] == 0).any() and (img[..., 3] == 255).any()
    row, col = 550, 500
    lon, lat = mc.to_lonlat(rm.grid.x0 + col * rm.grid.dx, rm.grid.y0 + row * rm.grid.dy)
    cs = md.cell_series(rm, float(lon), float(lat))
    with nc.Dataset(REAL / "sfincs_map.nc") as d:
        direct = np.ma.filled(d["zs"][:, row, col], np.nan).astype(float)
    np.testing.assert_allclose(cs.series.values, direct, atol=2e-3)
    assert not cs.slow
```

- [ ] **Step 2: Run it to verify it is skipped (cache not yet exported)**

Run: `cd /home/razinka/sfincs && micromamba run -n shiny python -m pytest app/test_map_data.py -q -k real_april`
Expected: 1 skipped.

- [ ] **Step 3: Export all six runs**

Check machine load first (`uptime`); then, from `curonian/`:

```bash
cd /home/razinka/sfincs/curonian
for r in april_2013 april_2013_gridwind april_2013_gridwind_pressure xaver_2013 xaver_2013_gridwind xaver_2013_gridwind_pressure; do
  micromamba run -n hydromt-sfincs python -m prep.export_map_cache --run $r || break
done
du -sh runs/*/zs_series.npy
ls -l runs/april_2013/map_* runs/april_2013/zs_series.npy
```
Expected: six summary lines (`april_2013 (april_2013): 331933 cells x 649 hours, ranges {...}`, Xaver runs 313 hours); `zs_series.npy` ≈ 431 MB (April) / 208 MB (Xaver); files mode `-rw-r--r--`.

- [ ] **Step 4: Run the integration test**

Run: `cd /home/razinka/sfincs && micromamba run -n shiny python -m pytest app/test_map_data.py -q -k real_april`
Expected: 1 passed.

- [ ] **Step 5: Update the README**

In `curonian/README.md`, in the run-sequence block, add after each `validate.py` line (both events):
```
    micromamba run -n hydromt-sfincs python -m prep.export_map_cache --run xaver_2013
```
(and `--run april_2013` after the April `validate.py` line). Then add, after the paragraph that introduces the viewer / `deploy/deploy.sh` (search for `laguna.ku.lt/sfincs`), a paragraph:

```markdown
**Map tab.** The viewer's Map tab plays a run hour by hour on a WebGL map —
water level or change from start (relative to the starting water level nearby,
so the starting shoreline shows no false step), plus the run's maximum —
with the stations coloured by model − gauge wherever a gauge reading lies within
30 min of the frame, the sea boundary, river inflows, active area and channel
centrelines drawn on top, and a click on any cell plotting its series. It needs
`prep.export_map_cache --run <name>` after each run: that writes the cell-series
cache (~430 MB per April run, ~210 MB per Xaver run, git-ignored under `runs/`)
and `results/<name>/gauge_obs.csv` (committed). Without it the tab still plays,
but a click reads `sfincs_map.nc` directly (~4 s).
```

- [ ] **Step 6: Run both suites**

Run: `cd /home/razinka/sfincs/curonian && micromamba run -n hydromt-sfincs python -m pytest tests -q` → all pass. `cd .. && micromamba run -n shiny python -m pytest app/ -q` → all pass.

- [ ] **Step 7: Commit**

```bash
cd /home/razinka/sfincs
git add curonian/results/*/gauge_obs.csv curonian/README.md app/test_map_data.py
git commit -m "Map tab: export the six runs' caches, commit their gauge readings, document

<trailer lines from Global Constraints>"
```

---

### Task 8: Playwright acceptance test and final check

**Files:**
- Create: `app/e2e/test_map_playback.py`
- Create: `app/e2e/conftest.py`

**Interfaces:**
- Consumes: the running app (Task 6) with the exported caches (Task 7); `window.__mapAcks` from `map_ack.js`; element ids `map_play`, `map_hour`, `map_time`, `variant`, `map_cell_plot`, the deck.gl canvas inside `#map`.
- Produces: an opt-in acceptance test (`SFINCS_E2E=1`).

- [ ] **Step 1: Write the server fixture**

Create `app/e2e/conftest.py`:

```python
"""Opt-in browser tests: SFINCS_E2E=1 micromamba run -n shiny python -m pytest app/e2e -q"""
import os
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import pytest

APP_DIR = Path(__file__).resolve().parents[1]

if os.environ.get("SFINCS_E2E") != "1":
    collect_ignore_glob = ["test_*.py"]


@pytest.fixture(scope="session")
def app_url():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    env = {**os.environ, "SFINCS_DATA_DIR": "/home/razinka/sfincs/curonian"}
    proc = subprocess.Popen([sys.executable, "-m", "shiny", "run", "--port", str(port), "app.py"],
                            cwd=APP_DIR, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    url = f"http://127.0.0.1:{port}/"
    for _ in range(60):
        try:
            urllib.request.urlopen(url, timeout=1)
            break
        except OSError:
            time.sleep(0.5)
    else:
        proc.kill()
        raise RuntimeError("app did not start")
    yield url
    proc.terminate()
    proc.wait(timeout=10)
```

- [ ] **Step 2: Write the acceptance tests**

Create `app/e2e/test_map_playback.py`:

```python
"""Acceptance tests for the Map tab (spec: Testing -> Playback)."""
import statistics

from playwright.sync_api import Page, expect


def _open_map(page: Page, url: str, variant: str) -> None:
    page.goto(url)
    page.select_option("#variant", variant)
    page.get_by_role("tab", name="Map").click()
    expect(page.locator("#map_time")).to_contain_text("UTC", timeout=30_000)
    page.wait_for_function("window.__mapAcks && window.__mapAcks.length > 0", timeout=30_000)


def _acks(page: Page) -> list[dict]:
    return page.evaluate("window.__mapAcks.slice()")


def test_playback_pace_on_april(page: Page, app_url: str):
    _open_map(page, app_url, "april_2013")
    start = len(_acks(page))
    page.click("#map_play")
    page.wait_for_function(f"window.__mapAcks.length >= {start + 101}", timeout=120_000)
    page.click("#map_play")
    times = [a["t"] for a in _acks(page)[start:start + 101]]
    gaps = [b - a for a, b in zip(times, times[1:])]
    assert statistics.median(gaps) <= 300, f"median {statistics.median(gaps):.0f} ms"
    assert max(gaps) <= 1000, f"max {max(gaps):.0f} ms"


def test_slow_link_drops_frames_not_time(page: Page, app_url: str):
    _open_map(page, app_url, "april_2013")
    # Chromium's Network.emulateNetworkConditions does not throttle WebSocket
    # throughput, so a slow link is simulated by delaying each acknowledgement.
    page.evaluate("window.__mapAckDelay = 800")
    start_acks = len(_acks(page))
    page.click("#map_play")
    page.wait_for_timeout(10_000)
    page.click("#map_play")
    page.wait_for_timeout(2_000)      # let the last delayed acks and slider update land
    shown = int(page.locator("#map_hour").input_value())
    sent = len(_acks(page)) - start_acks
    assert shown >= 32, f"hour {shown} after 10 s: time fell behind"        # 0.8 x 40 ticks
    assert sent < shown, "every frame was delivered: no dropping happened with 800 ms acks"


def test_switching_run_mid_playback_resets_cleanly(page: Page, app_url: str):
    _open_map(page, app_url, "april_2013")
    page.click("#map_play")
    page.wait_for_timeout(2_000)
    page.select_option("#variant", "xaver_2013")
    expect(page.locator("#map_time")).to_contain_text("(1/313)", timeout=30_000)
    switch_at = page.evaluate("performance.now()")
    page.wait_for_timeout(1_500)
    late = [a for a in _acks(page) if a["t"] > switch_at + 500 and a["run"] != "xaver_2013"]
    assert late == []
    assert page.locator("#map_play").inner_text() == "Play"


def test_click_on_water_draws_a_series(page: Page, app_url: str):
    _open_map(page, app_url, "april_2013")
    expect(page.locator("#map_cell_caption")).to_have_text("")        # placeholder plot, no series
    box = page.locator("#map canvas").first.bounding_box()
    page.mouse.click(box["x"] + box["width"] * 0.45, box["y"] + box["height"] * 0.55)
    expect(page.locator("#map_cell_caption")).to_contain_text("cell row", timeout=15_000)
```

- [ ] **Step 3: Run the acceptance tests**

Run: `cd /home/razinka/sfincs && SFINCS_E2E=1 micromamba run -n shiny python -m pytest app/e2e -q`
Expected: 4 passed. If `test_click_on_water_draws_a_series` lands on land at that screen position (the initial view centres on 21.25 E, 55.40 N, lagoon), move the click fraction and note the change. If the pace test fails, record the measured median/max and profile `md.frame_image` (render ~0.11 s at 1040 × 1138 was measured while planning) before changing anything.

- [ ] **Step 4: Manual station-hover check**

With the app running (`shiny run --port 8765`), use the Playwright MCP browser: April run, Map tab, drag the slider to `2013-04-24 06:00`, hover the Klaipėda marker → tooltip shows `model … vs gauge … at 06:00; error …`; move to `09:00` → `no reading this hour`; hover Rusnė → `modelled only (gauge zero unknown)`. Screenshot both.

- [ ] **Step 5: Full suites, then commit**

Run: `cd /home/razinka/sfincs && micromamba run -n shiny python -m pytest app/ -q` (e2e ignored without the variable) and `cd curonian && micromamba run -n hydromt-sfincs python -m pytest tests -q`. Both pass.

```bash
cd /home/razinka/sfincs
git add app/e2e/
git commit -m "Map tab: Playwright acceptance tests for pace, frame dropping, run switch, click

<trailer lines from Global Constraints>"
```

- [ ] **Step 6: Deployment note for the user**

Report that `sudo bash deploy/deploy.sh` publishes the tab (it rsyncs `app/`, including `app/www/` and the new modules); nothing else changes on the server. Do not run it (it needs root).
