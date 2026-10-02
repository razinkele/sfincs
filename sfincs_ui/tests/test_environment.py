import os
import stat
import subprocess
from pathlib import Path

import pytest

from sfincs_ui.config import Config
from sfincs_ui.services.environment import check_environment

BANNER = b"------------ Welcome to SFINCS ------------\n"


def _fake_runner(responses):
    """Return a subprocess.run stand-in keyed on argv[0] / argv[-1]."""
    calls = []

    def run(argv, **kwargs):
        calls.append((argv, kwargs))
        for key, outcome in responses.items():
            if key in argv or key == argv[0]:
                if isinstance(outcome, Exception):
                    raise outcome
                return subprocess.CompletedProcess(argv, outcome[0], stdout=outcome[1], stderr=b"")
        return subprocess.CompletedProcess(argv, 0, stdout=b"", stderr=b"")

    run.calls = calls
    return run


@pytest.fixture
def layout(tmp_path):
    ws = tmp_path / "ws"; ws.mkdir()
    cur = tmp_path / "curonian"; cur.mkdir()
    (cur / "build_model.py").write_text("")
    (cur / "validate.py").write_text("")
    binary = tmp_path / "sfincs"
    binary.write_text("#!/bin/sh\necho x\n")
    binary.chmod(binary.stat().st_mode | stat.S_IEXEC)
    return Config(workspace=ws, curonian_dir=cur, sfincs_bin=binary, model_python="fake-python")


def test_all_good_shallow(layout):
    runner = _fake_runner({str(layout.sfincs_bin): (2, BANNER), "fake-python": (0, b"")})
    report = check_environment(layout, runner=runner)
    assert report.ok and report.problems == []
    bin_call = next(c for c in runner.calls if c[0][0] == str(layout.sfincs_bin))
    assert Path(bin_call[1]["cwd"]).exists() is False  # temp dir removed afterwards
    assert bin_call[1]["timeout"] == 15
    model_call = next(c for c in runner.calls if c[0][0] == "fake-python")
    assert model_call[1]["timeout"] == 20


def test_missing_binary_reported(layout):
    """Review Focus 4."""
    cfg = layout.model_copy(update={"sfincs_bin": layout.workspace / "nope"})
    report = check_environment(cfg, runner=_fake_runner({"fake-python": (0, b"")}))
    assert not report.ok
    assert any("nope" in p and "binary" in p.lower() for p in report.problems)


def test_binary_without_banner_reported(layout):
    runner = _fake_runner({str(layout.sfincs_bin): (0, b"something else"), "fake-python": (0, b"")})
    report = check_environment(layout, runner=runner)
    assert any("banner" in p.lower() for p in report.problems)


def test_model_python_timeout_reported(layout):
    """Review Focus 4: a dead micromamba must not hang startup."""
    runner = _fake_runner({
        str(layout.sfincs_bin): (2, BANNER),
        "fake-python": subprocess.TimeoutExpired(cmd="fake-python", timeout=20),
    })
    report = check_environment(layout, runner=runner)
    assert any("model environment" in p.lower() and "timed out after 20 s" in p.lower() for p in report.problems)


def test_model_python_import_failure_reported(layout):
    runner = _fake_runner({str(layout.sfincs_bin): (2, BANNER), "fake-python": (1, b"")})
    report = check_environment(layout, runner=runner)
    assert any("hydromt_sfincs" in p for p in report.problems)


def test_model_python_not_found_reported(layout):
    runner = _fake_runner({str(layout.sfincs_bin): (2, BANNER), "fake-python": FileNotFoundError("fake-python")})
    report = check_environment(layout, runner=runner)
    assert any("fake-python" in p for p in report.problems)


def test_curonian_dir_without_scripts_reported(layout, tmp_path):
    cfg = layout.model_copy(update={"curonian_dir": tmp_path / "empty"})
    (tmp_path / "empty").mkdir()
    report = check_environment(cfg, runner=_fake_runner({str(layout.sfincs_bin): (2, BANNER)}))
    assert any("build_model.py" in p for p in report.problems)


def test_unwritable_workspace_reported(layout):
    if os.geteuid() == 0:
        pytest.skip("root ignores permission bits")
    layout.workspace.chmod(0o500)
    try:
        report = check_environment(layout, runner=_fake_runner({str(layout.sfincs_bin): (2, BANNER)}))
    finally:
        layout.workspace.chmod(0o700)
    assert any("workspace" in p.lower() and "writable" in p.lower() for p in report.problems)


