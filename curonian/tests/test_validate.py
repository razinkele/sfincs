import numpy as np
import pandas as pd
import pytest

import common
import validate as va
from prep import make_forcing as mf

APRIL = common.event("april_2013")


def test_parse_args_default_run_name():
    args = va.parse_args([])
    assert args.run == "xaver_2013"


def test_parse_args_custom_run_name():
    args = va.parse_args(["--run", "xaver_2013_gridwind"])
    assert args.run == "xaver_2013_gridwind"


def test_event_and_run_compose_in_validate():
    assert va.parse_args([]).run == "xaver_2013"
    assert va.parse_args(["--event", "april_2013"]).run == "april_2013"
    assert va.parse_args(["--event", "april_2013", "--run", "april_2013_test"]).run == "april_2013_test"


def test_skill_on_synthetic_series():
    t = pd.date_range("2013-12-01", periods=240, freq="h")
    model = pd.Series(np.exp(-((np.arange(240) - 100) / 30.0) ** 2), index=t)   # a single, isolated peak
    obs = model.iloc[6::12] + 0.1                       # 06:00 and 18:00 readings
    s = va.skill(model, obs)
    assert abs(s["bias"] + 0.1) < 1e-9 and abs(s["rmse"] - 0.1) < 1e-9 and s["r"] > 0.999
    assert abs(s["peak_err_m"] + 0.1) < 0.02 and abs(s["peak_dt_h"]) <= 12 and s["n"] == len(obs)


def test_skill_tie_break_is_plateau_centre_independent_of_obs():
    t = pd.date_range("2020-01-01", periods=20, freq="h")
    vals = np.zeros(20)
    vals[8:12] = 1.0                                     # flat 4-point plateau at the max; centre = t[9]
    model = pd.Series(vals, index=t)
    # obs spans the whole series (so the model search window still includes the plateau), but
    # its own maximum reading sits either well before or well after the plateau. Each also
    # samples one point inside the plateau (below 0.9, so it never becomes the obs peak) purely
    # so model values at the obs times aren't all identical -- avoids a degenerate corrcoef.
    obs_before = pd.Series([0.0, 0.9, 0.5, 0.0], index=[t[0], t[2], t[9], t[19]])
    obs_after = pd.Series([0.0, 0.5, 0.9, 0.0], index=[t[0], t[9], t[16], t[19]])
    s_before = va.skill(model, obs_before)
    s_after = va.skill(model, obs_after)
    assert s_before["peak_time"] == t[9] and s_after["peak_time"] == t[9]
    dt_diff = s_before["peak_dt_h"] - s_after["peak_dt_h"]
    expected = (obs_after.idxmax() - obs_before.idxmax()) / pd.Timedelta("1h")
    assert abs(dt_diff - expected) < 1e-9


def test_flood_map_south_up_raster(tmp_path):
    import netCDF4 as nc
    import rasterio

    subgrid_dir = tmp_path / "subgrid"
    subgrid_dir.mkdir()
    ground = np.full((40, 40), -1.0, dtype="float32")
    ground[:, :20] = 1.0                                 # west half is +1 m land, east half is -1 m
    transform = rasterio.Affine(5.0, 0.0, 0.0, 0.0, 5.0, 0.0)   # south-up: positive e (row 0 = south edge)
    with rasterio.open(subgrid_dir / "dep_subgrid.tif", "w", driver="GTiff", height=40, width=40,
                        count=1, dtype="float32", crs="EPSG:3346", transform=transform) as dst:
        dst.write(ground, 1)

    with nc.Dataset(tmp_path / "sfincs_map.nc", "w") as d:
        d.createDimension("n", 2); d.createDimension("m", 2); d.createDimension("timemax", 1)
        x = d.createVariable("x", "f4", ("n", "m")); y = d.createVariable("y", "f4", ("n", "m"))
        zb = d.createVariable("zb", "f4", ("n", "m")); zsmax = d.createVariable("zsmax", "f4", ("timemax", "n", "m"))
        x[:] = [[50.0, 150.0], [50.0, 150.0]]
        y[:] = [[50.0, 50.0], [150.0, 150.0]]             # ascending with row index
        zb[:] = 0.0
        zsmax[:] = 1.5

    area = va.flood_map(tmp_path, tmp_path / "map.png", window=(0, 0, 200, 200))
    expected = (100.0 * 200.0) / 1e6                     # west-half land area, in km^2
    assert abs(area - expected) / expected < 0.01
    assert (tmp_path / "map.png").exists()


