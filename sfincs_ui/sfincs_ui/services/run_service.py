"""Launch, list, inspect and control runs. Every path enforces access control (spec section 5)."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from sfincs_ui.config import Config
from sfincs_ui.exceptions import LaunchRefused, NotAllowed, NotFound
from sfincs_ui.models import ACTIVE_JOB_STATUSES, Project, Run, new_id
from sfincs_ui.services import access_control as ac
from sfincs_ui.services.job_runner import LOG_NAMES, JobRunner
from sfincs_ui.services.model_service import write_settings
from sfincs_ui.services.progress import parse_progress, tail_lines
from sfincs_ui.services.project_service import ProjectService
from sfincs_ui.services.settings_service import SettingsService

DOWNLOADS = ("sfincs_his.nc", "sfincs.inp", "settings.json", "overrides.diff")
MAX_NAME = 100


def free_space_gb(path: Path) -> float:
    return shutil.disk_usage(path).free / 1e9


class RunService:
    def __init__(self, config: Config, settings_service: SettingsService, project_service: ProjectService,
                 runner: JobRunner, session_factory=None, templates=None):
        if session_factory is None:
            from sfincs_ui.db.base import get_session_factory
            session_factory = get_session_factory()
        if templates is None:
            from sfincs_ui.templates import TEMPLATES
            templates = TEMPLATES
        self._config = config
        self._settings = settings_service
        self._projects = project_service
        self._runner = runner
        self._sf = session_factory
        self._templates = templates

    # -- dict shape --------------------------------------------------------

    def _to_dict(self, r: Run, session) -> dict:
        p = session.get(Project, r.project_id)
        return {"id": r.id, "project_id": r.project_id, "project_name": p.name if p else "?", "owner_id": p.owner_id if p else None,
                "name": r.name, "status": r.status, "threads": r.threads, "public": r.public, "pinned": r.pinned,
                "created_at": r.created_at, "started_at": r.started_at, "finished_at": r.finished_at, "exit_code": r.exit_code,
                "summary": json.loads(r.summary_json) if r.summary_json else None, "workdir": r.workdir,
                "stages": [{"stage": j.stage, "status": j.status, "started_at": j.started_at, "finished_at": j.finished_at,
                            "exit_code": j.exit_code} for j in r.jobs]}

    def _load(self, session, run_id: str) -> Run:
        r = session.get(Run, run_id)
        if r is None:
            raise NotFound("Run not found")
        return r

    def _viewable(self, user, run_id) -> dict:
        s = self._sf()
        try:
            d = self._to_dict(self._load(s, run_id), s)
        finally:
            s.close()
        ac.require_view_run(user, d)
        return d

    def _modifiable(self, user, run_id) -> dict:
        s = self._sf()
        try:
            d = self._to_dict(self._load(s, run_id), s)
        finally:
            s.close()
        ac.require_modify_run(user, d)
        return d

    # -- launch ------------------------------------------------------------

    def launch(self, user: dict | None, project_id: str, name: str, threads: int) -> dict:
        ac.require_user(user)
        project = self._projects.get(user, project_id)  # require_use_project
        name = (name or "").strip()
        if not name or len(name) > MAX_NAME:
            raise LaunchRefused(f"Run name must be 1-{MAX_NAME} characters")
        cap = self._settings.get("max_threads")
        try:
            threads = int(threads)
        except (TypeError, ValueError):
            raise LaunchRefused("Threads must be a whole number") from None
        if not 1 <= threads <= cap:
            raise LaunchRefused(f"Threads must be between 1 and {cap} (the server cap)")
        free = free_space_gb(self._config.workspace)
        if free < self._config.min_free_gb:
            raise LaunchRefused(f"Launch refused: {free:.1f} GB free on the workspace volume, below the floor of {self._config.min_free_gb} GB")
        template = self._templates[project["template"]]
        settings = template.validate(project["settings"])
        run_id = new_id()
        run_dir = self._projects.project_dir(project_id) / run_id
        write_settings(run_dir, settings)  # may raise (disk full, permissions): nothing is in the DB yet
        s = self._sf()
        try:
            r = Run(id=run_id, project_id=project_id, name=name, status="queued", settings_json=json.dumps(settings),
                    workdir=str(run_dir), threads=threads)
            s.add(r); s.commit()
            d = self._to_dict(r, s)
        finally:
            s.close()
        try:
            self._runner.submit(run_id)
        except Exception:
            s = self._sf()
            try:
                row = s.get(Run, run_id)
                if row is not None:
                    s.delete(row); s.commit()
            finally:
                s.close()
            shutil.rmtree(run_dir, ignore_errors=True)
            raise
        return d

    # -- reads -------------------------------------------------------------

    def list_for(self, user: dict | None) -> list[dict]:
        if not user:
            return []
        s = self._sf()
        try:
            q = s.query(Run)
            if not ac.is_admin(user):
                q = q.join(Project, Run.project_id == Project.id).filter(Project.owner_id == user["id"])
            return [self._to_dict(r, s) for r in q.order_by(Run.created_at.desc()).all()]
        finally:
            s.close()

    def running_jobs(self, user: dict | None) -> list[dict]:
        if not ac.is_admin(user):
            raise NotAllowed("Administrator access required")
        return self._runner.active_jobs()

    def get(self, user: dict | None, run_id: str) -> dict:
        return self._viewable(user, run_id)

    def log_tail(self, user: dict | None, run_id: str, n: int = 50) -> tuple[str | None, str]:
        d = self._viewable(user, run_id)
        stages = d["stages"]
        active = [st for st in stages if st["status"] in ACTIVE_JOB_STATUSES]
        current = (active or stages or [None])[-1]
        if current is None:
            return None, ""
        return current["stage"], tail_lines(Path(d["workdir"]) / LOG_NAMES[current["stage"]], n)

    def progress(self, user: dict | None, run_id: str) -> dict | None:
        d = self._viewable(user, run_id)
        return parse_progress(tail_lines(Path(d["workdir"]) / "sfincs.log", 400))

    def download_path(self, user: dict | None, run_id: str, name: str) -> Path:
        d = self._viewable(user, run_id)
        if name not in DOWNLOADS:
            raise NotFound(f"{name} is not downloadable")
        path = Path(d["workdir"]) / name
        if not path.is_file():
            raise NotFound(f"{name} is not available for this run")
        return path

    # -- mutations ---------------------------------------------------------

    async def cancel(self, user: dict | None, run_id: str) -> None:
        self._modifiable(user, run_id)
        await self._runner.cancel(run_id)

    def set_pinned(self, user: dict | None, run_id: str, flag: bool) -> dict:
        return self._set_flag(user, run_id, "pinned", bool(flag))

    def set_public(self, user: dict | None, run_id: str, flag: bool) -> dict:
        return self._set_flag(user, run_id, "public", bool(flag))

    def _set_flag(self, user, run_id, attr, value) -> dict:
        self._modifiable(user, run_id)
        s = self._sf()
        try:
            r = self._load(s, run_id); setattr(r, attr, value); s.commit()
            return self._to_dict(r, s)
        finally:
            s.close()
