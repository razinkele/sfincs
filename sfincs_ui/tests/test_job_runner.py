import asyncio
import os

import pytest

from sfincs_ui.services.procs import is_alive, proc_starttime
from tests.runner_helpers import make_run, run_row

S = {"alpha": 0.7}


async def test_chain_build_then_simulate_finishes(runner, db, tmp_path):
    run_id = make_run(db, tmp_path, "fake", S, threads=3)
    await runner.start()
    runner.submit(run_id)
    await runner.wait(run_id, timeout=20)
    row = run_row(db, run_id)
    assert row["status"] == "finished" and row["exit_code"] == 0 and row["finished_at"] is not None
    assert [j["stage"] for j in row["jobs"]] == ["build", "simulate"]
    assert all(j["status"] == "completed" and j["exit_code"] == 0 and j["pid"] for j in row["jobs"])
    wd = row["workdir"]
    assert (wd / "overrides.diff").exists() and "+alpha           = 0.7" in (wd / "overrides.diff").read_text()
    assert (wd / "sfincs_his.nc").exists() and "Simulation finished" in (wd / "sfincs.log").read_text()
    assert "threads=3" in (wd / "sfincs.log").read_text()
    assert (wd / "build.log").read_text().startswith("fake build starting")


async def test_failed_build_stops_chain(runner, db, tmp_path, monkeypatch):
    monkeypatch.setenv("FAKE_FAIL_BUILD", "1")
    run_id = make_run(db, tmp_path, "fake", S)
    await runner.start()
    runner.submit(run_id)
    await runner.wait(run_id, timeout=20)
    row = run_row(db, run_id)
    assert row["status"] == "failed" and [j["stage"] for j in row["jobs"]] == ["build"]
    assert row["summary"]["stage"] == "build" and row["summary"]["exit_code"] == 1
    assert "fake build failed" in row["summary"]["log_tail"]
    assert not (row["workdir"] / "sfincs_his.nc").exists()


async def test_failed_simulate_marks_failed_with_log_tail(runner, db, tmp_path, monkeypatch):
    monkeypatch.setenv("FAKE_FAIL_SIM", "1")
    run_id = make_run(db, tmp_path, "fake", S)
    await runner.start()
    runner.submit(run_id)
    await runner.wait(run_id, timeout=20)
    row = run_row(db, run_id)
    assert row["status"] == "failed" and [j["stage"] for j in row["jobs"]] == ["build", "simulate"]
    assert row["summary"]["stage"] == "simulate" and row["summary"]["exit_code"] == 3
    assert "fatal: fake failure" in row["summary"]["log_tail"]


async def test_partial_build_without_overrides_fails(runner, db, tmp_path, monkeypatch):
    monkeypatch.setenv("FAKE_PARTIAL", "1")
    run_id = make_run(db, tmp_path, "fake", S)
    await runner.start()
    runner.submit(run_id)
    await runner.wait(run_id, timeout=20)
    row = run_row(db, run_id)
    assert row["status"] == "failed" and row["summary"]["exit_code"] == 1
    assert (row["workdir"] / "sfincs.dep").exists() and not (row["workdir"] / "overrides.diff").exists()


async def test_cancel_kills_the_process_and_marks_cancelled(runner, db, tmp_path, monkeypatch):
    monkeypatch.setenv("FAKE_STEPS", "200")
    monkeypatch.setenv("FAKE_SLEEP", "0.1")
    run_id = make_run(db, tmp_path, "fake", S)
    await runner.start()
    runner.submit(run_id)
    while not any(j["stage"] == "simulate" and j["pid"] for j in run_row(db, run_id)["jobs"]):
        await asyncio.sleep(0.02)
    pid = next(j["pid"] for j in run_row(db, run_id)["jobs"] if j["stage"] == "simulate")
    await runner.cancel(run_id)
    row = run_row(db, run_id)
    assert row["status"] == "cancelled" and row["jobs"][-1]["status"] == "cancelled"
    assert proc_starttime(pid) is None or not is_alive(pid, None)


async def test_task_cancellation_does_not_kill_the_child(runner, db, tmp_path, monkeypatch):
    """Spec section 3: uvicorn's shutdown cancels tasks; the solver must survive."""
    monkeypatch.setenv("FAKE_STEPS", "200")
    monkeypatch.setenv("FAKE_SLEEP", "0.1")
    run_id = make_run(db, tmp_path, "fake", S)
    await runner.start()
    task = runner.submit(run_id)
    while not any(j["stage"] == "simulate" and j["pid"] for j in run_row(db, run_id)["jobs"]):
        await asyncio.sleep(0.02)
    pid, st = next((j["pid"], proc_starttime(j["pid"])) for j in run_row(db, run_id)["jobs"] if j["stage"] == "simulate")
    await runner.stop()
    assert task.cancelled() or task.done()
    await asyncio.sleep(0.3)
    assert is_alive(pid, st), "the detached solver must outlive the asyncio task"
    assert run_row(db, run_id)["status"] == "running"  # left for reconciliation


async def test_simulate_cap_is_respected_by_concurrent_chains(runner, db, tmp_path, monkeypatch):
    """Review Focus 3: two launches with max_simulations = 1 never simulate at once."""
    monkeypatch.setenv("FAKE_STEPS", "6")
    monkeypatch.setenv("FAKE_SLEEP", "0.1")
    a = make_run(db, tmp_path, "fake", S, name="a")
    b = make_run(db, tmp_path, "fake", S, name="b")
    await runner.start()
    runner.submit(a); runner.submit(b)
    peak = 0
    while not all(run_row(db, r)["status"] in ("finished", "failed") for r in (a, b)):
        running = sum(1 for r in (a, b) for j in run_row(db, r)["jobs"] if j["stage"] == "simulate" and j["status"] == "running")
        peak = max(peak, running)
        await asyncio.sleep(0.02)
    assert peak == 1
    assert run_row(db, a)["status"] == run_row(db, b)["status"] == "finished"


async def test_validate_stage_runs_when_template_has_validation(runner, db, tmp_path):
    run_id = make_run(db, tmp_path, "fake_v", S)
    await runner.start()
    runner.submit(run_id)
    await runner.wait(run_id, timeout=20)
    row = run_row(db, run_id)
    assert [j["stage"] for j in row["jobs"]] == ["build", "simulate", "validate"]
    assert (row["workdir"] / "validation" / "validation.md").exists() and row["status"] == "finished"


async def test_active_jobs_and_plan_stages(runner, db, tmp_path, monkeypatch):
    monkeypatch.setenv("FAKE_STEPS", "100")
    monkeypatch.setenv("FAKE_SLEEP", "0.1")
    run_id = make_run(db, tmp_path, "fake", S)
    specs = runner.plan_stages(run_id)
    assert [s.stage for s in specs] == ["build", "simulate"]
    assert specs[1].argv[0].endswith("fake_sfincs.sh") and specs[1].env["OMP_NUM_THREADS"] == "1"
    assert specs[1].cwd == run_row(db, run_id)["workdir"] and specs[1].log_path.name == "sfincs.log"
    assert specs[1].stdout_path.name == "simulate.log" and specs[0].stdout_path == specs[0].log_path
    await runner.start()
    runner.submit(run_id)
    while not any(j["stage"] == "simulate" and j["status"] == "running" for j in run_row(db, run_id)["jobs"]):
        await asyncio.sleep(0.02)
    active = runner.active_jobs()
    assert len(active) == 1 and active[0]["stage"] == "simulate" and active[0]["run_id"] == run_id and active[0]["pid"]
    await runner.cancel(run_id)
    assert runner.active_jobs() == []
