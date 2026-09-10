import numpy as np
import pandas as pd
import pytest

import common
import validate as va


def test_parse_args_default_run_name():
    args = va.parse_args([])
    assert args.run == "xaver_2013"


def test_parse_args_custom_run_name():
    args = va.parse_args(["--run", "xaver_2013_gridwind"])
    assert args.run == "xaver_2013_gridwind"


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