def test_obs_order_parsing(tmp_path):
    (tmp_path / "sfincs.obs").write_text("1 2 Klaipeda\n3 4 'Nida'\n")
    assert va.station_names(tmp_path) == ["Klaipeda", "Nida"]


# ---------------------------------------------------------------------------
# criteria() -- spec section 9 success criteria on synthetic data
# ---------------------------------------------------------------------------

@pytest.fixture
def synth_run_dir(tmp_path):
    """A run_dir with a tiny, all-land, never-flooded subgrid + map.nc so criteria()'s
    C4 uplands check (which every criteria() call computes) always comes back "met" and
    stays out of the way of the C1-C3 assertions under test."""
    import netCDF4 as nc
    import rasterio

    subgrid_dir = tmp_path / "subgrid"
    subgrid_dir.mkdir()
    ground = np.full((40, 40), 5.0, dtype="float32")             # all land, above the C4 3 m cutoff
    transform = rasterio.Affine(5.0, 0.0, 0.0, 0.0, -5.0, 200.0)   # north-up (negative e)
    with rasterio.open(subgrid_dir / "dep_subgrid.tif", "w", driver="GTiff", height=40, width=40,
                        count=1, dtype="float32", crs="EPSG:3346", transform=transform) as dst:
        dst.write(ground, 1)

    with nc.Dataset(tmp_path / "sfincs_map.nc", "w") as d:
        d.createDimension("n", 2); d.createDimension("m", 2); d.createDimension("timemax", 1)
        x = d.createVariable("x", "f4", ("n", "m")); y = d.createVariable("y", "f4", ("n", "m"))
        zb = d.createVariable("zb", "f4", ("n", "m")); zsmax = d.createVariable("zsmax", "f4", ("timemax", "n", "m"))
        x[:] = [[50.0, 150.0], [50.0, 150.0]]
        y[:] = [[50.0, 50.0], [150.0, 150.0]]
        zb[:] = 0.0
        zsmax[:] = 5.0                                            # equals ground: nothing floods
    return tmp_path


SYNTH_WINDOW = (0, 0, 200, 200)   # matches synth_run_dir's tiny raster, not the real project CRS extent


def _base_his():
    # A small wobble, not a flat constant: skill()'s corrcoef is NaN (0/0) for two
    # constant vectors, which would print a numpy RuntimeWarning for whichever
    # criterion a given test *isn't* targeting (criteria() always computes all of them).
    idx = pd.date_range("2013-12-05", "2013-12-09", freq="h")
    wobble = 0.5 + 0.01 * np.sin(np.arange(len(idx)) / 6.0)
    return pd.DataFrame({"Uostadvaris": pd.Series(wobble, index=idx),
                          "Nida": pd.Series(wobble, index=idx),
                          "Klaipeda": pd.Series(wobble, index=idx)}, index=idx)


def _base_obs():
    """Non-degenerate obs for every gauge (wobble, not a constant -- see _base_his;
    also not empty, so the storm-window slice used for C1/C3 and the always-computed
    8 Dec 06:00 info lines never hit an empty-index edge case) for whichever criterion
    a given test isn't targeting."""
    idx = pd.date_range("2013-12-05 06:00", "2013-12-09 06:00", freq="12h")   # 06:00/18:00 marks
    wobble = 0.5 + 0.01 * np.cos(np.arange(len(idx)) / 3.0)
    base = pd.Series(wobble, index=idx)
    return {"Uostadvaris": base.copy(), "Nida": base.copy(), "Klaipeda": base.copy()}


def _verdict(crit, prefix):
    return next(c for c in crit if c["name"].startswith(prefix))["verdict"]


