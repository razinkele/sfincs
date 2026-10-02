import asyncio
import json
import os
import signal
import subprocess
import sys

import pytest

from sfincs_ui.models import Job, Run
from sfincs_ui.services.procs import proc_starttime
from sfincs_ui.services.reconcile import reconcile
from tests.runner_helpers import make_run, run_row

S = {"alpha": 0.7}


def _set(db, run_id, *, run_status, jobs):
    """Write the DB state a crashed process would have left: jobs = [(stage, status, pid, starttime)]."""
    s = db()
    try:
        run = s.get(Run, run_id); run.status = run_status
        for stage, status, pid, st in jobs:
            s.add(Job(run_id=run_id, stage=stage, status=status, pid=pid, proc_starttime=st,
                      log_path=str(run_row(db, run_id)["workdir"] / ("sfincs.log" if stage == "simulate" else f"{stage}.log"))))
        s.commit()
    finally:
        s.close()


def _built(workdir):
    (workdir / "sfincs.inp").write_text("alpha           = 0.5\n")
    (workdir / "sfincs.dep").write_text("0 0\n")


async def test_reconcile_alive_process_is_resumed(runner, db, tmp_path):
    """Review Focus 1: a solver that survived a restart is monitored, not respawned."""
    run_id = make_run(db, tmp_path, "fake", S)
    wd = run_row(db, run_id)["workdir"]
    _built(wd)
    from sfincs_ui.services.model_service import write_overrides
    write_overrides(wd, {"alpha": "0.7"})
    # a real detached process standing in for the running solver: it finishes the fake's way after 1 s
    proc = subprocess.Popen(["bash", "-c", "sleep 1; : > sfincs_his.nc; echo '---------- Simulation finished -----------' >> sfincs.log"],
                            cwd=wd, start_new_session=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    runner.spawned_pids.add(proc.pid)
    _set(db, run_id, run_status="running", jobs=[("build", "completed", 4242, 1), ("simulate", "running", proc.pid, proc_starttime(proc.pid))])
    decisions = reconcile(runner)
    assert decisions == [{"run_id": run_id, "stage": "simulate", "decision": "resumed"}]
    await runner.wait(run_id, timeout=20)
    row = run_row(db, run_id)
    assert row["status"] == "finished" and row["exit_code"] is None  # unknown after reconciliation
    assert row["jobs"][-1]["status"] == "completed" and row["jobs"][-1]["exit_code"] is None


async def test_reconcile_dead_with_evidence_completes_and_continues(runner, db, tmp_path):
    run_id = make_run(db, tmp_path, "fake_v", S)
    wd = run_row(db, run_id)["workdir"]
    _built(wd)
    from sfincs_ui.services.model_service import write_overrides
    write_overrides(wd, {"alpha": "0.7"})
    (wd / "sfincs_his.nc").touch(); (wd / "sfincs.log").write_text("---------- Simulation finished -----------\n")
    _set(db, run_id, run_status="running", jobs=[("build", "completed", 1, 1), ("simulate", "running", 2**22 - 2, 123)])
    decisions = reconcile(runner)
    assert decisions[0]["decision"] == "completed"
    await runner.wait(run_id, timeout=20)
    row = run_row(db, run_id)
    assert [j["stage"] for j in row["jobs"]] == ["build", "simulate", "validate"] and row["status"] == "finished"


async def test_reconcile_build_without_overrides_reapplies(runner, db, tmp_path):
    """Review Focus 2: the build wrote the model but died before overrides.diff."""
    run_id = make_run(db, tmp_path, "fake", S)
    wd = run_row(db, run_id)["workdir"]
    _built(wd)
    _set(db, run_id, run_status="building", jobs=[("build", "running", 2**22 - 2, 123)])
    decisions = reconcile(runner)
    assert decisions == [{"run_id": run_id, "stage": "build", "decision": "overrides_reapplied"}]
    assert (wd / "overrides.diff").exists() and "alpha           = 0.7" in (wd / "sfincs.inp").read_text()
    await runner.wait(run_id, timeout=20)
    assert run_row(db, run_id)["status"] == "finished"


def test_reconcile_dead_partial_is_interrupted(runner, db, tmp_path):
    run_id = make_run(db, tmp_path, "fake", S)
    wd = run_row(db, run_id)["workdir"]
    (wd / "sfincs.log").write_text("  40% complete,   10.0 s remaining ...\n")
    _set(db, run_id, run_status="running", jobs=[("build", "completed", 1, 1), ("simulate", "running", 2**22 - 2, 123)])
    assert reconcile(runner)[0]["decision"] == "interrupted"
    row = run_row(db, run_id)
    assert row["status"] == "failed" and row["summary"]["reason"] == "interrupted" and row["summary"]["stage"] == "simulate"
    assert "40% complete" in row["summary"]["log_tail"] and row["jobs"][-1]["status"] == "failed"


def test_reconcile_missing_directory_is_orphaned(runner, db, tmp_path):
    """Review Focus 4."""
    import shutil
    run_id = make_run(db, tmp_path, "fake", S)
    shutil.rmtree(run_row(db, run_id)["workdir"])
    _set(db, run_id, run_status="running", jobs=[("simulate", "running", 2**22 - 2, 123)])
    assert reconcile(runner)[0]["decision"] == "orphaned"
    row = run_row(db, run_id)
    assert row["status"] == "orphaned" and row["jobs"][-1]["status"] == "orphaned"


async def test_reconcile_requeues_queued_runs_and_fails_stage_without_jobs(runner, db, tmp_path):
    queued = make_run(db, tmp_path, "fake", S, name="q")
    stale = make_run(db, tmp_path, "fake", S, name="stale")
    _set(db, stale, run_status="building", jobs=[])
    decisions = {d["run_id"]: d["decision"] for d in reconcile(runner)}
    assert decisions[queued] == "requeued" and decisions[stale] == "interrupted"
    await runner.wait(queued, timeout=20)
    assert run_row(db, queued)["status"] == "finished"
    assert run_row(db, stale)["status"] == "failed"


async def test_start_runs_the_reconciler(db, tmp_path):
    from sfincs_ui import config
    from sfincs_ui.services.job_runner import JobRunner
    from sfincs_ui.services.settings_service import SettingsService
    from tests.fake_template import FAKE_SFINCS, FakeTemplate

    cfg = config.Config(workspace=tmp_path, database_url=f"sqlite:///{tmp_path / 'test.db'}", sfincs_bin=FAKE_SFINCS)
    config.set_config(cfg)
    r = JobRunner(cfg, SettingsService(cfg, session_factory=db), session_factory=db, templates={"fake": FakeTemplate()},
                  reconciler=reconcile, poll_interval=0.05)
    run_id = make_run(db, tmp_path, "fake", S)
    await r.start()
    try:
        await r.wait(run_id, timeout=20)
        assert run_row(db, run_id)["status"] == "finished"
    finally:
        await r.stop()
        for pid in r.spawned_pids:
            try:
                os.killpg(pid, signal.SIGKILL)
            except ProcessLookupError:
                pass


def test_reconcile_never_inherits_without_a_start_time(runner, db, tmp_path):
    """A row with a pid but no recorded start time could be any recycled process: treat it as dead."""
    import os
    run_id = make_run(db, tmp_path, "fake", S)
    _set(db, run_id, run_status="running", jobs=[("build", "completed", 1, 1), ("simulate", "running", os.getpid(), None)])
    decisions = reconcile(runner)
    assert decisions == [{"run_id": run_id, "stage": "simulate", "decision": "interrupted"}]
    assert run_row(db, run_id)["status"] == "failed"
