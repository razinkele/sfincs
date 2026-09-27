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
