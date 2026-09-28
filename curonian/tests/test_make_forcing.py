import numpy as np
import pandas as pd
import pytest

import common
from prep import make_forcing as mf

APRIL = common.event("april_2013")
XAVER = common.event("xaver_2013")


def _drifting(hours: pd.DatetimeIndex, drift_m: float = 0.15, days: float = 9.0) -> pd.Series:
    """A slow sinusoidal drift, like GTSM's multi-day level error at Klaipeda."""
    x = (hours - hours[0]) / pd.Timedelta("1D")
    return pd.Series(drift_m * np.sin(2 * np.pi * np.asarray(x) / days), index=hours)


def test_daily_fit_recovers_a_slow_drift_from_06_00_samples():
    """GTSM + slow drift, sampled once a day at 06:00, must give back the truth
    between samples to within the linear-interpolation error of the drift."""
    t = pd.date_range("2013-11-20", "2013-12-20", freq="h")
    truth = pd.Series(0.3 * np.sin(np.arange(len(t)) / 6.0), index=t)        # fast signal GTSM gets right
    model = truth - _drifting(t) - 0.20                                         # GTSM: drift + datum offset
    obs06 = truth[truth.index.hour == 6]
    fitted, info = mf.daily_fit_correction(model, obs06, t)
    err = (fitted - truth).loc[obs06.index[0]:obs06.index[-1]]   # between readings; ends are held flat
    assert err.abs().max() < 0.012                     # linear-interp error of the drift; 0.35 m uncorrected
    assert (fitted - truth)[obs06.index].abs().max() < 1e-9      # exact at the readings
    assert info["max_gap_h"] == 24.0
    assert info["resid_min"] < info["resid_max"]


def test_daily_fit_holds_the_end_residuals_flat():
    t = pd.date_range("2013-11-30", "2013-12-04", freq="h")
    model = pd.Series(0.0, index=t)
    obs06 = pd.Series([0.1, 0.3], index=pd.to_datetime(["2013-12-01 06:00", "2013-12-03 06:00"]))
    fitted, _ = mf.daily_fit_correction(model, obs06, t)
    assert fitted.iloc[0] == pytest.approx(0.1) and fitted.iloc[-1] == pytest.approx(0.3)
    assert fitted.loc["2013-12-02 06:00"] == pytest.approx(0.2)


def test_daily_fit_refuses_to_bridge_a_long_gap_inside_the_run():
    t = pd.date_range("2013-11-28", "2013-12-11", freq="h")
    model = pd.Series(0.0, index=t)
    days = pd.to_datetime(["2013-11-28 06:00", "2013-11-29 06:00"]).append(
        pd.date_range("2013-12-04 06:00", "2013-12-11 06:00", freq="D"))    # 29 Nov -> 4 Dec: 5 days
    with pytest.raises(ValueError, match="gap of 5 days"):
        mf.daily_fit_correction(model, pd.Series(0.1, index=days), t)


def test_daily_fit_ignores_readings_the_model_does_not_cover():
    t = pd.date_range("2013-11-28", "2013-12-11", freq="h")
    model = pd.Series(0.0, index=t)
    obs06 = pd.Series(0.1, index=pd.date_range("2013-11-20 06:00", "2013-12-20 06:00", freq="D"))
    fitted, info = mf.daily_fit_correction(model, obs06, t)
    assert fitted.notna().all() and np.allclose(fitted, 0.1) and info["n_readings"] == 13


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
    assert 300 < q[1].loc["2013-12-01":"2013-12-05"].mean() < 550
    assert 20 < q[2].min() and q[2].max() < 200          # measured Minija, m3/s


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
    assert 1800 < q[1].loc["2013-04-19":"2013-04-21"].max() < 2000      # the crest, 0.896 x 2150
    # measured Minija: ~14-20 m3/s before the freshet, peaking ~144 on 14 Apr
    assert q[2].loc["2013-04-05":"2013-04-10"].max() < 25
    assert 130 < q[2].loc["2013-04-13":"2013-04-16"].max() < 160


@pytest.mark.integration
def test_april_gauge_levels_reach_the_observed_crest():
    obs = mf.load_gauge_levels("Uostadvaris", APRIL)
    assert abs(obs.loc["2013-04-24 06:00"] - 0.54) < 1e-9


def test_daily_fit_refuses_a_run_end_far_from_any_reading():
    t = pd.date_range("2013-11-28", "2013-12-11", freq="h")
    model = pd.Series(0.0, index=t)
    days = pd.date_range("2013-11-28 06:00", "2013-12-05 06:00", freq="D")   # stops 6 days short
    with pytest.raises(ValueError, match="after the last reading"):
        mf.daily_fit_correction(model, pd.Series(0.1, index=days), t)
