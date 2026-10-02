import uuid

from sqlalchemy import inspect, text

from sfincs_ui.db import base
from sfincs_ui.models import ACTIVE_JOB_STATUSES, JOB_STAGES, RUN_STATUSES, Job, Project, Run, User, new_id


def test_tables_and_head(db):
    tables = set(inspect(base.get_engine()).get_table_names())
    assert {"projects", "runs", "jobs"} <= tables
    with base.get_engine().connect() as conn:
        assert conn.execute(text("SELECT version_num FROM alembic_version")).scalar() == "0002_projects_runs_jobs"


def test_new_id_is_uuid4_string():
    value = new_id()
    assert isinstance(value, str) and len(value) == 36 and uuid.UUID(value).version == 4


def test_project_run_job_round_trip_and_cascades(db):
    s = db()
    try:
        u = User(username="owner", password_hash="x", role="user", is_active=True)
        s.add(u); s.flush()
        p = Project(id=new_id(), owner_id=u.id, name="P", template="plane_beach", settings_json="{}")
        s.add(p); s.flush()
        r = Run(id=new_id(), project_id=p.id, name="r1", status="queued", settings_json="{}", workdir="/tmp/x", threads=2)
        s.add(r); s.flush()
        j = Job(run_id=r.id, stage="build", status="pending", log_path="/tmp/x/build.log")
        s.add(j); s.commit()
        assert r.public is False and r.pinned is False and r.exit_code is None
        assert j.pid is None and j.proc_starttime is None
        s.delete(p); s.commit()
        assert s.query(Run).count() == 0 and s.query(Job).count() == 0
    finally:
        s.close()


def test_deleting_owner_keeps_project_as_system_owned(db):
    s = db()
    try:
        u = User(username="owner2", password_hash="x", role="user", is_active=True)
        s.add(u); s.flush()
        p = Project(id=new_id(), owner_id=u.id, name="P2", template="plane_beach", settings_json="{}")
        s.add(p); s.commit()
        s.delete(u); s.commit()
        assert s.get(Project, p.id).owner_id is None
    finally:
        s.close()


def test_vocabularies():
    assert "orphaned" in RUN_STATUSES and "orphaned" not in ACTIVE_JOB_STATUSES
    assert JOB_STAGES == ("build", "simulate", "validate", "export")
