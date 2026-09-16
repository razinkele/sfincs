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


def test_registry_holds_both_events_keyed_by_name():
    assert set(common.EVENTS) == {"xaver_2013", "april_2013"}
    for name, ev in common.EVENTS.items():
        assert ev.name == name


def test_xaver_event_carries_todays_constants_unchanged():
    ev = common.event("xaver_2013")
    assert (ev.tref, ev.tstop) == (common.TREF, common.TSTOP)
    assert ev.calm_window == common.CALM_WINDOW
    assert ev.minija_q == common.MINIJA_Q_DEC
    assert ev.data_window == ("2013-11-20", "2013-12-20")   # today's SQL literals
    assert ev.score_window == (pd.Timestamp("2013-12-05"), pd.Timestamp("2013-12-09"))
    assert ev.zsini is None                                  # taken from the boundary
    assert ev.wind_check == (15.0, "the Xaver gale")
    assert ev.score_label == "Storm window"             # today's report heading


def test_april_event_matches_the_spec():
    ev = common.event("april_2013")
    assert ev.tref == pd.Timestamp("2013-04-05 00:00")
    assert ev.tstop == pd.Timestamp("2013-05-02 00:00")
    assert ev.calm_window == (pd.Timestamp("2013-04-05"), pd.Timestamp("2013-04-11"))
    assert ev.score_window == (pd.Timestamp("2013-04-13"), pd.Timestamp("2013-05-02"))
    assert ev.data_window == ("2013-03-26", "2013-05-12")
    assert ev.gtsm_months == ("04", "05")
    assert ev.minija_q == common.MINIJA_Q_APR == 83.0
    assert ev.wind_check is None
    assert ev.zsini == -0.17
    assert ev.score_label == "Scoring window"


def test_inputs_dir_derives_from_the_name_and_run_dir_does_not():
    ev = common.event("april_2013")
    assert ev.inputs_dir == common.INPUTS / "april_2013"
    assert not hasattr(ev, "run_dir"), (
        "run directories are keyed by run name, not event name: one event owns "
        "xaver_2013, xaver_2013_gridwind and xaver_2013_gridwind_pressure")


def test_events_are_frozen():
    with pytest.raises(Exception):
        common.event("xaver_2013").minija_q = 99.0


def test_unknown_event_names_itself_and_the_alternatives():
    with pytest.raises(KeyError, match="april_2013"):
        common.event("april2013")
