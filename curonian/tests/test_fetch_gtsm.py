import numpy as np
import pandas as pd
import pytest
import xarray as xr

import common
from prep import fetch_gtsm as fg

XAVER = common.EVENTS["xaver_2013"]


def test_gtsm_request_months_come_from_the_event():
    assert fg.request(common.event("xaver_2013"))["month"] == ["11", "12"]
    assert fg.request(common.event("april_2013"))["month"] == ["04", "05"]


def test_gtsm_downloads_into_the_event_directory():
    assert fg.target_for(common.event("april_2013")) == common.INPUTS / "april_2013" / "gtsm.zip"
    assert fg.target_for(common.event("xaver_2013")) == common.INPUTS / "xaver_2013" / "gtsm.zip"


def _fake_gtsm_file(path, lons, lats, start="2013-11-01", hours=48, offset=0.0):
    t = pd.date_range(start, periods=hours, freq="h")
    wl = np.zeros((hours, len(lons)), dtype="float32")
    wl[:, 0] = np.sin(np.arange(hours) / 6.0) + offset
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
    csv = XAVER.inputs_dir / "gtsm_klaipeda.csv"
    if not csv.exists():
        pytest.skip("run prep.fetch_gtsm first")
    s = pd.read_csv(csv, index_col=0, parse_dates=True)["waterlevel_m"]
    assert s.index.min() <= common.TREF and s.index.max() >= common.TSTOP
    assert (s.index.to_series().diff().dropna() == pd.Timedelta("1h")).all()
    assert s.loc["2013-12-05":"2013-12-08"].max() - s.loc["2013-11-28":"2013-12-03"].mean() > 0.3


def _fake_gtsm_file_stations_first(path, lons, lats, start="2013-11-01", hours=48, offset=0.0):
    """Same content as _fake_gtsm_file but stored (stations, time), the other dim order."""
    t = pd.date_range(start, periods=hours, freq="h")
    wl = np.zeros((len(lons), hours), dtype="float32")
    wl[0, :] = np.sin(np.arange(hours) / 6.0) + offset
    ds = xr.Dataset(
        {"waterlevel": (("stations", "time"), wl)},
        coords={"time": t, "stations": np.arange(len(lons)),
                "station_x_coordinate": ("stations", np.array(lons)),
                "station_y_coordinate": ("stations", np.array(lats))},
    )
    ds.to_netcdf(path)


def test_series_from_files_handles_stations_first_dim_order(tmp_path):
    """The (stations, time) branch of the dims ternary: same series, other layout."""
    p_time_first = tmp_path / "time_first.nc"
    p_stations_first = tmp_path / "stations_first.nc"
    _fake_gtsm_file(p_time_first, [21.05, 20.5], [55.72, 56.0], "2013-11-01")
    _fake_gtsm_file_stations_first(p_stations_first, [21.05, 20.5], [55.72, 56.0], "2013-11-01")

    s_time, _ = fg.series_from_files([p_time_first], lonlat=(21.09, 55.72))
    s_stations, _ = fg.series_from_files([p_stations_first], lonlat=(21.09, 55.72))
    pd.testing.assert_series_equal(s_time, s_stations)


def test_overlapping_files_keep_the_first_file_deterministically(tmp_path):
    """Monthly files overlap at the month boundary; dedup must be reproducible.

    sort_index() defaults to quicksort, which is not stable, so with a plain sort
    which of two equal timestamps survives ~duplicated() is an implementation
    detail of numpy's partitioning rather than a property of the data.
    """
    p1 = tmp_path / "a_2013_11.nc"; p2 = tmp_path / "b_2013_12.nc"
    _fake_gtsm_file(p1, [21.05, 20.5], [55.72, 56.0], "2013-11-01", hours=48)
    _fake_gtsm_file(p2, [21.05, 20.5], [55.72, 56.0], "2013-11-02", hours=48, offset=10.0)

    series, _ = fg.series_from_files([p1, p2], lonlat=(21.09, 55.72))
    overlap = pd.Timestamp("2013-11-02 05:00")                 # present in both files
    assert series.loc[overlap] < 5.0, "the first file's value must win the tie"
    assert series.index.is_monotonic_increasing and series.index.is_unique


def test_series_from_files_raises_on_a_gappy_series(tmp_path):
    """A gap in the GTSM series becomes a gap in the sea boundary; `python -O` would
    strip the bare assert that used to catch it."""
    p = tmp_path / "gappy_2013_11.nc"
    _fake_gtsm_file(p, [21.05, 20.5], [55.72, 56.0], "2013-11-01", hours=24)
    p2 = tmp_path / "gappy_2013_12.nc"
    _fake_gtsm_file(p2, [21.05, 20.5], [55.72, 56.0], "2013-11-05", hours=24)   # 3-day hole
    with pytest.raises(ValueError, match="gap"):
        fg.series_from_files([p, p2], lonlat=(21.09, 55.72))
