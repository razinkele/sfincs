# Curonian Lagoon SFINCS model (Storm Xaver hindcast) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build, run and validate a whole-lagoon SFINCS compound-flood model of the Curonian Lagoon and Nemunas delta for Storm Xaver, 28 Nov to 11 Dec 2013.

**Architecture:** Small preparation scripts in `~/SFINCS/curonian/prep/` each turn one raw source (isobaths, OSM, CDS, gauges, ERA5) into a reviewed input file under `inputs/`; `build_model.py` assembles them with HydroMT-SFINCS into `runs/xaver_2013/`; the Linux SFINCS binary runs it; `validate.py` scores the result against the gauges. Every script asserts on its own output; pytest covers the pure functions with synthetic data and the file outputs with integration tests.

**Tech Stack:** Python 3.11 in the `hydromt-sfincs` micromamba env (hydromt_sfincs 1.2.2, hydromt 0.10.1, geopandas 1.1, rasterio 1.4, xarray, scipy, netCDF4, requests, cdsapi, pytest); SFINCS v2.4.0 at `~/SFINCS/sfincs-linux/bin/sfincs`; OpenMP.

**Spec:** `docs/superpowers/specs/2026-09-04-curonian-lagoon-xaver-model-design.md`

## Global Constraints

- All Python runs inside the env: `micromamba run -n hydromt-sfincs python ...`. Never the system Python (NumPy 2.4 clash) and never a fresh env without the `sitecustomize.py` zlib fix (see `~/SFINCS/README.md`).
- CRS for every grid and geometry file: EPSG:3346. Time axis: naive UTC.
- Grid: `x0=270000 y0=6080000 dx=dy=100 mmax=1000 nmax=1100 rotation=0`; subgrid 20 px per cell, 10 levels.
- Period: `tref=tstart=20131128 000000`, `tstop=20131211 000000`; bias-correction window 28 Nov 00:00 to 4 Dec 00:00.
- Gauge datum: `level_m = (cm - 500) / 100`. One constant, `GAUGE_ZERO_CM` in `common.py`.
- Minija placeholder discharge: 46 m³/s constant. Nemunas travel-time shift: +1 day.
- Manning: 0.02 below +0.3 m, 0.06 above. `advection=1`, `alpha=0.5`, `huthresh=0.05`, `viscosity=1`.
- Channels: strait 400 m wide, bed −12 m; Atmata 200 m, −4 m; Skirvytė 150 m, −3 m.
- Raw data paths (read-only, never modified):
  - DEM `~/telemac/data/LowerNEMUNASdem_5m.tif`
  - EMODnet subset `~/telemac/Curonian/data/curonian_bathymetry_hires.nc` (lon/lat, variable `elevation`)
  - Isobaths `~/curonian/isobates.gpkg` layer `depth_isobates__isobates__depths`, field `depth`
  - Database `~/curonian/curonian_db.gpkg` (tables `physical_daily`, `river_discharge`, layer `lagoon_boundary`)
  - ERA5 `~/eutropy/era5_raw/era5_wind_nida_2013.nc` (`valid_time` seconds since 1970, `u10`, `v10`)
- Commits go to the `main` branch of `~/SFINCS`; `inputs/*.tif|*.nc` and run outputs are gitignored, GeoJSON and CSV inputs are committed.
- Commit message trailer on every commit:
  ```
  Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
  Claude-Session: https://claude.ai/code/session_01DifGpGPwDS99nbUF1t7FXx
  ```

Run tests with: `cd ~/SFINCS/curonian && micromamba run -n hydromt-sfincs python -m pytest tests -q`

---

## File structure

```
~/SFINCS/curonian/
├── common.py                  # constants, paths, datum conversion, DB access, projection helper
├── data_catalog.yml           # hydromt catalogue for the three elevation sources and the geometries
├── prep/
│   ├── __init__.py
│   ├── make_bathymetry.py     # isobaths -> inputs/lagoon_bathy_50m.tif
│   ├── make_channels.py       # OSM Overpass + fixed strait -> inputs/channels.geojson
│   ├── make_geometries.py     # active_region, boundary_ring, boundary_points, stations GeoJSON
│   ├── fetch_gtsm.py          # CDS download -> inputs/gtsm_klaipeda.csv
│   └── make_forcing.py        # inputs/bzs.csv, wind.csv, dis.csv, dis_points.geojson
├── build_model.py             # hydromt build -> runs/xaver_2013 (+ check_model)
├── validate.py                # skill stats, time-series figure, flood-extent map
├── tests/
│   ├── conftest.py
│   ├── test_common.py
│   ├── test_make_bathymetry.py
│   ├── test_make_channels.py
│   ├── test_make_geometries.py
│   ├── test_catalog.py
│   ├── test_fetch_gtsm.py
│   ├── test_make_forcing.py
│   ├── test_build_model.py
│   └── test_validate.py
├── inputs/                    # derived inputs (GeoJSON/CSV committed; tif/nc ignored)
├── runs/xaver_2013/           # SFINCS model + outputs (ignored)
└── README.md
```

Scripts are run as modules from the `curonian` folder so `common` and `prep` import cleanly:
`micromamba run -n hydromt-sfincs python -m prep.make_bathymetry`.

---

### Task 0: Scaffold, environment additions, shared constants

**Files:**
- Create: `curonian/common.py`, `curonian/prep/__init__.py`, `curonian/tests/conftest.py`, `curonian/tests/test_common.py`, `curonian/inputs/.gitkeep`, `curonian/runs/.gitkeep`, `curonian/README.md`
- Modify: `hydromt-sfincs.yml` (add `pytest`, `requests`, `pip: [cdsapi]`)

**Interfaces:**
- Produces (`common.py`): `ROOT, INPUTS, RUNS, RUN_XAVER: Path`; `DEM_5M, EMODNET, ISOBATHS, ISOBATH_LAYER, DB, ERA5_2013, SFINCS_BIN, RUN_SFINCS_SH`; `CRS=3346`; `X0, Y0, DX, DY, MMAX, NMAX`; `TREF, TSTOP: pd.Timestamp`; `CALM_WINDOW: tuple[pd.Timestamp, pd.Timestamp]`; `GAUGE_ZERO_CM=500.0`; `gauge_cm_to_m(cm) -> np.ndarray`; `KLAIPEDA_MOUTH_LONLAT=(21.09, 55.72)`; `MINIJA_Q_DEC=46.0`; `NEMUNAS_LAG_DAYS=1`; `lonlat_to_xy(lon, lat) -> tuple[float, float]`; `read_table(sql: str, params=()) -> pd.DataFrame`.

- [ ] **Step 1: Add pytest, requests and cdsapi to the environment**

```bash
micromamba install -y -n hydromt-sfincs --override-channels -c conda-forge pytest requests
micromamba run -n hydromt-sfincs python -m pip install "cdsapi>=0.7.5"
micromamba run -n hydromt-sfincs python -c "import pytest, cdsapi, requests; print('ok', cdsapi.__version__)"
```
Expected: `ok 0.7.x`.

- [ ] **Step 2: Record the additions in `hydromt-sfincs.yml`**

Append to the `dependencies:` list in `~/SFINCS/hydromt-sfincs.yml`:
```yaml
  - pytest
  - requests
  - pip
  - pip:
      - cdsapi>=0.7.5
```

- [ ] **Step 3: Write the failing test**

`curonian/tests/conftest.py`:
```python
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
```

`curonian/tests/test_common.py`:
```python
import numpy as np
import pandas as pd
import common


def test_gauge_conversion_uses_500cm_zero():
    assert common.gauge_cm_to_m(500) == 0.0
    assert common.gauge_cm_to_m(592) == 0.92
    np.testing.assert_allclose(common.gauge_cm_to_m([450, 550]), [-0.5, 0.5])


def test_grid_constants_match_spec():
    assert (common.X0, common.Y0, common.MMAX, common.NMAX) == (270_000, 6_080_000, 1000, 1100)
    assert common.DX == common.DY == 100.0
    assert common.CRS == 3346


def test_period_and_windows():
    assert common.TREF == pd.Timestamp("2013-11-28 00:00")
    assert common.TSTOP == pd.Timestamp("2013-12-11 00:00")
    assert common.CALM_WINDOW == (pd.Timestamp("2013-11-28"), pd.Timestamp("2013-12-04"))


def test_lonlat_to_xy_klaipeda_mouth_is_inside_domain():
    x, y = common.lonlat_to_xy(*common.KLAIPEDA_MOUTH_LONLAT)
    assert 315_000 < x < 322_000 and 6_177_000 < y < 6_183_000


def test_read_table_reads_gauge_rows():
    df = common.read_table(
        "SELECT date, site, wlevel_06 FROM physical_daily WHERE site=? AND date='2013-12-06'", ("Uostadvaris",)
    )
    assert len(df) == 1 and df.loc[0, "wlevel_06"] == 592


def test_raw_inputs_exist():
    for p in (common.DEM_5M, common.EMODNET, common.ISOBATHS, common.DB, common.ERA5_2013, common.SFINCS_BIN):
        assert p.exists(), p
```

- [ ] **Step 4: Run test to verify it fails**

Run: `cd ~/SFINCS/curonian && micromamba run -n hydromt-sfincs python -m pytest tests/test_common.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'common'`

- [ ] **Step 5: Write `common.py`**

```python
"""Shared constants and helpers for the Curonian Lagoon SFINCS model.

Everything the spec fixes as a project-wide value lives here so that a change
(e.g. the gauge zero) is a single edit.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import numpy as np
import pandas as pd
from pyproj import Transformer

ROOT = Path(__file__).resolve().parent
INPUTS = ROOT / "inputs"
RUNS = ROOT / "runs"
RUN_XAVER = RUNS / "xaver_2013"

HOME = Path.home()
DEM_5M = HOME / "telemac/data/LowerNEMUNASdem_5m.tif"
EMODNET = HOME / "telemac/Curonian/data/curonian_bathymetry_hires.nc"
ISOBATHS = HOME / "curonian/isobates.gpkg"
ISOBATH_LAYER = "depth_isobates__isobates__depths"
DB = HOME / "curonian/curonian_db.gpkg"
ERA5_2013 = HOME / "eutropy/era5_raw/era5_wind_nida_2013.nc"
SFINCS_BIN = HOME / "SFINCS/sfincs-linux/bin/sfincs"
RUN_SFINCS_SH = HOME / "SFINCS/run_sfincs.sh"

CRS = 3346  # LKS-94 / Lithuania TM
X0, Y0 = 270_000.0, 6_080_000.0
DX = DY = 100.0
MMAX, NMAX = 1000, 1100

TREF = pd.Timestamp("2013-11-28 00:00")
TSTOP = pd.Timestamp("2013-12-11 00:00")
CALM_WINDOW = (pd.Timestamp("2013-11-28"), pd.Timestamp("2013-12-04"))

GAUGE_ZERO_CM = 500.0
KLAIPEDA_MOUTH_LONLAT = (21.09, 55.72)
MINIJA_Q_DEC = 46.0
NEMUNAS_LAG_DAYS = 1

_TO_XY = Transformer.from_crs(4326, CRS, always_xy=True)


def gauge_cm_to_m(cm) -> np.ndarray:
    """Convert gauge readings in cm above gauge zero to metres in the model datum."""
    return (np.asarray(cm, dtype=float) - GAUGE_ZERO_CM) / 100.0


def lonlat_to_xy(lon: float, lat: float) -> tuple[float, float]:
    x, y = _TO_XY.transform(lon, lat)
    return float(x), float(y)


def read_table(sql: str, params: tuple = ()) -> pd.DataFrame:
    """Run a read-only SQL query against the attribute tables of curonian_db.gpkg."""
    uri = f"file:{DB}?mode=ro"
    with sqlite3.connect(uri, uri=True) as con:
        return pd.read_sql_query(sql, con, params=params)
```

