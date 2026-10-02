"""Run a run's stage chain as detached subprocesses (spec section 3).

Every stage is spawned in its own session with its output in a log file,
its pid and /proc start time recorded before it is awaited, and judged by
on-disk evidence when it ends. One monitor loop serves fresh processes
(Popen handle, exit code) and inherited ones after a restart (pid only,
exit code unknown). Cancelling the asyncio task never signals the child;
only cancel() does.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from sfincs_ui.config import Config
from sfincs_ui.models import ACTIVE_JOB_STATUSES, RUN_STATUS_FOR_STAGE, Job, Project, Run
from sfincs_ui.services.model_service import read_settings, write_overrides
from sfincs_ui.services.procs import is_alive, killpg_graceful, proc_starttime
from sfincs_ui.services.progress import FINISHED_LINE, tail_lines
from sfincs_ui.services.settings_service import SettingsService
from sfincs_ui.templates.base import Template
from sfincs_ui.timeutil import utcnow

logger = logging.getLogger(__name__)

LOG_NAMES = {"build": "build.log", "simulate": "sfincs.log", "validate": "validate.log", "export": "export.log"}
# The solver opens and truncates sfincs.log itself; its stdout must not share that file.
STDOUT_NAMES = {**LOG_NAMES, "simulate": "simulate.log"}
SUMMARY_TAIL = 50
OVERRIDES_DIFF = "overrides.diff"


@dataclass
class StageSpec:
    stage: str
    argv: list[str]
    cwd: Path
    env: dict[str, str]
    log_path: Path       # read for progress, evidence and the failure summary
    stdout_path: Path    # child's stdout+stderr; equals log_path except for simulate
    evidence: Callable[[], bool]


# -- evidence (spec section 3) ------------------------------------------------

def build_evidence(run_dir: Path, template: Template) -> bool:
    return (run_dir / "sfincs.inp").is_file() and all((run_dir / f).is_file() for f in template.model_files()) \
        and (run_dir / OVERRIDES_DIFF).is_file()


def simulate_evidence(run_dir: Path) -> bool:
    return (run_dir / "sfincs_his.nc").is_file() and FINISHED_LINE in tail_lines(run_dir / "sfincs.log", 200)


def validate_evidence(run_dir: Path) -> bool:
    return (run_dir / "validation" / "validation.md").is_file()


def export_evidence(run_dir: Path) -> bool:
    return (run_dir / "validation" / "map_meta.json").is_file()


def evidence_for(stage: str, run_dir: Path, template: Template) -> Callable[[], bool]:
    return {
        "build": lambda: build_evidence(run_dir, template),
        "simulate": lambda: simulate_evidence(run_dir),
        "validate": lambda: validate_evidence(run_dir),
        "export": lambda: export_evidence(run_dir),
    }[stage]


class JobRunner:
    def __init__(self, config: Config, settings_service: SettingsService, session_factory=None, *,
                 templates: dict[str, Template] | None = None, reconciler=None, poll_interval: float = 0.5,
                 grace_s: float = 30.0, aux_cap: int = 2):
        if session_factory is None:
            from sfincs_ui.db.base import get_session_factory
            session_factory = get_session_factory()
        if templates is None:
            from sfincs_ui.templates import TEMPLATES
            templates = TEMPLATES
        self._config = config
        self._settings = settings_service
        self._sf = session_factory
        self._templates = templates
        self._reconciler = reconciler
        self._poll = poll_interval
        self._grace = grace_s
        self._aux_cap = aux_cap
        self._tasks: dict[str, asyncio.Task] = {}
        self._procs: dict[str, subprocess.Popen] = {}  # live Popen handles, reaped after cancel
        self._claim_lock = asyncio.Lock()
        self.spawned_pids: set[int] = set()
        self.started = False

    # -- lifecycle ---------------------------------------------------------

    async def start(self) -> None:
        if self._reconciler is not None:
            self._reconciler(self)
        self.started = True

    async def stop(self) -> None:
        """Cancel the asyncio tasks only. Children keep running and are reconciled next start."""
        tasks = list(self._tasks.values())
        for t in tasks:
            t.cancel()
        for t in tasks:
            try:
                await t
            except (asyncio.CancelledError, Exception):
                pass
        self._tasks.clear()
        self.started = False

    def submit(self, run_id: str) -> asyncio.Task:
        return self.resume(run_id, 0, None)

    def resume(self, run_id: str, stage_index: int, inherited: tuple[int, int] | None) -> asyncio.Task:
        task = asyncio.get_running_loop().create_task(self._run_chain(run_id, stage_index, inherited), name=f"chain:{run_id}")
        self._tasks[run_id] = task
        task.add_done_callback(lambda t: self._tasks.pop(run_id, None) if self._tasks.get(run_id) is t else None)
        return task

    async def wait(self, run_id: str, timeout: float) -> None:
        task = self._tasks.get(run_id)
        if task is not None:
            await asyncio.wait_for(asyncio.shield(task), timeout)

    # -- planning ----------------------------------------------------------

    def _load(self, run_id: str) -> tuple[Run, Project, Template, dict, Path]:
        s = self._sf()
        try:
            run = s.get(Run, run_id)
            if run is None:
                raise LookupError(run_id)
            project = s.get(Project, run.project_id)
            s.expunge(run); s.expunge(project)
        finally:
            s.close()
        template = self._templates[project.template]
        run_dir = Path(run.workdir)
        settings = read_settings(run_dir) if (run_dir / "settings.json").exists() else json.loads(run.settings_json)
        return run, project, template, settings, run_dir

    def plan_stages(self, run_id: str) -> list[StageSpec]:
        run, _project, template, settings, run_dir = self._load(run_id)
        base_env = {k: v for k, v in os.environ.items()}

        def spec(stage: str, argv: list[str], cwd: Path, env: dict[str, str]) -> StageSpec:
            return StageSpec(stage, argv, cwd, env, run_dir / LOG_NAMES[stage], run_dir / STDOUT_NAMES[stage],
                             evidence_for(stage, run_dir, template))

        specs = [spec("build", template.build_command(run_dir, settings, self._config),
                      template.stage_cwd("build", run_dir, self._config), base_env)]
        specs.append(spec("simulate", [str(self._config.sfincs_bin)], run_dir, {**base_env, "OMP_NUM_THREADS": str(run.threads)}))
        vcmd = template.validate_command(run_dir, settings, self._config)
        if vcmd:
            specs.append(spec("validate", vcmd, template.stage_cwd("validate", run_dir, self._config), base_env))
        ecmd = template.export_command(run_dir, settings, self._config)
        if ecmd:
            specs.append(spec("export", ecmd, template.stage_cwd("export", run_dir, self._config), base_env))
        return specs

    # -- chain -------------------------------------------------------------

    async def _run_chain(self, run_id: str, start_index: int, inherited: tuple[int, int] | None) -> None:
        try:
            specs = self.plan_stages(run_id)
        except Exception:
            logger.exception("cannot plan stages for run %s", run_id)
            self._fail_run(run_id, "plan", "cannot plan stages", None, "")
            return
        for index in range(start_index, len(specs)):
            spec = specs[index]
            try:
                ok = await self._run_stage(run_id, spec, inherited if index == start_index else None)
            except asyncio.CancelledError:
                raise  # uvicorn shutdown: leave the child and the rows alone for reconciliation
            except Exception as exc:
                logger.exception("stage %s of run %s raised", spec.stage, run_id)
                self._fail_run(run_id, spec.stage, f"internal error: {exc}", None, tail_lines(spec.log_path, SUMMARY_TAIL))
                return
            if not ok:
                return
        self._finish_run(run_id)

    async def _run_stage(self, run_id: str, spec: StageSpec, inherited: tuple[int, int] | None) -> bool:
        _run, _p, template, settings, run_dir = self._load(run_id)
        if inherited is None:
            job_id = self._create_job(run_id, spec)
            await self._claim(run_id, job_id, spec.stage)
            if self._run_status(run_id) == "cancelled":
                return False
            try:
                proc, pid, starttime = self._spawn(spec)
                self._procs[run_id] = proc
                self._record_pid(job_id, pid, starttime)
            except Exception:
                self._fail_job(job_id, None)  # release the capacity slot before the chain fails the run
                raise
        else:
            job_id = self._active_job_id(run_id, spec.stage)
            proc, (pid, starttime) = None, inherited
        try:
            exit_code = await self._monitor(pid, starttime, proc)
        finally:
            self._procs.pop(run_id, None)
        if self._run_status(run_id) == "cancelled":
            return False
        if spec.stage == "build" and exit_code in (0, None):
            try:
                write_overrides(run_dir, template.inp_overrides(settings))
            except Exception as exc:  # the inp is missing or unreadable: the build did not really succeed
                logger.warning("overrides for run %s failed: %s", run_id, exc)
        if exit_code in (0, None) and spec.evidence():
            self._complete_job(job_id, exit_code)
            return True
        reason = "no completion evidence" if exit_code in (0, None) else f"exit code {exit_code}"
        self._fail_job(job_id, exit_code)
        self._fail_run(run_id, spec.stage, reason, exit_code, tail_lines(spec.log_path, SUMMARY_TAIL))
        return False

    async def _claim(self, run_id: str, job_id: int, stage: str) -> None:
        """Wait for capacity, then mark the job running (under the lock, so two chains cannot both claim)."""
        while True:
            async with self._claim_lock:
                if self._run_status(run_id) == "cancelled":
                    self._cancel_job(job_id)  # otherwise active-jobs would report this row forever
                    return
                if self._has_capacity(stage):
                    s = self._sf()
                    try:
                        job = s.get(Job, job_id); run = s.get(Run, run_id)
                        job.status = "running"; job.started_at = utcnow()
                        run.status = RUN_STATUS_FOR_STAGE[stage]
                        if run.started_at is None:
                            run.started_at = utcnow()
                        s.commit()
                    finally:
                        s.close()
                    return
            await asyncio.sleep(self._poll)

    def _has_capacity(self, stage: str) -> bool:
        s = self._sf()
        try:
            if stage == "simulate":
                running = s.query(Job).filter(Job.stage == "simulate", Job.status == "running").count()
                return running < self._settings.get("max_simulations")
            running = s.query(Job).filter(Job.stage != "simulate", Job.status == "running").count()
            return running < self._aux_cap
        finally:
            s.close()

    def _spawn(self, spec: StageSpec) -> tuple[subprocess.Popen, int, int | None]:
        spec.cwd.mkdir(parents=True, exist_ok=True)
        log = open(spec.stdout_path, "ab")  # the child owns this descriptor; closing ours is fine after spawn
        try:
            proc = subprocess.Popen(spec.argv, cwd=str(spec.cwd), env=spec.env, stdout=log, stderr=subprocess.STDOUT,
                                    stdin=subprocess.DEVNULL, start_new_session=True)
        finally:
            log.close()
        self.spawned_pids.add(proc.pid)
        return proc, proc.pid, proc_starttime(proc.pid)

    async def _monitor(self, pid: int, starttime: int | None, proc: subprocess.Popen | None) -> int | None:
        """Poll until the process is gone. Never catches CancelledError: a cancelled task leaves the child alone."""
        while True:
            if proc is not None:
                rc = proc.poll()
                if rc is not None:
                    return rc
            elif not is_alive(pid, starttime):
                return None
            await asyncio.sleep(self._poll)

    async def cancel(self, run_id: str) -> None:
        s = self._sf()
        try:
            run = s.get(Run, run_id)
            if run is None or run.status in ("finished", "failed", "cancelled", "orphaned"):
                return
            run.status = "cancelled"; run.finished_at = utcnow()
            active = [(j.id, j.pid, j.proc_starttime) for j in run.jobs if j.status in ACTIVE_JOB_STATUSES]
            s.commit()
        finally:
            s.close()
        for _jid, pid, st in active:
            if pid and is_alive(pid, st):
                await asyncio.to_thread(killpg_graceful, pid, self._grace)
        proc = self._procs.pop(run_id, None)
        if proc is not None:  # reap, so the pid is not left as a zombie
            try:
                await asyncio.to_thread(proc.wait, 5)
            except subprocess.TimeoutExpired:
                logger.warning("process %s of run %s did not exit after SIGKILL", proc.pid, run_id)
        s = self._sf()  # free the capacity slots only now that the processes are gone
        try:
            for jid, _pid, _st in active:
                job = s.get(Job, jid)
                if job is not None:
                    job.status = "cancelled"; job.finished_at = utcnow()
            s.commit()
        finally:
            s.close()
        task = self._tasks.get(run_id)
        if task is not None:
            task.cancel()

    # -- queries -----------------------------------------------------------

    def active_jobs(self) -> list[dict]:
        s = self._sf()
        try:
            rows = (s.query(Job, Run).join(Run, Job.run_id == Run.id)
                    .filter(Job.status.in_(ACTIVE_JOB_STATUSES)).order_by(Job.id).all())
            return [{"job_id": j.id, "run_id": r.id, "run_name": r.name, "stage": j.stage, "status": j.status,
                     "pid": j.pid, "proc_starttime": j.proc_starttime, "started_at": j.started_at, "workdir": r.workdir}
                    for j, r in rows]
        finally:
            s.close()

    # -- row helpers -------------------------------------------------------

    def _run_status(self, run_id: str) -> str | None:
        s = self._sf()
        try:
            run = s.get(Run, run_id)
            return run.status if run else None
        finally:
            s.close()

    def _create_job(self, run_id: str, spec: StageSpec) -> int:
        s = self._sf()
        try:
            job = Job(run_id=run_id, stage=spec.stage, status="queued", log_path=str(spec.log_path))
            s.add(job); s.commit()
            return job.id
        finally:
            s.close()

    def _active_job_id(self, run_id: str, stage: str) -> int:
        s = self._sf()
        try:
            job = (s.query(Job).filter(Job.run_id == run_id, Job.stage == stage, Job.status.in_(ACTIVE_JOB_STATUSES))
                   .order_by(Job.id.desc()).first())
            if job is None:
                job = Job(run_id=run_id, stage=stage, status="running", log_path="", started_at=utcnow())
                s.add(job); s.commit()
            return job.id
        finally:
            s.close()

    def _record_pid(self, job_id: int, pid: int, starttime: int | None) -> None:
        s = self._sf()
        try:
            job = s.get(Job, job_id); job.pid = pid; job.proc_starttime = starttime; s.commit()
        finally:
            s.close()

    def _cancel_job(self, job_id: int) -> None:
        s = self._sf()
        try:
            job = s.get(Job, job_id); job.status = "cancelled"; job.finished_at = utcnow(); s.commit()
        finally:
            s.close()

    def _complete_job(self, job_id: int, exit_code: int | None) -> None:
        s = self._sf()
        try:
            job = s.get(Job, job_id); job.status = "completed"; job.exit_code = exit_code; job.finished_at = utcnow(); s.commit()
        finally:
            s.close()

    def _fail_job(self, job_id: int, exit_code: int | None) -> None:
        s = self._sf()
        try:
            job = s.get(Job, job_id); job.status = "failed"; job.exit_code = exit_code; job.finished_at = utcnow(); s.commit()
        finally:
            s.close()

    def _fail_run(self, run_id: str, stage: str, reason: str, exit_code: int | None, log_tail: str) -> None:
        s = self._sf()
        try:
            run = s.get(Run, run_id)
            if run is None or run.status == "cancelled":
                return
            run.status = "failed"; run.finished_at = utcnow(); run.exit_code = exit_code
            run.summary_json = json.dumps({"stage": stage, "reason": reason, "exit_code": exit_code, "log_tail": log_tail})
            s.commit()
        finally:
            s.close()

    def _finish_run(self, run_id: str) -> None:
        s = self._sf()
        try:
            run = s.get(Run, run_id)
            if run is None or run.status == "cancelled":
                return
            codes = [j.exit_code for j in run.jobs]
            run.status = "finished"; run.finished_at = utcnow()
            run.exit_code = None if any(c is None for c in codes) else 0
            s.commit()
        finally:
            s.close()