def test_criteria_c1_uostadvaris_met(synth_run_dir):
    his = _base_his()
    his.loc["2013-12-06 06:00", "Uostadvaris"] = 1.00        # peak err +0.08 m, dt 0 h
    obs = _base_obs()
    obs["Uostadvaris"].loc[pd.Timestamp("2013-12-06 06:00")] = 0.92
    crit = va.criteria(his, obs, synth_run_dir, window=SYNTH_WINDOW)
    assert _verdict(crit, "C1") == "met"


def test_criteria_c1_uostadvaris_not_met(synth_run_dir):
    his = _base_his()
    his.loc["2013-12-06 06:00", "Uostadvaris"] = 2.00         # peak err +1.08 m: far outside +/-0.15
    obs = _base_obs()
    obs["Uostadvaris"].loc[pd.Timestamp("2013-12-06 06:00")] = 0.92
    crit = va.criteria(his, obs, synth_run_dir, window=SYNTH_WINDOW)
    assert _verdict(crit, "C1") == "not met"


def test_criteria_c2_nida_met(synth_run_dir):
    his = _base_his()
    his.loc["2013-12-07 06:00", "Nida"] = 0.40
    his.loc["2013-12-08 18:00", "Nida"] = 0.80                # rise reproduced, err = -0.04 m
    crit = va.criteria(his, _base_obs(), synth_run_dir, window=SYNTH_WINDOW)
    assert _verdict(crit, "C2") == "met"


def test_criteria_c2_nida_marginal(synth_run_dir):
    his = _base_his()
    his.loc["2013-12-07 06:00", "Nida"] = 0.40
    his.loc["2013-12-08 18:00", "Nida"] = 0.70                # rise reproduced, err = -0.14 m (>0.10)
    crit = va.criteria(his, _base_obs(), synth_run_dir, window=SYNTH_WINDOW)
    assert _verdict(crit, "C2") == "met (marginal)"


def test_criteria_c2_nida_not_met_no_rise(synth_run_dir):
    his = _base_his()
    his.loc["2013-12-07 06:00", "Nida"] = 0.80
    his.loc["2013-12-08 18:00", "Nida"] = 0.40                # falls instead of rising
    crit = va.criteria(his, _base_obs(), synth_run_dir, window=SYNTH_WINDOW)
    assert _verdict(crit, "C2") == "not met"


def test_criteria_c3_klaipeda_met(synth_run_dir):
    his = _base_his()
    times = [pd.Timestamp(t) for t in
              ("2013-12-05 06:00", "2013-12-06 06:00", "2013-12-07 06:00", "2013-12-08 06:00")]
    model_vals = [0.40, 0.60, 0.55, 0.50]
    for t, v in zip(times, model_vals):
        his.loc[t, "Klaipeda"] = v
    obs = _base_obs()
    obs["Klaipeda"] = pd.Series([v + 0.05 for v in model_vals], index=times)   # constant +0.05 m bias
    crit = va.criteria(his, obs, synth_run_dir, window=SYNTH_WINDOW)
    assert _verdict(crit, "C3") == "met"


def test_criteria_c3_klaipeda_not_met(synth_run_dir):
    his = _base_his()
    times = [pd.Timestamp(t) for t in
              ("2013-12-05 06:00", "2013-12-06 06:00", "2013-12-07 06:00", "2013-12-08 06:00")]
    model_vals = [0.40, 0.60, 0.55, 0.50]
    for t, v in zip(times, model_vals):
        his.loc[t, "Klaipeda"] = v
    obs = _base_obs()
    obs["Klaipeda"] = pd.Series([v + 0.30 for v in model_vals], index=times)   # constant +0.30 m bias
    crit = va.criteria(his, obs, synth_run_dir, window=SYNTH_WINDOW)
    assert _verdict(crit, "C3") == "not met"


