"""Pick up where a previous process left off (spec section 3, Reconciliation on startup).

Driven from every job row left in an active status, grouped by run, plus the
queued runs that never got a job. Each run is decided and committed on its
own: one run that cannot be reconciled is failed (with its job rows) and the
others still continue.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from sfincs_ui.models import ACTIVE_JOB_STATUSES, Job, Project, Run
from sfincs_ui.services.job_runner import SUMMARY_TAIL, JobRunner, evidence_for
from sfincs_ui.services.model_service import read_settings, write_overrides
from sfincs_ui.services.procs import is_alive, killpg_graceful
from sfincs_ui.services.progress import tail_lines
from sfincs_ui.timeutil import utcnow

logger = logging.getLogger(__name__)
STAGE_STATUSES = ("building", "running", "validating", "exporting")
TERMINAL_RUN_STATUSES = ("finished", "failed", "cancelled", "orphaned")


def reconcile(runner: JobRunner) -> list[dict]:
    decisions: list[dict] = []
    s = runner._sf()
    try:
        active_rows = (s.query(Job, Run).join(Run, Job.run_id == Run.id)
                       .filter(Job.status.in_(ACTIVE_JOB_STATUSES)).order_by(Job.id).all())
        jobs_by_run: dict[str, list[int]] = {}
        for job, run in active_rows:
            jobs_by_run.setdefault(run.id, []).append(job.id)
        open_runs = [r.id for r in s.query(Run).filter(Run.status.in_(("queued", *STAGE_STATUSES)))
                     .order_by(Run.created_at).all()]
        # Runs still in progress first (creation order), then terminal runs that left active job rows.
        run_ids = open_runs + [rid for rid in jobs_by_run if rid not in open_runs]
        for run_id in run_ids:
            try:
                decisions.append(_decide(runner, s, s.get(Run, run_id), [s.get(Job, j) for j in jobs_by_run.get(run_id, [])]))
                s.commit()
            except Exception as exc:
                s.rollback()
                logger.exception("reconcile: cannot reconcile run %s", run_id)
                decisions.append(_fail_after_error(s, run_id, jobs_by_run.get(run_id, []), exc))
    finally:
        s.close()

    # Start the chains only after the rows are committed.
    for d in decisions:
        try:
            if d["decision"] == "requeued":
                if d["stage"] is None:
                    runner.submit(d["run_id"])
                else:
                    runner.resume(d["run_id"], _stage_index(runner, d["run_id"], d["stage"]), None)
            elif d["decision"] == "resumed":
                runner.resume(d["run_id"], _stage_index(runner, d["run_id"], d["stage"]), d["_inherit"])
            elif d["decision"] in ("completed", "overrides_reapplied"):
                runner.resume(d["run_id"], _stage_index(runner, d["run_id"], d["stage"]) + 1, None)
        except Exception as exc:
            logger.exception("reconcile: cannot continue run %s", d["run_id"])
            if "_inherit" in d:  # a live process nobody can monitor: stop it rather than leave it unaccounted for
                _kill_quietly(runner, *d["_inherit"])
            _fail_run_by_id(runner, d["run_id"], d["stage"] or "plan", f"cannot plan stages: {exc}")
            d["decision"] = "failed"
    for d in decisions:
        d.pop("_inherit", None)
        logger.info("reconcile: run %s stage %s -> %s", d["run_id"], d["stage"], d["decision"])
    return decisions


def _decide(runner: JobRunner, s, run: Run, active: list[Job]) -> dict:
    """Repair one run's rows in session s (not committed) and return its decision."""
    if run.status in TERMINAL_RUN_STATUSES:
        # e.g. a restart during cancel's grace period, or kill-jobs interrupted between its steps
        for job in active:
            if job.pid and job.proc_starttime is not None and is_alive(job.pid, job.proc_starttime):
                killpg_graceful(job.pid, runner._grace)
            job.status = "cancelled"; job.finished_at = utcnow()
        return {"run_id": run.id, "stage": active[-1].stage, "decision": "closed_stale"}
    if not active:
        if run.status == "queued":
            return {"run_id": run.id, "stage": None, "decision": "requeued"}
        _fail(run, run.status, "interrupted", "")
        return {"run_id": run.id, "stage": None, "decision": "interrupted"}
    project = s.get(Project, run.project_id)
    template = runner._templates.get(project.template) if project else None
    run_dir = Path(run.workdir)
    for stale in active[:-1]:
        stale.status = "failed"; stale.finished_at = utcnow()
    job = active[-1]
    if not run_dir.is_dir() or template is None:
        job.status = "orphaned"; job.finished_at = utcnow(); run.status = "orphaned"; run.finished_at = utcnow()
        return {"run_id": run.id, "stage": job.stage, "decision": "orphaned"}
    if not job.pid:
        # queued (waiting for capacity) or claimed-but-not-spawned: no process ever existed.
        job.status = "cancelled"; job.finished_at = utcnow()
        return {"run_id": run.id, "stage": job.stage, "decision": "requeued"}
    if job.proc_starttime is not None and is_alive(job.pid, job.proc_starttime):
        return {"run_id": run.id, "stage": job.stage, "decision": "resumed", "_inherit": (job.pid, job.proc_starttime)}
    evidence = evidence_for(job.stage, run_dir, template)
    if job.stage == "build" and not evidence() and (run_dir / "sfincs.inp").is_file() \
            and all((run_dir / f).is_file() for f in template.model_files()):
        settings = read_settings(run_dir) if (run_dir / "settings.json").exists() else json.loads(run.settings_json)
        write_overrides(run_dir, template.inp_overrides(settings))
        decision = "overrides_reapplied"
    elif evidence():
        decision = "completed"
    else:
        _fail(run, job.stage, "interrupted", tail_lines(Path(job.log_path), SUMMARY_TAIL))
        job.status = "failed"; job.finished_at = utcnow()
        return {"run_id": run.id, "stage": job.stage, "decision": "interrupted"}
    job.status = "completed"; job.exit_code = None; job.finished_at = utcnow()
    return {"run_id": run.id, "stage": job.stage, "decision": decision}


