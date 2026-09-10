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
