import geopandas as gpd
import numpy as np
import pytest
from shapely.geometry import LineString

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


def test_datasets_riv_is_one_entry_per_channel_not_one_combined():
    """SubgridTableRegular.build() calls burn_river_rect once per datasets_riv entry,
    per tile, passing that entry's whole gdf_zb through unclipped. A single combined
    entry let an isolated per-tile fragment of one channel be "nearest" to every
    OTHER channel's zb points too (nearest() has no distance cutoff) -- measured as
    a strait-mouth cell reading -6.96 m and an atmata cell reading the strait's
    -12.00 m (see .superpowers/sdd/2026-09-16-april-2013-nemunas-flood/
    fix-distributary-bed-report.md). One entry per channel makes that impossible:
    each entry's gdf_zb only ever carries its own channel's values."""
    entries = bm.datasets_riv()
    assert len(entries) == 3
    by_channel = {}
    for entry in entries:
        gdf_riv = entry["centerlines"]
        gdf_zb = entry["point_zb"]
        assert set(gdf_riv["name"]) == set(gdf_zb["channel"]), "centerline and zb points must be the same channel"
        name = gdf_riv["name"].iloc[0]
        by_channel[name] = (gdf_riv, gdf_zb)
        assert len(gdf_riv) == 1, f"{name}: centerlines entry must hold only its own channel"
        assert len(gdf_zb) > 0, f"{name}: point_zb entry must not be empty"
    assert set(by_channel) == {"strait", "atmata", "skirvyte"}
    assert (by_channel["strait"][1]["rivbed"] == -12.0).all()


def _flat_elevation_da(nx=10, ny=10, res=100.0, x0=1000.0, y0=1000.0):
    """A tiny synthetic elevation DataArray with the hydromt raster accessor wired
    up -- just enough for burn_river_rect() to clip/mask/reproject against."""
    import xarray as xr

    xs = x0 + res * (np.arange(nx) + 0.5)
    ys = y0 + res * (np.arange(ny) + 0.5)
    da = xr.DataArray(np.zeros((ny, nx), dtype="float32"), dims=("y", "x"),
                       coords={"y": ys[::-1], "x": xs}, name="elevtn")
    da.raster.set_crs(common.CRS)
    da.raster.set_nodata(np.nan)
    return da


def test_burn_river_rect_bleeds_across_a_combined_entry_but_not_a_split_one():
    """Regression guard for the cross-channel contamination this fix discovered and
    had to work around (see .superpowers/sdd/2026-09-16-april-2013-nemunas-flood/
    fix-distributary-bed-report.md).

    hydromt_sfincs.workflows.bathymetry.burn_river_rect() clips `gdf_riv` to the
    elevation raster's own extent, but NOT `gdf_zb` -- and its nearest()-based
    point-to-line assignment has no distance cutoff. If one call's `gdf_riv` +
    `gdf_zb` cover multiple channels and the elevation raster (a "tile", in
    SubgridTableRegular's real per-block burn) happens to contain only one
    channel's geometry, every OTHER channel's zb points are still "nearest" to
    that one local line by default and corrupt it. This is exactly what produced
    a strait cell at -6.96 m (every one of its own zb points is -12.0) and an
    atmata cell at the strait's own -12.00 m during this fix's first, literal-spec
    attempt (one combined `datasets_riv` entry for all three channels).

    Sabotage: a tiny elevation raster covers channel A's geometry only -- a
    stand-in for an isolated per-tile fragment. Channel B sits far outside it.
    A **combined** gdf_riv/gdf_zb (both channels together, the broken shape) must
    reproduce the bleed: A's cells stop being uniformly -12.0. Two **separate**
    calls, one per channel -- exactly what build_model.datasets_riv() does -- must
    not: A's cells stay exactly at A's own -12.0 regardless of what B says.
    """
    from hydromt_sfincs.workflows.bathymetry import burn_river_rect

    line_a = LineString([(1000.0, 1500.0), (1900.0, 1500.0)])   # inside the tile
    line_b = LineString([(50_000.0, 50_000.0), (50_900.0, 50_000.0)])  # far outside it

    gdf_riv = gpd.GeoDataFrame({"name": ["A", "B"], "rivwth": [100.0, 100.0]},
                               geometry=[line_a, line_b], crs=common.CRS)
    gdf_zb = gpd.GeoDataFrame(
        {"channel": ["A", "B"], "rivbed": [-12.0, -3.0]},
        geometry=[line_a.interpolate(0.5, normalized=True), line_b.interpolate(0.5, normalized=True)],
        crs=common.CRS)

    da_combined, _ = burn_river_rect(da_elv=_flat_elevation_da(), gdf_riv=gdf_riv.copy(), gdf_zb=gdf_zb.copy())
    burned_combined = da_combined.values[da_combined.values < -1.0]
    assert burned_combined.size > 0, "test setup produced no burned cells at all"
    assert not np.allclose(burned_combined, -12.0, atol=0.05), (
        "expected the known combined-entry bleed to reproduce here (channel A pulled "
        "away from its own -12.0 by channel B's far-away -3.0); if this now holds, "
        "hydromt_sfincs may have fixed the underlying issue upstream -- re-check "
        "before loosening this guard")

    gdf_riv_a = gdf_riv[gdf_riv["name"] == "A"].copy()
    gdf_zb_a = gdf_zb[gdf_zb["channel"] == "A"].copy()
    da_split, _ = burn_river_rect(da_elv=_flat_elevation_da(), gdf_riv=gdf_riv_a, gdf_zb=gdf_zb_a)
    burned_split = da_split.values[da_split.values < -1.0]
    assert burned_split.size > 0
    assert np.allclose(burned_split, -12.0, atol=0.01), \
        "a channel burned on its own must stay exactly at its own rivbed"


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