def _fail_after_error(s, run_id: str, job_ids: list[int], exc: Exception) -> dict:
    """After a rollback: fail the run (unless already terminal) and close its active job rows as failed."""
    stage = None
    try:
        run = s.get(Run, run_id)
        jobs = [j for j in (s.get(Job, jid) for jid in job_ids) if j is not None and j.status in ACTIVE_JOB_STATUSES]
        stage = jobs[-1].stage if jobs else None
        if run is not None and run.status not in TERMINAL_RUN_STATUSES:
            _fail(run, stage or run.status, f"cannot reconcile: {exc}", "")
        for job in jobs:
            job.status = "failed"; job.finished_at = utcnow()
        s.commit()
    except Exception:
        s.rollback()
        logger.exception("reconcile: cannot record the failure of run %s", run_id)
    return {"run_id": run_id, "stage": stage, "decision": "failed"}


def _kill_quietly(runner: JobRunner, pid: int, starttime: int | None) -> None:
    try:
        if starttime is not None and is_alive(pid, starttime):
            killpg_graceful(pid, runner._grace)
    except Exception:
        logger.exception("reconcile: cannot stop process %s", pid)


def _stage_index(runner: JobRunner, run_id: str, stage: str) -> int:
    return [spec.stage for spec in runner.plan_stages(run_id)].index(stage)


def _fail(run: Run, stage: str, reason: str, log_tail: str) -> None:
    run.status = "failed"; run.finished_at = utcnow()
    run.summary_json = json.dumps({"stage": stage, "reason": reason, "exit_code": None, "log_tail": log_tail})


def _fail_run_by_id(runner: JobRunner, run_id: str, stage: str, reason: str) -> None:
    runner._fail_jobs_for_run(run_id)
    s = runner._sf()
    try:
        run = s.get(Run, run_id)
        if run is not None and run.status not in TERMINAL_RUN_STATUSES:
            _fail(run, stage, reason, "")
            s.commit()
    finally:
        s.close()
