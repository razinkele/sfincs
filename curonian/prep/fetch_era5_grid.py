"""Gridded hourly ERA5 wind and mean sea level pressure over the Curonian Lagoon
domain, for the gridded-wind/pressure sensitivity runs (CDS).

Dataset: reanalysis-era5-single-levels. Unlike the single-point series used for the
baseline run's uniform wind (`common.ERA5_2013`), this fetches the whole 0.25 deg
box around the lagoon so `setup_wind_forcing_from_grid`/`setup_pressure_forcing_from_grid`
can resolve spatial structure in the storm.
"""
from __future__ import annotations

from pathlib import Path

import hydromt  # noqa: F401  -- registers the .raster accessor on xr.Dataset/DataArray
import netCDF4 as nc
import numpy as np
import pandas as pd
import xarray as xr

import common

DATASET = "reanalysis-era5-single-levels"
REQUEST = {
    "product_type": ["reanalysis"],
    "variable": ["10m_u_component_of_wind", "10m_v_component_of_wind", "mean_sea_level_pressure"],
    "year": ["2013"],
    "month": ["11", "12"],
    "day": [f"{d:02d}" for d in range(1, 32)],
    "time": [f"{h:02d}:00" for h in range(24)],
    "area": [56.0, 20.25, 54.75, 22.0],   # N, W, S, E
    "data_format": "netcdf",
    "download_format": "unarchived",
}

NIDA_LONLAT = (21.0, 55.25)   # ERA5 grid node used for the baseline uniform-wind point series


def download(target: Path = common.INPUTS / "era5_raw_2013_11_12.nc") -> Path:
    import cdsapi
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists() and target.stat().st_size > 1_000_000:
        print(f"using cached {target}")
        return target
    try:
        cdsapi.Client().retrieve(DATASET, REQUEST, str(target))
    except Exception as exc:
        print(f"CDS request failed for {DATASET} with form keys {sorted(REQUEST)}: {exc}")
        raise
    return target


def to_hydromt(ds: xr.Dataset) -> xr.Dataset:
    """Reshape a raw CDS reanalysis-era5-single-levels download into the layout
    `setup_wind_forcing_from_grid`/`setup_pressure_forcing_from_grid` expect:
    variables wind10_u, wind10_v, press_msl on coords time, y (descending), x
    (ascending), sliced to the model period with a 1 h pad on each side."""
    rename = {}
    if "u10" in ds.variables:
        rename["u10"] = "wind10_u"
    if "v10" in ds.variables:
        rename["v10"] = "wind10_v"
    if "msl" in ds.variables:
        rename["msl"] = "press_msl"
    if "valid_time" in ds.variables:
        rename["valid_time"] = "time"
    if "latitude" in ds.variables:
        rename["latitude"] = "y"
    if "longitude" in ds.variables:
        rename["longitude"] = "x"
    ds = ds.rename(rename)

    drop = [v for v in ("number", "expver") if v in ds.variables]
    if drop:
        ds = ds.drop_vars(drop)

    ds = ds.sortby("y", ascending=False).sortby("x")

    t0 = common.TREF - pd.Timedelta("1h")
    t1 = common.TSTOP + pd.Timedelta("1h")
    ds = ds.sel(time=slice(t0, t1))
    ds = ds.transpose("time", "y", "x")

    times = pd.DatetimeIndex(ds["time"].values)
    assert times.is_monotonic_increasing, "ERA5 time axis is not sorted"
    assert (times.to_series().diff().dropna() == pd.Timedelta("1h")).all(), "gaps in ERA5 hourly time axis"

    for var in ("wind10_u", "wind10_v", "press_msl"):
        assert not bool(np.isnan(ds[var].values).any()), f"NaN in {var}"

    assert bool((ds["press_msl"].values >= 90_000).all()) and bool((ds["press_msl"].values <= 110_000).all()), \
        "press_msl outside the 90000-110000 Pa sanity range"
    speed = np.hypot(ds["wind10_u"].values, ds["wind10_v"].values)
    assert bool((speed < 45).all()), "wind speed >= 45 m/s -- implausible for this domain/period"

    ds = ds[["wind10_u", "wind10_v", "press_msl"]]
    ds.raster.set_crs(4326)
    return ds