`curonian/prep/__init__.py`: empty file. `curonian/inputs/.gitkeep`, `curonian/runs/.gitkeep`: empty files.

`curonian/README.md`:
```markdown
# Curonian Lagoon SFINCS model

Whole-lagoon compound-flood model, first hindcast Storm Xaver (28 Nov – 11 Dec 2013).
Design: `../docs/superpowers/specs/2026-09-04-curonian-lagoon-xaver-model-design.md`.

All commands run from this folder inside the `hydromt-sfincs` env:

    micromamba run -n hydromt-sfincs python -m prep.make_bathymetry
    micromamba run -n hydromt-sfincs python -m prep.make_channels
    micromamba run -n hydromt-sfincs python -m prep.make_geometries
    micromamba run -n hydromt-sfincs python -m prep.fetch_gtsm
    micromamba run -n hydromt-sfincs python -m prep.make_forcing
    micromamba run -n hydromt-sfincs python build_model.py
    ../run_sfincs.sh runs/xaver_2013 16
    micromamba run -n hydromt-sfincs python validate.py

Tests: `micromamba run -n hydromt-sfincs python -m pytest tests -q`
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd ~/SFINCS/curonian && micromamba run -n hydromt-sfincs python -m pytest tests/test_common.py -q`
Expected: `6 passed`

- [ ] **Step 7: Commit**

```bash
cd ~/SFINCS && git add curonian hydromt-sfincs.yml && git commit -m "curonian: scaffold, shared constants, env additions (pytest, requests, cdsapi)

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01DifGpGPwDS99nbUF1t7FXx"
```

---

### Task 1: Lagoon bathymetry from isobaths

**Files:**
- Create: `curonian/prep/make_bathymetry.py`, `curonian/tests/test_make_bathymetry.py`

**Interfaces:**
- Consumes: `common.ISOBATHS, ISOBATH_LAYER, DB, INPUTS, CRS`
- Produces: `lagoon_polygon() -> shapely.Polygon` (largest part of `lagoon_boundary`, EPSG:3346); `isobath_points(iso: GeoDataFrame, lagoon: Polygon, spacing=50.0) -> tuple[np.ndarray (n,2), np.ndarray (n,)]` (xy, depth) including shoreline points at depth 0; `make_bathymetry(res=50.0, out=INPUTS/"lagoon_bathy_50m.tif") -> Path`. Output GeoTIFF: variable elevation in metres (negative below datum), nodata −9999 outside the lagoon polygon.

- [ ] **Step 1: Write the failing test**

`curonian/tests/test_make_bathymetry.py`:
```python
import numpy as np
import pytest
import rasterio
from shapely.geometry import LineString, Polygon
import geopandas as gpd

import common
from prep import make_bathymetry as mb


def test_lagoon_polygon_is_the_big_one():
    poly = mb.lagoon_polygon()
    assert 1500e6 < poly.area < 1700e6  # 1601 km2 in the database
    assert poly.is_valid


def test_isobath_points_adds_shoreline_zeros():
    lagoon = Polygon([(0, 0), (1000, 0), (1000, 1000), (0, 1000)])
    iso = gpd.GeoDataFrame(
        {"depth": [2.0, 4.0]},
        geometry=[LineString([(100, 500), (900, 500)]), LineString([(500, 100), (500, 900)])],
        crs=common.CRS,
    )
    xy, depth = mb.isobath_points(iso, lagoon, spacing=100.0)
    assert xy.shape[1] == 2 and len(xy) == len(depth)
    assert (depth == 0.0).sum() >= 40           # 4000 m of shoreline at 100 m spacing
    assert set(np.unique(depth)) == {0.0, 2.0, 4.0}
    assert xy[:, 0].min() >= 0 and xy[:, 0].max() <= 1000


@pytest.mark.integration
def test_make_bathymetry_writes_lagoon_grid(tmp_path):
    out = mb.make_bathymetry(res=200.0, out=tmp_path / "bathy_200m.tif")  # coarse for speed
    with rasterio.open(out) as src:
        assert src.crs.to_epsg() == common.CRS
        assert src.nodata == -9999
        z = src.read(1, masked=True)
        assert z.count() > 30_000                # ~1600 km2 / 0.04 km2
        assert -10.0 <= z.min() and z.max() <= 0.5
        assert -6.5 < np.ma.median(z) < -1.0    # lagoon mean depth ~3.8 m
        centre_x, centre_y = 318_000, 6_130_000   # open lagoon west of Ventė
        row, col = src.index(centre_x, centre_y)
        assert z[row, col] < -1.5
```

Add to `curonian/tests/conftest.py` (below the sys.path lines):
```python
import pytest


def pytest_configure(config):
    config.addinivalue_line("markers", "integration: uses real data on this machine or the network")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ~/SFINCS/curonian && micromamba run -n hydromt-sfincs python -m pytest tests/test_make_bathymetry.py -q`
Expected: FAIL with `ImportError: cannot import name 'make_bathymetry'` / `ModuleNotFoundError`

- [ ] **Step 3: Write `prep/make_bathymetry.py`**

```python
"""Interpolate the in-lagoon isobaths to a 50 m bathymetry grid (elevation, m).

Output covers the lagoon polygon only; everything else is nodata so that the
subgrid merge falls back to the DEM and EMODnet there.
"""
from __future__ import annotations

from pathlib import Path

import geopandas as gpd
import numpy as np
import xarray as xr
from rasterio.transform import from_origin
from scipy.interpolate import LinearNDInterpolator, NearestNDInterpolator
from shapely.geometry import Polygon
from shapely.ops import unary_union

import common

NODATA = -9999.0


def lagoon_polygon() -> Polygon:
    gdf = gpd.read_file(common.DB, layer="lagoon_boundary").to_crs(common.CRS)
    geom = unary_union(gdf.geometry.values)
    parts = list(geom.geoms) if geom.geom_type == "MultiPolygon" else [geom]
    poly = max(parts, key=lambda p: p.area)
    return poly.buffer(0)


def isobath_points(iso: gpd.GeoDataFrame, lagoon: Polygon, spacing: float = 50.0):
    """Vertices of the isobaths inside the lagoon plus shoreline vertices at depth 0."""
    iso = iso[(iso["depth"] >= 0) & (iso["depth"] <= 20)].to_crs(common.CRS)
    clipped = gpd.clip(iso, lagoon.buffer(100.0))
    xs, ys, ds = [], [], []
    for depth, geom in zip(clipped["depth"], clipped.geometry):
        if geom is None or geom.is_empty:
            continue
        for line in getattr(geom, "geoms", [geom]):
            coords = np.asarray(line.segmentize(spacing).coords)
            xs.append(coords[:, 0]); ys.append(coords[:, 1]); ds.append(np.full(len(coords), float(depth)))
    shore = np.asarray(lagoon.exterior.segmentize(spacing).coords)
    xs.append(shore[:, 0]); ys.append(shore[:, 1]); ds.append(np.zeros(len(shore)))
    xy = np.column_stack([np.concatenate(xs), np.concatenate(ys)])
    depth = np.concatenate(ds)
    xy, idx = np.unique(np.round(xy, 1), axis=0, return_index=True)
    return xy, depth[idx]


def make_bathymetry(res: float = 50.0, out: Path = common.INPUTS / "lagoon_bathy_50m.tif") -> Path:
    lagoon = lagoon_polygon()
    iso = gpd.read_file(common.ISOBATHS, layer=common.ISOBATH_LAYER)
    xy, depth = isobath_points(iso, lagoon)
    assert len(xy) > 1000, f"too few isobath points: {len(xy)}"

    minx, miny, maxx, maxy = lagoon.buffer(res).bounds
    minx, miny = np.floor(minx / res) * res, np.floor(miny / res) * res
    ncol, nrow = int(np.ceil((maxx - minx) / res)), int(np.ceil((maxy - miny) / res))
    transform = from_origin(minx, miny + nrow * res, res, res)
    xc = minx + res * (np.arange(ncol) + 0.5)
    yc = miny + nrow * res - res * (np.arange(nrow) + 0.5)      # north to south
    gx, gy = np.meshgrid(xc, yc)

    lin = LinearNDInterpolator(xy, depth)
    z = lin(gx, gy)
    holes = np.isnan(z)
    if holes.any():
        z[holes] = NearestNDInterpolator(xy, depth)(gx[holes], gy[holes])
    elev = -np.clip(z, 0.0, 20.0)

    da = xr.DataArray(elev.astype("float32"), dims=("y", "x"), coords={"y": yc, "x": xc}, name="elevtn")
    da.raster.set_crs(common.CRS)
    da.raster.set_nodata(np.nan)
    inside = da.raster.geometry_mask(gpd.GeoDataFrame(geometry=[lagoon], crs=common.CRS))
    da = da.where(inside)
    assert float(da.count()) > 0.9 * lagoon.area / res**2, "lagoon coverage below 90 %"
    assert float(da.min()) >= -20.0 and float(da.max()) <= 0.0

    out.parent.mkdir(parents=True, exist_ok=True)
    da.raster.to_raster(out, driver="GTiff", nodata=NODATA, compress="lzw")
    print(f"wrote {out}  {ncol}x{nrow} @ {res} m, valid cells {int(da.count())}, "
          f"elev {float(da.min()):.1f}..{float(da.max()):.1f} m")
    return out


if __name__ == "__main__":
    make_bathymetry()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd ~/SFINCS/curonian && micromamba run -n hydromt-sfincs python -m pytest tests/test_make_bathymetry.py -q`
Expected: `3 passed` (the integration test takes ~30 s)

- [ ] **Step 5: Produce the real input and inspect it**

```bash
cd ~/SFINCS/curonian && micromamba run -n hydromt-sfincs python -m prep.make_bathymetry
micromamba run -n hydromt-sfincs gdalinfo -stats inputs/lagoon_bathy_50m.tif | grep -E "Size|STATISTICS_(MIN|MAX|MEAN)"
```
Expected: about 1500 x 1900 cells, mean between −5 and −2 m, min ≥ −10.

- [ ] **Step 6: Commit**

