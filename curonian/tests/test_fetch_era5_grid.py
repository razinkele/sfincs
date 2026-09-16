import netCDF4 as nc
import numpy as np
import pandas as pd
import pytest
import xarray as xr

import common
from prep import fetch_era5_grid as feg

XAVER = common.EVENTS["xaver_2013"]


def _synthetic_raw(extra_hours=6):
    """Synthetic raw-CDS-shaped ERA5 dataset: dims (valid_time, latitude, longitude),
    latitude ascending, longitude ascending, an `expver` per-time coordinate (as real
    new-CDS single-levels downloads carry), values in the physically-valid range, and
    a time span padded past [TREF-1h, TSTOP+1h] on both ends so slicing has something
    to cut off."""
    t0 = common.TREF - pd.Timedelta(hours=1 + extra_hours)
    t1 = common.TSTOP + pd.Timedelta(hours=1 + extra_hours)
    times = pd.date_range(t0, t1, freq="h")
    lat = np.array([54.5, 55.0, 55.5])       # ascending -- to_hydromt must flip to descending
    lon = np.array([20.5, 21.0, 21.5])       # ascending already
    n = len(times)
    rng = np.random.default_rng(0)
    u10 = rng.normal(2.0, 1.0, size=(n, 3, 3)).astype("float32")
    v10 = rng.normal(2.0, 1.0, size=(n, 3, 3)).astype("float32")
    msl = (101_325 + rng.normal(0, 500, size=(n, 3, 3))).astype("float32")
    ds = xr.Dataset(
        {"u10": (("valid_time", "latitude", "longitude"), u10),
         "v10": (("valid_time", "latitude", "longitude"), v10),
         "msl": (("valid_time", "latitude", "longitude"), msl)},
        coords={"valid_time": times, "latitude": lat, "longitude": lon,
                "expver": ("valid_time", np.full(n, "0001"))},
    )
    ds["number"] = 0
    return ds


def test_to_hydromt_renames_orients_and_slices():
    ds = feg.to_hydromt(_synthetic_raw())
    assert set(ds.data_vars) == {"wind10_u", "wind10_v", "press_msl"}
    assert "expver" not in ds.variables and "number" not in ds.variables
    for v in ds.data_vars:
        assert ds[v].dims == ("time", "y", "x")
    y = ds["y"].values
    x = ds["x"].values
    assert list(y) == sorted(y, reverse=True), "y must be north-up (descending)"
    assert list(x) == sorted(x), "x must be ascending"
    # padded input hours outside [TREF-1h, TSTOP+1h] must be sliced away
    assert ds["time"].values.min() == np.datetime64(common.TREF - pd.Timedelta("1h"))
    assert ds["time"].values.max() == np.datetime64(common.TSTOP + pd.Timedelta("1h"))


def test_to_hydromt_raises_on_nan():
    ds = _synthetic_raw()
    ds["u10"][10, 0, 0] = np.nan
    with pytest.raises(AssertionError):
        feg.to_hydromt(ds)


def test_to_hydromt_raises_on_bad_pressure():
    ds = _synthetic_raw()
    ds["msl"][:, :, :] = 50_000.0   # far below the 90000-110000 Pa sanity range
    with pytest.raises(AssertionError):
        feg.to_hydromt(ds)


def test_to_hydromt_accepts_already_named_time_coordinate():
    """Older-style CDS files use `time` instead of `valid_time`; must pass through unrenamed."""
    ds = _synthetic_raw().rename({"valid_time": "time"})
    out = feg.to_hydromt(ds)
    assert "time" in out.coords


@pytest.mark.integration
def test_nida_check_near_zero_on_matching_point():
    """A synthetic grid built by embedding the real Nida ERA5 point series at the grid
    cell nearest (21.0, 55.25) must score ~0 RMSE against itself."""
    with nc.Dataset(common.ERA5_2013) as d:
        t = pd.to_datetime(d["valid_time"][:].astype("int64"), unit="s")
        u = d["u10"][:, 0, 0].astype(float)
        v = d["v10"][:, 0, 0].astype(float)
    t0, t1 = common.TREF - pd.Timedelta("1h"), common.TSTOP + pd.Timedelta("1h")
    mask = (t >= t0) & (t <= t1)
    t, u, v = t[mask], u[mask], v[mask]
    y = np.array([55.75, 55.25, 54.75])      # descending, as to_hydromt would produce
    x = np.array([20.5, 21.0, 21.5])
    n = len(t)
    wu = np.zeros((n, 3, 3), dtype="float64"); wu[:, 1, 1] = u
    wv = np.zeros((n, 3, 3), dtype="float64"); wv[:, 1, 1] = v
    msl = np.full((n, 3, 3), 101_325.0)
    ds = xr.Dataset(
        {"wind10_u": (("time", "y", "x"), wu), "wind10_v": (("time", "y", "x"), wv),
         "press_msl": (("time", "y", "x"), msl)},
        coords={"time": t, "y": y, "x": x},
    )
    rmse = feg.nida_check(ds)
    assert rmse < 0.01


@pytest.mark.integration
def test_real_era5_grid_covers_the_period():
    path = XAVER.inputs_dir / "era5_grid.nc"
    if not path.exists():
        pytest.skip("run prep.fetch_era5_grid first")
    with xr.open_dataset(path) as ds:
        t = pd.DatetimeIndex(ds["time"].values)
        assert t.min() <= common.TREF and t.max() >= common.TSTOP
        assert set(ds.data_vars) == {"wind10_u", "wind10_v", "press_msl"}
