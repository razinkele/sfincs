"""Pick up where a previous process left off (spec section 3, Reconciliation on startup)."""

from __future__ import annotations

import json
import logging
from pathlib import Path

from sfincs_ui.models import ACTIVE_JOB_STATUSES, RUN_STATUSES, Job, Project, Run
from sfincs_ui.services.job_runner import SUMMARY_TAIL, JobRunner, build_evidence, evidence_for
from sfincs_ui.services.model_service import read_settings, write_overrides
from sfincs_ui.services.procs import is_alive
from sfincs_ui.services.progress import tail_lines
from sfincs_ui.timeutil import utcnow

logger = logging.getLogger(__name__)
STAGE_STATUSES = ("building", "running", "validating", "exporting")


def reconcile(runner: JobRunner) -> list[dict]:
    decisions: list[dict] = []
    s = runner._sf()
    try:
        runs = s.query(Run).filter(Run.status.in_(("queued", *STAGE_STATUSES))).order_by(Run.created_at).all()
        for run in runs:
            project = s.get(Project, run.project_id)
            template = runner._templates.get(project.template) if project else None
            run_dir = Path(run.workdir)
            active = [j for j in run.jobs if j.status in ACTIVE_JOB_STATUSES]
            if run.status == "queued" and not active:
                decisions.append({"run_id": run.id, "stage": None, "decision": "requeued"})
                continue
            if not active:
                _fail(run, run.status, "interrupted", "", s)
                decisions.append({"run_id": run.id, "stage": None, "decision": "interrupted"})
                continue
            job = active[-1]
            if not run_dir.is_dir() or template is None:
                job.status = "orphaned"; job.finished_at = utcnow(); run.status = "orphaned"; run.finished_at = utcnow()
                decisions.append({"run_id": run.id, "stage": job.stage, "decision": "orphaned"})
                continue
            if job.pid and job.proc_starttime is not None and is_alive(job.pid, job.proc_starttime):
                decisions.append({"run_id": run.id, "stage": job.stage, "decision": "resumed", "_inherit": (job.pid, job.proc_starttime)})
                continue
            evidence = evidence_for(job.stage, run_dir, template)
            if job.stage == "build" and not evidence() and (run_dir / "sfincs.inp").is_file() \
                    and all((run_dir / f).is_file() for f in template.model_files()):
                settings = read_settings(run_dir) if (run_dir / "settings.json").exists() else json.loads(run.settings_json)
                write_overrides(run_dir, template.inp_overrides(settings))
                decision = "overrides_reapplied"
            elif evidence():
                decision = "completed"
            else:
                _fail(run, job.stage, "interrupted", tail_lines(Path(job.log_path), SUMMARY_TAIL), s)
                job.status = "failed"; job.finished_at = utcnow()
                decisions.append({"run_id": run.id, "stage": job.stage, "decision": "interrupted"})
                continue
            job.status = "completed"; job.exit_code = None; job.finished_at = utcnow()
            decisions.append({"run_id": run.id, "stage": job.stage, "decision": decision})
        s.commit()
    finally:
        s.close()

    # Start the chains only after the rows are committed.
    for d in decisions:
        if d["decision"] == "requeued":
            runner.submit(d["run_id"])
        elif d["decision"] == "resumed":
            index = _stage_index(runner, d["run_id"], d["stage"])
            runner.resume(d["run_id"], index, d.pop("_inherit"))
        elif d["decision"] in ("completed", "overrides_reapplied"):
            index = _stage_index(runner, d["run_id"], d["stage"])
            runner.resume(d["run_id"], index + 1, None)
    for d in decisions:
        d.pop("_inherit", None)
        logger.info("reconcile: run %s stage %s -> %s", d["run_id"], d["stage"], d["decision"])
    return decisions


def _stage_index(runner: JobRunner, run_id: str, stage: str) -> int:
    return [spec.stage for spec in runner.plan_stages(run_id)].index(stage)


def _fail(run: Run, stage: str, reason: str, log_tail: str, session) -> None:
    run.status = "failed"; run.finished_at = utcnow()
    run.summary_json = json.dumps({"stage": stage, "reason": reason, "exit_code": None, "log_tail": log_tail})