```bash
cd ~/SFINCS && git add curonian/prep/make_bathymetry.py curonian/tests && git commit -m "curonian: lagoon bathymetry grid from isobaths

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01DifGpGPwDS99nbUF1t7FXx"
```

---

### Task 2: Channel centrelines (strait, Atmata, Skirvytė)

**Files:**
- Create: `curonian/prep/make_channels.py`, `curonian/tests/test_make_channels.py`

**Interfaces:**
- Consumes: `common.INPUTS, CRS`
- Produces: `fetch_osm_rivers(timeout=90) -> dict[str, LineString]` in EPSG:4326 keyed `"atmata"`, `"skirvyte"`; `build_channels(osm: dict | None) -> GeoDataFrame` with columns `name, rivwth, rivbed, geometry` (EPSG:3346, 3 rows); `main()` writes `inputs/channels.geojson`.

- [ ] **Step 1: Write the failing test**

`curonian/tests/test_make_channels.py`:
```python
import pytest
from shapely.geometry import LineString

import common
from prep import make_channels as mc


def test_build_channels_from_fallback_has_three_rows():
    gdf = mc.build_channels(None)
    assert list(gdf["name"]) == ["strait", "atmata", "skirvyte"]
    assert gdf.crs.to_epsg() == common.CRS
    assert dict(zip(gdf["name"], gdf["rivwth"])) == {"strait": 400, "atmata": 200, "skirvyte": 150}
    assert dict(zip(gdf["name"], gdf["rivbed"])) == {"strait": -12.0, "atmata": -4.0, "skirvyte": -3.0}
    lengths = dict(zip(gdf["name"], gdf.geometry.length))
    assert 10_000 < lengths["strait"] < 20_000
    assert 5_000 < lengths["atmata"] < 25_000 and 5_000 < lengths["skirvyte"] < 25_000


def test_build_channels_prefers_osm_geometry():
    osm = {"atmata": LineString([(21.37, 55.30), (21.25, 55.335)]),
           "skirvyte": LineString([(21.37, 55.30), (21.28, 55.27)])}
    gdf = mc.build_channels(osm).set_index("name")
    assert gdf.loc["atmata", "geometry"].length == pytest.approx(
        mc.to_3346(osm["atmata"]).length, rel=1e-6)


@pytest.mark.integration
def test_fetch_osm_rivers_returns_both_distributaries():
    osm = mc.fetch_osm_rivers()
    assert set(osm) == {"atmata", "skirvyte"}
    for line in osm.values():
        assert line.geom_type == "LineString" and len(line.coords) > 5
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ~/SFINCS/curonian && micromamba run -n hydromt-sfincs python -m pytest tests/test_make_channels.py -q`
Expected: FAIL with `ImportError`

- [ ] **Step 3: Write `prep/make_channels.py`**

```python
"""Channel centrelines burned into the subgrid: Klaipėda strait, Atmata, Skirvytė.

Distributaries come from OSM Overpass (waterway=river); the strait has no OSM
fairway so it is a fixed coordinate list. Fallback coordinates cover an offline
Overpass. Output: inputs/channels.geojson with rivwth [m] and rivbed [m datum].
"""
from __future__ import annotations

import geopandas as gpd
import requests
from pyproj import Transformer
from shapely.geometry import LineString
from shapely.ops import linemerge, transform, unary_union

import common

OVERPASS = "https://overpass-api.de/api/interpreter"
QUERY = ('[out:json][timeout:60];'
         '(way["waterway"="river"]["name"~"^Atmata$|Skirvyt"](55.20,21.05,55.80,21.50););'
         'out geom;')

CHANNELS = {  # name: (rivwth m, rivbed m in model datum)
    "strait": (400, -12.0),
    "atmata": (200, -4.0),
    "skirvyte": (150, -3.0),
}
STRAIT_LONLAT = [(21.15, 55.62), (21.13, 55.65), (21.12, 55.68), (21.10, 55.71), (21.09, 55.73)]
FALLBACK_LONLAT = {
    "atmata": [(21.37, 55.30), (21.33, 55.31), (21.29, 55.32), (21.25, 55.335)],
    "skirvyte": [(21.37, 55.30), (21.34, 55.285), (21.31, 55.275), (21.28, 55.27)],
}
_T = Transformer.from_crs(4326, common.CRS, always_xy=True)


def to_3346(line_lonlat: LineString) -> LineString:
    return transform(lambda x, y, z=None: _T.transform(x, y), line_lonlat)


def _merge(lines: list[LineString]) -> LineString:
    merged = linemerge(unary_union(lines))
    if merged.geom_type == "MultiLineString":
        merged = max(merged.geoms, key=lambda g: g.length)
    return merged


def fetch_osm_rivers(timeout: int = 90) -> dict[str, LineString]:
    r = requests.post(OVERPASS, data={"data": QUERY}, timeout=timeout)
    r.raise_for_status()
    groups: dict[str, list[LineString]] = {"atmata": [], "skirvyte": []}
    for el in r.json().get("elements", []):
        name = el.get("tags", {}).get("name", "")
        key = "atmata" if name == "Atmata" else "skirvyte" if name.startswith("Skirvyt") else None
        if key and el.get("geometry"):
            groups[key].append(LineString([(p["lon"], p["lat"]) for p in el["geometry"]]))
    missing = [k for k, v in groups.items() if not v]
    if missing:
        raise RuntimeError(f"Overpass returned no ways for {missing}")
    return {k: _merge(v) for k, v in groups.items()}


def build_channels(osm: dict[str, LineString] | None) -> gpd.GeoDataFrame:
    geoms = {"strait": to_3346(LineString(STRAIT_LONLAT))}
    for key in ("atmata", "skirvyte"):
        src = osm[key] if osm and key in osm else LineString(FALLBACK_LONLAT[key])
        geoms[key] = to_3346(src)
    rows = [{"name": k, "rivwth": CHANNELS[k][0], "rivbed": CHANNELS[k][1], "geometry": geoms[k]}
            for k in ("strait", "atmata", "skirvyte")]
    gdf = gpd.GeoDataFrame(rows, crs=common.CRS)
    assert len(gdf) == 3 and gdf.geometry.is_valid.all()
    assert 10_000 < gdf.set_index("name").loc["strait", "geometry"].length < 20_000
    return gdf


def main(out=common.INPUTS / "channels.geojson") -> gpd.GeoDataFrame:
    try:
        osm = fetch_osm_rivers()
        source = "osm"
    except Exception as exc:  # network down or Overpass busy: use fixed coordinates
        print(f"Overpass unavailable ({exc}); using fallback coordinates")
        osm, source = None, "fallback"
    gdf = build_channels(osm)
    gdf["source"] = ["fixed", source, source]
    out.parent.mkdir(parents=True, exist_ok=True)
    gdf.to_file(out, driver="GeoJSON")
    print(f"wrote {out}\n{gdf[['name', 'rivwth', 'rivbed', 'source']]}\nlengths m: {gdf.geometry.length.round().tolist()}")
    return gdf


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd ~/SFINCS/curonian && micromamba run -n hydromt-sfincs python -m pytest tests/test_make_channels.py -q`
Expected: `3 passed`

- [ ] **Step 5: Produce the real input**

Run: `cd ~/SFINCS/curonian && micromamba run -n hydromt-sfincs python -m prep.make_channels`
Expected: `source` column shows `osm` for both distributaries; lengths roughly strait 13 km, Atmata 10–20 km, Skirvytė 8–20 km. If Overpass failed, rerun once before accepting the fallback.

- [ ] **Step 6: Commit**

```bash
cd ~/SFINCS && git add curonian/prep/make_channels.py curonian/tests/test_make_channels.py curonian/inputs/channels.geojson && git commit -m "curonian: channel centrelines for strait and Nemunas distributaries

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01DifGpGPwDS99nbUF1t7FXx"
```

---

### Task 3: Model geometries (active region, boundary ring, boundary points, stations)

**Files:**
- Create: `curonian/prep/make_geometries.py`, `curonian/tests/test_make_geometries.py`

**Interfaces:**
- Consumes: `prep.make_bathymetry.lagoon_polygon()`, `inputs/channels.geojson` (strait line), `common.KLAIPEDA_MOUTH_LONLAT, lonlat_to_xy, X0, Y0, DX, DY, MMAX, NMAX, INPUTS, CRS`
- Produces: `domain_box() -> Polygon`; `mouth_xy() -> tuple[float,float]`; `active_region(lagoon, strait_line) -> Polygon`; `boundary_ring(r_in=2000.0, r_out=2600.0) -> Polygon`; `boundary_points(n=7, r=2300.0) -> GeoDataFrame` (index 1..n, column `index`); `stations() -> GeoDataFrame` (columns `name`, geometry); `main()` writes `inputs/active_region.geojson`, `inputs/boundary_ring.geojson`, `inputs/boundary_points.geojson`, `inputs/stations.geojson`.

Station list (lon, lat): Klaipeda (21.09, 55.715), Juodkrante (21.11, 55.55), Nida (21.005, 55.303), Vente (21.19, 55.34), Uostadvaris (21.24, 55.33), Rusne (21.37, 55.30), Silute (21.48, 55.35), Atmata_mouth (21.23, 55.335), Zalivino_RU (21.05, 54.98).

- [ ] **Step 1: Write the failing test**

`curonian/tests/test_make_geometries.py`:
```python
import geopandas as gpd
from shapely.geometry import LineString, Polygon

import common
from prep import make_geometries as mg


def test_domain_box_matches_grid():
    b = mg.domain_box().bounds
    assert b == (270_000.0, 6_080_000.0, 370_000.0, 6_190_000.0)


def test_boundary_ring_is_annulus_at_the_mouth():
    ring = mg.boundary_ring()
    mx, my = mg.mouth_xy()
    assert ring.contains(mg.Point(mx + 2300, my)) and not ring.contains(mg.Point(mx + 1000, my))
    assert mg.domain_box().contains(ring)


def test_boundary_points_lie_on_the_seaward_arc():
    pts = mg.boundary_points()
    assert list(pts["index"]) == list(range(1, 8)) and pts.crs.to_epsg() == common.CRS
    mx, my = mg.mouth_xy()
    assert all(abs(p.distance(mg.Point(mx, my)) - 2300) < 1 for p in pts.geometry)
    assert (pts.geometry.x < mx + 200).all()          # seaward = west of the mouth


def test_active_region_contains_lagoon_delta_and_mouth_but_not_open_sea():
    lagoon = Polygon([(280_000, 6_090_000), (350_000, 6_090_000), (350_000, 6_170_000), (280_000, 6_170_000)])
    strait = LineString([(320_000, 6_168_000), (318_000, 6_180_000)])
    reg = mg.active_region(lagoon, strait)
    mx, my = mg.mouth_xy()
    assert reg.contains(mg.Point(300_000, 6_120_000))     # lagoon
    assert reg.contains(mg.Point(345_000, 6_118_000))     # Šilutė lowland
    assert reg.contains(mg.Point(mx - 1500, my))          # harbour mouth disc
    assert not reg.contains(mg.Point(mx - 8000, my))      # open Baltic
    assert mg.domain_box().contains(reg)


def test_stations_have_nine_named_points_inside_domain():
    st = mg.stations()
    assert len(st) == 9 and st["name"].is_unique
    assert st.geometry.within(mg.domain_box()).all()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ~/SFINCS/curonian && micromamba run -n hydromt-sfincs python -m pytest tests/test_make_geometries.py -q`
