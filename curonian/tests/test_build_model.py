import pytest

import common
import build_model as bm


def test_parse_args_defaults():
    args = bm.parse_args([])
    assert args.no_subgrid is False
    assert args.wind == "uniform"
    assert args.pressure is False
    assert args.run_name == "xaver_2013"


def test_parse_args_grid_wind_and_pressure():
    args = bm.parse_args(["--wind", "grid", "--pressure", "--run-name", "xaver_2013_gridwind_pressure",
                           "--no-subgrid"])
    assert args.no_subgrid is True
    assert args.wind == "grid"
    assert args.pressure is True
    assert args.run_name == "xaver_2013_gridwind_pressure"


def test_parse_args_pressure_without_grid_wind_exits():
    with pytest.raises(SystemExit):
        bm.parse_args(["--pressure"])


def test_event_and_run_name_compose():
    args = bm.parse_args([])
    assert args.event == "xaver_2013" and args.run_name == "xaver_2013"

    args = bm.parse_args(["--event", "april_2013"])
    assert args.run_name == "april_2013", "run name defaults to the event's name"

    args = bm.parse_args(["--event", "xaver_2013", "--wind", "grid",
                          "--run-name", "xaver_2013_gridwind"])
    assert (args.event, args.run_name) == ("xaver_2013", "xaver_2013_gridwind")


def test_april_config_uses_the_events_clock_and_initial_level(monkeypatch):
    """zsini comes from the event when it sets one, not from the sea boundary."""
    ev = common.event("april_2013")
    cfg = bm.config_for(ev, zs_boundary=-0.36)
    assert cfg["tstart"] == "20130405 000000" and cfg["tstop"] == "20130502 000000"
    assert cfg["zsini"] == -0.17

    cfg = bm.config_for(common.event("xaver_2013"), zs_boundary=0.389)
    assert cfg["zsini"] == 0.389, "Xaver keeps taking zsini from the boundary"


@pytest.mark.integration
def test_built_model_passes_checks():
    run = common.RUN_XAVER
    if not (run / "sfincs.inp").exists():
        pytest.skip("run build_model.py first")
    r = bm.check_model(run)
    assert 200_000 <= r["n_active"] <= 400_000, r
    assert 20 <= r["n_bnd"] <= 200 and r["bnd_in_ring"], r
    assert r["connected"], "strait not connected to the lagoon"
    inp = (run / "sfincs.inp").read_text()
    for key in ("sbgfile", "bzsfile", "bndfile", "srcfile", "disfile", "wndfile", "obsfile"):
        assert key in inp, key
    # hydromt_sfincs 1.2.2 writes the modern NetCDF subgrid table (sfincs_subgrid.nc),
    # not the legacy binary sfincs.sbg the task brief names -- see build_model.py's
    # comment in build() for why the legacy binary path is unusable here. The
    # installed SFINCS binary itself expects this format (its subgrid_uv_havg/nrep/
    # pwet Fortran variable names match the NetCDF table's fields exactly).
    assert "20131211 000000" in inp and "sfincs_subgrid.nc" in inp
    assert (run / "sfincs_subgrid.nc").exists()
    assert (run / "subgrid" / "dep_subgrid.tif").exists()


def test_check_model_constants_are_named_and_plausible():
    """The connectivity probe and ring tolerance were bare literals inside check_model."""
    assert bm.BND_RING_TOL_M == 150.0
    x, y = bm.OPEN_LAGOON_PROBE
    assert common.X0 < x < common.X0 + common.MMAX * common.DX
    assert common.Y0 < y < common.Y0 + common.NMAX * common.DY


@pytest.mark.integration
def test_open_lagoon_probe_sits_inside_the_active_region():
    """check_model()'s connectivity test compares the mouth against this point, so a
    probe outside the active region would silently make `connected` meaningless."""
    import geopandas as gpd
    from shapely.geometry import Point

    region_file = common.INPUTS / "active_region.geojson"
    if not region_file.exists():
        pytest.skip("run prep.make_geometries first")
    region = gpd.read_file(region_file).geometry.iloc[0]
    assert region.contains(Point(*bm.OPEN_LAGOON_PROBE))


@pytest.mark.integration
def test_inp_manning_land_matches_the_subgrid_tables():
    """sfincs.inp said manning_land = 0.04 while setup_subgrid was given 0.06.

    Inert in subgrid mode (roughness comes from the tables -- sfincs_subgrid.nc's
    uv_navg spans 0.02..0.06, so the 0.06 did land), but the inp keyword is what a
    reader checks first, and it disagreed with the model actually being run.
    """
    run = common.RUN_XAVER
    if not (run / "sfincs.inp").exists():
        pytest.skip("run build_model.py first")
    inp = dict(
        line.split("=", 1) for line in (run / "sfincs.inp").read_text().splitlines() if "=" in line
    )
    inp = {k.strip(): v.strip() for k, v in inp.items()}
    assert float(inp["manning_land"]) == 0.06, "inp disagrees with setup_subgrid's manning_land"
    assert float(inp["manning_sea"]) == 0.02
