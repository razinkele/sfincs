import numpy as np
import pandas as pd

import validate as va


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
