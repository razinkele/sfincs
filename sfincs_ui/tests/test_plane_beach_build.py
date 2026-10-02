import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

from sfincs_ui.templates import plane_beach_build


def _build(run_dir: Path, settings: dict) -> subprocess.CompletedProcess:
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "settings.json").write_text(json.dumps(settings))
    return subprocess.run([sys.executable, "-P", plane_beach_build.__file__, "--run-dir", str(run_dir),
                           "--settings", str(run_dir / "settings.json")], capture_output=True, text=True, timeout=60)


DEFAULTS = {"resolution_m": 100, "duration_hours": 6, "boundary_level_m": 2.0, "manning": 0.04,
            "alpha": 0.5, "huthresh": 0.05, "advection": True}


def test_builder_writes_the_test_model_at_100m(tmp_path):
    proc = _build(tmp_path / "run", DEFAULTS)
    assert proc.returncode == 0, proc.stderr
    files = {p.name for p in (tmp_path / "run").iterdir()}
    assert {"sfincs.inp", "sfincs.dep", "sfincs.msk", "sfincs.bnd", "sfincs.bzs", "sfincs.obs"} <= files
    dep = np.loadtxt(tmp_path / "run" / "sfincs.dep")
    assert dep.shape == (20, 50) and dep[0, 0] == pytest.approx(-5.0) and dep[0, -1] == pytest.approx(4.8)
    msk = np.loadtxt(tmp_path / "run" / "sfincs.msk", dtype=int)
    assert (msk[:, 0] == 2).all() and (msk[:, 1:] == 1).all()
    bzs = np.loadtxt(tmp_path / "run" / "sfincs.bzs")
    assert bzs[0].tolist() == [0.0, 0.0, 0.0] and bzs[-1, 0] == 21600 and bzs[-1, 1] == pytest.approx(2.0)
    inp = (tmp_path / "run" / "sfincs.inp").read_text()
    for line in ("mmax            = 50", "nmax            = 20", "dx              = 100.0", "tstop           = 20240101 060000",
                 "manning         = 0.04", "alpha           = 0.5", "huthresh        = 0.05", "advection       = 1"):
        assert line in inp, line
    assert "wrote plane beach" in proc.stdout


def test_builder_scales_with_resolution_and_duration(tmp_path):
    proc = _build(tmp_path / "run", {**DEFAULTS, "resolution_m": 20, "duration_hours": 3, "boundary_level_m": 1.0})
    assert proc.returncode == 0, proc.stderr
    dep = np.loadtxt(tmp_path / "run" / "sfincs.dep")
    assert dep.shape == (100, 250) and dep[0, -1] == pytest.approx(4.8, abs=0.05)
    inp = (tmp_path / "run" / "sfincs.inp").read_text()
    assert "tstop           = 20240101 030000" in inp and "dx              = 20.0" in inp
    bzs = np.loadtxt(tmp_path / "run" / "sfincs.bzs")
    assert bzs[-1, 0] == 10800 and bzs[-1, 1] == pytest.approx(1.0)


def test_builder_writes_defaults_for_override_keys_regardless_of_settings(tmp_path):
    """The override rewrite (model_service) is what applies alpha/huthresh/advection; the builder never does."""
    proc = _build(tmp_path / "run", {**DEFAULTS, "alpha": 0.9, "huthresh": 0.2, "advection": False})
    assert proc.returncode == 0
    inp = (tmp_path / "run" / "sfincs.inp").read_text()
    assert "alpha           = 0.5" in inp and "huthresh        = 0.05" in inp and "advection       = 1" in inp


def test_builder_rejects_bad_settings(tmp_path):
    proc = _build(tmp_path / "run", {**DEFAULTS, "resolution_m": 7})
    assert proc.returncode == 2 and "resolution_m" in proc.stderr


def test_builder_has_no_package_imports():
    src = Path(plane_beach_build.__file__).read_text()
    assert "sfincs_ui" not in src.replace("sfincs_ui/", "")  # the only allowed mention is in a path comment
    assert "import numpy" in src
