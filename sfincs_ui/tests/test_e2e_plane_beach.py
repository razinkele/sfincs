"""The one test that runs the real SFINCS binary: build, simulate, finish, read the his file."""

import os
import signal
import time

import netCDF4 as nc
import numpy as np
import pytest

from sfincs_ui import config
from sfincs_ui.services.auth_service import AuthService
from sfincs_ui.services.job_runner import JobRunner
from sfincs_ui.services.project_service import ProjectService
from sfincs_ui.services.reconcile import reconcile
from sfincs_ui.services.run_service import RunService
from sfincs_ui.services.settings_service import SettingsService
from sfincs_ui.templates import TEMPLATES

BINARY = config.REPO_ROOT / "sfincs-linux" / "bin" / "sfincs"
pytestmark = pytest.mark.skipif(not BINARY.exists(), reason="SFINCS binary not in this checkout")


async def test_plane_beach_run_end_to_end(db, tmp_path):
    cfg = config.Config(workspace=tmp_path, database_url=f"sqlite:///{tmp_path / 'test.db'}", sfincs_bin=BINARY, max_threads=4)
    config.set_config(cfg)
    auth = AuthService(session_factory=db)
    alice = auth.create_user("alice", "pw12345678")
    settings = SettingsService(cfg, session_factory=db)
    projects = ProjectService(cfg, session_factory=db, templates=TEMPLATES)
    runner = JobRunner(cfg, settings, session_factory=db, templates=TEMPLATES, reconciler=reconcile, poll_interval=0.1)
    runs = RunService(cfg, settings, projects, runner, session_factory=db, templates=TEMPLATES)
    try:
        project = projects.create(alice, "plane_beach", "E2E", {"alpha": 0.6})
        await runner.start()
        t0 = time.monotonic()
        run = runs.launch(alice, project["id"], "e2e", 2)
        await runner.wait(run["id"], timeout=120)
        elapsed = time.monotonic() - t0
        got = runs.get(alice, run["id"])
        assert got["status"] == "finished", got["summary"]
        assert [s["stage"] for s in got["stages"]] == ["build", "simulate"]
        his = runs.download_path(alice, run["id"], "sfincs_his.nc")
        with nc.Dataset(his) as d:
            zs = d["point_zs"][:]
            assert zs.shape[1] == 3 and zs.shape[0] >= 70
            assert float(zs[-1, 0]) == pytest.approx(2.0, abs=0.05)  # offshore station reaches the 2.0 m ramp
            assert float(zs[-1, 2]) < float(zs[-1, 0]) + 0.01  # inland never exceeds the boundary level
        inp = runs.download_path(alice, run["id"], "sfincs.inp").read_text()
        assert "alpha           = 0.6" in inp
        assert "+alpha           = 0.6" in runs.download_path(alice, run["id"], "overrides.diff").read_text()
        assert runs.progress(alice, run["id"])["percent"] >= 95
        print(f"\nplane beach 100 m, 6 h, 2 threads: {elapsed:.1f} s wall clock")
    finally:
        await runner.stop()
        for pid in runner.spawned_pids:
            try:
                os.killpg(pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
