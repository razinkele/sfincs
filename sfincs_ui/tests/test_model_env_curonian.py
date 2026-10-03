"""Model-env tests (spec section 6): run with `-m model_env`; minutes, not seconds."""

import json
import subprocess
import time
from pathlib import Path

import pytest

from sfincs_ui.config import REPO_ROOT

MODEL_PYTHON = ["micromamba", "-r", "/opt/micromamba", "run", "-n", "hydromt-sfincs", "python"]
CURONIAN = REPO_ROOT / "curonian"
pytestmark = pytest.mark.model_env


def _env_available() -> bool:
    try:
        return subprocess.run([*MODEL_PYTHON, "-c", "import hydromt_sfincs"], capture_output=True, timeout=120).returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


@pytest.fixture(scope="module", autouse=True)
def _need_env():
    if not _env_available():
        pytest.skip("hydromt-sfincs env not available")


def test_events_mirror_matches_common_events():
    """The template's event table must not drift from curonian/common.py."""
    from sfincs_ui.templates.curonian import CURONIAN_EVENTS

    code = ("import common, json; print(json.dumps({n: dict(title=e.title, tref=e.tref.strftime('%Y-%m-%d %H:%M'), "
            "tstop=e.tstop.strftime('%Y-%m-%d %H:%M'), data_end=str(e.data_window[1]) + ' 00:00', "
            "score_end=e.score_window[1].strftime('%Y-%m-%d %H:%M'), zsini=e.zsini) for n, e in common.EVENTS.items()}))")
    out = subprocess.run([*MODEL_PYTHON, "-c", code], cwd=CURONIAN, capture_output=True, text=True, timeout=120)
    assert out.returncode == 0, out.stderr
    real = json.loads(out.stdout)
    from sfincs_ui.templates.curonian import CuronianTemplate
    defaults = CuronianTemplate().defaults()
    bm = subprocess.run([*MODEL_PYTHON, "-c", "import build_model as b, json; print(json.dumps([b.MANNING_LAND, b.MANNING_SEA, b.RGH_LEV_LAND]))"],
                        cwd=CURONIAN, capture_output=True, text=True, timeout=120)
    assert bm.returncode == 0, bm.stderr
    assert [defaults["manning_land"], defaults["manning_sea"], defaults["rgh_lev_land"]] == json.loads(bm.stdout)
    assert set(real) == set(CURONIAN_EVENTS)
    for name, e in CURONIAN_EVENTS.items():
        r = real[name]
        assert (e.title, e.tref, e.tstop, e.data_window_end, e.score_window_end, e.zsini) == (r["title"], r["tref"], r["tstop"], r["data_end"], r["score_end"], r["zsini"]), name


def test_export_map_cache_imports_cleanly():
    out = subprocess.run([*MODEL_PYTHON, "-m", "prep.export_map_cache", "--help"], cwd=CURONIAN, capture_output=True, text=True, timeout=120)
    assert out.returncode == 0 and "--run-dir" in out.stdout and "--event" in out.stdout


def test_small_domain_build_applies_manning_land(tmp_path):
    """A sub-domain build with manning_land = 0.08 writes a subgrid roughness raster carrying that value."""
    # Window origin (314000, 6144000), 130 x 390 cells (13 x 39 km): the build needs the sea boundary ring
    # (y 6177-6183 km), a discharge point (Minija_mouth) and DEM coverage (y <= 6160.7 km) inside the grid,
    # so a 6 km square does not work; the window also straddles land and lagoon (n = 0.08 and 0.02).
    run_dir = tmp_path / "small"
    code = (
        "import sys, common, build_model as bm\n"
        f"bm.build(common.EVENTS['xaver_2013'], run_dir=sys.argv[1], manning_land=0.08, grid=(314000.0, 6144000.0, 130, 390), check=False)\n"
    )
    t0 = time.monotonic()
    out = subprocess.run([*MODEL_PYTHON, "-c", code, str(run_dir)], cwd=CURONIAN, capture_output=True, text=True, timeout=1800)
    elapsed = time.monotonic() - t0
    assert out.returncode == 0, out.stderr[-3000:]
    from sfincs_ui.templates.curonian import CuronianTemplate
    missing = [f for f in CuronianTemplate().model_files() if not (run_dir / f).exists()]
    assert not missing, f"template.model_files() entries absent after the build: {missing}"
    tifs = list((run_dir / "subgrid").glob("manning*.tif"))
    assert tifs, "setup_subgrid(write_man_tif=True) must write a manning raster"
    check = ("import sys, numpy as np, rasterio\n"
             "with rasterio.open(sys.argv[1]) as src: a = src.read(1, masked=True)\n"
             "print(float(np.nanmax(a.filled(np.nan))), float(np.nanmin(a.filled(np.nan))))")
    vals = subprocess.run([*MODEL_PYTHON, "-c", check, str(tifs[0])], capture_output=True, text=True, timeout=120)
    assert vals.returncode == 0, vals.stderr
    vmax, vmin = map(float, vals.stdout.split())
    assert vmax == pytest.approx(0.08, abs=1e-6) and vmin == pytest.approx(0.02, abs=1e-6)
    print(f"\nsmall-domain subgrid build: {elapsed:.0f} s")