def _write_south_up_run(tmp_path, north_is_land=True):
    """A run dir whose dep_subgrid.tif is south-up and varies by ROW, not column."""
    import netCDF4 as nc
    import rasterio

    subgrid_dir = tmp_path / "subgrid"
    subgrid_dir.mkdir()
    ground = np.full((40, 40), -1.0, dtype="float32")
    # South-up storage: row 0 is the SOUTH edge, row 39 the north. Put land in the north.
    ground[20:, :] = 1.0 if north_is_land else -1.0
    if not north_is_land:
        ground[:20, :] = 1.0
    transform = rasterio.Affine(5.0, 0.0, 0.0, 0.0, 5.0, 0.0)      # e > 0 => south-up
    with rasterio.open(subgrid_dir / "dep_subgrid.tif", "w", driver="GTiff", height=40, width=40,
                        count=1, dtype="float32", crs="EPSG:3346", transform=transform) as dst:
        dst.write(ground, 1)

    with nc.Dataset(tmp_path / "sfincs_map.nc", "w") as d:
        d.createDimension("n", 2); d.createDimension("m", 2); d.createDimension("timemax", 1)
        x = d.createVariable("x", "f4", ("n", "m")); y = d.createVariable("y", "f4", ("n", "m"))
        zb = d.createVariable("zb", "f4", ("n", "m")); zsmax = d.createVariable("zsmax", "f4", ("timemax", "n", "m"))
        x[:] = [[50.0, 150.0], [50.0, 150.0]]
        y[:] = [[50.0, 50.0], [150.0, 150.0]]
        zb[:] = 0.0
        zsmax[:] = 1.5
    return tmp_path


def test_flood_arrays_returns_north_up_rows_from_a_south_up_raster(tmp_path):
    """Catches a row flip, which flood_map()'s area total cannot see.

    The old south-up test varied ground by column only, so reversing the rows left
    the flooded area identical and the assertion passed either way. Assert the
    orientation itself: gy must descend and row 0 must be the northern land strip.
    """
    run = _write_south_up_run(tmp_path, north_is_land=True)
    ground, flooded, depth, gx, gy, cell_km2 = va._flood_arrays(run, window=(0, 0, 200, 200))

    assert gy[0] > gy[-1], "gy must run north -> south after normalisation"
    assert np.all(np.diff(gy) < 0)
    assert ground[0, :].mean() > 0, "row 0 must be the northern (land) half"
    assert ground[-1, :].mean() < 0, "last row must be the southern (sea) half"


def test_flood_arrays_row_orientation_matches_the_zb_fallback(tmp_path):
    """The no-dep_subgrid.tif branch must normalise orientation the same way."""
    import netCDF4 as nc

    with nc.Dataset(tmp_path / "sfincs_map.nc", "w") as d:
        d.createDimension("n", 2); d.createDimension("m", 2); d.createDimension("timemax", 1)
        x = d.createVariable("x", "f4", ("n", "m")); y = d.createVariable("y", "f4", ("n", "m"))
        zb = d.createVariable("zb", "f4", ("n", "m")); zsmax = d.createVariable("zsmax", "f4", ("timemax", "n", "m"))
        x[:] = [[50.0, 150.0], [50.0, 150.0]]
        y[:] = [[50.0, 50.0], [150.0, 150.0]]      # ascending with row index (south-up)
        zb[:] = [[-1.0, -1.0], [1.0, 1.0]]         # north row (index 1) is land
        zsmax[:] = 1.5

    ground, flooded, depth, gx, gy, cell_km2 = va._flood_arrays(tmp_path, window=(0, 0, 200, 200))
    assert gy[0] > gy[-1]
    assert ground[0, :].mean() > 0, "row 0 must be the northern (land) row"


def test_criteria_c1_not_met_when_peak_height_is_right_but_timing_is_not(synth_run_dir):
    """The |dt| > 6 h half of C1 had no test: only the peak-height branch was covered."""
    his = _base_his()
    his.loc["2013-12-08 18:00", "Uostadvaris"] = 1.00      # right height, 60 h late
    obs = _base_obs()
    obs["Uostadvaris"].loc[pd.Timestamp("2013-12-06 06:00")] = 0.92
    crit = va.criteria(his, obs, synth_run_dir, window=SYNTH_WINDOW)
    c1 = next(c for c in crit if c["name"].startswith("C1"))
    assert "+0.08" in c1["value"], "peak height must be inside +/-0.15 m for this to test timing"
    assert c1["verdict"] == "not met"


def test_c4_verdict_is_not_applicable_when_the_window_has_no_uplands():
    """0/0 makes frac_pct NaN, and `NaN < 1.0` is False -- which used to read "not met",
    i.e. a model failure, for a window that simply had nothing to measure."""
    assert va.c4_verdict(float("nan"), 0) == "n/a"
    assert va.c4_verdict(0.0, 0) == "n/a"


