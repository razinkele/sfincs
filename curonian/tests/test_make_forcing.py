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