Expected: FAIL with `ImportError`

- [ ] **Step 3: Write `prep/make_geometries.py`**

```python
"""Geometries that shape the model: active region, boundary ring, boundary points, stations."""
from __future__ import annotations

import geopandas as gpd
import numpy as np
from shapely.geometry import LineString, Point, Polygon, box
from shapely.ops import unary_union

import common
from prep.make_bathymetry import lagoon_polygon

STATIONS_LONLAT = {
    "Klaipeda": (21.09, 55.715), "Juodkrante": (21.11, 55.55), "Nida": (21.005, 55.303),
    "Vente": (21.19, 55.34), "Uostadvaris": (21.24, 55.33), "Rusne": (21.37, 55.30),
    "Silute": (21.48, 55.35), "Atmata_mouth": (21.23, 55.335), "Zalivino_RU": (21.05, 54.98),
}
DELTA_BOX = (325_000, 6_100_000, 370_000, 6_150_000)   # Šilutė / Rusnė / Russian lowlands


def domain_box() -> Polygon:
    return box(common.X0, common.Y0, common.X0 + common.MMAX * common.DX, common.Y0 + common.NMAX * common.DY)


def mouth_xy() -> tuple[float, float]:
    return common.lonlat_to_xy(*common.KLAIPEDA_MOUTH_LONLAT)


def active_region(lagoon: Polygon, strait_line: LineString, mouth_radius: float = 2600.0) -> Polygon:
    mx, my = mouth_xy()
    parts = [lagoon.buffer(2000.0), box(*DELTA_BOX), strait_line.buffer(1500.0), Point(mx, my).buffer(mouth_radius)]
    reg = unary_union(parts).intersection(domain_box())
    if reg.geom_type == "MultiPolygon":
        reg = max(reg.geoms, key=lambda g: g.area)
    return reg.buffer(0)


def boundary_ring(r_in: float = 2000.0, r_out: float = 2600.0) -> Polygon:
    mx, my = mouth_xy()
    return Point(mx, my).buffer(r_out).difference(Point(mx, my).buffer(r_in))


def boundary_points(n: int = 7, r: float = 2300.0) -> gpd.GeoDataFrame:
    """Points on the seaward arc (bearings 195°..345°, i.e. SSW through W to NNW)."""
    mx, my = mouth_xy()
    bearings = np.linspace(195, 345, n)
    geoms = [Point(mx + r * np.sin(np.radians(b)), my + r * np.cos(np.radians(b))) for b in bearings]
    return gpd.GeoDataFrame({"index": np.arange(1, n + 1)}, geometry=geoms, crs=common.CRS)


def stations() -> gpd.GeoDataFrame:
    rows = [{"name": k, "geometry": Point(*common.lonlat_to_xy(lon, lat))} for k, (lon, lat) in STATIONS_LONLAT.items()]
    return gpd.GeoDataFrame(rows, crs=common.CRS)


def main(inputs=common.INPUTS) -> None:
    lagoon = lagoon_polygon()
    channels = gpd.read_file(inputs / "channels.geojson").set_index("name")
    reg = active_region(lagoon, channels.loc["strait", "geometry"])
    ring = boundary_ring()
    assert domain_box().contains(reg) and domain_box().contains(ring)
    assert reg.intersects(ring), "boundary ring must touch the active region"
    gpd.GeoDataFrame(geometry=[reg], crs=common.CRS).to_file(inputs / "active_region.geojson", driver="GeoJSON")
    gpd.GeoDataFrame(geometry=[ring], crs=common.CRS).to_file(inputs / "boundary_ring.geojson", driver="GeoJSON")
    boundary_points().to_file(inputs / "boundary_points.geojson", driver="GeoJSON")
    stations().to_file(inputs / "stations.geojson", driver="GeoJSON")
    print(f"active region {reg.area/1e6:.0f} km2; wrote 4 GeoJSON files to {inputs}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd ~/SFINCS/curonian && micromamba run -n hydromt-sfincs python -m pytest tests/test_make_geometries.py -q`
Expected: `5 passed`

- [ ] **Step 5: Produce the real inputs**

Run: `cd ~/SFINCS/curonian && micromamba run -n hydromt-sfincs python -m prep.make_geometries`
Expected: active region between 2500 and 4500 km².

- [ ] **Step 6: Commit**

```bash
cd ~/SFINCS && git add curonian/prep/make_geometries.py curonian/tests/test_make_geometries.py curonian/inputs/*.geojson && git commit -m "curonian: active region, boundary ring and points, stations

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01DifGpGPwDS99nbUF1t7FXx"
```

---

### Task 4: HydroMT data catalogue

**Files:**
- Create: `curonian/data_catalog.yml`, `curonian/tests/test_catalog.py`

**Interfaces:**
- Consumes: `inputs/lagoon_bathy_50m.tif` (Task 1), `inputs/channels.geojson` (Task 2), the four GeoJSON files (Task 3), raw DEM and EMODnet paths.
- Produces: catalogue source names used by `build_model.py`: `dem_5m`, `lagoon_bathy_50m`, `emodnet_2022`, `lagoon_boundary`, `channels`, `active_region`, `boundary_ring`.

- [ ] **Step 1: Write the failing test**

`curonian/tests/test_catalog.py`:
```python
import pytest
from hydromt import DataCatalog

import common


@pytest.mark.integration
def test_catalog_sources_load():
    dc = DataCatalog(data_libs=[str(common.ROOT / "data_catalog.yml")])
    for name in ("dem_5m", "lagoon_bathy_50m", "emodnet_2022", "lagoon_boundary", "channels", "active_region", "boundary_ring"):
        assert name in dc.sources, name
    bbox_xy = (330_000, 6_115_000, 332_000, 6_117_000)   # 2 x 2 km near Rusnė, EPSG:3346
    dem = dc.get_rasterdataset("dem_5m", bbox=bbox_xy, buffer=0)
    assert dem.raster.crs.to_epsg() == common.CRS and dem.name == "elevtn"
    assert abs(dem.raster.res[0]) == 5.0 and float(dem.max()) < 20
    bathy = dc.get_rasterdataset("lagoon_bathy_50m", bbox=(315_000, 6_125_000, 320_000, 6_130_000), buffer=0)
    assert float(bathy.min()) < -1.0
    emod = dc.get_rasterdataset("emodnet_2022", bbox=(20.85, 55.65, 20.95, 55.75), buffer=0)
    assert emod.raster.crs.is_geographic and emod.name == "elevtn" and float(emod.min()) < -10
    ch = dc.get_geodataframe("channels")
    assert set(ch["name"]) == {"strait", "atmata", "skirvyte"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ~/SFINCS/curonian && micromamba run -n hydromt-sfincs python -m pytest tests/test_catalog.py -q`
Expected: FAIL (catalogue file missing)

- [ ] **Step 3: Write `data_catalog.yml`**

```yaml
# HydroMT 0.10 data catalogue for the Curonian Lagoon SFINCS model.
# Paths are absolute on this machine; raw sources are read-only.
meta:
  root: /home/razinka/SFINCS/curonian
  version: 2026-09-04

dem_5m:
  data_type: RasterDataset
  driver: raster
  path: /home/razinka/telemac/data/LowerNEMUNASdem_5m.tif
  crs: 3346
  nodata: -9999
  rename:
    LowerNEMUNASdem_5m: elevtn
  meta:
    category: topography
    notes: 5 m DEM of the lower Nemunas; flat 0 inside the lagoon, absent on the Spit

lagoon_bathy_50m:
  data_type: RasterDataset
  driver: raster
  path: inputs/lagoon_bathy_50m.tif
  crs: 3346
  nodata: -9999
  rename:
    lagoon_bathy_50m: elevtn
  meta:
    category: bathymetry
    notes: interpolated from ~/curonian/isobates.gpkg by prep/make_bathymetry.py

emodnet_2022:
  data_type: RasterDataset
  driver: netcdf
  path: /home/razinka/telemac/Curonian/data/curonian_bathymetry_hires.nc
  crs: 4326
  rename:
    elevation: elevtn
  meta:
    category: bathymetry
    notes: EMODnet 2022 subset; fallback only (Spit land, Baltic outside the strait)

lagoon_boundary:
  data_type: GeoDataFrame
  driver: vector
  path: /home/razinka/curonian/curonian_db.gpkg
  driver_kwargs:
    layer: lagoon_boundary
  crs: 3346

channels:
  data_type: GeoDataFrame
  driver: vector
  path: inputs/channels.geojson
  crs: 3346

active_region:
  data_type: GeoDataFrame
  driver: vector
  path: inputs/active_region.geojson
  crs: 3346

boundary_ring:
  data_type: GeoDataFrame
  driver: vector
  path: inputs/boundary_ring.geojson
  crs: 3346
```