def test_c4_verdict_still_scores_a_window_that_has_uplands():
    assert va.c4_verdict(0.0, 5000) == "met"
    assert va.c4_verdict(0.99, 5000) == "met"
    assert va.c4_verdict(1.0, 5000) == "not met"
    assert va.c4_verdict(37.5, 5000) == "not met"


@pytest.fixture
def lowland_run_dir(tmp_path):
    """Like synth_run_dir but every pixel is below the C4 3 m cutoff: no uplands at all."""
    import netCDF4 as nc
    import rasterio

    subgrid_dir = tmp_path / "subgrid"
    subgrid_dir.mkdir()
    ground = np.full((40, 40), 0.5, dtype="float32")              # land, but nowhere near 3 m
    transform = rasterio.Affine(5.0, 0.0, 0.0, 0.0, -5.0, 200.0)
    with rasterio.open(subgrid_dir / "dep_subgrid.tif", "w", driver="GTiff", height=40, width=40,
                        count=1, dtype="float32", crs="EPSG:3346", transform=transform) as dst:
        dst.write(ground, 1)

    with nc.Dataset(tmp_path / "sfincs_map.nc", "w") as d:
        d.createDimension("n", 2); d.createDimension("m", 2); d.createDimension("timemax", 1)
        x = d.createVariable("x", "f4", ("n", "m")); y = d.createVariable("y", "f4", ("n", "m"))
        zb = d.createVariable("zb", "f4", ("n", "m")); zsmax = d.createVariable("zsmax", "f4", ("timemax", "n", "m"))
        x[:] = [[50.0, 150.0], [50.0, 150.0]]
        y[:] = [[50.0, 50.0], [150.0, 150.0]]
        zb[:] = 0.0
        zsmax[:] = 0.5
    return tmp_path


def test_criteria_c4_reports_na_on_a_window_without_uplands(lowland_run_dir):
    crit = va.criteria(_base_his(), _base_obs(), lowland_run_dir, window=SYNTH_WINDOW)
    c4 = next(c for c in crit if c["name"].startswith("C4"))
    assert c4["verdict"] == "n/a"
    assert "no land above 3 m" in c4["value"]


# ---------------------------------------------------------------------------
# criteria() dispatch on the event
# ---------------------------------------------------------------------------

def test_criteria_defaults_to_xaver(synth_run_dir):
    got = va.criteria(_base_his(), _base_obs(), synth_run_dir, window=SYNTH_WINDOW)
    assert got[0]["name"].startswith("C1")


def test_criteria_raises_rather_than_scoring_with_the_wrong_events_rules(synth_run_dir):
    class Fake:
        name = "not_an_event"
    with pytest.raises(KeyError):
        va.criteria(_base_his(), _base_obs(), synth_run_dir, window=SYNTH_WINDOW, event=Fake())


# ---------------------------------------------------------------------------
# april_criteria() -- spec section 8 success criteria for the April freshet
# ---------------------------------------------------------------------------

def _april_his(peak_day="2013-04-24", cross_day="2013-04-20", head=0.48, peak=0.54, klaipeda=None):
    """Synthetic hourly model output that passes every April criterion.

    `peak` defaults to the real observed Uostadvaris crest (0.54 m) so A1 comes
    back "met" by construction; sabotage tests override it to move only the
    peak's *height*, independent of `peak_day` (its timing) and `cross_day`
    (the filling rate) -- each parameter isolates a single criterion.

    `klaipeda` overrides the Klaipeda column outright (reindexed onto this
    function's hourly index): by default it is `u - head`, a deterministic
    function of the river signal that can never demonstrate A4 "met", since it
    carries no independent sea variability. Tests that need A4 to flip in
    either direction supply a real or a flat Klaipeda series instead.
    """
    t = pd.date_range("2013-04-05", "2013-05-02", freq="h")
    u = pd.Series(np.interp(t.asi8,
        pd.to_datetime(["2013-04-05", cross_day, peak_day, "2013-05-02"]).asi8,
        [-0.13, 0.20, peak, 0.30]), index=t)
    k = klaipeda.reindex(t).interpolate(method="time", limit_direction="both") if klaipeda is not None else u - head
    return pd.DataFrame({"Uostadvaris": u, "Klaipeda": k,
                         "Nida": u - 0.18, "Vente": u - 0.25}, index=t)


