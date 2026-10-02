"""Create project and run rows directly for runner tests."""

from __future__ import annotations

import json
from pathlib import Path

from sfincs_ui.models import Job, Project, Run, User, new_id
from sfincs_ui.services.model_service import write_settings


def make_user(session_factory, username="owner", role="user") -> int:
    s = session_factory()
    try:
        u = User(username=username, password_hash="x", role=role, is_active=True)
        s.add(u); s.commit()
        return u.id
    finally:
        s.close()


def make_run(session_factory, workspace: Path, template_key: str, settings: dict, *, owner_id: int | None = None,
             threads: int = 1, name: str = "run") -> str:
    """Project + run rows with the run directory and settings.json in place (what RunService.launch does)."""
    s = session_factory()
    try:
        p = Project(id=new_id(), owner_id=owner_id, name="proj", template=template_key, settings_json=json.dumps(settings))
        s.add(p); s.flush()
        run_dir = workspace / p.id / new_id()
        r = Run(id=run_dir.name, project_id=p.id, name=name, status="queued", settings_json=json.dumps(settings),
                workdir=str(run_dir), threads=threads)
        s.add(r); s.commit()
        write_settings(run_dir, settings)
        return r.id
    finally:
        s.close()


def run_row(session_factory, run_id: str) -> dict:
    s = session_factory()
    try:
        r = s.get(Run, run_id)
        jobs = [{"stage": j.stage, "status": j.status, "pid": j.pid, "exit_code": j.exit_code, "log_path": j.log_path}
                for j in s.query(Job).filter_by(run_id=run_id).order_by(Job.id).all()]
        return {"status": r.status, "exit_code": r.exit_code, "summary": json.loads(r.summary_json) if r.summary_json else None,
                "workdir": Path(r.workdir), "started_at": r.started_at, "finished_at": r.finished_at, "jobs": jobs}
    finally:
        s.close()