def nida_check(ds: xr.Dataset) -> float:
    """RMSE (m/s) of 10 m wind speed between the grid cell nearest the Nida ERA5 node
    (21.0E, 55.25N) and the existing point file (`common.ERA5_2013`), over the period
    common to both. Both are ERA5 and that point is itself an ERA5 grid node, so this
    should come out well below 0.5 m/s; it is a sanity check on grid orientation and
    time alignment in `to_hydromt`, not a physical comparison."""
    lon, lat = NIDA_LONLAT
    yi = int(np.argmin(np.abs(ds["y"].values - lat)))
    xi = int(np.argmin(np.abs(ds["x"].values - lon)))
    grid_u = ds["wind10_u"].isel(y=yi, x=xi).values
    grid_v = ds["wind10_v"].isel(y=yi, x=xi).values
    grid_speed = pd.Series(np.hypot(grid_u, grid_v), index=pd.DatetimeIndex(ds["time"].values))

    with nc.Dataset(common.ERA5_2013) as d:
        t = pd.to_datetime(d["valid_time"][:].astype("int64"), unit="s")
        u = d["u10"][:, 0, 0].astype(float)
        v = d["v10"][:, 0, 0].astype(float)
    point_speed = pd.Series(np.hypot(u, v), index=t)

    both = pd.concat([grid_speed.rename("grid"), point_speed.rename("point")], axis=1, join="inner")
    assert len(both) > 0, "no overlapping timestamps between the gridded and point ERA5 series"
    rmse = float(np.sqrt(((both["grid"] - both["point"]) ** 2).mean()))
    assert rmse < 0.5, f"Nida-point wind speed RMSE {rmse:.3f} m/s exceeds 0.5 m/s"
    return rmse


def _peak_and_location(da: xr.DataArray) -> tuple[float, pd.Timestamp, float, float]:
    vals = da.values
    idx = np.unravel_index(np.nanargmax(vals), vals.shape)
    time = pd.Timestamp(da["time"].values[idx[0]])
    y = float(da["y"].values[idx[1]])
    x = float(da["x"].values[idx[2]])
    return float(vals[idx]), time, y, x


def main() -> xr.Dataset:
    raw = download()
    with xr.open_dataset(raw) as raw_ds:
        ds = to_hydromt(raw_ds.load())

    out = common.INPUTS / "era5_grid_xaver.nc"
    ds.to_netcdf(out, encoding={"time": {"units": "hours since 1970-01-01"}})

    rmse = nida_check(ds)

    speed = np.hypot(ds["wind10_u"], ds["wind10_v"])
    speed.name = "speed"
    peak, peak_time, peak_y, peak_x = _peak_and_location(speed)

    press = ds["press_msl"]
    mean_press = float(press.mean())
    min_press = float(press.min())
    min_idx = np.unravel_index(np.nanargmin(press.values), press.values.shape)
    min_press_time = pd.Timestamp(ds["time"].values[min_idx[0]])

    ny, nx, nt = ds.sizes["y"], ds.sizes["x"], ds.sizes["time"]
    dy = float(abs(ds["y"].values[1] - ds["y"].values[0]))
    dx = float(abs(ds["x"].values[1] - ds["x"].values[0]))
    t0 = pd.Timestamp(ds["time"].values.min())
    t1 = pd.Timestamp(ds["time"].values.max())

    summary = (
        f"grid: {nt} time steps x {ny} y x {nx} x, resolution {dy:.2f} x {dx:.2f} deg\n"
        f"period: {t0} to {t1}\n"
        f"Nida-point wind speed RMSE: {rmse:.3f} m/s\n"
        f"peak wind speed: {peak:.1f} m/s at {peak_time} ({peak_y:.2f}N, {peak_x:.2f}E)\n"
        f"mean sea level pressure: {mean_press:.0f} Pa\n"
        f"pressure minimum: {min_press:.0f} Pa at {min_press_time}\n"
    )
    (common.INPUTS / "era5_grid_summary.txt").write_text(summary)
    print(summary)
    return ds


if __name__ == "__main__":
    main()