@pytest.mark.integration
def test_april_criteria_pass_on_a_faithful_model(synth_run_dir):
    obs = {g: mf.load_gauge_levels(g, APRIL) for g in va.GAUGES}
    crit = va.april_criteria(_april_his(), obs, synth_run_dir, SYNTH_WINDOW)
    assert [c["name"][:3] for c in crit] == ["A1 ", "A2a", "A2b", "A3 ", "A4 ", "A5 "]
    for p in ("A1", "A2a", "A2b", "A3"):
        assert _verdict(crit, p) == "met", p
    a2b = next(c for c in crit if c["name"].startswith("A2b"))
    assert "22 Apr-24 Apr" in a2b["value"], (
        "pins the derived plateau to the gauge's actual 22-24 Apr readings, so a "
        "change in PLATEAU_TIE_M or the database fails loudly instead of "
        "silently widening or narrowing the acceptance band")
    # A4 is not asserted here: the synthetic Klaipeda is a constant offset from the
    # river signal (u - head), not an independent sea record, so it does not clear
    # A4's no-skill-baseline bar even when every river-side criterion passes. That
    # is a property of this fixture, not a defect in A4 -- see test_a4_met_when_...
    # and test_a4_not_met_when_... below, which exercise A4 directly.


@pytest.mark.integration
def test_a1_fails_when_the_model_overshoots_the_peak(synth_run_dir):
    obs = {g: mf.load_gauge_levels(g, APRIL) for g in va.GAUGES}
    crit = va.april_criteria(_april_his(peak=0.90), obs, synth_run_dir, SYNTH_WINDOW)
    assert _verdict(crit, "A1") == "not met"
    assert _verdict(crit, "A2b") == "met", "only the peak's height changed, not its timing"


@pytest.mark.integration
def test_a2a_fails_when_the_lagoon_fills_two_days_early(synth_run_dir):
    obs = {g: mf.load_gauge_levels(g, APRIL) for g in va.GAUGES}
    crit = va.april_criteria(_april_his(cross_day="2013-04-18"), obs, synth_run_dir, SYNTH_WINDOW)
    assert _verdict(crit, "A2a") == "not met"
    assert _verdict(crit, "A2b") == "met", "the crest is still in the plateau -- A2a is the sharp half"


@pytest.mark.integration
def test_a2b_fails_when_the_crest_lands_outside_the_plateau(synth_run_dir):
    obs = {g: mf.load_gauge_levels(g, APRIL) for g in va.GAUGES}
    crit = va.april_criteria(_april_his(peak_day="2013-04-28"), obs, synth_run_dir, SYNTH_WINDOW)
    assert _verdict(crit, "A2b") == "not met"
    assert _verdict(crit, "A2a") == "met", "the filling rate is unaffected by when the crest itself lands"


@pytest.mark.integration
def test_a3_fails_when_the_delta_does_not_stand_above_the_sea(synth_run_dir):
    obs = {g: mf.load_gauge_levels(g, APRIL) for g in va.GAUGES}
    crit = va.april_criteria(_april_his(head=0.20), obs, synth_run_dir, SYNTH_WINDOW)
    assert _verdict(crit, "A3") == "not met"


@pytest.mark.integration
def test_a3_reports_na_when_the_crest_window_has_no_gauge_readings(synth_run_dir):
    """An empty `stamps` (e.g. a gap in the record over 22-26 Apr) has nothing to
    measure -- c4_verdict's "n/a" ruling applies here too, not a "not met" that
    would misreport a data gap as a model failure."""
    obs = {g: mf.load_gauge_levels(g, APRIL) for g in va.GAUGES}
    obs["Uostadvaris"] = obs["Uostadvaris"].drop(obs["Uostadvaris"].loc["2013-04-22":"2013-04-26"].index)
    crit = va.april_criteria(_april_his(), obs, synth_run_dir, SYNTH_WINDOW)
    assert _verdict(crit, "A3") == "n/a"


