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
