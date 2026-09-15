import numpy as np
import pandas as pd
import pytest
import common

CRS_FOR_TEST = 3346


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


@pytest.mark.integration
def test_read_table_reads_gauge_rows():
    df = common.read_table(
        "SELECT date, site, wlevel_06 FROM physical_daily WHERE site=? AND date='2013-12-06'", ("Uostadvaris",)
    )
    assert len(df) == 1 and df.loc[0, "wlevel_06"] == 592


def test_repo_paths_are_derived_from_this_file_not_hardcoded():
    """SFINCS_BIN/RUN_SFINCS_SH must sit inside the checkout that holds common.py.

    Regression guard: both were hardcoded to ~/SFINCS/... and broke when the
    checkout was renamed to ~/sfincs, which also took data_catalog.yml's root
    with it and made the model unbuildable.
    """
    assert common.REPO == common.ROOT.parent
    for p in (common.SFINCS_BIN, common.RUN_SFINCS_SH):
        assert common.REPO in p.parents, p


@pytest.mark.integration
def test_raw_inputs_exist():
    for p in (common.DEM_5M, common.EMODNET, common.ISOBATHS, common.DB, common.ERA5_2013, common.SFINCS_BIN):
        assert p.exists(), p


def test_db_uri_percent_encodes_special_characters():
    """A path with a space, '?' or '#' must survive as a literal sqlite URI path.

    Unencoded, '?' starts the query string and '#' the fragment, so sqlite would
    open the wrong (or no) file. Fixed paths today, but the bug is silent.
    """
    from pathlib import Path

    uri = common._db_uri(Path("/tmp/odd name/db?x#y.gpkg"))
    assert uri.startswith("file:/tmp/odd%20name/db%3Fx%23y.gpkg")
    assert uri.endswith("?mode=ro")


def test_db_uri_uses_the_project_database_by_default():
    assert common._db_uri() == f"file:{common.DB}?mode=ro"


def test_write_geojson_trims_coordinates_to_millimetres(tmp_path):
    """Committed GeoJSON carried full float64 coordinates (17 significant digits).

    In a projected CRS in metres, 3 decimals is a millimetre -- far below the 100 m
    grid and the 5 m DEM -- so the extra digits are noise that makes every regenerated
    file a large, unreadable diff.
    """
    import geopandas as gpd
    from shapely.geometry import Point

    gdf = gpd.GeoDataFrame({"name": ["a"]},
                           geometry=[Point(317168.465127572009806, 6179433.5118923299014)],
                           crs=CRS_FOR_TEST)
    out = tmp_path / "pts.geojson"
    common.write_geojson(gdf, out)

    text = out.read_text()
    assert "317168.465" in text
    assert "317168.4651" not in text, "coordinates were not trimmed"
    assert gpd.read_file(out).crs.to_epsg() == CRS_FOR_TEST