@pytest.mark.integration
def test_a4_met_when_klaipeda_tracks_the_gauge(synth_run_dir):
    """A4 never flips to "met" under the default fixture (see the faithful test's
    comment); supplying a Klaipeda series that actually tracks the real gauge
    shows A4 can pass, and that A1-A3 (which never look at Klaipeda except A3's
    head) are unaffected."""
    obs = {g: mf.load_gauge_levels(g, APRIL) for g in va.GAUGES}
    t = pd.date_range("2013-04-05", "2013-05-02", freq="h")
    k = obs["Klaipeda"].reindex(t).interpolate(method="time", limit_direction="both")
    crit = va.april_criteria(_april_his(klaipeda=k), obs, synth_run_dir, SYNTH_WINDOW)
    assert _verdict(crit, "A4") == "met"
    for p in ("A1", "A2a", "A2b"):
        assert _verdict(crit, p) == "met", p


@pytest.mark.integration
def test_a4_not_met_when_klaipeda_is_flat(synth_run_dir):
    """A flat sea series at the window mean carries the observed mean but none of
    the observed variability -- the definition of failing the no-skill baseline
    A4 exists to enforce."""
    obs = {g: mf.load_gauge_levels(g, APRIL) for g in va.GAUGES}
    t = pd.date_range("2013-04-05", "2013-05-02", freq="h")
    lo, hi = APRIL.score_window
    # A tiny (1 mm) wobble, not a bare constant -- an exactly flat vector makes
    # skill()'s corrcoef 0/0 (see _base_his's comment on the same aliasing), which
    # would print a numpy RuntimeWarning unrelated to what this test is checking.
    flat = pd.Series(obs["Klaipeda"].loc[lo:hi].mean(), index=t) + 0.001 * np.sin(np.arange(len(t)) / 6.0)
    crit = va.april_criteria(_april_his(klaipeda=flat), obs, synth_run_dir, SYNTH_WINDOW)
    assert _verdict(crit, "A4") == "not met"


@pytest.mark.integration
def test_a4_reports_na_when_the_observed_sea_has_gone_quiet(synth_run_dir):
    """If the window's observed Klaipeda variability ever fell to or below
    A4_RMSE_MAX, a flat, no-skill series would clear the RMSE bar too -- A4 must
    say so ("n/a") instead of silently reporting a false "met". Exercises the
    branch test_a4_met/test_a4_not_met cannot reach, since today's real sigma
    (~0.089 m) sits just above the threshold."""
    obs = {g: mf.load_gauge_levels(g, APRIL) for g in va.GAUGES}
    lo, hi = APRIL.score_window
    quiet = obs["Klaipeda"].loc[lo:hi].copy()
    quiet[:] = quiet.mean() + 0.01 * np.sin(np.arange(len(quiet)))   # sd well under A4_RMSE_MAX
    obs["Klaipeda"] = quiet
    crit = va.april_criteria(_april_his(), obs, synth_run_dir, SYNTH_WINDOW)
    assert _verdict(crit, "A4") == "n/a"


@pytest.mark.integration
def test_criteria_dispatches_april_to_april_criteria(synth_run_dir):
    obs = {g: mf.load_gauge_levels(g, APRIL) for g in va.GAUGES}
    got = va.criteria(_april_his(), obs, synth_run_dir, window=SYNTH_WINDOW, event=APRIL)
    assert got[0]["name"].startswith("A1")


@pytest.mark.integration
def test_a5_reports_na_on_a_window_without_uplands(lowland_run_dir):
    """Mirrors test_criteria_c4_reports_na_on_a_window_without_uplands: A5 reuses
    C4's logic including its no-uplands value guard, not just its verdict."""
    obs = {g: mf.load_gauge_levels(g, APRIL) for g in va.GAUGES}
    crit = va.april_criteria(_april_his(), obs, lowland_run_dir, SYNTH_WINDOW)
    a5 = next(c for c in crit if c["name"].startswith("A5"))
    assert a5["verdict"] == "n/a"
    assert "no land above 3 m" in a5["value"]
