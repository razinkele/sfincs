import numpy as np
import pandas as pd
import common


def test_gauge_conversion_uses_500cm_zero():
    assert common.gauge_cm_to_m(500) == 0.0
    assert common.gauge_cm_to_m(592) == 0.92
    np.testing.assert_allclose(common.gauge_cm_to_m([450, 550]), [-0.5, 0.5])


def test_grid_constants_match_spec():
    assert (common.X0, common.Y0, common.MMAX, common.NMAX) == (270_000, 6_080_000, 1000, 1100)
    assert common.DX == common.DY == 100.0
    assert common.CRS == 3346


def test_period_and_windows():
    assert common.TREF == pd.Timestamp("2013-11-28 00:00")
    assert common.TSTOP == pd.Timestamp("2013-12-11 00:00")
    assert common.CALM_WINDOW == (pd.Timestamp("2013-11-28"), pd.Timestamp("2013-12-04"))


def test_lonlat_to_xy_klaipeda_mouth_is_inside_domain():
    x, y = common.lonlat_to_xy(*common.KLAIPEDA_MOUTH_LONLAT)
    assert 315_000 < x < 322_000 and 6_177_000 < y < 6_183_000


def test_read_table_reads_gauge_rows():
    df = common.read_table(
        "SELECT date, site, wlevel_06 FROM physical_daily WHERE site=? AND date='2013-12-06'", ("Uostadvaris",)
    )
    assert len(df) == 1 and df.loc[0, "wlevel_06"] == 592


def test_raw_inputs_exist():
    for p in (common.DEM_5M, common.EMODNET, common.ISOBATHS, common.DB, common.ERA5_2013, common.SFINCS_BIN):
        assert p.exists(), p
