import numpy as np
import pandas as pd
import pytest

import common
from prep import make_forcing as mf

APRIL = common.event("april_2013")
XAVER = common.event("xaver_2013")


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
    df = mf.boundary_forcing(gtsm, npoints=7, event=XAVER)
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
    obs = mf.load_gauge_levels("Uostadvaris", XAVER)
    assert abs(obs.loc["2013-12-06 06:00"] - 0.92) < 1e-9
    q = mf.discharge_forcing(XAVER)
    assert q.index[0] == common.TREF and q.index[-1] == common.TSTOP
    assert 350 < q[1].loc["2013-12-01":"2013-12-05"].mean() < 600 and (q[2] == common.MINIJA_Q_DEC).all()


def test_bias_correct_ignores_observations_outside_the_calm_window():
    """The offset must come from the calm window only.

    The existing test puts every observation inside the window, so the `obs.loc[
    window]` clip never does anything. Here the out-of-window readings are wildly
    off: if they leaked into the mean, the offset would move by ~5 m.
    """
    t = pd.date_range("2013-11-27", "2013-12-10", freq="h")
    model = pd.Series(0.5, index=t)
    inside = pd.Series(0.05, index=pd.date_range("2013-11-28 06:00", "2013-12-03 06:00", freq="D"))
    outside = pd.Series(10.0, index=pd.date_range("2013-12-06 06:00", "2013-12-09 06:00", freq="D"))
    obs = pd.concat([inside, outside]).sort_index()

    corrected, offset = mf.bias_correct(model, obs, common.CALM_WINDOW)
    assert abs(offset - (0.05 - 0.5)) < 1e-9
    assert abs(corrected.iloc[0] - 0.05) < 1e-9


def test_boundary_forcing_raises_when_the_period_cannot_be_filled():
    """Runtime validation must survive `python -O`, which strips bare asserts.

    A sea boundary quietly full of NaN is the worst possible silent failure here:
    SFINCS would be handed a boundary it cannot integrate.
    """
    outside = pd.date_range("2014-06-01", periods=48, freq="h")      # nowhere near the run period
    with pytest.raises(ValueError, match="boundary"):
        mf.boundary_forcing(pd.Series(np.nan, index=outside), npoints=7, event=XAVER)


@pytest.mark.parametrize("ev", [XAVER, APRIL], ids=lambda e: e.name)
def test_boundary_forcing_spans_whichever_event_it_is_given(ev):
    t = pd.date_range(ev.tref - pd.Timedelta("1D"), ev.tstop + pd.Timedelta("1D"), freq="h")
    gtsm = pd.Series(np.linspace(0, 1, len(t)), index=t)
    df = mf.boundary_forcing(gtsm, npoints=7, event=ev)
    assert df.index[0] == ev.tref and df.index[-1] == ev.tstop
    assert df.notna().all().all()


def test_wind_check_none_skips_the_peak_assertion_but_not_the_span_guard():
    """April has no gale to assert -- but an empty slice must still fail loudly."""
    t = pd.date_range(APRIL.tref - pd.Timedelta("1h"), APRIL.tstop + pd.Timedelta("1h"), freq="h")
    calm = pd.DataFrame({"mag": 5.0, "dir": 180.0}, index=t)
    mf.check_wind(calm, APRIL)                      # no raise: wind_check is None

    with pytest.raises(ValueError, match="does not cover"):
        mf.check_wind(calm.iloc[:10], APRIL)        # truncated -> raises anyway


def test_wind_check_still_demands_the_gale_for_xaver():
    t = pd.date_range(XAVER.tref - pd.Timedelta("1h"), XAVER.tstop + pd.Timedelta("1h"), freq="h")
    calm = pd.DataFrame({"mag": 5.0, "dir": 180.0}, index=t)
    with pytest.raises(ValueError, match="Xaver gale"):
        mf.check_wind(calm, XAVER)


@pytest.mark.integration
def test_april_discharge_carries_the_freshet_and_its_own_minija():
    q = mf.discharge_forcing(APRIL)
    assert q.index[0] == APRIL.tref and q.index[-1] == APRIL.tstop
    assert 2000 < q[1].loc["2013-04-19":"2013-04-21"].max() < 2300      # the crest
    assert (q[2] == common.MINIJA_Q_APR).all()


@pytest.mark.integration
def test_april_gauge_levels_reach_the_observed_crest():
    obs = mf.load_gauge_levels("Uostadvaris", APRIL)
    assert abs(obs.loc["2013-04-24 06:00"] - 0.54) < 1e-9