def test_deep_checks_inputs_and_catalogue(layout, tmp_path, monkeypatch):
    cur = layout.curonian_dir
    (cur / "inputs" / "xaver_2013" / "gtsm").mkdir(parents=True)
    (cur / "inputs" / "xaver_2013" / "era5_grid.nc").write_bytes(b"")
    (cur / "inputs" / "april_2013").mkdir()
    (cur / "inputs" / "lagoon_bathy_50m.tif").write_bytes(b"")
    (cur / "data_catalog.yml").write_text("a:\n  path: /nonexistent/one.tif\nb:\n  path: relative/ok.nc\n")
    monkeypatch.setenv("SFINCS_CURONIAN_DB", str(tmp_path / "missing.gpkg"))
    runner = _fake_runner({str(layout.sfincs_bin): (2, BANNER), "fake-python": (0, b"")})
    report = check_environment(layout, deep=True, runner=runner)
    joined = "\n".join(report.problems)
    assert "april_2013/era5_grid.nc" in joined and "april_2013/gtsm" in joined
    assert "/nonexistent/one.tif" in joined
    assert "relative/ok.nc" not in joined
    assert "missing.gpkg" in joined and "gauge database" in joined.lower()
    # deep mode asked the model env to open the GeoTIFF
    snippets = [c[0][-1] for c in runner.calls if c[0][0] == "fake-python"]
    assert any("rasterio.open" in s for s in snippets)
    # deep checks keep the long timeout; only the startup import check is short
    geotiff_call = next(c for c in runner.calls if c[0][0] == "fake-python" and "rasterio.open" in c[0][-1])
    assert geotiff_call[1]["timeout"] == 120
    import_call = next(c for c in runner.calls if c[0][0] == "fake-python" and "hydromt_sfincs" in c[0][-1])
    assert import_call[1]["timeout"] == 120


def test_deep_gauge_database_opens_read_only(layout, tmp_path, monkeypatch):
    import sqlite3

    db = tmp_path / "gauges.gpkg"
    sqlite3.connect(db).close()
    monkeypatch.setenv("SFINCS_CURONIAN_DB", str(db))
    (layout.curonian_dir / "inputs").mkdir()
    runner = _fake_runner({str(layout.sfincs_bin): (2, BANNER), "fake-python": (0, b"")})
    report = check_environment(layout, deep=True, runner=runner)
    assert not any("gauge database" in p.lower() for p in report.problems)


def test_deep_unreadable_catalogue_is_a_problem_not_an_exception(layout, monkeypatch):
    import os as _os

    if _os.geteuid() == 0:
        pytest.skip("root ignores permission bits")
    (layout.curonian_dir / "inputs").mkdir()
    cat = layout.curonian_dir / "data_catalog.yml"
    cat.write_text("a:\n  path: /x\n")
    cat.chmod(0o000)
    monkeypatch.setenv("SFINCS_CURONIAN_DB", "/nonexistent.gpkg")
    runner = _fake_runner({str(layout.sfincs_bin): (2, BANNER), "fake-python": (0, b"")})
    try:
        report = check_environment(layout, deep=True, runner=runner)
    finally:
        cat.chmod(0o644)
    assert any("Catalogue not readable" in p for p in report.problems)


def test_deep_catalogue_with_too_few_absolute_paths_is_reported(layout, monkeypatch):
    (layout.curonian_dir / "inputs").mkdir()
    (layout.curonian_dir / "data_catalog.yml").write_text("a:\n  path: relative/only.nc\n")
    monkeypatch.setenv("SFINCS_CURONIAN_DB", "/nonexistent.gpkg")
    runner = _fake_runner({str(layout.sfincs_bin): (2, BANNER), "fake-python": (0, b"")})
    report = check_environment(layout, deep=True, runner=runner)
    assert any("expected at least 3" in p for p in report.problems)


def test_real_binary_prints_banner_if_present():
    """Runs the actual solver when this checkout has it; skipped elsewhere."""
    cfg = Config(workspace=Path("/tmp"))
    if not cfg.sfincs_bin.exists():
        pytest.skip("no sfincs binary in this checkout")
    runner_calls = []

    def runner(argv, **kw):
        runner_calls.append(argv)
        if argv[0] == str(cfg.sfincs_bin):
            return subprocess.run(argv, **kw)
        return subprocess.CompletedProcess(argv, 0, stdout=b"", stderr=b"")

    report = check_environment(cfg.model_copy(update={"workspace": cfg.repo_root / "sfincs_ui"}), runner=runner)
    assert not any("banner" in p.lower() for p in report.problems)