If the DEM band is not named `LowerNEMUNASdem_5m` when loaded (the test's `dem.name == "elevtn"` fails), print `dc.get_rasterdataset("dem_5m").name` and put that name in the `rename` block instead. Same for `lagoon_bathy_50m`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd ~/SFINCS/curonian && micromamba run -n hydromt-sfincs python -m pytest tests/test_catalog.py -q`
Expected: `1 passed`

- [ ] **Step 5: Commit**

```bash
cd ~/SFINCS && git add curonian/data_catalog.yml curonian/tests/test_catalog.py && git commit -m "curonian: hydromt data catalogue

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01DifGpGPwDS99nbUF1t7FXx"
```

---

### Task 5: GTSM hourly sea level from the Climate Data Store

**Files:**
- Create: `curonian/prep/fetch_gtsm.py`, `curonian/tests/test_fetch_gtsm.py`

**Interfaces:**
- Consumes: `~/.cdsapirc`, `common.KLAIPEDA_MOUTH_LONLAT, INPUTS`
- Produces: `download(target=INPUTS/"gtsm_2013_11_12.zip") -> Path`; `extract_nearest(zip_path, lonlat) -> tuple[pd.Series, dict]` hourly series named `waterlevel_m` (naive UTC index) and `{"lon", "lat", "distance_km", "station"}`; `main()` writes `inputs/gtsm_klaipeda.csv` (columns `time, waterlevel_m`) and prints the station distance.

- [ ] **Step 1: Check the CDS credentials and the dataset form**

```bash
grep -E "^url" ~/.cdsapirc
curl -s "https://cds.climate.copernicus.eu/api/catalogue/v1/collections/sis-water-level-change-timeseries-cmip6/form.json" \
  | micromamba run -n hydromt-sfincs python -c "
import json,sys
for w in json.load(sys.stdin):
    if w.get('type') in ('StringListWidget','StringListArrayWidget','StringChoiceWidget'):
        vals=w.get('details',{}).get('values') or [v for g in w.get('details',{}).get('groups',[]) for v in g.get('values',[])]
        print(w['name'], '->', vals[:12])"
```
Expected: the `url` line is `https://cds.climate.copernicus.eu/api` (the new CDS). If it ends in `/v2`, replace the file with the new URL and the personal access token from https://cds.climate.copernicus.eu/profile before continuing. The form must list `variable` containing `total_water_level`, `experiment` containing `reanalysis`, `temporal_aggregation` containing `hourly`, plus `year` and `month`. If a key is named differently, use the printed names in `REQUEST` below. The dataset licence must be accepted once on its CDS page.

- [ ] **Step 2: Write the failing test**

`curonian/tests/test_fetch_gtsm.py`:
```python
import numpy as np
import pandas as pd
import pytest
import xarray as xr

import common
from prep import fetch_gtsm as fg


def _fake_gtsm_file(path, lons, lats, start="2013-11-01", hours=48):
    t = pd.date_range(start, periods=hours, freq="h")
    wl = np.zeros((hours, len(lons)), dtype="float32")
    wl[:, 0] = np.sin(np.arange(hours) / 6.0)
    ds = xr.Dataset(
        {"waterlevel": (("time", "stations"), wl)},
        coords={"time": t, "stations": np.arange(len(lons)),
                "station_x_coordinate": ("stations", np.array(lons)),
                "station_y_coordinate": ("stations", np.array(lats))},
    )
    ds.to_netcdf(path)


def test_nearest_station_and_hourly_series(tmp_path):
    p1 = tmp_path / "a_2013_11.nc"; p2 = tmp_path / "a_2013_12.nc"
    _fake_gtsm_file(p1, [21.05, 20.5], [55.72, 56.0], "2013-11-01")
    _fake_gtsm_file(p2, [21.05, 20.5], [55.72, 56.0], "2013-11-03")
    series, meta = fg.series_from_files([p1, p2], lonlat=(21.09, 55.72))
    assert meta["station"] == 0 and meta["distance_km"] < 5
    assert series.index.freq == "h" or (series.index[1] - series.index[0]) == pd.Timedelta("1h")
    assert len(series) == 96 and series.index.is_monotonic_increasing and series.notna().all()
    assert series.name == "waterlevel_m"


@pytest.mark.integration
def test_real_gtsm_csv_covers_the_event():
    csv = common.INPUTS / "gtsm_klaipeda.csv"
    if not csv.exists():
        pytest.skip("run prep.fetch_gtsm first")
    s = pd.read_csv(csv, index_col=0, parse_dates=True)["waterlevel_m"]
    assert s.index.min() <= common.TREF and s.index.max() >= common.TSTOP
    assert (s.index.to_series().diff().dropna() == pd.Timedelta("1h")).all()
    assert s.loc["2013-12-05":"2013-12-08"].max() - s.loc["2013-11-28":"2013-12-03"].mean() > 0.3
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd ~/SFINCS/curonian && micromamba run -n hydromt-sfincs python -m pytest tests/test_fetch_gtsm.py -q`
Expected: FAIL with `ImportError`

- [ ] **Step 4: Write `prep/fetch_gtsm.py`**

```python
"""Hourly total water level near Klaipėda from the GTSM-ERA5 reanalysis (CDS).

Dataset: sis-water-level-change-timeseries-cmip6, experiment reanalysis, hourly.
The download is a zip of monthly NetCDF files with a `stations` dimension.
"""
from __future__ import annotations

import zipfile
from pathlib import Path

import numpy as np
import pandas as pd
import xarray as xr

import common

DATASET = "sis-water-level-change-timeseries-cmip6"
REQUEST = {
    "variable": ["total_water_level"],
    "experiment": ["reanalysis"],
    "temporal_aggregation": ["hourly"],
    "year": ["2013"],
    "month": ["11", "12"],
}
VAR_NAMES = ("waterlevel", "total_water_level", "water_level")
LON_NAMES = ("station_x_coordinate", "lon", "longitude")
LAT_NAMES = ("station_y_coordinate", "lat", "latitude")


def download(target: Path = common.INPUTS / "gtsm_2013_11_12.zip") -> Path:
    import cdsapi
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists() and target.stat().st_size > 1_000_000:
        print(f"using cached {target}")
        return target
    cdsapi.Client().retrieve(DATASET, REQUEST, str(target))
    return target


def _pick(ds: xr.Dataset, names) -> str:
    for n in names:
        if n in ds.variables:
            return n
    raise KeyError(f"none of {names} in {list(ds.variables)}")


def _haversine_km(lon1, lat1, lon2, lat2):
    lon1, lat1, lon2, lat2 = map(np.radians, (lon1, lat1, lon2, lat2))
    a = np.sin((lat2 - lat1) / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin((lon2 - lon1) / 2) ** 2
    return 6371.0 * 2 * np.arcsin(np.sqrt(a))


def series_from_files(files: list[Path], lonlat=common.KLAIPEDA_MOUTH_LONLAT):
    parts, meta = [], None
    for f in sorted(files):
        with xr.open_dataset(f) as ds:
            var, lonn, latn = _pick(ds, VAR_NAMES), _pick(ds, LON_NAMES), _pick(ds, LAT_NAMES)
            lon, lat = ds[lonn].values.ravel(), ds[latn].values.ravel()
            d = _haversine_km(lon, lat, lonlat[0], lonlat[1])
            i = int(np.argmin(d))
            if meta is None:
                meta = {"station": i, "lon": float(lon[i]), "lat": float(lat[i]), "distance_km": float(d[i])}
            s = ds[var].isel({ds[var].dims[-1]: i}).to_series() if ds[var].dims[-1] != "time" \
                else ds[var].isel({ds[var].dims[0]: i}).to_series()
            parts.append(s)
    series = pd.concat(parts).sort_index()
    series = series[~series.index.duplicated()].astype(float)
    series.index = pd.DatetimeIndex(series.index).tz_localize(None)
    series = series.asfreq("h")
    assert series.notna().all(), "gaps in GTSM series"
    series.name = "waterlevel_m"
    return series, meta


def extract_nearest(zip_path: Path, lonlat=common.KLAIPEDA_MOUTH_LONLAT):
    outdir = zip_path.with_suffix("")
    outdir.mkdir(exist_ok=True)
    with zipfile.ZipFile(zip_path) as z:
        names = [n for n in z.namelist() if n.endswith(".nc")]
        z.extractall(outdir, members=names)
    return series_from_files([outdir / n for n in names], lonlat)


def main(out: Path = common.INPUTS / "gtsm_klaipeda.csv") -> pd.Series:
    zip_path = download()
    series, meta = extract_nearest(zip_path)
    assert meta["distance_km"] < 60, f"nearest GTSM station is {meta['distance_km']:.0f} km away"
    series.to_csv(out, index_label="time")
    print(f"wrote {out}: {series.index.min()} -> {series.index.max()}, station {meta}")
    return series


if __name__ == "__main__":
    main()
```

- [ ] **Step 5: Run the unit test**

Run: `cd ~/SFINCS/curonian && micromamba run -n hydromt-sfincs python -m pytest tests/test_fetch_gtsm.py -q -k nearest`
Expected: `1 passed`

- [ ] **Step 6: Download the real data and run the integration test**

```bash
cd ~/SFINCS/curonian && micromamba run -n hydromt-sfincs python -m prep.fetch_gtsm
micromamba run -n hydromt-sfincs python -m pytest tests/test_fetch_gtsm.py -q
```
Expected: the CDS job may queue for minutes; the printed station distance must be below 60 km; `2 passed`. If the download fails on request keys, fix `REQUEST` from the form printed in Step 1. If the zip contains a single file for both months, `series_from_files` still works.

- [ ] **Step 7: Commit**

```bash
cd ~/SFINCS && git add curonian/prep/fetch_gtsm.py curonian/tests/test_fetch_gtsm.py curonian/inputs/gtsm_klaipeda.csv && git commit -m "curonian: GTSM hourly sea level near Klaipeda from CDS

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01DifGpGPwDS99nbUF1t7FXx"
```

---

### Task 6: Forcing time series (sea boundary, wind, discharge)

**Files:**
- Create: `curonian/prep/make_forcing.py`, `curonian/tests/test_make_forcing.py`

**Interfaces:**
- Consumes: `inputs/gtsm_klaipeda.csv`, `inputs/boundary_points.geojson`, `common.read_table, gauge_cm_to_m, CALM_WINDOW, TREF, TSTOP, ERA5_2013, MINIJA_Q_DEC, NEMUNAS_LAG_DAYS, lonlat_to_xy`
- Produces: `load_gauge_levels(site) -> pd.Series` (m, index at 06:00/18:00); `bias_correct(model, obs, window) -> tuple[pd.Series, float]`; `boundary_forcing(gtsm, npoints) -> pd.DataFrame` (hourly, columns 1..n); `wind_forcing(era5_path) -> pd.DataFrame` (columns `mag`, `dir`); `discharge_forcing() -> pd.DataFrame` (columns 1=Nemunas, 2=Minija); `discharge_points() -> GeoDataFrame` (index col, 2 rows); `main()` writes `inputs/bzs.csv`, `inputs/wind.csv`, `inputs/dis.csv`, `inputs/dis_points.geojson`, `inputs/forcing_summary.txt`.

CSV conventions: index label `time`, ISO timestamps, one column per point named by its integer index (`1`, `2`, ...). `wind.csv` columns are `time,mag,dir`.

- [ ] **Step 1: Write the failing test**

`curonian/tests/test_make_forcing.py`:
```python
import numpy as np
import pandas as pd
import pytest

import common
from prep import make_forcing as mf


def test_bias_correct_aligns_calm_window_means():
    t = pd.date_range("2013-11-27", "2013-12-10", freq="h")
    model = pd.Series(0.5 + 0.1 * np.sin(np.arange(len(t)) / 10), index=t)
    obs = pd.Series(0.05, index=pd.date_range("2013-11-28 06:00", "2013-12-03 06:00", freq="D"))
    corrected, offset = mf.bias_correct(model, obs, common.CALM_WINDOW)
    win = corrected.loc[common.CALM_WINDOW[0]:common.CALM_WINDOW[1]]
    assert abs(win.reindex(obs.index, method="nearest").mean() - 0.05) < 1e-9
    assert abs(offset - (0.05 - model.reindex(obs.index, method="nearest").mean())) < 1e-9


def test_boundary_forcing_covers_period_on_all_points():
    t = pd.date_range("2013-11-27", "2013-12-12", freq="h")
    gtsm = pd.Series(np.linspace(0, 1, len(t)), index=t)
    df = mf.boundary_forcing(gtsm, npoints=7)
    assert list(df.columns) == list(range(1, 8))
    assert df.index[0] == common.TREF and df.index[-1] == common.TSTOP
    assert (df.nunique(axis=1) == 1).all() and df.notna().all().all()


def test_wind_from_uv_gives_meteorological_direction():
    t = pd.date_range("2013-11-28", periods=3, freq="h")
    u = np.array([0.0, 10.0, 0.0]); v = np.array([10.0, 0.0, -10.0])   # from S, from W, from N
    df = mf.wind_from_uv(t, u, v)
    np.testing.assert_allclose(df["mag"], [10, 10, 10])
    np.testing.assert_allclose(df["dir"], [180, 270, 0], atol=1e-6)


def test_nemunas_lag_and_hourly_interpolation():
    daily = pd.Series([400.0, 500.0, 600.0], index=pd.to_datetime(["2013-11-27", "2013-11-28", "2013-11-29"]))
    hourly = mf.lag_and_resample(daily, lag_days=1, start=pd.Timestamp("2013-11-28"), stop=pd.Timestamp("2013-11-29"))
    assert hourly.loc["2013-11-28 00:00"] == 400.0        # 27 Nov value arrives one day later
    assert hourly.loc["2013-11-29 00:00"] == 500.0
    assert abs(hourly.loc["2013-11-28 12:00"] - 450.0) < 1e-9


@pytest.mark.integration
def test_real_gauges_and_discharge():
    obs = mf.load_gauge_levels("Uostadvaris")
    assert abs(obs.loc["2013-12-06 06:00"] - 0.92) < 1e-9
    q = mf.discharge_forcing()
    assert q.index[0] == common.TREF and q.index[-1] == common.TSTOP
    assert 350 < q[1].loc["2013-12-01":"2013-12-05"].mean() < 600 and (q[2] == common.MINIJA_Q_DEC).all()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ~/SFINCS/curonian && micromamba run -n hydromt-sfincs python -m pytest tests/test_make_forcing.py -q`
Expected: FAIL with `ImportError`

- [ ] **Step 3: Write `prep/make_forcing.py`**

```python
"""Forcing time series for the Xaver run: sea boundary, uniform wind, river discharge."""
from __future__ import annotations

from pathlib import Path

import geopandas as gpd
import netCDF4 as nc
import numpy as np
import pandas as pd
from shapely.geometry import Point

import common

NEMUNAS_APEX_LONLAT = (21.38, 55.30)   # Rusnė, where the Nemunas splits into Atmata and Skirvytė
MINIJA_MOUTH_LONLAT = (21.25, 55.42)


def load_gauge_levels(site: str) -> pd.Series:
    df = common.read_table(
        "SELECT date, wlevel_06, wlevel_18 FROM physical_daily WHERE site=? AND date BETWEEN '2013-11-20' AND '2013-12-20'",
        (site,))
    rows = []
    for _, r in df.iterrows():
        for col, hh in (("wlevel_06", 6), ("wlevel_18", 18)):
            if pd.notna(r[col]) and r[col] > 0:
                rows.append((pd.Timestamp(r["date"]) + pd.Timedelta(hours=hh), common.gauge_cm_to_m(r[col]).item()))
    s = pd.Series(dict(rows)).sort_index()
    s.name = site
    return s


def bias_correct(model: pd.Series, obs: pd.Series, window) -> tuple[pd.Series, float]:
    obs_w = obs.loc[window[0]:window[1]]
    model_at_obs = model.reindex(obs_w.index, method="nearest", tolerance=pd.Timedelta("1h"))
    offset = float(obs_w.mean() - model_at_obs.mean())
    return model + offset, offset


def boundary_forcing(gtsm: pd.Series, npoints: int) -> pd.DataFrame:
    t = pd.date_range(common.TREF, common.TSTOP, freq="h")
    s = gtsm.reindex(t).interpolate(limit_direction="both")
    assert s.notna().all()
    return pd.DataFrame({i: s.values for i in range(1, npoints + 1)}, index=t)


def wind_from_uv(t, u, v) -> pd.DataFrame:
    mag = np.hypot(u, v)
    direction = (270.0 - np.degrees(np.arctan2(v, u))) % 360.0     # direction the wind comes FROM
    return pd.DataFrame({"mag": mag, "dir": direction}, index=pd.DatetimeIndex(t))


def wind_forcing(era5_path: Path = common.ERA5_2013) -> pd.DataFrame:
    with nc.Dataset(era5_path) as d:
        t = pd.to_datetime(d["valid_time"][:].astype("int64"), unit="s")
        u = d["u10"][:, 0, 0].astype(float); v = d["v10"][:, 0, 0].astype(float)
    df = wind_from_uv(t, u, v)
    df = df.loc[common.TREF - pd.Timedelta("1h"): common.TSTOP + pd.Timedelta("1h")]
    assert df.notna().all().all() and df["mag"].max() > 15, "expected the Xaver gale in the wind series"
    return df


def lag_and_resample(daily: pd.Series, lag_days: int, start: pd.Timestamp, stop: pd.Timestamp) -> pd.Series:
    shifted = daily.copy()
    shifted.index = shifted.index + pd.Timedelta(days=lag_days)
    hourly = shifted.resample("h").interpolate("linear")
    return hourly.loc[start:stop]


def cmems_daily_boundary(path: Path = common.HOME / "curonian/shyfem_box/cmems_boundary/cmems_bal_boundary_2009_2014.nc",
                         lonlat=common.KLAIPEDA_MOUTH_LONLAT) -> pd.Series:
    """Fallback sea level: daily-mean CMEMS `sla` at the grid point nearest the mouth, interpolated to hourly."""
    with nc.Dataset(path) as d:
        t = pd.to_datetime([str(x) for x in nc.num2date(d["time"][:], d["time"].units, only_use_cftime_datetimes=False)])
        la, lo = d["latitude"][:], d["longitude"][:]
        i, j = int(np.argmin(abs(la - lonlat[1]))), int(np.argmin(abs(lo - lonlat[0])))
        sla = np.ma.filled(d["sla"][:, i, j], np.nan)
    daily = pd.Series(sla, index=t + pd.Timedelta(hours=12)).loc["2013-11-20":"2013-12-20"]   # daily means -> noon
    hourly = daily.resample("h").interpolate("linear")
    assert hourly.notna().all(), "CMEMS sla has gaps near the mouth"
    hourly.name = "waterlevel_m"
    return hourly


def discharge_forcing() -> pd.DataFrame:
    df = common.read_table(
        "SELECT date, discharge_m3s FROM river_discharge WHERE river='Nemunas' AND gauge='Smalininkai' "
        "AND date BETWEEN '2013-11-20' AND '2013-12-20' ORDER BY date")
    daily = pd.Series(df["discharge_m3s"].values, index=pd.to_datetime(df["date"]))
    nem = lag_and_resample(daily, common.NEMUNAS_LAG_DAYS, common.TREF, common.TSTOP)
    assert nem.notna().all() and nem.index[0] == common.TREF and nem.index[-1] == common.TSTOP
    return pd.DataFrame({1: nem.values, 2: common.MINIJA_Q_DEC}, index=nem.index)


def discharge_points() -> gpd.GeoDataFrame:
    pts = [Point(*common.lonlat_to_xy(*NEMUNAS_APEX_LONLAT)), Point(*common.lonlat_to_xy(*MINIJA_MOUTH_LONLAT))]
    return gpd.GeoDataFrame({"index": [1, 2], "name": ["Nemunas_Rusne", "Minija_mouth"]}, geometry=pts, crs=common.CRS)


def main(inputs: Path = common.INPUTS, use_cmems: bool = False) -> None:
    if use_cmems:
        gtsm = cmems_daily_boundary()
        print("using the daily CMEMS cache as sea boundary (fallback)")
    else:
        gtsm = pd.read_csv(inputs / "gtsm_klaipeda.csv", index_col=0, parse_dates=True)["waterlevel_m"]
    klaipeda = load_gauge_levels("Klaipeda")
    corrected, offset = bias_correct(gtsm, klaipeda, common.CALM_WINDOW)
    bnd_pts = gpd.read_file(inputs / "boundary_points.geojson")
    bzs = boundary_forcing(corrected, len(bnd_pts))
    bzs.to_csv(inputs / "bzs.csv", index_label="time")

    wind = wind_forcing()
    wind.to_csv(inputs / "wind.csv", index_label="time")

    dis = discharge_forcing()
    dis.to_csv(inputs / "dis.csv", index_label="time")
    discharge_points().to_file(inputs / "dis_points.geojson", driver="GeoJSON")

    storm = corrected.loc["2013-12-05":"2013-12-08"]
    summary = (f"GTSM offset applied: {offset:+.3f} m (calm window {common.CALM_WINDOW[0].date()}..{common.CALM_WINDOW[1].date()})\n"
               f"boundary level: start {corrected.loc[common.TREF]:.2f} m, storm peak {storm.max():.2f} m at {storm.idxmax()}\n"
               f"Klaipeda 06h obs peak: {klaipeda.max():.2f} m at {klaipeda.idxmax()}\n"
               f"wind peak: {wind['mag'].max():.1f} m/s at {wind['mag'].idxmax()} from {wind.loc[wind['mag'].idxmax(), 'dir']:.0f} deg\n"
               f"Nemunas Q: {dis[1].min():.0f}..{dis[1].max():.0f} m3/s; Minija constant {common.MINIJA_Q_DEC} m3/s\n")
    (inputs / "forcing_summary.txt").write_text(summary)
    print(summary)


if __name__ == "__main__":
    import sys
    main(use_cmems="--cmems" in sys.argv)
```

The `--cmems` switch is the spec's fallback: run `python -m prep.make_forcing --cmems` only if the GTSM series is unusable at Klaipėda (Step 5 check fails badly); it smears the surge peak, so say so in `forcing_summary.txt`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd ~/SFINCS/curonian && micromamba run -n hydromt-sfincs python -m pytest tests/test_make_forcing.py -q`
Expected: `5 passed`

- [ ] **Step 5: Produce the real inputs and sanity-check the summary**

Run: `cd ~/SFINCS/curonian && micromamba run -n hydromt-sfincs python -m prep.make_forcing`
Expected: offset within ±0.6 m; boundary storm peak 0.7–1.2 m between 5 Dec 18:00 and 7 Dec 12:00; wind peak 19.5 m/s on 6 Dec 06:00 from ~236°; Nemunas 350–560 m³/s. If the GTSM peak is more than 12 h from the Klaipėda 06:00 peak on 6 Dec, record that in the summary; it is a finding, not a blocker.

- [ ] **Step 6: Commit**

```bash
cd ~/SFINCS && git add curonian/prep/make_forcing.py curonian/tests/test_make_forcing.py curonian/inputs/bzs.csv curonian/inputs/wind.csv curonian/inputs/dis.csv curonian/inputs/dis_points.geojson curonian/inputs/forcing_summary.txt && git commit -m "curonian: sea boundary, wind and discharge forcing for Xaver 2013

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01DifGpGPwDS99nbUF1t7FXx"
```

---

### Task 7: Build the SFINCS model with HydroMT

**Files:**
- Create: `curonian/build_model.py`, `curonian/tests/test_build_model.py`

**Interfaces:**
- Consumes: `data_catalog.yml` sources, `inputs/*.csv`, `inputs/*.geojson`, `common.*`
- Produces: `build(run_dir=common.RUN_XAVER, subgrid=True) -> SfincsModel`; `check_model(run_dir) -> dict` with keys `n_active`, `n_bnd`, `connected`, `bnd_in_ring`; model files in `runs/xaver_2013/` including `subgrid/dep_subgrid.tif`.

- [ ] **Step 1: Write the failing test**

`curonian/tests/test_build_model.py`:
```python
import pytest

import common
import build_model as bm


@pytest.mark.integration
def test_built_model_passes_checks():
    run = common.RUN_XAVER
    if not (run / "sfincs.inp").exists():
        pytest.skip("run build_model.py first")
    r = bm.check_model(run)
    assert 200_000 <= r["n_active"] <= 400_000, r
    assert 20 <= r["n_bnd"] <= 200 and r["bnd_in_ring"], r
    assert r["connected"], "strait not connected to the lagoon"
    inp = (run / "sfincs.inp").read_text()
    for key in ("sbgfile", "bzsfile", "bndfile", "srcfile", "disfile", "wndfile", "obsfile"):
        assert key in inp, key
    assert "20131211 000000" in inp and "sfincs.sbg" in inp
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ~/SFINCS/curonian && micromamba run -n hydromt-sfincs python -m pytest tests/test_build_model.py -q`
Expected: FAIL with `ImportError: cannot import build_model`

- [ ] **Step 3: Write `build_model.py`**

```python
"""Assemble the Curonian Lagoon SFINCS model for Storm Xaver with HydroMT-SFINCS 1.2."""
from __future__ import annotations

import sys
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
from scipy import ndimage

import common

DATASETS_DEP = [
    {"elevtn": "lagoon_bathy_50m", "mask": "lagoon_boundary", "reproj_method": "bilinear"},
    {"elevtn": "dem_5m", "reproj_method": "bilinear"},
    {"elevtn": "emodnet_2022", "reproj_method": "bilinear"},
]
DATASETS_RIV = [{"centerlines": "channels", "rivwth": 200, "rivbed": -4.0, "segment_length": 250}]


def _read_ts(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, index_col=0, parse_dates=True)
    df.columns = [int(c) for c in df.columns]
    return df


def build(run_dir: Path = common.RUN_XAVER, subgrid: bool = True):
    from hydromt_sfincs import SfincsModel

    inputs = common.INPUTS
    sf = SfincsModel(root=str(run_dir), mode="w+", data_libs=[str(common.ROOT / "data_catalog.yml")], write_gis=False)
    sf.setup_grid(x0=common.X0, y0=common.Y0, dx=common.DX, dy=common.DY, nmax=common.NMAX, mmax=common.MMAX,
                  rotation=0, epsg=common.CRS)
    sf.setup_dep(datasets_dep=DATASETS_DEP)
    sf.setup_mask_active(mask="active_region", zmax=10.0, drop_area=0.5, fill_area=10.0, reset_mask=True)
    sf.setup_mask_bounds(btype="waterlevel", include_mask="boundary_ring", reset_bounds=True)
    if subgrid:
        sf.setup_subgrid(datasets_dep=DATASETS_DEP, datasets_riv=DATASETS_RIV, nr_subgrid_pixels=20, nlevels=10,
                         manning_land=0.06, manning_sea=0.02, rgh_lev_land=0.3, write_dep_tif=True)
    else:
        sf.setup_manning_roughness(manning_land=0.06, manning_sea=0.02, rgh_lev_land=0.3)

    sf.setup_config(
        tref=common.TREF.strftime("%Y%m%d %H%M%S"), tstart=common.TREF.strftime("%Y%m%d %H%M%S"),
        tstop=common.TSTOP.strftime("%Y%m%d %H%M%S"),
        advection=1, alpha=0.5, huthresh=0.05, viscosity=1,
        dtout=3600, dthisout=600, dtmaxout=99999999,
    )
    bzs = _read_ts(inputs / "bzs.csv")
    sf.setup_config(zsini=float(bzs.iloc[0].mean()))
    sf.setup_waterlevel_forcing(timeseries=bzs,
                                locations=gpd.read_file(inputs / "boundary_points.geojson").set_index("index", drop=False))
    sf.setup_discharge_forcing(timeseries=_read_ts(inputs / "dis.csv"),
                               locations=gpd.read_file(inputs / "dis_points.geojson").set_index("index", drop=False))
    sf.setup_wind_forcing(timeseries=str(inputs / "wind.csv"))
    sf.setup_observation_points(locations=gpd.read_file(inputs / "stations.geojson"))
    sf.write()
    print(check_model(run_dir))
    return sf


def check_model(run_dir: Path = common.RUN_XAVER) -> dict:
    from hydromt_sfincs import SfincsModel

    sf = SfincsModel(root=str(run_dir), mode="r")
    sf.read()
    msk = sf.grid["msk"].values
    active = msk > 0
    labels, _ = ndimage.label(active, structure=np.ones((3, 3)))
    x = sf.grid["msk"].raster.xcoords.values; y = sf.grid["msk"].raster.ycoords.values
    def label_at(px, py):
        return labels[int(np.argmin(abs(y - py))), int(np.argmin(abs(x - px)))]
    mx, my = common.lonlat_to_xy(*common.KLAIPEDA_MOUTH_LONLAT)
    connected = label_at(mx, my) == label_at(318_000, 6_130_000) != 0   # mouth vs open lagoon
    ring = gpd.read_file(common.INPUTS / "boundary_ring.geojson").geometry.iloc[0]
    rows, cols = np.where(msk == 2)
    bnd_in_ring = all(ring.buffer(150).contains(gpd.points_from_xy([x[c]], [y[r]])[0]) for r, c in zip(rows, cols))
    return {"n_active": int(active.sum()), "n_bnd": int((msk == 2).sum()), "connected": bool(connected),
            "bnd_in_ring": bool(bnd_in_ring)}


if __name__ == "__main__":
    build(subgrid="--no-subgrid" not in sys.argv)
```

Notes for the implementer:
- `DATASETS_RIV` passes `rivwth`/`rivbed` as fallbacks only; the per-feature values in `channels.geojson` take precedence.
- `dtmaxout=99999999` keeps a single `zsmax` over the whole run.
- If `setup_subgrid` fails on memory, lower `nrmax` to 1000. If it fails on the `mask` key, replace `"mask": "lagoon_boundary"` with `"gdf_valid": gpd.read_file(common.DB, layer="lagoon_boundary").to_crs(common.CRS)`.

- [ ] **Step 4: Build once without subgrid to validate masks and forcing quickly**

```bash
cd ~/SFINCS/curonian && micromamba run -n hydromt-sfincs python build_model.py --no-subgrid 2>&1 | tail -5
ls runs/xaver_2013
```
Expected: the check dict prints with `n_active` in 200–400 k, `n_bnd` 20–200, `connected: True`, `bnd_in_ring: True`, and the folder holds `sfincs.inp, sfincs.msk, sfincs.ind, sfincs.dep, sfincs.bnd, sfincs.bzs, sfincs.src, sfincs.dis, sfincs.wnd, sfincs.obs`. If `connected` is False, widen `strait_line.buffer` in `make_geometries.active_region` to 2500 m and rerun Task 3's script. If `n_active` is too high, lower `zmax` to 8.

- [ ] **Step 5: Full build with subgrid**

Run: `cd ~/SFINCS/curonian && micromamba run -n hydromt-sfincs python build_model.py 2>&1 | tail -5`
Expected: takes 10–40 minutes; `runs/xaver_2013/sfincs.sbg` and `runs/xaver_2013/subgrid/dep_subgrid.tif` exist; `sfincs.inp` contains `sbgfile = sfincs.sbg`.

- [ ] **Step 6: Run the test**

Run: `cd ~/SFINCS/curonian && micromamba run -n hydromt-sfincs python -m pytest tests/test_build_model.py -q`
Expected: `1 passed`

- [ ] **Step 7: Commit**

```bash
cd ~/SFINCS && git add curonian/build_model.py curonian/tests/test_build_model.py && git commit -m "curonian: hydromt build of the Xaver 2013 model

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01DifGpGPwDS99nbUF1t7FXx"
```

---

### Task 8: Dry run and full run

**Files:**
- Modify: `curonian/README.md` (add run timings)

**Interfaces:**
- Consumes: `runs/xaver_2013/`, `~/SFINCS/run_sfincs.sh`
- Produces: `runs/xaver_2013/sfincs_his.nc`, `sfincs_map.nc`, `sfincs_log.txt`

- [ ] **Step 1: One-day dry run**

```bash
cd ~/SFINCS/curonian/runs/xaver_2013 && cp sfincs.inp sfincs.inp.full
sed -i 's/^tstop .*/tstop                = 20131129 000000/' sfincs.inp
cd ~/SFINCS/curonian && ../run_sfincs.sh runs/xaver_2013 16 | tail -15
```
Expected: `Simulation finished`, no `Error`/`Warning` lines about missing files, average time step above 2 s, wall time under 10 minutes. If the time step collapses below 1 s, look for isolated deep cells in the log's max-velocity location and raise `z_minimum` in `setup_subgrid` to −20.

- [ ] **Step 2: Restore the full period and run**

```bash
cd ~/SFINCS/curonian/runs/xaver_2013 && mv sfincs.inp.full sfincs.inp
cd ~/SFINCS/curonian && ../run_sfincs.sh runs/xaver_2013 16 | tail -15
ls -la runs/xaver_2013/sfincs_his.nc runs/xaver_2013/sfincs_map.nc
```
Expected: `Simulation finished`; record wall time and mean time step in `README.md` under a "Run log" heading, e.g. `Xaver 2013 full run: 38 min on 16 threads, mean dt 5.1 s`.

- [ ] **Step 3: Quick look at the station output**

```bash
cd ~/SFINCS/curonian && micromamba run -n hydromt-sfincs python -c "
import netCDF4 as nc, numpy as np
d=nc.Dataset('runs/xaver_2013/sfincs_his.nc'); zs=d['point_zs'][:]; t=nc.num2date(d['time'][:], d['time'].units)
names=[''.join(c.decode() for c in r).strip() for r in d['station_name'][:]]
for i,n in enumerate(names): print(f'{n:14s} min {zs[:,i].min():6.2f} max {zs[:,i].max():6.2f} at {t[int(np.argmax(zs[:,i]))]}')"
```
Expected: every station varies (max − min > 0.2 m); Uostadvaris and Vente peak on 6 Dec, Nida later on 7–8 Dec. A flat station means it sits on an inactive cell: move it in `make_geometries.STATIONS_LONLAT` by a few hundred metres into water, rerun Task 3's script, `build_model.py`, and the run.

- [ ] **Step 4: Commit the README note**

```bash
cd ~/SFINCS && git add curonian/README.md && git commit -m "curonian: Xaver 2013 run log

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01DifGpGPwDS99nbUF1t7FXx"
```

---

### Task 9: Validation against the gauges and flood-extent map

**Files:**
- Create: `curonian/validate.py`, `curonian/tests/test_validate.py`

**Interfaces:**
- Consumes: `runs/xaver_2013/sfincs_his.nc`, `sfincs_map.nc`, `subgrid/dep_subgrid.tif`, `sfincs.obs`, `prep.make_forcing.load_gauge_levels`
- Produces: `load_his(run_dir) -> pd.DataFrame` (columns = station names from `sfincs.obs` order); `skill(model: pd.Series, obs: pd.Series) -> dict(bias, rmse, r, peak_err_m, peak_dt_h, n)`; `flood_map(run_dir, out_png, window=(325_000, 6_105_000, 360_000, 6_145_000)) -> float` (flooded km²); `main()` writes `runs/xaver_2013/validation.md`, `validation_timeseries.png`, `flood_extent_delta.png`.

- [ ] **Step 1: Write the failing test**

`curonian/tests/test_validate.py`:
```python
import numpy as np
import pandas as pd

import validate as va


def test_skill_on_synthetic_series():
    t = pd.date_range("2013-12-01", periods=240, freq="h")
    model = pd.Series(np.sin(np.arange(240) / 20), index=t)
    obs_t = t[6::12]                                    # 06:00 and 18:00 readings
    obs = pd.Series(np.sin(np.arange(240)[6::12] / 20) + 0.1, index=obs_t)
    s = va.skill(model, obs)
    assert abs(s["bias"] + 0.1) < 1e-9 and abs(s["rmse"] - 0.1) < 1e-9 and s["r"] > 0.999
    assert abs(s["peak_err_m"] + 0.1) < 0.02 and abs(s["peak_dt_h"]) <= 12 and s["n"] == len(obs)


def test_obs_order_parsing(tmp_path):
    (tmp_path / "sfincs.obs").write_text("1 2 Klaipeda\n3 4 'Nida'\n")
    assert va.station_names(tmp_path) == ["Klaipeda", "Nida"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ~/SFINCS/curonian && micromamba run -n hydromt-sfincs python -m pytest tests/test_validate.py -q`
Expected: FAIL with `ImportError`

- [ ] **Step 3: Write `validate.py`**

```python
"""Score the Xaver run against the gauges and draw the delta flood extent."""
from __future__ import annotations

from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import netCDF4 as nc
import numpy as np
import pandas as pd
import rasterio
from rasterio.windows import from_bounds

import common
from prep.make_forcing import load_gauge_levels

GAUGES = ("Klaipeda", "Nida", "Vente", "Uostadvaris")


def station_names(run_dir: Path) -> list[str]:
    """Station order of sfincs.obs; names from its third column, else from inputs/stations.geojson."""
    lines = [l.split() for l in (run_dir / "sfincs.obs").read_text().splitlines() if l.strip()]
    names = [l[2].strip("\"'") for l in lines if len(l) >= 3]
    if len(names) != len(lines):
        import geopandas as gpd
        names = list(gpd.read_file(common.INPUTS / "stations.geojson")["name"])
        assert len(names) == len(lines), "obs file and stations.geojson disagree on station count"
    return names


def load_his(run_dir: Path = common.RUN_XAVER) -> pd.DataFrame:
    with nc.Dataset(run_dir / "sfincs_his.nc") as d:
        t = pd.to_datetime([str(x) for x in nc.num2date(d["time"][:], d["time"].units, only_use_cftime_datetimes=False)])
        zs = np.ma.filled(d["point_zs"][:], np.nan)
    names = station_names(run_dir)
    assert zs.shape[1] == len(names), (zs.shape, names)
    return pd.DataFrame(zs, index=t, columns=names)


def skill(model: pd.Series, obs: pd.Series) -> dict:
    m = model.reindex(obs.index, method="nearest", tolerance=pd.Timedelta("30min"))
    ok = m.notna() & obs.notna()
    m, o = m[ok], obs[ok]
    err = m - o
    return {
        "bias": float(err.mean()), "rmse": float(np.sqrt((err ** 2).mean())),
        "r": float(np.corrcoef(m, o)[0, 1]) if len(o) > 2 else np.nan,
        "peak_err_m": float(model.loc[obs.index.min():obs.index.max()].max() - o.max()),
        "peak_dt_h": float((model.loc[obs.index.min():obs.index.max()].idxmax() - o.idxmax()) / pd.Timedelta("1h")),
        "n": int(ok.sum()),
    }


def flood_map(run_dir: Path = common.RUN_XAVER, out_png: Path | None = None,
              window=(325_000, 6_105_000, 360_000, 6_145_000)) -> float:
    with nc.Dataset(run_dir / "sfincs_map.nc") as d:
        zsmax = np.ma.filled(d["zsmax"][:], np.nan)
        zsmax = zsmax[-1] if zsmax.ndim == 3 else zsmax
        x = d["x"][:]; y = d["y"][:]
        x = x[0, :] if x.ndim == 2 else x; y = y[:, 0] if y.ndim == 2 else y
    dep_tif = run_dir / "subgrid" / "dep_subgrid.tif"
    if dep_tif.exists():
        with rasterio.open(dep_tif) as src:
            win = from_bounds(*window, transform=src.transform)
            ground = src.read(1, window=win, masked=True).filled(np.nan)
            tr = src.window_transform(win)
            gx = tr.c + tr.a * (np.arange(ground.shape[1]) + 0.5)
            gy = tr.f + tr.e * (np.arange(ground.shape[0]) + 0.5)
        ix = np.clip(np.searchsorted(x, gx) - 1, 0, len(x) - 1); iy = np.clip(np.searchsorted(y, gy) - 1, 0, len(y) - 1)
        zs_fine = zsmax[np.ix_(iy, ix)]
        depth = zs_fine - ground
        cell_km2 = abs(tr.a * tr.e) / 1e6
    else:
        sel_x = (x >= window[0]) & (x <= window[2]); sel_y = (y >= window[1]) & (y <= window[3])
        with nc.Dataset(run_dir / "sfincs_map.nc") as d:
            zb = np.ma.filled(d["zb"][:], np.nan)
        depth = (zsmax - zb)[np.ix_(sel_y, sel_x)]; gx, gy = x[sel_x], y[sel_y]
        ground = zb[np.ix_(sel_y, sel_x)]; cell_km2 = 0.01
    flooded = np.isfinite(depth) & (depth > 0.05) & (ground > 0.0)      # land only
    area_km2 = float(flooded.sum() * cell_km2)
    if out_png:
        fig, ax = plt.subplots(figsize=(9, 8))
        ax.imshow(np.where(ground > 0, ground, np.nan), extent=[gx[0], gx[-1], gy[-1], gy[0]], cmap="Greys_r", vmin=-2, vmax=8)
        im = ax.imshow(np.where(flooded, depth, np.nan), extent=[gx[0], gx[-1], gy[-1], gy[0]], cmap="Blues", vmin=0, vmax=2)
        fig.colorbar(im, ax=ax, label="max flood depth on land [m]")
        ax.set_title(f"Xaver 2013: flooded land in the delta window = {area_km2:.1f} km²")
        fig.savefig(out_png, dpi=150); plt.close(fig)
    return area_km2


def main(run_dir: Path = common.RUN_XAVER) -> None:
    his = load_his(run_dir)
    lines = ["# Xaver 2013 validation", "", "| station | n | bias m | RMSE m | r | peak err m | peak dt h |", "|---|---|---|---|---|---|---|"]
    fig, axes = plt.subplots(len(GAUGES), 1, figsize=(10, 3 * len(GAUGES)), sharex=True)
    for ax, g in zip(axes, GAUGES):
        obs = load_gauge_levels(g)
        s = skill(his[g], obs)
        lines.append(f"| {g} | {s['n']} | {s['bias']:+.2f} | {s['rmse']:.2f} | {s['r']:.2f} | {s['peak_err_m']:+.2f} | {s['peak_dt_h']:+.0f} |")
        ax.plot(his.index, his[g], label="SFINCS"); ax.plot(obs.index, obs.values, "o", ms=4, label="gauge (06/18 h)")
        ax.set_ylabel(f"{g} [m]"); ax.grid(alpha=0.3); ax.legend(loc="upper left")
    fig.autofmt_xdate(); fig.tight_layout(); fig.savefig(run_dir / "validation_timeseries.png", dpi=130); plt.close(fig)
    area = flood_map(run_dir, run_dir / "flood_extent_delta.png")
    lines += ["", f"Flooded land in the delta window (depth > 5 cm, ground > 0 m): **{area:.1f} km²**", "",
              "Targets: Uostadvaris peak within ±0.15 m and ±6 h; Nida 8 Dec rise within ±0.15 m; Klaipeda RMSE ≤ 0.15 m."]
    (run_dir / "validation.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run the unit tests**

Run: `cd ~/SFINCS/curonian && micromamba run -n hydromt-sfincs python -m pytest tests/test_validate.py -q`
Expected: `2 passed`

- [ ] **Step 5: Validate the real run**

Run: `cd ~/SFINCS/curonian && micromamba run -n hydromt-sfincs python validate.py`
Expected: a table for the four gauges and two PNGs in `runs/xaver_2013/`. Copy `validation.md` and both PNGs into `curonian/results/xaver_2013/` so they are committed:
```bash
mkdir -p ~/SFINCS/curonian/results/xaver_2013 && cp ~/SFINCS/curonian/runs/xaver_2013/{validation.md,validation_timeseries.png,flood_extent_delta.png} ~/SFINCS/curonian/results/xaver_2013/
```

- [ ] **Step 6: Commit**

```bash
cd ~/SFINCS && git add curonian/validate.py curonian/tests/test_validate.py curonian/results && git commit -m "curonian: validation against gauges and delta flood-extent map

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01DifGpGPwDS99nbUF1t7FXx"
```

---

### Task 10: Results write-up against the success criteria

**Files:**
- Modify: `curonian/README.md`

- [ ] **Step 1: Add a "Results: Xaver 2013" section to `curonian/README.md`**

Paste the validation table from `results/xaver_2013/validation.md`, then one line per success criterion from the spec (section 9) stating met / not met with the number, then a "Findings" list covering at least: the GTSM offset and its peak timing versus the Klaipėda 06:00 gauge, the Uostadvaris peak comparison, the Nida delayed rise, the flooded area in the delta window, and which of the flagged assumptions (gauge zero, Minija constant, channel dimensions, uniform wind) the results suggest revisiting first.

- [ ] **Step 2: Run the whole test suite**

Run: `cd ~/SFINCS/curonian && micromamba run -n hydromt-sfincs python -m pytest tests -q`
Expected: all tests pass (integration tests included, since all inputs now exist).

- [ ] **Step 3: Commit**

```bash
cd ~/SFINCS && git add curonian/README.md && git commit -m "curonian: Xaver 2013 results against the success criteria

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01DifGpGPwDS99nbUF1t7FXx"
```
