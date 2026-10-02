# SFINCS UI Milestone 2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A logged-in user creates a plane-beach project, edits its settings, launches a run, watches it build and simulate, downloads `sfincs_his.nc`, and the run survives `systemctl restart sfincs-ui` mid-simulation.

**Architecture:** Three new tables (projects, runs, jobs). A template interface answers the spec's five questions; the plane-beach template is the first implementation, built by a standalone numpy script. A job runner inside the uvicorn process launches every stage as a detached subprocess (own session, log file, pid and `/proc` start time recorded), monitors fresh and inherited processes through one `/proc`-polling loop, judges completion from on-disk evidence, and reconciles left-over jobs at startup. Services (project, run, access control) are plain Python over SQLAlchemy; three new pages (Projects, Setup, Runs) follow the milestone 1 pattern of re-validated identity on every call.

**Tech Stack:** as milestone 1: Python 3.13 in `/opt/micromamba/envs/shiny` (shiny 1.8.0, sqlalchemy 2.0.50, alembic 1.18.4, pydantic-settings 2.14.1, httpx 0.28.1, pytest 9 with asyncio auto mode, numpy, netCDF4, psutil 7.2). Bash for the deploy script. The SFINCS binary at `sfincs-linux/bin/sfincs`.

**Spec:** `docs/superpowers/specs/2026-09-30-sfincs-ui-design.md`, sections 1 (template interface), 2 (projects, runs, tables), 3 (job execution), 4 (Projects, Setup, Runs pages), 5 (access rules, errors), 6 (tests, milestone 2). Milestone 1's plan (`docs/superpowers/plans/2026-10-01-sfincs-ui-milestone-1.md`) defines the code this plan extends.

## Global Constraints

- **Interpreter and tests.** Every Python command runs with `/opt/micromamba/envs/shiny/bin/python`. Never `pip install` anything into that env. Test command: `cd /home/razinka/sfincs/sfincs_ui && /opt/micromamba/envs/shiny/bin/python -m pytest -q`. Milestone 1 ends at 117 passing tests; each task states the expected count after it.
- **Layout.** Spec path `sfincs_ui/<x>` means `sfincs_ui/sfincs_ui/<x>`; the outer `sfincs_ui/` holds `pyproject.toml`, `alembic.ini`, `tests/`.
- **No changes to `app/` or `deploy/deploy.sh`.** `git diff --stat main -- app/ deploy/deploy.sh` must be empty at the end.
- **Identity.** `current_user()` is re-validated on every call (milestone 1 fix wave); every mutation in a page server calls it first; services enforce `can_view_run` / `can_modify_run` / `can_modify_project` and raise `NotAllowed`. Pages show notifications, never tracebacks.
- **Process lifetime (spec section 3).** Every stage subprocess is launched with `start_new_session=True`, stdout and stderr redirected to the stage's log file, **never `subprocess.PIPE`**; its pid and `/proc/<pid>/stat` field 22 (start time, parsed after the last `)`) are stored in `jobs` before the stage is awaited. `except asyncio.CancelledError` never signals a child; only `cancel()` does (SIGTERM to the process group, SIGKILL after 30 s). Model-env stages run with `cwd=CURONIAN_DIR`; `simulate` runs with cwd = run directory and `OMP_NUM_THREADS=<threads>`.
- **Completion evidence** (spec section 3): build = `sfincs.inp` plus the template's model files plus `overrides.diff`; simulate = `sfincs_his.nc` present and the line `---------- Simulation finished -----------` in `sfincs.log` (verified present in every log on this host, test model and Curonian runs alike); validate = `validation.md`; export = `map_meta.json`.
- **Queue policy** comes from `SettingsService.get("max_simulations")` and `get("max_threads")` at decision time, never cached; builds, validations and exports share a cap of 2. A launch is refused with the current numbers when free space on the workspace volume is below `MIN_FREE_GB`.
- **Tests never leave a process running.** Every test that spawns or fakes a stage registers the pid for teardown kill (`killpg` on the process group). Test fakes are shell scripts under `tests/fixtures/` and are themselves exercised by the tests.
- **Builder scripts are standalone.** The plane-beach builder has no `sfincs_ui` imports and is invoked by absolute path: `[sys.executable, "-P", str(Path(plane_beach_build.__file__)), ...]`, so it works from the source tree in tests and from the editable prod install alike.
- **Run directories** live at `<workspace>/<project_id>/<run_id>/`; nothing is ever written under `curonian/runs` or `curonian/results`.
- **Database.** Hand-written migration `0002_projects_runs_jobs`; `python -m alembic -c alembic.ini check` prints "No new upgrade operations detected." Project and run ids are `String(36)` UUID4 strings.
- **Commits** end with `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`.

## Review Focus

Input classes the spec implies but no task's tests exercised at first draft. Each line's test is added to the owning task.

1. **A deploy restart during `simulate`.** Expected: the solver keeps running, the restarted queue finds the live pid with the recorded start time, resumes monitoring, and the run finishes with `exit_code` NULL. Test in Task 6 (`test_reconcile_alive_process_is_resumed`), acceptance in Task 11.
2. **A build that writes the model files but dies before `overrides.diff`.** Expected: reconciliation re-applies the overrides from `settings.json` and continues the chain. Test in Task 6 (`test_reconcile_build_without_overrides_reapplies`).
3. **Two launches racing `max_simulations = 1`.** Expected: exactly one simulate stage runs at a time; the second waits in `queued`. Test in Task 5 (`test_simulate_cap_is_respected_by_concurrent_chains`).
4. **A run directory deleted while its job row is active.** Expected: the job and run become `orphaned`, nothing crashes. Test in Task 6 (`test_reconcile_missing_directory_is_orphaned`).
5. **A user acting on another user's run** (cancel, pin, publish, download, log tail). Expected: `NotAllowed` and nothing changes; an admin may. Tests in Task 2 (`test_can_modify_run_matrix`) and Task 7 (`test_cancel_other_users_run_refused`, `test_download_path_other_users_private_run_refused`).

## File structure

```
sfincs_ui/sfincs_ui/
  models/project.py                 Project, Run, Job, status/stage vocabularies
  migrations/versions/0002_projects_runs_jobs.py
  exceptions.py                     NotAllowed, QueueFull, QuotaExceeded, TemplateError, BuildError, LaunchRefused
  services/access_control.py        can_view_run, can_modify_run, can_modify_project, require_*
  templates/__init__.py             TEMPLATES registry, get_template
  templates/base.py                 SettingField, Template
  templates/plane_beach.py          PlaneBeachTemplate
  templates/plane_beach_build.py    standalone builder script (numpy only)
  services/model_service.py         write_settings, apply_overrides, write_overrides, read_settings
  services/procs.py                 proc_starttime, is_alive, killpg_graceful
  services/progress.py              parse_progress, tail_lines
  services/job_runner.py            StageSpec, JobRunner (spawn, monitor, chain, cancel, capacity)
  services/reconcile.py             reconcile(runner) at startup
  services/project_service.py       ProjectService
  services/run_service.py           RunService
  middleware/lifespan.py            LifespanMiddleware(on_startup, on_shutdown)
  pages/projects.py, pages/setup.py, pages/runs.py
  __main__.py                       + active-jobs, kill-jobs
  app.py                            wires runner, services, pages
sfincs_ui/tests/
  fixtures/fake_build.sh, fixtures/fake_sfincs.sh, fake_template.py
  test_models_projects.py, test_access_control.py, test_templates.py, test_plane_beach_build.py,
  test_model_service.py, test_procs_progress.py, test_job_runner.py, test_reconcile.py,
  test_project_service.py, test_run_service.py, test_cli_jobs.py, test_pages_m2.py,
  test_app_http_m2.py, test_e2e_plane_beach.py
deploy/deploy_ui.sh                 MILESTONE 2 markers replaced (active-jobs warn/--wait, kill-jobs on uninstall)
sfincs_ui/README.md, deploy/README.md
```

---

### Task 1: Projects, runs and jobs tables

**Files:**
- Create: `sfincs_ui/sfincs_ui/models/project.py`
- Modify: `sfincs_ui/sfincs_ui/models/__init__.py`
- Modify: `sfincs_ui/sfincs_ui/migrations/env.py` (import the new module)
- Create: `sfincs_ui/sfincs_ui/migrations/versions/0002_projects_runs_jobs.py`
- Test: `sfincs_ui/tests/test_models_projects.py`
- Modify: `sfincs_ui/tests/test_db_init.py` (head revision is now `0002_projects_runs_jobs`; table set grows)

**Interfaces:**
- Consumes: `Base`, `User` (milestone 1).
- Produces: `Project(id: str uuid, owner_id: int|None FK users SET NULL, name, template, settings_json, created_at, updated_at)`; `Run(id: str uuid, project_id FK CASCADE, name, status, settings_json, workdir, threads, public, pinned, created_at, started_at, finished_at, exit_code: int|None, summary_json: str|None)`; `Job(id int, run_id FK CASCADE, stage, status, pid: int|None, proc_starttime: int|None, log_path, created_at, started_at, finished_at, exit_code: int|None)`. Vocabularies: `RUN_STATUSES = ("queued","building","running","validating","exporting","finished","failed","cancelled","orphaned")`, `JOB_STAGES = ("build","simulate","validate","export")`, `JOB_STATUSES = ("pending","queued","running","completed","failed","cancelled","orphaned")`, `ACTIVE_JOB_STATUSES = ("pending","queued","running")`, `new_id() -> str`.

- [ ] **Step 1: Write the failing tests**

`sfincs_ui/tests/test_models_projects.py`:

```python
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
    assert "orphaned" in RUN_STATUSES and "orphaned" in ACTIVE_JOB_STATUSES is False
    assert JOB_STAGES == ("build", "simulate", "validate", "export")
```

Update `sfincs_ui/tests/test_db_init.py`: the head assertion becomes `== "0002_projects_runs_jobs"` and the required table set gains `"projects", "runs", "jobs"`.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd /home/razinka/sfincs/sfincs_ui && /opt/micromamba/envs/shiny/bin/python -m pytest tests/test_models_projects.py tests/test_db_init.py -q`
Expected: FAIL with `ImportError: cannot import name 'Project'` and the head assertion.

- [ ] **Step 3: Write the models**

`sfincs_ui/sfincs_ui/models/project.py`:

```python
"""Projects (template + settings), runs (immutable snapshots) and their stage jobs."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from sfincs_ui.db.base import Base

RUN_STATUSES = ("queued", "building", "running", "validating", "exporting", "finished", "failed", "cancelled", "orphaned")
JOB_STAGES = ("build", "simulate", "validate", "export")
JOB_STATUSES = ("pending", "queued", "running", "completed", "failed", "cancelled", "orphaned")
ACTIVE_JOB_STATUSES = ("pending", "queued", "running")
# runs.status while a stage runs, by stage
RUN_STATUS_FOR_STAGE = {"build": "building", "simulate": "running", "validate": "validating", "export": "exporting"}


def new_id() -> str:
    return str(uuid.uuid4())


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    owner_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    template: Mapped[str] = mapped_column(String(64), nullable=False)
    settings_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)

    runs: Mapped[list["Run"]] = relationship("Run", back_populates="project", cascade="all, delete-orphan")


class Run(Base):
    __tablename__ = "runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="queued", index=True)
    settings_json: Mapped[str] = mapped_column(Text, nullable=False)
    workdir: Mapped[str] = mapped_column(String(1024), nullable=False)
    threads: Mapped[int] = mapped_column(Integer, nullable=False)
    public: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    pinned: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    exit_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    summary_json: Mapped[str | None] = mapped_column(Text, nullable=True)

    project: Mapped["Project"] = relationship("Project", back_populates="runs")
    jobs: Mapped[list["Job"]] = relationship("Job", back_populates="run", cascade="all, delete-orphan", order_by="Job.id")


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(String(36), ForeignKey("runs.id", ondelete="CASCADE"), nullable=False, index=True)
    stage: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending", index=True)
    pid: Mapped[int | None] = mapped_column(Integer, nullable=True)
    proc_starttime: Mapped[int | None] = mapped_column(Integer, nullable=True)
    log_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    exit_code: Mapped[int | None] = mapped_column(Integer, nullable=True)

    run: Mapped["Run"] = relationship("Run", back_populates="jobs")
```

`models/__init__.py`: add `from sfincs_ui.models.project import (ACTIVE_JOB_STATUSES, JOB_STAGES, JOB_STATUSES, RUN_STATUS_FOR_STAGE, RUN_STATUSES, Job, Project, Run, new_id)` and extend `__all__`.

`migrations/env.py`: add `from sfincs_ui.models import project  # noqa: F401` (the existing guard test `test_every_model_module_is_imported_by_env_py` enforces this).

- [ ] **Step 4: Write the migration**

`sfincs_ui/sfincs_ui/migrations/versions/0002_projects_runs_jobs.py`:

```python
"""projects, runs and jobs

Revision ID: 0002_projects_runs_jobs
Revises: 0001_initial
Create Date: 2026-10-02
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0002_projects_runs_jobs"
down_revision: Union[str, Sequence[str], None] = "0001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_NOW = sa.text("(CURRENT_TIMESTAMP)")


def upgrade() -> None:
    op.create_table(
        "projects",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("owner_id", sa.Integer(), nullable=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("template", sa.String(64), nullable=False),
        sa.Column("settings_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=_NOW, nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=_NOW, nullable=False),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "runs",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("project_id", sa.String(36), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("settings_json", sa.Text(), nullable=False),
        sa.Column("workdir", sa.String(1024), nullable=False),
        sa.Column("threads", sa.Integer(), nullable=False),
        sa.Column("public", sa.Boolean(), nullable=False),
        sa.Column("pinned", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=_NOW, nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.Column("exit_code", sa.Integer(), nullable=True),
        sa.Column("summary_json", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_runs_project_id", "runs", ["project_id"])
    op.create_index("ix_runs_status", "runs", ["status"])
    op.create_table(
        "jobs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("run_id", sa.String(36), nullable=False),
        sa.Column("stage", sa.String(16), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("pid", sa.Integer(), nullable=True),
        sa.Column("proc_starttime", sa.Integer(), nullable=True),
        sa.Column("log_path", sa.String(1024), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=_NOW, nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.Column("exit_code", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["run_id"], ["runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_jobs_run_id", "jobs", ["run_id"])
    op.create_index("ix_jobs_status", "jobs", ["status"])


def downgrade() -> None:
    op.drop_table("jobs")
    op.drop_table("runs")
    op.drop_table("projects")
```

- [ ] **Step 5: Run the tests and the autogenerate check**

Run: `cd /home/razinka/sfincs/sfincs_ui && /opt/micromamba/envs/shiny/bin/python -m pytest tests/test_models_projects.py tests/test_db_init.py -q`
Expected: 9 passed

Run (from `sfincs_ui/`):
```bash
export SFINCS_UI_WORKSPACE=/tmp/claude-1000/-home-razinka-sfincs/946ef2e3-64b8-42c9-b324-8e8da9f13c98/scratchpad/ag3; mkdir -p "$SFINCS_UI_WORKSPACE"
/opt/micromamba/envs/shiny/bin/python -c "from sfincs_ui.db import base; base.init_db()"
/opt/micromamba/envs/shiny/bin/python -m alembic -c alembic.ini check
```
Expected: `No new upgrade operations detected.` If it reports a difference, fix the revision, not the models.

Run the full suite: expected 122 passed (117 + 5).

- [ ] **Step 6: Commit**

```bash
cd /home/razinka/sfincs
git add sfincs_ui/sfincs_ui/models sfincs_ui/sfincs_ui/migrations sfincs_ui/tests/test_models_projects.py sfincs_ui/tests/test_db_init.py
git commit -m "sfincs_ui: projects, runs and jobs tables (migration 0002)

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 2: Typed exceptions and access control

**Files:**
- Create: `sfincs_ui/sfincs_ui/exceptions.py`
- Create: `sfincs_ui/sfincs_ui/services/access_control.py`
- Test: `sfincs_ui/tests/test_access_control.py`

**Interfaces:**
- Produces: exceptions `SfincsUiError(Exception)` with subclasses `NotAllowed`, `QueueFull`, `QuotaExceeded`, `TemplateError`, `BuildError`, `LaunchRefused`, `NotFound`. Access control over plain dicts (`user` dict from `AuthService`, `run` dict with keys `owner_id`, `public`, and optional `baseline: bool`; `project` dict with `owner_id`): `is_admin(user)`, `can_view_run(user, run) -> bool` (public or baseline or owner or admin), `can_modify_run(user, run) -> bool` (owner or admin; a baseline is never modifiable), `can_modify_project(user, project) -> bool` (owner or admin; a system project with `owner_id None` is modifiable only by admin), `can_use_project(user, project) -> bool` (logged in and (owner or admin or system example)), and `require_view_run / require_modify_run / require_modify_project / require_use_project / require_user` raising `NotAllowed`.

- [ ] **Step 1: Write the failing tests**

`sfincs_ui/tests/test_access_control.py`:

```python
import pytest

from sfincs_ui.exceptions import NotAllowed, SfincsUiError
from sfincs_ui.services import access_control as ac

ADMIN = {"id": 1, "username": "root", "role": "admin", "is_active": True}
OWNER = {"id": 2, "username": "alice", "role": "user", "is_active": True}
OTHER = {"id": 3, "username": "bob", "role": "user", "is_active": True}


def _run(owner_id=2, public=False, baseline=False):
    return {"id": "r", "owner_id": owner_id, "public": public, "baseline": baseline}


@pytest.mark.parametrize("user,run,expected", [
    (None, _run(), False), (None, _run(public=True), True), (None, _run(baseline=True), True),
    (OTHER, _run(), False), (OTHER, _run(public=True), True),
    (OWNER, _run(), True), (ADMIN, _run(), True), (ADMIN, _run(owner_id=None), True),
])
def test_can_view_run_matrix(user, run, expected):
    assert ac.can_view_run(user, run) is expected


@pytest.mark.parametrize("user,run,expected", [
    (None, _run(), False), (OTHER, _run(), False), (OTHER, _run(public=True), False),
    (OWNER, _run(), True), (ADMIN, _run(), True), (ADMIN, _run(baseline=True), False), (OWNER, _run(baseline=True), False),
])
def test_can_modify_run_matrix(user, run, expected):
    """Review Focus 5: only the owner or an admin may act on a run; baselines never."""
    assert ac.can_modify_run(user, run) is expected


def test_project_rules():
    own = {"id": "p", "owner_id": 2}
    system = {"id": "e", "owner_id": None}
    assert ac.can_modify_project(OWNER, own) and not ac.can_modify_project(OTHER, own)
    assert ac.can_modify_project(ADMIN, system) and not ac.can_modify_project(OWNER, system)
    assert ac.can_use_project(OWNER, own) and ac.can_use_project(OTHER, system) and not ac.can_use_project(None, system)
    assert not ac.can_use_project(OTHER, own)


def test_require_helpers_raise_not_allowed():
    with pytest.raises(NotAllowed):
        ac.require_modify_run(OTHER, _run())
    with pytest.raises(NotAllowed):
        ac.require_view_run(None, _run())
    with pytest.raises(NotAllowed):
        ac.require_user(None)
    assert ac.require_user(OWNER) == OWNER
    ac.require_view_run(None, _run(public=True))  # no raise
    assert issubclass(NotAllowed, SfincsUiError)


def test_inactive_user_has_no_rights():
    inactive = {**OWNER, "is_active": False}
    assert not ac.can_modify_run(inactive, _run()) and not ac.can_view_run(inactive, _run())
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd /home/razinka/sfincs/sfincs_ui && /opt/micromamba/envs/shiny/bin/python -m pytest tests/test_access_control.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'sfincs_ui.exceptions'`

- [ ] **Step 3: Write the modules**

`sfincs_ui/sfincs_ui/exceptions.py`:

```python
"""Typed errors raised by services; pages turn them into notifications (spec section 5)."""


class SfincsUiError(Exception):
    """Base class: the message is safe to show to the user."""


class NotAllowed(SfincsUiError):
    pass


class NotFound(SfincsUiError):
    pass


class QueueFull(SfincsUiError):
    pass


class QuotaExceeded(SfincsUiError):
    pass


class LaunchRefused(SfincsUiError):
    pass


class TemplateError(SfincsUiError):
    pass


class BuildError(SfincsUiError):
    pass
```

`sfincs_ui/sfincs_ui/services/access_control.py`:

```python
"""Who may see or change a run or a project (spec section 5, Access rules).

Rules over plain dicts so pages and services share one implementation:
  can_view_run     = run.public or run is a baseline or owner or admin
  can_modify_run   = owner or admin (never for a baseline)
  can_modify_project = owner or admin (a system example only by admin)
  can_use_project  = logged in and (owner or admin or a system example)
Every read path calls the view rule and every mutation the modify rule
inside the service, raising NotAllowed otherwise.
"""

from __future__ import annotations

from sfincs_ui.exceptions import NotAllowed
from sfincs_ui.models.user import ROLE_ADMIN


def _active(user: dict | None) -> bool:
    return bool(user) and user.get("is_active", True) is not False


def is_admin(user: dict | None) -> bool:
    return _active(user) and user.get("role") == ROLE_ADMIN


def _owns(user: dict | None, owner_id) -> bool:
    return _active(user) and owner_id is not None and user.get("id") == owner_id


def can_view_run(user: dict | None, run: dict) -> bool:
    if run.get("public") or run.get("baseline"):
        return True
    return _owns(user, run.get("owner_id")) or is_admin(user)


def can_modify_run(user: dict | None, run: dict) -> bool:
    if run.get("baseline"):
        return False
    return _owns(user, run.get("owner_id")) or is_admin(user)


def can_modify_project(user: dict | None, project: dict) -> bool:
    return _owns(user, project.get("owner_id")) or is_admin(user)


def can_use_project(user: dict | None, project: dict) -> bool:
    if not _active(user):
        return False
    return project.get("owner_id") is None or _owns(user, project.get("owner_id")) or is_admin(user)


def require_user(user: dict | None) -> dict:
    if not _active(user):
        raise NotAllowed("Log in to do this")
    return user


def require_view_run(user: dict | None, run: dict) -> None:
    if not can_view_run(user, run):
        raise NotAllowed("You may not view this run")


def require_modify_run(user: dict | None, run: dict) -> None:
    if not can_modify_run(user, run):
        raise NotAllowed("Only the run's owner or an administrator may do this")


def require_modify_project(user: dict | None, project: dict) -> None:
    if not can_modify_project(user, project):
        raise NotAllowed("Only the project's owner or an administrator may do this")


def require_use_project(user: dict | None, project: dict) -> None:
    if not can_use_project(user, project):
        raise NotAllowed("You may not use this project")
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd /home/razinka/sfincs/sfincs_ui && /opt/micromamba/envs/shiny/bin/python -m pytest tests/test_access_control.py -q`
Expected: 18 passed (full suite 140)

- [ ] **Step 5: Commit**

```bash
cd /home/razinka/sfincs
git add sfincs_ui/sfincs_ui/exceptions.py sfincs_ui/sfincs_ui/services/access_control.py sfincs_ui/tests/test_access_control.py
git commit -m "sfincs_ui: typed exceptions and run/project access rules

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 3: Template interface, the plane-beach template and its builder

**Files:**
- Create: `sfincs_ui/sfincs_ui/templates/__init__.py`
- Create: `sfincs_ui/sfincs_ui/templates/base.py`
- Create: `sfincs_ui/sfincs_ui/templates/plane_beach.py`
- Create: `sfincs_ui/sfincs_ui/templates/plane_beach_build.py` (standalone script, numpy only)
- Modify: `sfincs_ui/pyproject.toml` (package-data: `templates/*.py` are package modules already; nothing to add)
- Test: `sfincs_ui/tests/test_templates.py`, `sfincs_ui/tests/test_plane_beach_build.py`

**Interfaces:**
- Consumes: `Config` (fields `sfincs_bin`, `curonian_dir`), `TemplateError`.
- Produces: `SettingField(key, label, kind: "int"|"float"|"choice"|"bool", default, minimum=None, maximum=None, choices=None, explanation="", group="Model")`; abstract `Template` with attributes `key`, `title`, `description`, `has_validation: bool`, `has_export: bool`, and methods `fields() -> list[SettingField]`, `defaults() -> dict`, `validate(settings: dict) -> dict` (coerced, bounded copy; unknown keys dropped; raises `TemplateError` naming the field), `build_command(run_dir: Path, settings: dict, config: Config) -> list[str]`, `stage_cwd(stage: str, run_dir: Path, config: Config) -> Path`, `inp_overrides(settings) -> dict[str, str]` (keys rewritten in `sfincs.inp` after the build), `model_files() -> tuple[str, ...]` (files whose presence is build evidence besides `sfincs.inp`), `validate_command(run_dir, settings, config) -> list[str] | None`, `export_command(run_dir, settings, config) -> list[str] | None`, `default_threads(settings) -> int`, `geometry_layers(project_dir: Path, settings) -> list[dict]`, `example_projects() -> list[tuple[str, dict]]`. Registry `TEMPLATES: dict[str, Template]` and `get_template(key)` raising `TemplateError`. `PlaneBeachTemplate` with key `"plane_beach"`.

Plane-beach settings (the test template, from `test_model/make_test_model.py`): the domain is a fixed 5 km × 2 km plane beach, bed rising from −5 m at the west edge to +4.8 m at the east edge; the western column is a water-level boundary that ramps from 0 to `boundary_level_m` over `duration_hours`; three observation points at x = 1050, 2550, 3250 m (offshore, initial shoreline, inland), y = 1050 m.

| key | kind | default | bounds / choices | group | explanation |
|---|---|---|---|---|---|
| `resolution_m` | choice | 100 | 100, 50, 20, 10, 5 | Model | Cell size. 100 m runs in a second; 5 m takes minutes (acceptance runs use it). |
| `duration_hours` | int | 6 | 1..24 | Model | Length of the simulation and of the boundary ramp. |
| `boundary_level_m` | float | 2.0 | 0.5..4.0 | Model | Water level at the western boundary at the end of the ramp. |
| `manning` | float | 0.04 | 0.01..0.10 | Model | Uniform bed roughness. |
| `alpha` | float | 0.5 | 0.1..0.9 | Solver overrides | CFL number (`alpha` in sfincs.inp). |
| `huthresh` | float | 0.05 | 0.001..0.5 | Solver overrides | Wet/dry threshold depth (m). |
| `advection` | bool | True | | Solver overrides | Momentum advection on/off (`advection` 1/0). |

`inp_overrides` returns `{"alpha": "0.5", "huthresh": "0.05", "advection": "1"}`-style strings for the three override keys; the builder always writes the defaults so the override rewrite (Task 4) is exercised on every run. `default_threads` is 1. Example project: `("Plane beach example", defaults())`.

- [ ] **Step 1: Write the failing tests**

`sfincs_ui/tests/test_templates.py`:

```python
import sys
from pathlib import Path

import pytest

from sfincs_ui.config import Config
from sfincs_ui.exceptions import TemplateError
from sfincs_ui.templates import TEMPLATES, get_template
from sfincs_ui.templates.base import SettingField, Template
from sfincs_ui.templates.plane_beach import PlaneBeachTemplate


@pytest.fixture
def tpl():
    return get_template("plane_beach")


def test_registry():
    assert isinstance(TEMPLATES["plane_beach"], PlaneBeachTemplate)
    assert isinstance(get_template("plane_beach"), Template)
    with pytest.raises(TemplateError):
        get_template("nope")


def test_fields_and_defaults(tpl):
    keys = [f.key for f in tpl.fields()]
    assert keys == ["resolution_m", "duration_hours", "boundary_level_m", "manning", "alpha", "huthresh", "advection"]
    assert all(isinstance(f, SettingField) and f.explanation for f in tpl.fields())
    assert tpl.defaults() == {"resolution_m": 100, "duration_hours": 6, "boundary_level_m": 2.0, "manning": 0.04,
                              "alpha": 0.5, "huthresh": 0.05, "advection": True}
    assert {f.key for f in tpl.fields() if f.group == "Solver overrides"} == {"alpha", "huthresh", "advection"}


def test_validate_coerces_bounds_and_drops_unknown(tpl):
    s = tpl.validate({"resolution_m": "50", "duration_hours": "3", "boundary_level_m": "1.5", "manning": 0.02,
                      "alpha": "0.7", "huthresh": 0.1, "advection": "0", "evil": 1})
    assert s == {"resolution_m": 50, "duration_hours": 3, "boundary_level_m": 1.5, "manning": 0.02,
                 "alpha": 0.7, "huthresh": 0.1, "advection": False}
    with pytest.raises(TemplateError, match="duration_hours"):
        tpl.validate({**tpl.defaults(), "duration_hours": 0})
    with pytest.raises(TemplateError, match="resolution_m"):
        tpl.validate({**tpl.defaults(), "resolution_m": 33})
    with pytest.raises(TemplateError, match="alpha"):
        tpl.validate({**tpl.defaults(), "alpha": "abc"})
    assert tpl.validate({}) == tpl.defaults()  # missing keys take defaults


def test_build_command_is_the_standalone_script(tpl, tmp_path):
    cfg = Config(workspace=tmp_path)
    argv = tpl.build_command(tmp_path / "run", tpl.defaults(), cfg)
    assert argv[0] == sys.executable and argv[1] == "-P"
    assert Path(argv[2]).name == "plane_beach_build.py" and Path(argv[2]).is_absolute()
    assert argv[3:] == ["--run-dir", str(tmp_path / "run"), "--settings", str(tmp_path / "run" / "settings.json")]
    assert tpl.stage_cwd("build", tmp_path / "run", cfg) == tmp_path / "run"
    assert tpl.stage_cwd("simulate", tmp_path / "run", cfg) == tmp_path / "run"


def test_overrides_validation_export_and_evidence(tpl, tmp_path):
    cfg = Config(workspace=tmp_path)
    assert tpl.inp_overrides({**tpl.defaults(), "alpha": 0.7, "advection": False}) == {"alpha": "0.7", "huthresh": "0.05", "advection": "0"}
    assert tpl.validate_command(tmp_path, tpl.defaults(), cfg) is None and tpl.has_validation is False
    assert tpl.export_command(tmp_path, tpl.defaults(), cfg) is None and tpl.has_export is False
    assert set(tpl.model_files()) == {"sfincs.dep", "sfincs.msk", "sfincs.bnd", "sfincs.bzs", "sfincs.obs"}
    assert tpl.default_threads(tpl.defaults()) == 1
    assert tpl.example_projects()[0][0] == "Plane beach example"
    layers = tpl.geometry_layers(tmp_path, tpl.defaults())
    assert {l["name"] for l in layers} == {"domain", "boundary", "stations"}
```

`sfincs_ui/tests/test_plane_beach_build.py`:

```python
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

from sfincs_ui.templates import plane_beach_build


def _build(run_dir: Path, settings: dict) -> subprocess.CompletedProcess:
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "settings.json").write_text(json.dumps(settings))
    return subprocess.run([sys.executable, "-P", plane_beach_build.__file__, "--run-dir", str(run_dir),
                           "--settings", str(run_dir / "settings.json")], capture_output=True, text=True, timeout=60)


DEFAULTS = {"resolution_m": 100, "duration_hours": 6, "boundary_level_m": 2.0, "manning": 0.04,
            "alpha": 0.5, "huthresh": 0.05, "advection": True}


def test_builder_writes_the_test_model_at_100m(tmp_path):
    proc = _build(tmp_path / "run", DEFAULTS)
    assert proc.returncode == 0, proc.stderr
    files = {p.name for p in (tmp_path / "run").iterdir()}
    assert {"sfincs.inp", "sfincs.dep", "sfincs.msk", "sfincs.bnd", "sfincs.bzs", "sfincs.obs"} <= files
    dep = np.loadtxt(tmp_path / "run" / "sfincs.dep")
    assert dep.shape == (20, 50) and dep[0, 0] == pytest.approx(-5.0) and dep[0, -1] == pytest.approx(4.8)
    msk = np.loadtxt(tmp_path / "run" / "sfincs.msk", dtype=int)
    assert (msk[:, 0] == 2).all() and (msk[:, 1:] == 1).all()
    bzs = np.loadtxt(tmp_path / "run" / "sfincs.bzs")
    assert bzs[0].tolist() == [0.0, 0.0, 0.0] and bzs[-1, 0] == 21600 and bzs[-1, 1] == pytest.approx(2.0)
    inp = (tmp_path / "run" / "sfincs.inp").read_text()
    for line in ("mmax            = 50", "nmax            = 20", "dx              = 100.0", "tstop           = 20240101 060000",
                 "manning         = 0.04", "alpha           = 0.5", "huthresh        = 0.05", "advection       = 1"):
        assert line in inp, line
    assert "wrote plane beach" in proc.stdout


def test_builder_scales_with_resolution_and_duration(tmp_path):
    proc = _build(tmp_path / "run", {**DEFAULTS, "resolution_m": 20, "duration_hours": 3, "boundary_level_m": 1.0})
    assert proc.returncode == 0, proc.stderr
    dep = np.loadtxt(tmp_path / "run" / "sfincs.dep")
    assert dep.shape == (100, 250) and dep[0, -1] == pytest.approx(4.8, abs=0.05)
    inp = (tmp_path / "run" / "sfincs.inp").read_text()
    assert "tstop           = 20240101 030000" in inp and "dx              = 20.0" in inp
    bzs = np.loadtxt(tmp_path / "run" / "sfincs.bzs")
    assert bzs[-1, 0] == 10800 and bzs[-1, 1] == pytest.approx(1.0)


def test_builder_writes_defaults_for_override_keys_regardless_of_settings(tmp_path):
    """The override rewrite (model_service) is what applies alpha/huthresh/advection; the builder never does."""
    proc = _build(tmp_path / "run", {**DEFAULTS, "alpha": 0.9, "huthresh": 0.2, "advection": False})
    assert proc.returncode == 0
    inp = (tmp_path / "run" / "sfincs.inp").read_text()
    assert "alpha           = 0.5" in inp and "huthresh        = 0.05" in inp and "advection       = 1" in inp


def test_builder_rejects_bad_settings(tmp_path):
    proc = _build(tmp_path / "run", {**DEFAULTS, "resolution_m": 7})
    assert proc.returncode == 2 and "resolution_m" in proc.stderr


def test_builder_has_no_package_imports():
    src = Path(plane_beach_build.__file__).read_text()
    assert "sfincs_ui" not in src.replace("sfincs_ui/", "")  # the only allowed mention is in a path comment
    assert "import numpy" in src
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd /home/razinka/sfincs/sfincs_ui && /opt/micromamba/envs/shiny/bin/python -m pytest tests/test_templates.py tests/test_plane_beach_build.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'sfincs_ui.templates'`

- [ ] **Step 3: Write the template base and registry**

`sfincs_ui/sfincs_ui/templates/base.py`:

```python
"""A template answers the spec's five questions (section 1): settings schema,
build command and inp overrides, validation, geometry, export, plus its
example projects."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from sfincs_ui.config import Config
from sfincs_ui.exceptions import TemplateError

Kind = Literal["int", "float", "choice", "bool"]


@dataclass(frozen=True)
class SettingField:
    key: str
    label: str
    kind: Kind
    default: Any
    minimum: float | None = None
    maximum: float | None = None
    choices: tuple | None = None
    explanation: str = ""
    group: str = "Model"

    def coerce(self, raw: Any) -> Any:
        try:
            if self.kind == "bool":
                if isinstance(raw, str):
                    return raw.strip().lower() in ("1", "true", "yes", "on")
                return bool(raw)
            if self.kind == "int":
                value: Any = int(float(raw))
            elif self.kind == "float":
                value = float(raw)
            else:  # choice: compare as the type of the first choice
                value = type(self.choices[0])(raw)
        except (TypeError, ValueError) as exc:
            raise TemplateError(f"{self.key}: not a valid {self.kind}") from exc
        if self.kind == "choice" and value not in self.choices:
            raise TemplateError(f"{self.key}: must be one of {', '.join(map(str, self.choices))}")
        if self.minimum is not None and value < self.minimum:
            raise TemplateError(f"{self.key}: must be at least {self.minimum}")
        if self.maximum is not None and value > self.maximum:
            raise TemplateError(f"{self.key}: must be at most {self.maximum}")
        return value


class Template(ABC):
    key: str
    title: str
    description: str
    has_validation: bool = False
    has_export: bool = False

    @abstractmethod
    def fields(self) -> list[SettingField]: ...

    def defaults(self) -> dict:
        return {f.key: f.default for f in self.fields()}

    def validate(self, settings: dict) -> dict:
        out = {}
        for f in self.fields():
            out[f.key] = f.coerce(settings.get(f.key, f.default))
        return out

    @abstractmethod
    def build_command(self, run_dir: Path, settings: dict, config: Config) -> list[str]: ...

    def stage_cwd(self, stage: str, run_dir: Path, config: Config) -> Path:
        return run_dir

    @abstractmethod
    def inp_overrides(self, settings: dict) -> dict[str, str]: ...

    @abstractmethod
    def model_files(self) -> tuple[str, ...]: ...

    def validate_command(self, run_dir: Path, settings: dict, config: Config) -> list[str] | None:
        return None

    def export_command(self, run_dir: Path, settings: dict, config: Config) -> list[str] | None:
        return None

    def default_threads(self, settings: dict) -> int:
        return 1

    def geometry_layers(self, project_dir: Path, settings: dict) -> list[dict]:
        return []

    def example_projects(self) -> list[tuple[str, dict]]:
        return []
```

`sfincs_ui/sfincs_ui/templates/__init__.py`:

```python
from sfincs_ui.exceptions import TemplateError
from sfincs_ui.templates.base import SettingField, Template
from sfincs_ui.templates.plane_beach import PlaneBeachTemplate

TEMPLATES: dict[str, Template] = {t.key: t for t in (PlaneBeachTemplate(),)}


def get_template(key: str) -> Template:
    try:
        return TEMPLATES[key]
    except KeyError:
        raise TemplateError(f"unknown template {key!r}") from None


__all__ = ["TEMPLATES", "get_template", "SettingField", "Template", "PlaneBeachTemplate"]
```

- [ ] **Step 4: Write the plane-beach template**

`sfincs_ui/sfincs_ui/templates/plane_beach.py`:

```python
"""The test template: a plane beach flooded by a rising boundary level (from test_model/)."""

from __future__ import annotations

import sys
from pathlib import Path

from sfincs_ui.config import Config
from sfincs_ui.templates import plane_beach_build
from sfincs_ui.templates.base import SettingField, Template

DOMAIN_X_M, DOMAIN_Y_M = 5000.0, 2000.0
STATIONS = (("offshore", 1050.0, 1050.0), ("shoreline", 2550.0, 1050.0), ("inland", 3250.0, 1050.0))
OVERRIDE_KEYS = ("alpha", "huthresh", "advection")


class PlaneBeachTemplate(Template):
    key = "plane_beach"
    title = "Plane beach (test model)"
    description = ("A 5 km by 2 km plane beach rising from -5 m to +4.8 m, flooded by a water level ramping up "
                   "at the western boundary. Builds in a second; no validation, no map export.")

    def fields(self) -> list[SettingField]:
        return [
            SettingField("resolution_m", "Cell size (m)", "choice", 100, choices=(100, 50, 20, 10, 5),
                         explanation="100 m runs in a second; 5 m takes minutes and is what the restart acceptance uses."),
            SettingField("duration_hours", "Duration (h)", "int", 6, minimum=1, maximum=24,
                         explanation="Length of the simulation and of the boundary ramp."),
            SettingField("boundary_level_m", "Boundary level (m)", "float", 2.0, minimum=0.5, maximum=4.0,
                         explanation="Water level at the western boundary at the end of the ramp."),
            SettingField("manning", "Manning n", "float", 0.04, minimum=0.01, maximum=0.10,
                         explanation="Uniform bed roughness."),
            SettingField("alpha", "alpha", "float", 0.5, minimum=0.1, maximum=0.9, group="Solver overrides",
                         explanation="CFL number; lower is more stable and slower."),
            SettingField("huthresh", "huthresh (m)", "float", 0.05, minimum=0.001, maximum=0.5, group="Solver overrides",
                         explanation="Wet/dry threshold depth."),
            SettingField("advection", "Advection", "bool", True, group="Solver overrides",
                         explanation="Momentum advection on or off."),
        ]

    def build_command(self, run_dir: Path, settings: dict, config: Config) -> list[str]:
        return [sys.executable, "-P", str(Path(plane_beach_build.__file__).resolve()),
                "--run-dir", str(run_dir), "--settings", str(run_dir / "settings.json")]

    def inp_overrides(self, settings: dict) -> dict[str, str]:
        s = self.validate(settings)
        return {"alpha": str(s["alpha"]), "huthresh": str(s["huthresh"]), "advection": "1" if s["advection"] else "0"}

    def model_files(self) -> tuple[str, ...]:
        return ("sfincs.dep", "sfincs.msk", "sfincs.bnd", "sfincs.bzs", "sfincs.obs")

    def geometry_layers(self, project_dir: Path, settings: dict) -> list[dict]:
        box = [[0, 0], [DOMAIN_X_M, 0], [DOMAIN_X_M, DOMAIN_Y_M], [0, DOMAIN_Y_M], [0, 0]]
        return [
            {"name": "domain", "geometry": {"type": "Polygon", "coordinates": [box]}},
            {"name": "boundary", "geometry": {"type": "LineString", "coordinates": [[0, 0], [0, DOMAIN_Y_M]]}},
            {"name": "stations", "geometry": {"type": "MultiPoint", "coordinates": [[x, y] for _, x, y in STATIONS]},
             "labels": [n for n, _, _ in STATIONS]},
        ]

    def example_projects(self) -> list[tuple[str, dict]]:
        return [("Plane beach example", self.defaults())]
```

- [ ] **Step 5: Write the standalone builder**

`sfincs_ui/sfincs_ui/templates/plane_beach_build.py` (no package imports; run by absolute path):

```python
#!/usr/bin/env python3
"""Write a plane-beach SFINCS model directory from settings.json.

Standalone on purpose: launched as a subprocess by absolute path, it must
import nothing from the UI package (tests never install it). Mirrors
test_model/make_test_model.py with the cell size, duration and boundary level
taken from the settings. The three solver override keys are always written at
their defaults; the UI rewrites them afterwards and records overrides.diff.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

DOMAIN_X_M, DOMAIN_Y_M = 5000.0, 2000.0
ZB_WEST, ZB_EAST = -5.0, 4.8
RESOLUTIONS = (100, 50, 20, 10, 5)
STATIONS = ((1050.0, 1050.0, "offshore"), (2550.0, 1050.0, "shoreline"), (3250.0, 1050.0, "inland"))


def parse_settings(raw: dict) -> dict:
    try:
        res = int(float(raw.get("resolution_m", 100)))
        hours = int(float(raw.get("duration_hours", 6)))
        level = float(raw.get("boundary_level_m", 2.0))
        manning = float(raw.get("manning", 0.04))
    except (TypeError, ValueError) as exc:
        raise SystemExit(f"settings: {exc}")
    if res not in RESOLUTIONS:
        raise SystemExit(f"resolution_m must be one of {RESOLUTIONS}, got {res}")
    if not 1 <= hours <= 24:
        raise SystemExit(f"duration_hours must be 1..24, got {hours}")
    if not 0.5 <= level <= 4.0:
        raise SystemExit(f"boundary_level_m must be 0.5..4.0, got {level}")
    if not 0.01 <= manning <= 0.10:
        raise SystemExit(f"manning must be 0.01..0.10, got {manning}")
    return {"resolution_m": res, "duration_hours": hours, "boundary_level_m": level, "manning": manning}


def write_model(run_dir: Path, s: dict) -> None:
    dx = dy = float(s["resolution_m"])
    mmax, nmax = int(DOMAIN_X_M / dx), int(DOMAIN_Y_M / dy)
    tstop_s = s["duration_hours"] * 3600
    run_dir.mkdir(parents=True, exist_ok=True)

    x_centres = (np.arange(mmax) + 0.5) * dx
    zb_row = ZB_WEST + (ZB_EAST - ZB_WEST) * (x_centres - dx / 2) / (DOMAIN_X_M - dx)
    np.savetxt(run_dir / "sfincs.dep", np.tile(zb_row, (nmax, 1)), fmt="%.3f")

    msk = np.ones((nmax, mmax), dtype=int)
    msk[:, 0] = 2
    np.savetxt(run_dir / "sfincs.msk", msk, fmt="%d")

    xc = dx / 2
    (run_dir / "sfincs.bnd").write_text(f"{xc:.1f} {dy / 2:.1f}\n{xc:.1f} {(nmax - 0.5) * dy:.1f}\n")

    t = np.arange(0, tstop_s + 1, 600)
    zs = s["boundary_level_m"] * t / tstop_s
    np.savetxt(run_dir / "sfincs.bzs", np.column_stack([t, zs, zs]), fmt="%.1f %.4f %.4f")

    (run_dir / "sfincs.obs").write_text("".join(f"{x:.1f} {y:.1f} {name}\n" for x, y, name in STATIONS))

    (run_dir / "sfincs.inp").write_text(f"""\
x0              = 0.0
y0              = 0.0
mmax            = {mmax}
nmax            = {nmax}
dx              = {dx}
dy              = {dy}
rotation        = 0

tref            = 20240101 000000
tstart          = 20240101 000000
tstop           = 20240101 {s['duration_hours']:02d}0000

inputformat     = asc
outputformat    = net

depfile         = sfincs.dep
mskfile         = sfincs.msk
bndfile         = sfincs.bnd
bzsfile         = sfincs.bzs
obsfile         = sfincs.obs

advection       = 1
alpha           = 0.5
huthresh        = 0.05
manning         = {s['manning']}
zsini           = 0.0

dtout           = 1800
dthisout        = 300
dtmaxout        = {tstop_s}
""")


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="write a plane-beach SFINCS model")
    p.add_argument("--run-dir", required=True, type=Path)
    p.add_argument("--settings", required=True, type=Path)
    args = p.parse_args(argv)
    try:
        raw = json.loads(args.settings.read_text())
    except (OSError, ValueError) as exc:
        print(f"cannot read settings: {exc}", file=sys.stderr)
        return 2
    try:
        s = parse_settings(raw)
    except SystemExit as exc:
        print(str(exc), file=sys.stderr)
        return 2
    write_model(args.run_dir, s)
    print(f"wrote plane beach ({s['resolution_m']} m cells, {s['duration_hours']} h) to {args.run_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

Note the `duration_hours` formatting: `tstop = 20240101 {hours:02d}0000` requires hours ≤ 24; 24 gives `240000`, which SFINCS reads as the next midnight. The bounds enforce 1..24.

- [ ] **Step 6: Run the tests to verify they pass**

Run: `cd /home/razinka/sfincs/sfincs_ui && /opt/micromamba/envs/shiny/bin/python -m pytest tests/test_templates.py tests/test_plane_beach_build.py -q`
Expected: 10 passed (full suite 150)

- [ ] **Step 7: Commit**

```bash
cd /home/razinka/sfincs
git add sfincs_ui/sfincs_ui/templates sfincs_ui/tests/test_templates.py sfincs_ui/tests/test_plane_beach_build.py
git commit -m "sfincs_ui: template interface and the plane-beach template with its standalone builder

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 4: Overrides, process helpers and progress parsing

**Files:**
- Create: `sfincs_ui/sfincs_ui/services/model_service.py`
- Create: `sfincs_ui/sfincs_ui/services/procs.py`
- Create: `sfincs_ui/sfincs_ui/services/progress.py`
- Test: `sfincs_ui/tests/test_model_service.py`, `sfincs_ui/tests/test_procs_progress.py`

**Interfaces:**
- Produces (model_service): `write_settings(run_dir, settings) -> Path` (`settings.json`, sorted keys, indent 2); `read_settings(run_dir) -> dict`; `apply_overrides(inp_path: Path, overrides: dict[str, str]) -> str` (rewrites `key = value` lines in place keeping the file's `%-15s = ` alignment, appends keys that were absent, writes the file, returns the unified diff old→new, empty when nothing changed); `write_overrides(run_dir, overrides) -> Path` (applies to `run_dir/"sfincs.inp"`, then writes `overrides.diff` last; idempotent: a second call leaves the inp unchanged and rewrites the same diff text that the first call produced, because the diff is computed against the pristine copy saved as `sfincs.inp.orig` on the first call); `OVERRIDES_DIFF = "overrides.diff"`.
- Produces (procs): `proc_starttime(pid) -> int | None` (field 22 of `/proc/<pid>/stat`, parsed after the last `)`; None when the pid is gone); `is_alive(pid, starttime) -> bool` (exists and start time matches); `killpg_graceful(pid, grace_s=30.0, sleep=time.sleep) -> str` (SIGTERM the process group, poll up to `grace_s`, SIGKILL if still alive; returns "terminated", "killed" or "gone"); `find_pids_in_session(pid) -> list[int]` is not needed.
- Produces (progress): `parse_progress(text) -> dict | None` with `{"percent": int, "remaining_s": float | None}` from the last `NN% complete, X s remaining` line (`-` → None); `FINISHED_LINE = "---------- Simulation finished -----------"`; `tail_lines(path, n) -> str` (last n lines, empty string when the file is absent, reads only the tail of large files).

- [ ] **Step 1: Write the failing tests**

`sfincs_ui/tests/test_model_service.py`:

```python
import json

from sfincs_ui.services.model_service import OVERRIDES_DIFF, apply_overrides, read_settings, write_overrides, write_settings

INP = """\
x0              = 0.0
mmax            = 50

advection       = 1
alpha           = 0.5
huthresh        = 0.05
manning         = 0.04
"""


def test_settings_round_trip(tmp_path):
    p = write_settings(tmp_path, {"b": 1, "a": [1, 2]})
    assert p.name == "settings.json" and p.read_text() == '{\n  "a": [\n    1,\n    2\n  ],\n  "b": 1\n}'
    assert read_settings(tmp_path) == {"b": 1, "a": [1, 2]}


def test_apply_overrides_rewrites_in_place_and_appends_missing(tmp_path):
    inp = tmp_path / "sfincs.inp"
    inp.write_text(INP)
    diff = apply_overrides(inp, {"alpha": "0.7", "advection": "0", "tstop": "20240101 030000"})
    text = inp.read_text()
    assert "alpha           = 0.7\n" in text and "advection       = 0\n" in text
    assert "huthresh        = 0.05\n" in text and text.endswith("tstop           = 20240101 030000\n")
    assert text.index("advection") < text.index("alpha")  # order preserved
    assert "-alpha           = 0.5" in diff and "+alpha           = 0.7" in diff and "+tstop" in diff


def test_apply_overrides_no_change_gives_empty_diff(tmp_path):
    inp = tmp_path / "sfincs.inp"
    inp.write_text(INP)
    assert apply_overrides(inp, {"alpha": "0.5"}) == ""
    assert inp.read_text() == INP


def test_write_overrides_is_idempotent_and_writes_diff_last(tmp_path):
    (tmp_path / "sfincs.inp").write_text(INP)
    first = write_overrides(tmp_path, {"alpha": "0.7"})
    assert first.name == OVERRIDES_DIFF and "+alpha           = 0.7" in first.read_text()
    assert (tmp_path / "sfincs.inp.orig").read_text() == INP
    text_after_first = (tmp_path / "sfincs.inp").read_text()
    second = write_overrides(tmp_path, {"alpha": "0.7"})
    assert (tmp_path / "sfincs.inp").read_text() == text_after_first
    assert second.read_text() == first.read_text()


def test_write_overrides_records_empty_diff_when_nothing_changes(tmp_path):
    (tmp_path / "sfincs.inp").write_text(INP)
    p = write_overrides(tmp_path, {"alpha": "0.5"})
    assert p.exists() and p.read_text() == ""
```

`sfincs_ui/tests/test_procs_progress.py`:

```python
import os
import signal
import subprocess
import sys
import time

import pytest

from sfincs_ui.services.procs import is_alive, killpg_graceful, proc_starttime
from sfincs_ui.services.progress import FINISHED_LINE, parse_progress, tail_lines


@pytest.fixture
def sleeper():
    proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"], start_new_session=True,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    yield proc
    if proc.poll() is None:
        os.killpg(proc.pid, signal.SIGKILL)
        proc.wait()


def test_proc_starttime_and_is_alive(sleeper):
    st = proc_starttime(sleeper.pid)
    assert isinstance(st, int) and st > 0
    assert is_alive(sleeper.pid, st)
    assert not is_alive(sleeper.pid, st + 1)
    assert proc_starttime(2**22 - 1) is None and not is_alive(2**22 - 1, 1)


def test_proc_starttime_parses_comm_with_spaces_and_parens():
    # /proc/self/stat for a process named "a b) c" still parses: split after the LAST ')'
    st = proc_starttime(os.getpid())
    stat = open(f"/proc/{os.getpid()}/stat").read()
    assert st == int(stat.rsplit(")", 1)[1].split()[19])


def test_killpg_graceful_terminates_then_kills(sleeper):
    # the child ignores SIGTERM, so the helper must escalate to SIGKILL
    stubborn = subprocess.Popen([sys.executable, "-c", "import signal, time; signal.signal(signal.SIGTERM, signal.SIG_IGN); time.sleep(60)"],
                                start_new_session=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        time.sleep(0.5)
        assert killpg_graceful(sleeper.pid, grace_s=5) == "terminated"
        assert killpg_graceful(stubborn.pid, grace_s=1) == "killed"
        assert killpg_graceful(stubborn.pid, grace_s=1) == "gone"
    finally:
        for p in (sleeper, stubborn):
            if p.poll() is None:
                os.killpg(p.pid, signal.SIGKILL)
            p.wait()


def test_parse_progress():
    assert parse_progress("") is None
    assert parse_progress("   0% complete,       - s remaining ...\n") == {"percent": 0, "remaining_s": None}
    text = "  15% complete,  1188.8 s remaining ...\n  20% complete,  1100.0 s remaining ...\n"
    assert parse_progress(text) == {"percent": 20, "remaining_s": 1100.0}
    assert FINISHED_LINE == "---------- Simulation finished -----------"


def test_tail_lines(tmp_path):
    assert tail_lines(tmp_path / "missing.log", 5) == ""
    p = tmp_path / "x.log"
    p.write_text("".join(f"line {i}\n" for i in range(1000)))
    out = tail_lines(p, 3)
    assert out == "line 997\nline 998\nline 999\n"
    assert tail_lines(p, 5000).startswith("line 0\n")
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd /home/razinka/sfincs/sfincs_ui && /opt/micromamba/envs/shiny/bin/python -m pytest tests/test_model_service.py tests/test_procs_progress.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'sfincs_ui.services.model_service'`

- [ ] **Step 3: Write model_service.py**

```python
"""Per-run files the UI owns: settings.json, the sfincs.inp override rewrite and overrides.diff.

Overrides are applied after the builder writes sfincs.inp (spec section 3) so
the step is a pure text transformation. The pristine file is kept as
sfincs.inp.orig so the recorded diff is always original -> final and a
re-application after an interrupted build is idempotent.
"""

from __future__ import annotations

import difflib
import json
import re
from pathlib import Path

SETTINGS_FILE = "settings.json"
OVERRIDES_DIFF = "overrides.diff"
ORIG_INP = "sfincs.inp.orig"
_LINE = re.compile(r"^(\s*)([A-Za-z_][A-Za-z0-9_]*)(\s*=\s*)(.*?)(\s*)$")


def write_settings(run_dir: Path, settings: dict) -> Path:
    run_dir.mkdir(parents=True, exist_ok=True)
    path = run_dir / SETTINGS_FILE
    path.write_text(json.dumps(settings, indent=2, sort_keys=True))
    return path


def read_settings(run_dir: Path) -> dict:
    return json.loads((run_dir / SETTINGS_FILE).read_text())


def _rewrite(text: str, overrides: dict[str, str]) -> str:
    remaining = dict(overrides)
    out = []
    for line in text.splitlines(keepends=True):
        m = _LINE.match(line.rstrip("\n"))
        if m and m.group(2) in remaining:
            value = remaining.pop(m.group(2))
            out.append(f"{m.group(1)}{m.group(2)}{m.group(3)}{value}\n")
        else:
            out.append(line)
    if remaining:
        if out and not out[-1].endswith("\n"):
            out[-1] += "\n"
        for key, value in remaining.items():
            out.append(f"{key:<15} = {value}\n")
    return "".join(out)


def apply_overrides(inp_path: Path, overrides: dict[str, str]) -> str:
    old = inp_path.read_text()
    new = _rewrite(old, overrides)
    if new == old:
        return ""
    inp_path.write_text(new)
    return "".join(difflib.unified_diff(old.splitlines(keepends=True), new.splitlines(keepends=True),
                                        fromfile="sfincs.inp (built)", tofile="sfincs.inp (overrides applied)"))


def write_overrides(run_dir: Path, overrides: dict[str, str]) -> Path:
    """Apply overrides to run_dir/sfincs.inp from its pristine copy and write overrides.diff last."""
    inp, orig = run_dir / "sfincs.inp", run_dir / ORIG_INP
    if not orig.exists():
        orig.write_text(inp.read_text())
    inp.write_text(orig.read_text())
    diff = apply_overrides(inp, overrides)
    path = run_dir / OVERRIDES_DIFF
    path.write_text(diff)
    return path
```

- [ ] **Step 4: Write procs.py and progress.py**

`sfincs_ui/sfincs_ui/services/procs.py`:

```python
"""Process identity and termination through /proc and process groups."""

from __future__ import annotations

import os
import signal
import time


def proc_starttime(pid: int) -> int | None:
    """Field 22 of /proc/<pid>/stat (clock ticks since boot). None when the pid is gone.

    The comm field (2) may contain spaces and parentheses, so split after the
    LAST ')' and count fields from there: field 22 is index 19 of the remainder.
    """
    try:
        stat = open(f"/proc/{pid}/stat").read()
    except (FileNotFoundError, ProcessLookupError, PermissionError):
        return None
    try:
        return int(stat.rsplit(")", 1)[1].split()[19])
    except (IndexError, ValueError):
        return None


def is_alive(pid: int, starttime: int | None) -> bool:
    current = proc_starttime(pid)
    return current is not None and (starttime is None or current == starttime)


def killpg_graceful(pid: int, grace_s: float = 30.0, sleep=time.sleep) -> str:
    """SIGTERM the process group, wait up to grace_s, then SIGKILL. Returns what happened."""
    try:
        os.killpg(pid, signal.SIGTERM)
    except ProcessLookupError:
        return "gone"
    deadline = time.monotonic() + grace_s
    while time.monotonic() < deadline:
        if proc_starttime(pid) is None or _is_zombie(pid):
            return "terminated"
        sleep(0.2)
    try:
        os.killpg(pid, signal.SIGKILL)
    except ProcessLookupError:
        return "terminated"
    return "killed"


def _is_zombie(pid: int) -> bool:
    try:
        return open(f"/proc/{pid}/stat").read().rsplit(")", 1)[1].split()[0] == "Z"
    except (OSError, IndexError):
        return True
```

`sfincs_ui/sfincs_ui/services/progress.py`:

```python
"""Read SFINCS progress from sfincs.log and tail stage logs."""

from __future__ import annotations

import os
import re
from pathlib import Path

FINISHED_LINE = "---------- Simulation finished -----------"
_PROGRESS = re.compile(r"^\s*(\d+)% complete,\s*(-|[\d.]+) s remaining", re.M)


def parse_progress(text: str) -> dict | None:
    matches = _PROGRESS.findall(text)
    if not matches:
        return None
    percent, remaining = matches[-1]
    return {"percent": int(percent), "remaining_s": None if remaining == "-" else float(remaining)}


def tail_lines(path: Path, n: int, max_bytes: int = 256 * 1024) -> str:
    try:
        size = os.path.getsize(path)
        with open(path, "rb") as fh:
            fh.seek(max(0, size - max_bytes))
            chunk = fh.read().decode("utf-8", errors="replace")
    except OSError:
        return ""
    lines = chunk.splitlines(keepends=True)
    if size > max_bytes and lines:
        lines = lines[1:]  # drop the partial first line
    return "".join(lines[-n:])
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `cd /home/razinka/sfincs/sfincs_ui && /opt/micromamba/envs/shiny/bin/python -m pytest tests/test_model_service.py tests/test_procs_progress.py -q`
Expected: 10 passed (full suite 160)

- [ ] **Step 6: Commit**

```bash
cd /home/razinka/sfincs
git add sfincs_ui/sfincs_ui/services/model_service.py sfincs_ui/sfincs_ui/services/procs.py sfincs_ui/sfincs_ui/services/progress.py sfincs_ui/tests/test_model_service.py sfincs_ui/tests/test_procs_progress.py
git commit -m "sfincs_ui: sfincs.inp overrides with overrides.diff, /proc helpers and progress parsing

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 5: Job runner: detached stages, one monitor loop, chain, capacity, cancel

**Files:**
- Create: `sfincs_ui/sfincs_ui/services/job_runner.py`
- Create: `sfincs_ui/tests/fixtures/fake_build.sh`, `sfincs_ui/tests/fixtures/fake_sfincs.sh`, `sfincs_ui/tests/fixtures/fake_validate.sh` (all `chmod +x`)
- Create: `sfincs_ui/tests/fake_template.py`
- Create: `sfincs_ui/tests/runner_helpers.py`
- Modify: `sfincs_ui/tests/conftest.py` (the `runner` fixture)
- Test: `sfincs_ui/tests/test_job_runner.py`

**Interfaces:**
- Consumes: models (Task 1), `Template`/`TEMPLATES` (Task 3), `write_overrides`, `read_settings`, `proc_starttime`, `is_alive`, `killpg_graceful`, `tail_lines`, `FINISHED_LINE` (Task 4), `SettingsService.get("max_simulations")`, `Config.sfincs_bin`.
- Produces: `StageSpec(stage, argv, cwd, env, log_path, evidence)` dataclass; `JobRunner(config, settings_service, session_factory=None, *, templates=None, reconciler=None, poll_interval=0.5, grace_s=30.0, aux_cap=2)` with `async start()` (runs `reconciler(self)` when given, then marks itself started), `async stop()` (cancels the chain tasks only), `submit(run_id) -> asyncio.Task` (chain from stage 0), `resume(run_id, stage_index, inherited: tuple[int, int] | None) -> asyncio.Task` (chain from `stage_index`; when `inherited=(pid, starttime)` the first stage is monitored, not spawned), `async cancel(run_id)`, `async wait(run_id, timeout)` (await the chain task), `plan_stages(run_id) -> list[StageSpec]`, `active_jobs() -> list[dict]` (rows with status in `ACTIVE_JOB_STATUSES`, with run name, stage, pid, started_at), `spawned_pids: set[int]`, `started: bool`. Module helpers: `build_evidence(run_dir, template) -> bool`, `simulate_evidence(run_dir) -> bool`, `validate_evidence(run_dir) -> bool`, `export_evidence(run_dir) -> bool`, `evidence_for(stage, run_dir, template)`, `LOG_NAMES = {"build": "build.log", "simulate": "sfincs.log", "validate": "validate.log", "export": "export.log"}`, `SUMMARY_TAIL = 50`.
- Run status transitions: `queued` → (`building` | `running` | `validating` | `exporting` as each stage claims) → `finished`; `failed` with `summary_json = {"stage", "reason", "exit_code", "log_tail"}`; `cancelled`.

Design, for the implementer (spec section 3): a stage is **claimed** under an `asyncio.Lock` when capacity allows (simulate: fewer than `max_simulations` jobs with stage `simulate` and status `running`; other stages: fewer than `aux_cap` running), by setting the job to `running` with `started_at`; then it is **spawned** with `subprocess.Popen(argv, cwd=..., env=..., stdout=<log file>, stderr=subprocess.STDOUT, stdin=DEVNULL, start_new_session=True)`, the pid and `proc_starttime(pid)` are written to the job row **before** monitoring begins; the **monitor** polls every `poll_interval`: with a `Popen` handle, `proc.poll()` yields the exit code; for an inherited pid, `is_alive(pid, starttime)` yields liveness and the exit code stays `None`. `except asyncio.CancelledError` is never written around the child: the loop simply propagates cancellation. After the process ends the stage is **judged**: exit code 0 or `None`, plus the stage's evidence, means `completed`; otherwise `failed` with the last 50 log lines. After `build` completes, and before judging, the runner applies the template's overrides (`write_overrides`) so `overrides.diff` is the last build artefact. `cancel()` marks the run `cancelled`, runs `killpg_graceful(pid, grace_s)` in `asyncio.to_thread`, then cancels the chain task; a chain that sees `cancelled` after its monitor returns stops without touching the run status.

- [ ] **Step 1: Write the fakes and helpers**

`sfincs_ui/tests/fixtures/fake_build.sh`:

```bash
#!/usr/bin/env bash
# Fake build stage. Usage: fake_build.sh <run_dir>
# FAKE_SLEEP=<s>   wait before writing (default 0)
# FAKE_FAIL_BUILD=1  exit 1 without writing the model files
# FAKE_PARTIAL=1   write the model files but exit 1 (dies "after" writing)
set -u
run_dir="$1"
echo "fake build starting in $run_dir"
sleep "${FAKE_SLEEP:-0}"
if [[ "${FAKE_FAIL_BUILD:-0}" == "1" ]]; then echo "fake build failed" >&2; exit 1; fi
mkdir -p "$run_dir"
printf 'alpha           = 0.5\nhuthresh        = 0.05\n' > "$run_dir/sfincs.inp"
echo "0 0" > "$run_dir/sfincs.dep"
echo "fake build wrote model files"
if [[ "${FAKE_PARTIAL:-0}" == "1" ]]; then exit 1; fi
exit 0
```

`sfincs_ui/tests/fixtures/fake_sfincs.sh` (runs with cwd = run dir, like the real solver):

```bash
#!/usr/bin/env bash
# Fake SFINCS solver: prints the real progress line format into sfincs.log in the cwd.
# FAKE_STEPS=<n>    progress lines (default 4)      FAKE_SLEEP=<s>  between lines (default 0.05)
# FAKE_FAIL_SIM=1   exit 3 before the finish line   FAKE_STUBBORN=1 ignore SIGTERM
set -u
if [[ "${FAKE_STUBBORN:-0}" == "1" ]]; then trap '' TERM; fi
echo "------------ Welcome to SFINCS ------------"
echo "threads=${OMP_NUM_THREADS:-unset}"
steps="${FAKE_STEPS:-4}"
for ((i=1; i<=steps; i++)); do
  pct=$(( i * 100 / steps ))
  printf '  %d%% complete,  %s s remaining ...\n' "$pct" "$(( steps - i ))"
  sleep "${FAKE_SLEEP:-0.05}"
done
if [[ "${FAKE_FAIL_SIM:-0}" == "1" ]]; then echo "fatal: fake failure"; exit 3; fi
: > sfincs_his.nc
echo "---------- Simulation finished -----------"
echo "----------- Closing off SFINCS -----------"
exit 0
```

`sfincs_ui/tests/fixtures/fake_validate.sh`:

```bash
#!/usr/bin/env bash
# Fake validate stage. Usage: fake_validate.sh <run_dir> <out_dir>
set -u
mkdir -p "$2"
echo "# validation" > "$2/validation.md"
echo "fake validate wrote $2/validation.md"
```

Run `chmod +x sfincs_ui/tests/fixtures/*.sh`.

`sfincs_ui/tests/fake_template.py`:

```python
"""A template whose stages are the shell fakes under tests/fixtures/."""

from __future__ import annotations

from pathlib import Path

from sfincs_ui.config import Config
from sfincs_ui.templates.base import SettingField, Template

FIXTURES = Path(__file__).resolve().parent / "fixtures"
FAKE_BUILD = FIXTURES / "fake_build.sh"
FAKE_SFINCS = FIXTURES / "fake_sfincs.sh"
FAKE_VALIDATE = FIXTURES / "fake_validate.sh"


class FakeTemplate(Template):
    key = "fake"
    title = "Fake"
    description = "shell fakes"

    def __init__(self, with_validation: bool = False):
        self.has_validation = with_validation

    def fields(self) -> list[SettingField]:
        return [SettingField("alpha", "alpha", "float", 0.5, minimum=0.1, maximum=0.9, group="Solver overrides")]

    def build_command(self, run_dir: Path, settings: dict, config: Config) -> list[str]:
        return ["bash", str(FAKE_BUILD), str(run_dir)]

    def inp_overrides(self, settings: dict) -> dict[str, str]:
        return {"alpha": str(self.validate(settings)["alpha"])}

    def model_files(self) -> tuple[str, ...]:
        return ("sfincs.dep",)

    def validate_command(self, run_dir: Path, settings: dict, config: Config) -> list[str] | None:
        if not self.has_validation:
            return None
        return ["bash", str(FAKE_VALIDATE), str(run_dir), str(run_dir / "validation")]

    def example_projects(self) -> list[tuple[str, dict]]:
        return [("Fake example", self.defaults())]
```

`sfincs_ui/tests/runner_helpers.py`:

```python
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
```

Add to `sfincs_ui/tests/conftest.py`:

```python
@pytest.fixture
def runner(db, tmp_path):
    """A JobRunner over the fake template with a fast poll; kills every spawned process group at teardown."""
    import os
    import signal

    from sfincs_ui import config
    from sfincs_ui.services.job_runner import JobRunner
    from sfincs_ui.services.settings_service import SettingsService
    from tests.fake_template import FAKE_SFINCS, FakeTemplate

    cfg = config.Config(workspace=tmp_path, database_url=f"sqlite:///{tmp_path / 'test.db'}", sfincs_bin=FAKE_SFINCS,
                        max_simulations=1, max_threads=4)
    config.set_config(cfg)
    r = JobRunner(cfg, SettingsService(cfg, session_factory=db), session_factory=db,
                  templates={"fake": FakeTemplate(), "fake_v": FakeTemplate(with_validation=True)}, poll_interval=0.05, grace_s=2.0)
    yield r
    for pid in list(r.spawned_pids):
        try:
            os.killpg(pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
```

(`tests/__init__.py` exists from milestone 1, so `from tests.fake_template import ...` resolves with `pythonpath = ["."]`.)

- [ ] **Step 2: Write the failing runner tests**

`sfincs_ui/tests/test_job_runner.py`:

```python
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
    await runner.start()
    runner.submit(run_id)
    while not any(j["stage"] == "simulate" and j["status"] == "running" for j in run_row(db, run_id)["jobs"]):
        await asyncio.sleep(0.02)
    active = runner.active_jobs()
    assert len(active) == 1 and active[0]["stage"] == "simulate" and active[0]["run_id"] == run_id and active[0]["pid"]
    await runner.cancel(run_id)
    assert runner.active_jobs() == []
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `cd /home/razinka/sfincs/sfincs_ui && /opt/micromamba/envs/shiny/bin/python -m pytest tests/test_job_runner.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'sfincs_ui.services.job_runner'`

- [ ] **Step 4: Write the runner**

`sfincs_ui/sfincs_ui/services/job_runner.py`:

```python
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
from datetime import datetime
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
SUMMARY_TAIL = 50
OVERRIDES_DIFF = "overrides.diff"


@dataclass
class StageSpec:
    stage: str
    argv: list[str]
    cwd: Path
    env: dict[str, str]
    log_path: Path
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
        specs = [StageSpec("build", template.build_command(run_dir, settings, self._config),
                           template.stage_cwd("build", run_dir, self._config), base_env,
                           run_dir / LOG_NAMES["build"], evidence_for("build", run_dir, template))]
        specs.append(StageSpec("simulate", [str(self._config.sfincs_bin)], run_dir,
                               {**base_env, "OMP_NUM_THREADS": str(run.threads)},
                               run_dir / LOG_NAMES["simulate"], evidence_for("simulate", run_dir, template)))
        vcmd = template.validate_command(run_dir, settings, self._config)
        if vcmd:
            specs.append(StageSpec("validate", vcmd, template.stage_cwd("validate", run_dir, self._config), base_env,
                                   run_dir / LOG_NAMES["validate"], evidence_for("validate", run_dir, template)))
        ecmd = template.export_command(run_dir, settings, self._config)
        if ecmd:
            specs.append(StageSpec("export", ecmd, template.stage_cwd("export", run_dir, self._config), base_env,
                                   run_dir / LOG_NAMES["export"], evidence_for("export", run_dir, template)))
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
            ok = await self._run_stage(run_id, spec, inherited if index == start_index else None)
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
            proc, pid, starttime = self._spawn(spec)
            self._record_pid(job_id, pid, starttime)
        else:
            job_id = self._active_job_id(run_id, spec.stage)
            proc, (pid, starttime) = None, inherited
        exit_code = await self._monitor(pid, starttime, proc)
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
        log = open(spec.log_path, "ab")  # the child owns this descriptor; closing ours is fine after spawn
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
            active = [j for j in run.jobs if j.status in ACTIVE_JOB_STATUSES]
            pids = [(j.pid, j.proc_starttime) for j in active if j.pid]
            for j in active:
                j.status = "cancelled"; j.finished_at = utcnow()
            s.commit()
        finally:
            s.close()
        for pid, st in pids:
            if is_alive(pid, st):
                await asyncio.to_thread(killpg_graceful, pid, self._grace)
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
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `cd /home/razinka/sfincs/sfincs_ui && /opt/micromamba/envs/shiny/bin/python -m pytest tests/test_job_runner.py -q`
Expected: 9 passed, and `ps -eo pid,cmd | grep -c fake_sfincs` prints 0 afterwards (no leaked processes). Full suite 169 passed.

- [ ] **Step 6: Commit**

```bash
cd /home/razinka/sfincs
git add sfincs_ui/sfincs_ui/services/job_runner.py sfincs_ui/tests/fixtures sfincs_ui/tests/fake_template.py sfincs_ui/tests/runner_helpers.py sfincs_ui/tests/conftest.py sfincs_ui/tests/test_job_runner.py
git commit -m "sfincs_ui: job runner with detached stages, one monitor loop, capacity claims and cancel

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 6: Reconciliation at startup

**Files:**
- Create: `sfincs_ui/sfincs_ui/services/reconcile.py`
- Test: `sfincs_ui/tests/test_reconcile.py`

**Interfaces:**
- Consumes: `JobRunner` (Task 5: `plan_stages`, `resume`, `_sf`, `_templates`), `is_alive`, `write_overrides`, evidence helpers.
- Produces: `reconcile(runner: JobRunner) -> list[dict]` (one decision per touched run: `{"run_id", "stage", "decision"}` with decisions `resumed`, `completed`, `overrides_reapplied`, `interrupted`, `orphaned`, `requeued`), suitable as `JobRunner(reconciler=reconcile)`. Decisions follow spec section 3: for every job in an active status: directory gone → job and run `orphaned`; pid alive with the recorded start time → `resume(run_id, index, (pid, starttime))`; dead with complete evidence → job `completed` (exit_code NULL), chain resumed at the next stage; dead `build` with `sfincs.inp` and the model files present but no `overrides.diff` → overrides re-applied, job `completed`, chain resumed; otherwise → job `failed`, run `failed` with reason `interrupted`. A run left `queued` with no active job is resubmitted. A run in a stage status with no job rows is `failed` with reason `interrupted`.

- [ ] **Step 1: Write the failing tests**

`sfincs_ui/tests/test_reconcile.py`:

```python
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
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd /home/razinka/sfincs/sfincs_ui && /opt/micromamba/envs/shiny/bin/python -m pytest tests/test_reconcile.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'sfincs_ui.services.reconcile'`

- [ ] **Step 3: Write reconcile.py**

```python
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
            if job.pid and is_alive(job.pid, job.proc_starttime):
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
```

Note for the implementer: `resume(run_id, index + 1, None)` on the last stage runs an empty loop and `_finish_run` marks the run finished, which is what "dead with complete evidence on the final stage" needs.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd /home/razinka/sfincs/sfincs_ui && /opt/micromamba/envs/shiny/bin/python -m pytest tests/test_reconcile.py -q`
Expected: 7 passed (full suite 176), no leaked processes.

- [ ] **Step 5: Commit**

```bash
cd /home/razinka/sfincs
git add sfincs_ui/sfincs_ui/services/reconcile.py sfincs_ui/tests/test_reconcile.py
git commit -m "sfincs_ui: reconcile left-over jobs at startup (resume, complete, re-apply overrides, interrupt, orphan)

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 7: Project and run services

**Files:**
- Create: `sfincs_ui/sfincs_ui/services/project_service.py`
- Create: `sfincs_ui/sfincs_ui/services/run_service.py`
- Test: `sfincs_ui/tests/test_project_service.py`, `sfincs_ui/tests/test_run_service.py`

**Interfaces:**
- Consumes: models, templates registry, access control, `JobRunner`, `SettingsService`, `write_settings`, `parse_progress`, `tail_lines`, exceptions.
- Produces: `ProjectService(config, session_factory=None, templates=None)` with `ensure_examples() -> int` (seeds one system project per template example, idempotent on (template, name) with `owner_id NULL`), `examples() -> list[dict]`, `list_for(user) -> list[dict]` (own projects, newest first), `get(user, project_id) -> dict` (`require_use_project`; `NotFound`), `create(user, template_key, name, settings=None) -> dict`, `clone(user, project_id, new_name) -> dict` (copies settings only), `rename(user, project_id, name)`, `update_settings(user, project_id, settings) -> dict` (validated by the template), `delete(user, project_id)` (`require_modify_project`; refuses while a run of the project is active; removes run directories and the project directory), `project_dir(project_id) -> Path`. Project dicts: `id, owner_id, owner, name, template, template_title, settings, created_at, updated_at, run_count`.
- `RunService(config, settings_service, project_service, runner, session_factory=None, templates=None)` with `launch(user, project_id, name, threads) -> dict` (checks: `require_user`, project usable, name non-empty ≤ 100 chars, `1 ≤ threads ≤ settings.get("max_threads")` else `LaunchRefused` naming the cap, free space ≥ `MIN_FREE_GB` else `LaunchRefused` with the numbers, template-validated settings snapshot → `write_settings`; creates the run `queued` and calls `runner.submit`), `list_for(user) -> list[dict]` (own runs, newest first; admins: all runs), `running_jobs() -> list[dict]` (for admins: `runner.active_jobs()`), `get(user, run_id) -> dict` (`require_view_run`), `async cancel(user, run_id)`, `set_pinned(user, run_id, flag)`, `set_public(user, run_id, flag)`, `log_tail(user, run_id, n=50) -> tuple[str | None, str]` (active or last stage and its tail), `progress(user, run_id) -> dict | None`, `download_path(user, run_id, name) -> Path` (`name` in `("sfincs_his.nc", "sfincs.inp", "settings.json", "overrides.diff")`; `NotFound` when absent), `free_space_gb(path) -> float` module function. Run dicts: `id, project_id, project_name, owner_id, name, status, threads, public, pinned, created_at, started_at, finished_at, exit_code, summary, stages: [{stage, status, started_at, finished_at, exit_code}]`.

- [ ] **Step 1: Write the failing tests**

`sfincs_ui/tests/test_project_service.py`:

```python
import pytest

from sfincs_ui.config import Config
from sfincs_ui.exceptions import NotAllowed, NotFound, TemplateError
from sfincs_ui.services.auth_service import AuthService
from sfincs_ui.services.project_service import ProjectService
from tests.fake_template import FakeTemplate


@pytest.fixture
def users(db):
    auth = AuthService(session_factory=db)
    admin, _ = auth.ensure_admin("root", "pw12345678")
    alice = auth.create_user("alice", "pw12345678")
    bob = auth.create_user("bob", "pw12345678")
    return admin, alice, bob


@pytest.fixture
def svc(db, tmp_path):
    return ProjectService(Config(workspace=tmp_path), session_factory=db, templates={"fake": FakeTemplate()})


def test_examples_are_seeded_once(svc):
    assert svc.ensure_examples() == 1 and svc.ensure_examples() == 0
    ex = svc.examples()
    assert len(ex) == 1 and ex[0]["owner_id"] is None and ex[0]["name"] == "Fake example" and ex[0]["template"] == "fake"


def test_create_list_get_rename_update(svc, users):
    _, alice, bob = users
    p = svc.create(alice, "fake", "My project")
    assert p["owner_id"] == alice["id"] and p["settings"] == {"alpha": 0.5} and p["template_title"] == "Fake"
    assert svc.project_dir(p["id"]).is_dir()
    assert [x["id"] for x in svc.list_for(alice)] == [p["id"]] and svc.list_for(bob) == []
    assert svc.get(alice, p["id"])["name"] == "My project"
    with pytest.raises(NotAllowed):
        svc.get(bob, p["id"])
    with pytest.raises(NotFound):
        svc.get(alice, "nope")
    svc.rename(alice, p["id"], "Renamed")
    updated = svc.update_settings(alice, p["id"], {"alpha": "0.8", "evil": 1})
    assert updated["settings"] == {"alpha": 0.8} and updated["name"] == "Renamed"
    with pytest.raises(TemplateError):
        svc.update_settings(alice, p["id"], {"alpha": 5})
    with pytest.raises(NotAllowed):
        svc.update_settings(bob, p["id"], {"alpha": 0.2})


def test_clone_copies_settings_only_and_examples_are_usable_by_all(svc, users):
    _, alice, bob = users
    svc.ensure_examples()
    ex = svc.examples()[0]
    c = svc.clone(bob, ex["id"], "Bob's copy")
    assert c["owner_id"] == bob["id"] and c["settings"] == ex["settings"] and c["id"] != ex["id"]
    with pytest.raises(NotAllowed):
        svc.rename(bob, ex["id"], "hijack")  # system project: admin only
    with pytest.raises(NotAllowed):
        svc.create(None, "fake", "anon")
    with pytest.raises(TemplateError):
        svc.create(alice, "unknown", "x")


def test_delete_removes_directory_and_refuses_while_active(svc, users, db, tmp_path):
    from tests.runner_helpers import make_run
    from sfincs_ui.models import Run

    _, alice, bob = users
    p = svc.create(alice, "fake", "P")
    with pytest.raises(NotAllowed):
        svc.delete(bob, p["id"])
    svc.delete(alice, p["id"])
    assert not svc.project_dir(p["id"]).exists() and svc.list_for(alice) == []
    run_id = make_run(db, tmp_path, "fake", {"alpha": 0.5}, owner_id=alice["id"])
    s = db(); project_id = s.get(Run, run_id).project_id; s.get(Run, run_id).status = "running"; s.commit(); s.close()
    with pytest.raises(NotAllowed, match="active"):
        svc.delete(alice, project_id)
```

`sfincs_ui/tests/test_run_service.py`:

```python
import asyncio

import pytest

from sfincs_ui.exceptions import LaunchRefused, NotAllowed, NotFound
from sfincs_ui.services import run_service as rs
from sfincs_ui.services.auth_service import AuthService
from sfincs_ui.services.project_service import ProjectService
from sfincs_ui.services.run_service import RunService
from sfincs_ui.services.settings_service import SettingsService
from tests.fake_template import FakeTemplate


@pytest.fixture
def world(db, tmp_path, runner):
    from sfincs_ui.config import get_config
    cfg = get_config()  # set by the runner fixture: max_simulations=1, max_threads=4, fake binary
    auth = AuthService(session_factory=db)
    admin, _ = auth.ensure_admin("root", "pw12345678")
    alice = auth.create_user("alice", "pw12345678")
    bob = auth.create_user("bob", "pw12345678")
    templates = {"fake": FakeTemplate()}
    projects = ProjectService(cfg, session_factory=db, templates=templates)
    settings = SettingsService(cfg, session_factory=db)
    runs = RunService(cfg, settings, projects, runner, session_factory=db, templates=templates)
    project = projects.create(alice, "fake", "P", {"alpha": 0.7})
    return {"admin": admin, "alice": alice, "bob": bob, "projects": projects, "runs": runs, "project": project, "cfg": cfg}


async def test_launch_runs_to_completion_and_exposes_downloads(world, runner):
    await runner.start()
    r = world["runs"].launch(world["alice"], world["project"]["id"], "first", 2)
    assert r["status"] == "queued" and r["threads"] == 2 and r["owner_id"] == world["alice"]["id"]
    await runner.wait(r["id"], timeout=20)
    got = world["runs"].get(world["alice"], r["id"])
    assert got["status"] == "finished" and [s["stage"] for s in got["stages"]] == ["build", "simulate"]
    assert world["runs"].download_path(world["alice"], r["id"], "sfincs_his.nc").is_file()
    assert "+alpha           = 0.7" in world["runs"].download_path(world["alice"], r["id"], "overrides.diff").read_text()
    with pytest.raises(NotFound):
        world["runs"].download_path(world["alice"], r["id"], "sfincs_map.nc")
    stage, text = world["runs"].log_tail(world["alice"], r["id"])
    assert stage == "simulate" and "Simulation finished" in text
    assert world["runs"].progress(world["alice"], r["id"])["percent"] == 100


def test_launch_refusals(world, monkeypatch):
    runs, alice, pid = world["runs"], world["alice"], world["project"]["id"]
    with pytest.raises(LaunchRefused, match="4"):
        runs.launch(alice, pid, "x", 9)
    with pytest.raises(LaunchRefused):
        runs.launch(alice, pid, "x", 0)
    with pytest.raises(LaunchRefused, match="name"):
        runs.launch(alice, pid, "  ", 1)
    with pytest.raises(NotAllowed):
        runs.launch(world["bob"], pid, "x", 1)
    with pytest.raises(NotAllowed):
        runs.launch(None, pid, "x", 1)
    monkeypatch.setattr(rs, "free_space_gb", lambda path: 12.5)
    with pytest.raises(LaunchRefused, match="12.5 GB free.*100 GB"):
        runs.launch(alice, pid, "x", 1)


async def test_cancel_other_users_run_refused(world, runner, monkeypatch):
    """Review Focus 5."""
    monkeypatch.setenv("FAKE_STEPS", "100"); monkeypatch.setenv("FAKE_SLEEP", "0.1")
    await runner.start()
    r = world["runs"].launch(world["alice"], world["project"]["id"], "slow", 1)
    while world["runs"].get(world["alice"], r["id"])["status"] != "running":
        await asyncio.sleep(0.02)
    with pytest.raises(NotAllowed):
        await world["runs"].cancel(world["bob"], r["id"])
    with pytest.raises(NotAllowed):
        world["runs"].set_pinned(world["bob"], r["id"], True)
    with pytest.raises(NotAllowed):
        world["runs"].set_public(world["bob"], r["id"], True)
    with pytest.raises(NotAllowed):
        world["runs"].log_tail(world["bob"], r["id"])
    assert world["runs"].get(world["alice"], r["id"])["status"] == "running"
    await world["runs"].cancel(world["admin"], r["id"])  # an admin may
    assert world["runs"].get(world["alice"], r["id"])["status"] == "cancelled"


async def test_download_path_other_users_private_run_refused_until_public(world, runner):
    """Review Focus 5."""
    await runner.start()
    r = world["runs"].launch(world["alice"], world["project"]["id"], "p", 1)
    await runner.wait(r["id"], timeout=20)
    with pytest.raises(NotAllowed):
        world["runs"].download_path(world["bob"], r["id"], "sfincs_his.nc")
    with pytest.raises(NotAllowed):
        world["runs"].get(None, r["id"])
    world["runs"].set_public(world["alice"], r["id"], True)
    assert world["runs"].download_path(world["bob"], r["id"], "sfincs_his.nc").is_file()
    assert world["runs"].get(None, r["id"])["public"] is True
    world["runs"].set_pinned(world["alice"], r["id"], True)
    assert world["runs"].get(world["alice"], r["id"])["pinned"] is True


async def test_list_for_scopes_and_running_jobs(world, runner, monkeypatch):
    monkeypatch.setenv("FAKE_STEPS", "100"); monkeypatch.setenv("FAKE_SLEEP", "0.1")
    await runner.start()
    r = world["runs"].launch(world["alice"], world["project"]["id"], "mine", 1)
    assert [x["id"] for x in world["runs"].list_for(world["alice"])] == [r["id"]]
    assert world["runs"].list_for(world["bob"]) == []
    assert [x["id"] for x in world["runs"].list_for(world["admin"])] == [r["id"]]
    while not world["runs"].running_jobs():
        await asyncio.sleep(0.02)
    assert world["runs"].running_jobs()[0]["run_id"] == r["id"]
    await world["runs"].cancel(world["alice"], r["id"])


def test_free_space_gb(tmp_path):
    assert rs.free_space_gb(tmp_path) > 0
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd /home/razinka/sfincs/sfincs_ui && /opt/micromamba/envs/shiny/bin/python -m pytest tests/test_project_service.py tests/test_run_service.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'sfincs_ui.services.project_service'`

- [ ] **Step 3: Write project_service.py**

```python
"""Projects: a template plus a settings document, owned by a user, with a workspace directory."""

from __future__ import annotations

import json
import logging
import shutil
from pathlib import Path

from sfincs_ui.config import Config
from sfincs_ui.exceptions import NotAllowed, NotFound, TemplateError
from sfincs_ui.models import ACTIVE_JOB_STATUSES, Project, Run, User, new_id
from sfincs_ui.services import access_control as ac
from sfincs_ui.timeutil import utcnow

logger = logging.getLogger(__name__)
MAX_NAME = 100
_ACTIVE_RUN_STATUSES = ("queued", "building", "running", "validating", "exporting")


class ProjectService:
    def __init__(self, config: Config, session_factory=None, templates=None):
        if session_factory is None:
            from sfincs_ui.db.base import get_session_factory
            session_factory = get_session_factory()
        if templates is None:
            from sfincs_ui.templates import TEMPLATES
            templates = TEMPLATES
        self._config = config
        self._sf = session_factory
        self._templates = templates

    def _template(self, key: str):
        try:
            return self._templates[key]
        except KeyError:
            raise TemplateError(f"unknown template {key!r}") from None

    def project_dir(self, project_id: str) -> Path:
        return self._config.workspace / project_id

    def _to_dict(self, p: Project, session) -> dict:
        owner = session.get(User, p.owner_id) if p.owner_id else None
        tpl = self._templates.get(p.template)
        return {"id": p.id, "owner_id": p.owner_id, "owner": owner.username if owner else None, "name": p.name,
                "template": p.template, "template_title": tpl.title if tpl else p.template,
                "settings": json.loads(p.settings_json), "created_at": p.created_at, "updated_at": p.updated_at,
                "run_count": session.query(Run).filter(Run.project_id == p.id).count()}

    def _get_row(self, session, project_id: str) -> Project:
        p = session.get(Project, project_id)
        if p is None:
            raise NotFound("Project not found")
        return p

    # -- examples ----------------------------------------------------------

    def ensure_examples(self) -> int:
        created = 0
        s = self._sf()
        try:
            for tpl in self._templates.values():
                for name, settings in tpl.example_projects():
                    exists = s.query(Project).filter(Project.owner_id.is_(None), Project.template == tpl.key, Project.name == name).first()
                    if exists is None:
                        p = Project(id=new_id(), owner_id=None, name=name, template=tpl.key, settings_json=json.dumps(tpl.validate(settings)))
                        s.add(p); s.flush()
                        self.project_dir(p.id).mkdir(parents=True, exist_ok=True)
                        created += 1
            s.commit()
            return created
        finally:
            s.close()

    def examples(self) -> list[dict]:
        s = self._sf()
        try:
            rows = s.query(Project).filter(Project.owner_id.is_(None)).order_by(Project.name).all()
            return [self._to_dict(p, s) for p in rows]
        finally:
            s.close()

    # -- CRUD --------------------------------------------------------------

    def list_for(self, user: dict | None) -> list[dict]:
        if not user:
            return []
        s = self._sf()
        try:
            rows = s.query(Project).filter(Project.owner_id == user["id"]).order_by(Project.created_at.desc()).all()
            return [self._to_dict(p, s) for p in rows]
        finally:
            s.close()

    def get(self, user: dict | None, project_id: str) -> dict:
        s = self._sf()
        try:
            p = self._get_row(s, project_id)
            d = self._to_dict(p, s)
            ac.require_use_project(user, d)
            return d
        finally:
            s.close()

    def create(self, user: dict | None, template_key: str, name: str, settings: dict | None = None) -> dict:
        ac.require_user(user)
        tpl = self._template(template_key)
        name = _clean_name(name)
        s = self._sf()
        try:
            p = Project(id=new_id(), owner_id=user["id"], name=name, template=tpl.key,
                        settings_json=json.dumps(tpl.validate(settings or {})))
            s.add(p); s.commit()
            self.project_dir(p.id).mkdir(parents=True, exist_ok=True)
            return self._to_dict(p, s)
        finally:
            s.close()

    def clone(self, user: dict | None, project_id: str, new_name: str) -> dict:
        src = self.get(user, project_id)  # require_use_project: examples and own projects
        return self.create(user, src["template"], new_name, src["settings"])

    def rename(self, user: dict | None, project_id: str, name: str) -> dict:
        name = _clean_name(name)
        s = self._sf()
        try:
            p = self._get_row(s, project_id)
            ac.require_modify_project(user, self._to_dict(p, s))
            p.name = name; s.commit()
            return self._to_dict(p, s)
        finally:
            s.close()

    def update_settings(self, user: dict | None, project_id: str, settings: dict) -> dict:
        s = self._sf()
        try:
            p = self._get_row(s, project_id)
            ac.require_modify_project(user, self._to_dict(p, s))
            p.settings_json = json.dumps(self._template(p.template).validate(settings)); s.commit()
            return self._to_dict(p, s)
        finally:
            s.close()

    def delete(self, user: dict | None, project_id: str) -> None:
        s = self._sf()
        try:
            p = self._get_row(s, project_id)
            ac.require_modify_project(user, self._to_dict(p, s))
            if s.query(Run).filter(Run.project_id == p.id, Run.status.in_(_ACTIVE_RUN_STATUSES)).count():
                raise NotAllowed("This project has an active run; cancel it first")
            s.delete(p); s.commit()
        finally:
            s.close()
        shutil.rmtree(self.project_dir(project_id), ignore_errors=True)


def _clean_name(name: str) -> str:
    name = (name or "").strip()
    if not name or len(name) > MAX_NAME:
        raise TemplateError(f"name must be 1-{MAX_NAME} characters")
    return name
```

- [ ] **Step 4: Write run_service.py**

```python
"""Launch, list, inspect and control runs. Every path enforces access control (spec section 5)."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from sfincs_ui.config import Config
from sfincs_ui.exceptions import LaunchRefused, NotAllowed, NotFound
from sfincs_ui.models import ACTIVE_JOB_STATUSES, Job, Project, Run, new_id
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
        s = self._sf()
        try:
            r = Run(id=run_id, project_id=project_id, name=name, status="queued", settings_json=json.dumps(settings),
                    workdir=str(run_dir), threads=threads)
            s.add(r); s.commit()
            write_settings(run_dir, settings)
            d = self._to_dict(r, s)
        finally:
            s.close()
        self._runner.submit(run_id)
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

    def running_jobs(self) -> list[dict]:
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
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `cd /home/razinka/sfincs/sfincs_ui && /opt/micromamba/envs/shiny/bin/python -m pytest tests/test_project_service.py tests/test_run_service.py -q`
Expected: 10 passed (full suite 186), no leaked processes.

- [ ] **Step 6: Commit**

```bash
cd /home/razinka/sfincs
git add sfincs_ui/sfincs_ui/services/project_service.py sfincs_ui/sfincs_ui/services/run_service.py sfincs_ui/tests/test_project_service.py sfincs_ui/tests/test_run_service.py
git commit -m "sfincs_ui: project and run services with access control, launch checks and downloads

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 8: Lifespan start, `active-jobs` / `kill-jobs`, deploy markers

**Files:**
- Create: `sfincs_ui/sfincs_ui/middleware/lifespan.py`
- Modify: `sfincs_ui/sfincs_ui/__main__.py` (two subcommands)
- Modify: `deploy/deploy_ui.sh` (replace the three `MILESTONE 2` comments; add `--wait`)
- Modify: `deploy/README.md` (modes table gains `--wait`; restart semantics)
- Test: `sfincs_ui/tests/test_lifespan.py`, `sfincs_ui/tests/test_cli_jobs.py`

**Interfaces:**
- Produces: `LifespanMiddleware(app, on_startup: Callable[[], Awaitable[None]] | None, on_shutdown: Callable[[], Awaitable[None]] | None)`: on `lifespan.startup` awaits `on_startup()` before forwarding the message to the inner app; on `lifespan.shutdown` awaits `on_shutdown()` after the inner app has handled it; non-lifespan scopes pass through. A startup hook exception is logged and the startup still proceeds (the banner already tells the user when the environment is broken; a reconciliation error must not take the whole app down).
- CLI: `python -m sfincs_ui active-jobs` prints one line per job in an active status (`<stage>\t<status>\tpid=<pid>\talive=<yes|no>\trun=<name>\t<workdir>`), exit 0 when none, 1 when at least one `simulate` job is alive, 2 when active rows exist but none is alive (stale rows the next start will reconcile). `python -m sfincs_ui kill-jobs` sends `killpg_graceful` to every alive active job, marks those jobs and runs `cancelled`, prints what it did, exit 0.
- Deploy: `--restart` and install mode run `active-jobs` as `shiny`; on exit 1 they **warn** (`"a simulation is running (pid …); restarting anyway: KillMode=process keeps it alive and the queue reconciles it"`) and proceed; `--wait` is a new mode that polls `active-jobs` every 30 s for up to 90 minutes until exit is not 1, then restarts. `--uninstall` runs `kill-jobs` before stopping the unit.

- [ ] **Step 1: Write the failing tests**

`sfincs_ui/tests/test_lifespan.py`:

```python
from unittest.mock import AsyncMock

from sfincs_ui.middleware.lifespan import LifespanMiddleware


async def _lifespan_messages():
    msgs = [{"type": "lifespan.startup"}, {"type": "lifespan.shutdown"}]

    async def receive():
        return msgs.pop(0)

    return receive


async def test_hooks_run_around_the_inner_app():
    order = []

    async def inner(scope, receive, send):
        while True:
            m = await receive()
            order.append(m["type"])
            if m["type"] == "lifespan.startup":
                await send({"type": "lifespan.startup.complete"})
            else:
                await send({"type": "lifespan.shutdown.complete"})
                return

    async def up():
        order.append("up")

    async def down():
        order.append("down")

    mw = LifespanMiddleware(inner, on_startup=up, on_shutdown=down)
    await mw({"type": "lifespan"}, await _lifespan_messages(), AsyncMock())
    assert order == ["up", "lifespan.startup", "lifespan.shutdown", "down"]


async def test_startup_failure_is_logged_not_fatal(caplog):
    async def inner(scope, receive, send):
        m = await receive(); await send({"type": "lifespan.startup.complete"})
        m = await receive(); await send({"type": "lifespan.shutdown.complete"})

    async def boom():
        raise RuntimeError("reconcile exploded")

    mw = LifespanMiddleware(inner, on_startup=boom, on_shutdown=None)
    await mw({"type": "lifespan"}, await _lifespan_messages(), AsyncMock())
    assert "reconcile exploded" in caplog.text


async def test_http_passes_through():
    inner = AsyncMock()
    await LifespanMiddleware(inner, None, None)({"type": "http"}, AsyncMock(), AsyncMock())
    inner.assert_called_once()
```

`sfincs_ui/tests/test_cli_jobs.py`:

```python
import os
import signal
import subprocess
import sys

from sfincs_ui import __main__ as cli
from sfincs_ui.models import Job, Run
from sfincs_ui.services.procs import is_alive, proc_starttime
from tests.runner_helpers import make_run, run_row


def _job(db, run_id, pid, st, stage="simulate"):
    s = db()
    try:
        s.get(Run, run_id).status = "running"
        s.add(Job(run_id=run_id, stage=stage, status="running", pid=pid, proc_starttime=st, log_path=""))
        s.commit()
    finally:
        s.close()


def test_active_jobs_exit_codes(db, tmp_path, capsys):
    assert cli.main(["active-jobs"]) == 0
    run_id = make_run(db, tmp_path, "fake", {"alpha": 0.5})
    _job(db, run_id, 2**22 - 2, 123)  # dead pid
    assert cli.main(["active-jobs"]) == 2
    assert "alive=no" in capsys.readouterr().out
    proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"], start_new_session=True)
    try:
        _job(db, run_id, proc.pid, proc_starttime(proc.pid))
        assert cli.main(["active-jobs"]) == 1
        out = capsys.readouterr().out
        assert f"pid={proc.pid}" in out and "alive=yes" in out and "simulate" in out
    finally:
        os.killpg(proc.pid, signal.SIGKILL); proc.wait()


def test_kill_jobs_terminates_and_cancels(db, tmp_path, capsys):
    run_id = make_run(db, tmp_path, "fake", {"alpha": 0.5})
    proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"], start_new_session=True)
    try:
        st = proc_starttime(proc.pid)
        _job(db, run_id, proc.pid, st)
        assert cli.main(["kill-jobs"]) == 0
        proc.wait(timeout=5)
        assert not is_alive(proc.pid, st)
        row = run_row(db, run_id)
        assert row["status"] == "cancelled" and row["jobs"][-1]["status"] == "cancelled"
        assert f"{proc.pid}" in capsys.readouterr().out
        assert cli.main(["active-jobs"]) == 0
    finally:
        if proc.poll() is None:
            os.killpg(proc.pid, signal.SIGKILL); proc.wait()
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd /home/razinka/sfincs/sfincs_ui && /opt/micromamba/envs/shiny/bin/python -m pytest tests/test_lifespan.py tests/test_cli_jobs.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'sfincs_ui.middleware.lifespan'` and `SystemExit: 2` (unknown subcommand).

- [ ] **Step 3: Write the lifespan middleware**

`sfincs_ui/sfincs_ui/middleware/lifespan.py`:

```python
"""Run coroutines at ASGI lifespan startup and shutdown.

The job runner needs a running event loop, which exists only once uvicorn is
up; starting it from the first request would race. Startup runs the hook
before the inner app's startup; shutdown runs it after the inner app's
shutdown. A startup hook failure is logged, never fatal: the banner already
reports a broken environment, and a reconciliation error must not stop the
pages from serving.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


class LifespanMiddleware:
    def __init__(self, app, on_startup=None, on_shutdown=None):
        self.app = app
        self._on_startup = on_startup
        self._on_shutdown = on_shutdown

    async def __call__(self, scope, receive, send):
        if scope["type"] != "lifespan":
            await self.app(scope, receive, send)
            return

        async def wrapped_receive():
            message = await receive()
            if message["type"] == "lifespan.startup" and self._on_startup is not None:
                try:
                    await self._on_startup()
                except Exception:
                    logger.exception("startup hook failed; continuing without it")
            return message

        async def wrapped_send(message):
            await send(message)
            if message["type"] == "lifespan.shutdown.complete" and self._on_shutdown is not None:
                try:
                    await self._on_shutdown()
                except Exception:
                    logger.exception("shutdown hook failed")

        await self.app(scope, wrapped_receive, wrapped_send)
```

- [ ] **Step 4: Add the CLI subcommands**

In `sfincs_ui/sfincs_ui/__main__.py` add two handlers and register them in `main()` after `preflight`:

```python
def _cmd_active_jobs(_args) -> int:
    from sfincs_ui.db import base
    from sfincs_ui.models import ACTIVE_JOB_STATUSES, Job, Run
    from sfincs_ui.services.procs import is_alive

    base.init_db()
    s = base.get_session_factory()()
    try:
        rows = (s.query(Job, Run).join(Run, Job.run_id == Run.id)
                .filter(Job.status.in_(ACTIVE_JOB_STATUSES)).order_by(Job.id).all())
        any_alive = False
        for job, run in rows:
            alive = bool(job.pid) and is_alive(job.pid, job.proc_starttime)
            any_alive = any_alive or (alive and job.stage == "simulate")
            print(f"{job.stage}\t{job.status}\tpid={job.pid}\talive={'yes' if alive else 'no'}\trun={run.name}\t{run.workdir}")
        if not rows:
            return 0
        return 1 if any_alive else 2
    finally:
        s.close()


def _cmd_kill_jobs(_args) -> int:
    from sfincs_ui.db import base
    from sfincs_ui.models import ACTIVE_JOB_STATUSES, Job, Run
    from sfincs_ui.services.procs import is_alive, killpg_graceful
    from sfincs_ui.timeutil import utcnow

    base.init_db()
    s = base.get_session_factory()()
    try:
        rows = s.query(Job).filter(Job.status.in_(ACTIVE_JOB_STATUSES)).order_by(Job.id).all()
        for job in rows:
            outcome = "no process"
            if job.pid and is_alive(job.pid, job.proc_starttime):
                outcome = killpg_graceful(job.pid, grace_s=30.0)
            job.status = "cancelled"; job.finished_at = utcnow()
            run = s.get(Run, job.run_id)
            if run is not None and run.status not in ("finished", "failed", "cancelled", "orphaned"):
                run.status = "cancelled"; run.finished_at = utcnow()
            print(f"{job.stage} pid={job.pid}: {outcome}; run {job.run_id} cancelled")
        s.commit()
        print(f"{len(rows)} active job(s) handled")
        return 0
    finally:
        s.close()
```

and in `main()`:

```python
    sub.add_parser("active-jobs", help="list active stage jobs; exit 1 when a simulation is alive").set_defaults(func=_cmd_active_jobs)
    sub.add_parser("kill-jobs", help="terminate every detached stage and cancel its run (used by uninstall)").set_defaults(func=_cmd_kill_jobs)
```

- [ ] **Step 5: Replace the deploy markers**

In `deploy/deploy_ui.sh`:

1. Add `--wait` to the usage header and to the `case "$MODE"` list.
2. Add a helper after `render_template`:

```bash
# Exit 1 from active-jobs means a simulation is alive. The unit's KillMode=process
# keeps it alive across a restart and the queue reconciles it at startup, so a
# restart is safe; we warn so the operator knows a run is in flight.
warn_if_simulating() {
    local out rc
    out="$(as_shiny active-jobs 2>/dev/null)"; rc=$?
    if [[ $rc -eq 1 ]]; then
        warn "a simulation is running; restarting anyway (KillMode=process keeps it alive, the queue reconciles it):"
        echo "$out" | sed 's/^/      /'
    fi
    return 0
}
wait_for_simulations() {  # --wait: poll up to 90 minutes
    local rc
    for _ in $(seq 1 180); do
        as_shiny active-jobs >/dev/null 2>&1; rc=$?
        [[ $rc -ne 1 ]] && return 0
        info "a simulation is running; waiting 30 s (--wait)"
        sleep 30
    done
    warn "simulation still running after 90 minutes; restarting anyway"
}
```

3. `--restart` mode: replace the first `MILESTONE 2` comment block and the restart line with:

```bash
    need_root --restart
    [[ -f "$ENV_FILE" ]] || fail "${ENV_FILE} missing; run a full install first"
    warn_if_simulating
    systemctl restart "$SERVICE_NAME" || fail "could not restart ${SERVICE_NAME}; see: journalctl -u ${SERVICE_NAME} -n 40"
    info "restarted ${SERVICE_NAME}"
    exit 0
```

4. Add a `--wait` mode block right after `--restart` with the same body but `wait_for_simulations` in place of `warn_if_simulating`.
5. `--uninstall`: replace the second `MILESTONE 2` comment with `[[ -f "$ENV_FILE" ]] && as_shiny kill-jobs || true` before `systemctl stop`.
6. Install mode: replace the third `MILESTONE 2` comment with `warn_if_simulating` immediately before `systemctl restart "$SERVICE_NAME"`.

`deploy/README.md`: in the SFINCS UI section's command list add `sudo bash deploy/deploy_ui.sh --wait        # wait for running simulations, then restart`, and add the sentence: "A restart while a simulation runs is safe: the unit's `KillMode=process` leaves the solver alive and the queue reconciles it at startup; the script warns. systemd logs `Found left-over process … Ignoring` for the surviving solver, which is expected."

- [ ] **Step 6: Run the tests and static checks**

Run: `cd /home/razinka/sfincs/sfincs_ui && /opt/micromamba/envs/shiny/bin/python -m pytest tests/test_lifespan.py tests/test_cli_jobs.py -q`
Expected: 5 passed (full suite 191)

Run: `cd /home/razinka/sfincs && bash -n deploy/deploy_ui.sh && grep -c 'MILESTONE 2' deploy/deploy_ui.sh`
Expected: no syntax error, `0`.

- [ ] **Step 7: Commit**

```bash
cd /home/razinka/sfincs
git add sfincs_ui/sfincs_ui/middleware/lifespan.py sfincs_ui/sfincs_ui/__main__.py deploy/deploy_ui.sh deploy/README.md sfincs_ui/tests/test_lifespan.py sfincs_ui/tests/test_cli_jobs.py
git commit -m "sfincs_ui: lifespan hooks, active-jobs and kill-jobs; deploy restart warns about live simulations

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 9: Projects, Setup and Runs pages

**Files:**
- Create: `sfincs_ui/sfincs_ui/pages/projects.py`
- Create: `sfincs_ui/sfincs_ui/pages/setup.py`
- Create: `sfincs_ui/sfincs_ui/pages/runs.py`
- Modify: `sfincs_ui/sfincs_ui/pages/home.py` (example projects list)
- Test: `sfincs_ui/tests/test_pages_m2.py`

**Interfaces:**
- Consumes: `ProjectService`, `RunService`, `SettingsService`, `TEMPLATES`, exceptions, `current_user()`.
- Produces: `projects.projects_ui(id)`, `projects.projects_server(id, project_service, current_user, active_project: reactive.Value[str | None], goto: Callable[[str], None])`; `setup.setup_ui(id)`, `setup.setup_server(id, project_service, run_service, settings_service, current_user, active_project, active_run: reactive.Value[str | None], goto)`; `runs.runs_ui(id)`, `runs.runs_server(id, run_service, current_user, active_run)`; pure helpers `setup.render_field(field, value) -> Tag` (one Shiny input per `SettingField.kind`, id = field key), `setup.collect_settings(input, fields) -> dict`, `runs.status_badge(status) -> str`, `runs.format_stages(stages) -> list[str]`, `runs.progress_bar(progress: dict | None) -> Tag`. `goto(panel_name)` calls `ui.update_navs("main_nav", selected=panel_name)`.

Page behaviour (spec section 4):
- **Projects** (login): table of my projects (name, template, runs, updated) with Open (sets `active_project`, `goto("Setup")`), Clone, Rename, Delete (modal confirmation; deletes the project's runs); "New project" modal (template select, name); the example projects listed with Clone. Anonymous: "Log in to create projects."
- **Setup** (login): shows the active project's name and template; the template's fields rendered by group ("Model", then "Solver overrides" with the default shown beside each field and a `changed` class when the value differs from the default); Save settings; "Launch run" opens a modal with run name (default `<project name> <n+1>`) and threads (numeric, default `template.default_threads`, max = `settings_service.get("max_threads")` shown in the label); on launch → `run_service.launch`, `active_run` set, `goto("Runs")`. Errors (`TemplateError`, `LaunchRefused`, `NotAllowed`) become notifications.
- **Runs** (login): table of my runs (name, project, status badge, threads, started, finished) with Select; admins also see a "Running now (all users)" table from `running_jobs()`. Selected run: stage timeline (`format_stages`), progress bar from `progress()` while running, log tail refreshed every 2 s only while the selected run is active (`reactive.invalidate_later(2)` inside the render that reads it), Cancel (active runs), Pin/Unpin, Public/Private toggles, Download `sfincs_his.nc` (`@render.download`, through `download_path`, so access control applies). Failed runs show the summary's stage, reason and log tail.
- **Home**: lists `project_service.examples()` as cards with "Clone into my projects" (login required).

- [ ] **Step 1: Write the failing tests**

`sfincs_ui/tests/test_pages_m2.py`:

```python
from shiny import ui

from sfincs_ui.pages import projects, runs, setup
from sfincs_ui.templates import get_template


def test_pages_render_with_expected_ids():
    html = str(projects.projects_ui("projects"))
    for i in ("projects-new_project_btn", "projects-project_table", "projects-examples"):
        assert i in html
    html = str(setup.setup_ui("setup"))
    for i in ("setup-form", "setup-save_btn", "setup-launch_btn", "setup-header"):
        assert i in html
    html = str(runs.runs_ui("runs"))
    for i in ("runs-run_table", "runs-detail", "runs-log_tail", "runs-download_his"):
        assert i in html


def test_render_field_per_kind():
    tpl = get_template("plane_beach")
    fields = {f.key: f for f in tpl.fields()}
    assert 'type="number"' in str(setup.render_field(fields["duration_hours"], 6))
    assert "<select" in str(setup.render_field(fields["resolution_m"], 100)) and 'value="100"' in str(setup.render_field(fields["resolution_m"], 100))
    assert 'type="checkbox"' in str(setup.render_field(fields["advection"], True))
    assert "changed" in str(setup.render_field(fields["alpha"], 0.7)) and "changed" not in str(setup.render_field(fields["alpha"], 0.5))
    assert "default 0.5" in str(setup.render_field(fields["alpha"], 0.7))


def test_collect_settings_reads_each_field():
    tpl = get_template("plane_beach")

    class FakeInput:
        def __init__(self, values):
            self._v = values

        def __getitem__(self, key):
            return lambda: self._v[key]

    values = {"resolution_m": "50", "duration_hours": 3, "boundary_level_m": 1.5, "manning": 0.03, "alpha": 0.6, "huthresh": 0.1, "advection": False}
    assert setup.collect_settings(FakeInput(values), tpl.fields()) == values


def test_runs_helpers():
    assert "bg-success" in runs.status_badge("finished") and "bg-danger" in runs.status_badge("failed")
    assert "bg-warning" in runs.status_badge("running") and "bg-secondary" in runs.status_badge("queued")
    stages = [{"stage": "build", "status": "completed", "started_at": None, "finished_at": None, "exit_code": 0},
              {"stage": "simulate", "status": "running", "started_at": None, "finished_at": None, "exit_code": None}]
    assert runs.format_stages(stages) == ["build: completed (exit 0)", "simulate: running"]
    assert "45%" in str(runs.progress_bar({"percent": 45, "remaining_s": 120.0})) and "2.0 min" in str(runs.progress_bar({"percent": 45, "remaining_s": 120.0}))
    assert str(runs.progress_bar(None)) == ""
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd /home/razinka/sfincs/sfincs_ui && /opt/micromamba/envs/shiny/bin/python -m pytest tests/test_pages_m2.py -q`
Expected: FAIL with `ImportError: cannot import name 'projects'`

- [ ] **Step 3: Write the Projects page**

`sfincs_ui/sfincs_ui/pages/projects.py`:

```python
"""Projects: my projects and the shipped examples (spec section 4)."""

from __future__ import annotations

import logging

from shiny import module, reactive, render, ui

from sfincs_ui.exceptions import SfincsUiError
from sfincs_ui.templates import TEMPLATES

logger = logging.getLogger(__name__)


@module.ui
def projects_ui() -> ui.Tag:
    return ui.div(
        ui.div(ui.h3("Projects", class_="me-auto"),
               ui.input_action_button("new_project_btn", "New project", class_="btn-primary"),
               class_="d-flex align-items-center mb-2"),
        ui.output_ui("project_table"),
        ui.hr(),
        ui.h5("Example projects"),
        ui.output_ui("examples"),
        class_="container py-3",
    )


@module.server
def projects_server(input, output, session, project_service, current_user, active_project, goto):
    tick = reactive.value(0)
    registered: set[str] = set()

    def _refresh():
        tick.set(tick.get() + 1)

    def _notify(exc: Exception):
        ui.notification_show(str(exc), type="error", duration=8)

    @render.ui
    def project_table():
        tick.get()
        user = current_user()
        if user is None:
            return ui.p("Log in to create projects.", class_="text-muted")
        rows = project_service.list_for(user)
        if not rows:
            return ui.p("No projects yet. Create one or clone an example.", class_="text-muted")
        body = []
        for p in rows:
            _register(p["id"])
            body.append(ui.tags.tr(
                ui.tags.td(p["name"]), ui.tags.td(p["template_title"]), ui.tags.td(str(p["run_count"])),
                ui.tags.td(str(p["updated_at"])[:16]),
                ui.tags.td(
                    ui.input_action_button(f"open_{_safe(p['id'])}", "Open", class_="btn-sm btn-primary me-1"),
                    ui.input_action_button(f"clone_{_safe(p['id'])}", "Clone", class_="btn-sm btn-outline-secondary me-1"),
                    ui.input_action_button(f"rename_{_safe(p['id'])}", "Rename", class_="btn-sm btn-outline-secondary me-1"),
                    ui.input_action_button(f"delete_{_safe(p['id'])}", "Delete", class_="btn-sm btn-outline-danger"),
                ),
            ))
        return ui.tags.table(ui.tags.thead(ui.tags.tr(*[ui.tags.th(h) for h in ("Name", "Template", "Runs", "Updated", "")])),
                             ui.tags.tbody(*body), class_="table table-sm align-middle")

    @render.ui
    def examples():
        tick.get()
        rows = project_service.examples()
        if not rows:
            return ui.p("No example projects.", class_="text-muted")
        cards = []
        for p in rows:
            _register(p["id"])
            cards.append(ui.div(ui.h6(p["name"]), ui.p(TEMPLATES[p["template"]].description, class_="small text-muted"),
                                ui.input_action_button(f"clone_{_safe(p['id'])}", "Clone into my projects", class_="btn-sm btn-outline-primary"),
                                class_="card p-3 me-2 mb-2", style="max-width: 24rem"))
        return ui.div(*cards, class_="d-flex flex-wrap")

    def _register(project_id: str):
        if project_id in registered:
            return
        registered.add(project_id)
        pid = _safe(project_id)

        @reactive.effect
        @reactive.event(input[f"open_{pid}"])
        def _open():
            if current_user() is None:
                return
            active_project.set(project_id)
            goto("Setup")

        @reactive.effect
        @reactive.event(input[f"clone_{pid}"])
        def _clone():
            user = current_user()
            if user is None:
                ui.notification_show("Log in to clone a project", type="warning"); return
            try:
                src = project_service.get(user, project_id)
                p = project_service.clone(user, project_id, f"{src['name']} (copy)")
                active_project.set(p["id"]); _refresh()
                ui.notification_show(f"Cloned as {p['name']}", type="message")
            except SfincsUiError as exc:
                _notify(exc)

        @reactive.effect
        @reactive.event(input[f"rename_{pid}"])
        def _rename():
            if current_user() is None:
                return
            ui.modal_show(ui.modal(ui.input_text(f"rename_name_{pid}", "New name"), title="Rename project",
                                   footer=ui.div(ui.modal_button("Cancel"), ui.input_action_button(f"confirm_rename_{pid}", "Rename", class_="btn-primary")),
                                   easy_close=True))

        @reactive.effect
        @reactive.event(input[f"confirm_rename_{pid}"])
        def _do_rename():
            try:
                project_service.rename(current_user(), project_id, input[f"rename_name_{pid}"]())
                ui.modal_remove(); _refresh()
            except SfincsUiError as exc:
                _notify(exc)

        @reactive.effect
        @reactive.event(input[f"delete_{pid}"])
        def _delete():
            if current_user() is None:
                return
            ui.modal_show(ui.modal(ui.p("Delete this project and all its runs?"), title="Delete project",
                                   footer=ui.div(ui.modal_button("Cancel"), ui.input_action_button(f"confirm_delete_{pid}", "Delete", class_="btn-danger")),
                                   easy_close=True))

        @reactive.effect
        @reactive.event(input[f"confirm_delete_{pid}"])
        def _do_delete():
            try:
                project_service.delete(current_user(), project_id)
                if active_project.get() == project_id:
                    active_project.set(None)
                ui.modal_remove(); _refresh()
            except SfincsUiError as exc:
                _notify(exc)

    @reactive.effect
    @reactive.event(input.new_project_btn)
    def _new():
        if current_user() is None:
            ui.notification_show("Log in to create a project", type="warning"); return
        ui.modal_show(ui.modal(
            ui.input_select("new_template", "Template", {k: t.title for k, t in TEMPLATES.items()}),
            ui.input_text("new_name", "Name"),
            title="New project",
            footer=ui.div(ui.modal_button("Cancel"), ui.input_action_button("confirm_new", "Create", class_="btn-primary")),
            easy_close=True))

    @reactive.effect
    @reactive.event(input.confirm_new)
    def _do_new():
        try:
            p = project_service.create(current_user(), input.new_template(), input.new_name())
            active_project.set(p["id"]); ui.modal_remove(); _refresh(); goto("Setup")
        except SfincsUiError as exc:
            _notify(exc)


def _safe(project_id: str) -> str:
    return project_id.replace("-", "_")
```

- [ ] **Step 4: Write the Setup page**

`sfincs_ui/sfincs_ui/pages/setup.py`:

```python
"""Setup: the template's settings form for the active project, and the Launch dialog."""

from __future__ import annotations

import logging

from shiny import module, reactive, render, ui

from sfincs_ui.exceptions import SfincsUiError
from sfincs_ui.templates import get_template
from sfincs_ui.templates.base import SettingField

logger = logging.getLogger(__name__)


def render_field(field: SettingField, value) -> ui.Tag:
    changed = "changed" if value != field.default else ""
    label = ui.span(field.label, ui.span(f" (default {field.default})", class_="text-muted small") if field.group == "Solver overrides" else "")
    if field.kind == "bool":
        widget = ui.input_checkbox(field.key, label, bool(value))
    elif field.kind == "choice":
        widget = ui.input_select(field.key, label, {str(c): str(c) for c in field.choices}, selected=str(value))
    else:
        step = 1 if field.kind == "int" else None
        widget = ui.input_numeric(field.key, label, value, min=field.minimum, max=field.maximum, step=step)
    return ui.div(widget, ui.p(field.explanation, class_="text-muted small mb-2"), class_=f"setting {changed}".strip())


def collect_settings(input, fields: list[SettingField]) -> dict:
    out = {}
    for f in fields:
        raw = input[f.key]()
        out[f.key] = raw
    return out


@module.ui
def setup_ui() -> ui.Tag:
    return ui.div(
        ui.output_ui("header"),
        ui.row(
            ui.column(7, ui.output_ui("form")),
            ui.column(5, ui.div(ui.input_action_button("save_btn", "Save settings", class_="btn-outline-primary w-100 mb-2"),
                                ui.input_action_button("launch_btn", "Launch run", class_="btn-primary w-100"),
                                ui.p("The map preview arrives with the Curonian template.", class_="text-muted small mt-3"),
                                class_="card p-3")),
        ),
        class_="container py-3",
    )


@module.server
def setup_server(input, output, session, project_service, run_service, settings_service, current_user, active_project, active_run, goto):
    def _project():
        pid = active_project.get()
        user = current_user()
        if pid is None or user is None:
            return None
        try:
            return project_service.get(user, pid)
        except SfincsUiError:
            return None

    def _notify(exc):
        ui.notification_show(str(exc), type="error", duration=8)

    @render.ui
    def header():
        if current_user() is None:
            return ui.p("Log in and open a project to edit its settings.", class_="text-muted")
        p = _project()
        if p is None:
            return ui.p("Open a project on the Projects page.", class_="text-muted")
        return ui.div(ui.h3(p["name"]), ui.p(p["template_title"], class_="text-muted"))

    @render.ui
    def form():
        p = _project()
        if p is None:
            return None
        tpl = get_template(p["template"])
        groups: dict[str, list] = {}
        for f in tpl.fields():
            groups.setdefault(f.group, []).append(render_field(f, p["settings"].get(f.key, f.default)))
        return ui.div(*[ui.div(ui.h5(g), *items, class_="mb-3") for g, items in groups.items()])

    def _current_settings(p) -> dict:
        return collect_settings(input, get_template(p["template"]).fields())

    @reactive.effect
    @reactive.event(input.save_btn)
    def _save():
        p = _project()
        if p is None:
            return
        try:
            project_service.update_settings(current_user(), p["id"], _current_settings(p))
            ui.notification_show("Settings saved", type="message")
        except SfincsUiError as exc:
            _notify(exc)

    @reactive.effect
    @reactive.event(input.launch_btn)
    def _launch_dialog():
        p = _project()
        if p is None:
            return
        tpl = get_template(p["template"])
        cap = settings_service.get("max_threads")
        ui.modal_show(ui.modal(
            ui.input_text("run_name", "Run name", value=f"{p['name']} {p['run_count'] + 1}"),
            ui.input_numeric("run_threads", f"Threads (1-{cap})", tpl.default_threads(p["settings"]), min=1, max=cap, step=1),
            ui.p("Unsaved settings are saved first.", class_="text-muted small"),
            title="Launch run",
            footer=ui.div(ui.modal_button("Cancel"), ui.input_action_button("confirm_launch", "Launch", class_="btn-primary")),
            easy_close=True))

    @reactive.effect
    @reactive.event(input.confirm_launch)
    def _do_launch():
        p = _project()
        if p is None:
            return
        try:
            user = current_user()
            project_service.update_settings(user, p["id"], _current_settings(p))
            run = run_service.launch(user, p["id"], input.run_name(), input.run_threads())
            active_run.set(run["id"]); ui.modal_remove(); goto("Runs")
            ui.notification_show(f"Launched {run['name']}", type="message")
        except SfincsUiError as exc:
            _notify(exc)
```

- [ ] **Step 5: Write the Runs page**

`sfincs_ui/sfincs_ui/pages/runs.py`:

```python
"""Runs: my runs, the selected run's stages, progress and log tail, and run controls."""

from __future__ import annotations

import asyncio
import logging

from shiny import module, reactive, render, ui

from sfincs_ui.exceptions import SfincsUiError
from sfincs_ui.models import ACTIVE_JOB_STATUSES
from sfincs_ui.services import access_control as ac

logger = logging.getLogger(__name__)
_ACTIVE = ("queued", "building", "running", "validating", "exporting")
_BADGE = {"finished": "bg-success", "failed": "bg-danger", "cancelled": "bg-dark", "orphaned": "bg-dark",
          "queued": "bg-secondary", "building": "bg-info", "running": "bg-warning text-dark", "validating": "bg-info", "exporting": "bg-info"}


def status_badge(status: str) -> str:
    return f'<span class="badge {_BADGE.get(status, "bg-secondary")}">{status}</span>'


def format_stages(stages: list[dict]) -> list[str]:
    out = []
    for s in stages:
        line = f"{s['stage']}: {s['status']}"
        if s.get("exit_code") is not None:
            line += f" (exit {s['exit_code']})"
        out.append(line)
    return out


def progress_bar(progress: dict | None):
    if not progress:
        return ui.TagList()
    pct = progress["percent"]
    remaining = progress.get("remaining_s")
    label = f"{pct}%" + (f", about {remaining / 60:.1f} min remaining" if remaining is not None else "")
    return ui.div(ui.div(label, class_="progress-bar", role="progressbar", style=f"width: {pct}%"), class_="progress mb-2")


@module.ui
def runs_ui() -> ui.Tag:
    return ui.div(
        ui.h3("Runs"),
        ui.output_ui("running_now"),
        ui.output_ui("run_table"),
        ui.hr(),
        ui.output_ui("detail"),
        ui.output_ui("progress"),
        ui.div(ui.output_ui("controls"), class_="mb-2"),
        ui.download_button("download_his", "Download sfincs_his.nc", class_="btn-sm btn-outline-secondary mb-2"),
        ui.pre(ui.output_text("log_tail"), class_="small bg-body-tertiary p-2", style="max-height: 24rem; overflow: auto"),
        class_="container py-3",
    )


@module.server
def runs_server(input, output, session, run_service, current_user, active_run):
    tick = reactive.value(0)
    registered: set[str] = set()

    def _refresh():
        tick.set(tick.get() + 1)

    def _notify(exc):
        ui.notification_show(str(exc), type="error", duration=8)

    def _selected() -> dict | None:
        rid = active_run.get()
        user = current_user()
        if rid is None:
            return None
        try:
            return run_service.get(user, rid)
        except SfincsUiError:
            return None

    @render.ui
    def running_now():
        tick.get()
        user = current_user()
        if not ac.is_admin(user):
            return None
        jobs = run_service.running_jobs()
        if not jobs:
            return None
        reactive.invalidate_later(5)
        return ui.div(ui.h6("Running now (all users)"),
                      ui.tags.ul(*[ui.tags.li(f"{j['run_name']}: {j['stage']} ({j['status']}, pid {j['pid']})") for j in jobs]))

    @render.ui
    def run_table():
        tick.get()
        user = current_user()
        if user is None:
            return ui.p("Log in to see your runs.", class_="text-muted")
        rows = run_service.list_for(user)
        if any(r["status"] in _ACTIVE for r in rows):
            reactive.invalidate_later(3)
        if not rows:
            return ui.p("No runs yet. Launch one from Setup.", class_="text-muted")
        body = []
        for r in rows:
            _register(r["id"])
            body.append(ui.tags.tr(
                ui.tags.td(r["name"]), ui.tags.td(r["project_name"]), ui.tags.td(ui.HTML(status_badge(r["status"]))),
                ui.tags.td(str(r["threads"])), ui.tags.td(str(r["started_at"] or "")[:16]), ui.tags.td(str(r["finished_at"] or "")[:16]),
                ui.tags.td(ui.input_action_button(f"select_{_safe(r['id'])}", "Select", class_="btn-sm btn-outline-primary")),
            ))
        return ui.tags.table(ui.tags.thead(ui.tags.tr(*[ui.tags.th(h) for h in ("Run", "Project", "Status", "Threads", "Started", "Finished", "")])),
                             ui.tags.tbody(*body), class_="table table-sm align-middle")

    def _register(run_id: str):
        if run_id in registered:
            return
        registered.add(run_id)

        @reactive.effect
        @reactive.event(input[f"select_{_safe(run_id)}"])
        def _select():
            active_run.set(run_id)

    @render.ui
    def detail():
        tick.get()
        r = _selected()
        if r is None:
            return ui.p("Select a run.", class_="text-muted")
        if r["status"] in _ACTIVE:
            reactive.invalidate_later(2)
        parts = [ui.h5(f"{r['name']} ", ui.HTML(status_badge(r["status"]))),
                 ui.p(f"Project {r['project_name']}, {r['threads']} thread(s)", class_="text-muted small"),
                 ui.tags.ul(*[ui.tags.li(line) for line in format_stages(r["stages"])])]
        if r["status"] == "failed" and r["summary"]:
            parts.append(ui.div(ui.strong(f"Failed in {r['summary']['stage']}: {r['summary']['reason']}"),
                                ui.pre(r["summary"]["log_tail"], class_="small"), class_="alert alert-danger"))
        return ui.div(*parts)

    @render.ui
    def progress():
        r = _selected()
        if r is None or r["status"] != "running":
            return None
        reactive.invalidate_later(2)
        try:
            return progress_bar(run_service.progress(current_user(), r["id"]))
        except SfincsUiError:
            return None

    @render.text
    def log_tail():
        r = _selected()
        if r is None:
            return ""
        if r["status"] in _ACTIVE:
            reactive.invalidate_later(2)
        try:
            stage, text = run_service.log_tail(current_user(), r["id"])
        except SfincsUiError:
            return ""
        return f"[{stage}]\n{text}" if stage else ""

    @render.ui
    def controls():
        r = _selected()
        user = current_user()
        if r is None or not ac.can_modify_run(user, {"owner_id": r["owner_id"], "public": r["public"]}):
            return None
        buttons = []
        if r["status"] in _ACTIVE:
            buttons.append(ui.input_action_button("cancel_btn", "Cancel", class_="btn-sm btn-outline-danger me-1"))
        buttons.append(ui.input_action_button("pin_btn", "Unpin" if r["pinned"] else "Pin", class_="btn-sm btn-outline-secondary me-1"))
        buttons.append(ui.input_action_button("public_btn", "Make private" if r["public"] else "Make public", class_="btn-sm btn-outline-secondary"))
        return ui.div(*buttons)

    @reactive.effect
    @reactive.event(input.cancel_btn)
    async def _cancel():
        r = _selected()
        if r is None:
            return
        try:
            await run_service.cancel(current_user(), r["id"]); _refresh()
            ui.notification_show("Run cancelled", type="message")
        except SfincsUiError as exc:
            _notify(exc)

    @reactive.effect
    @reactive.event(input.pin_btn)
    def _pin():
        r = _selected()
        if r is None:
            return
        try:
            run_service.set_pinned(current_user(), r["id"], not r["pinned"]); _refresh()
        except SfincsUiError as exc:
            _notify(exc)

    @reactive.effect
    @reactive.event(input.public_btn)
    def _public():
        r = _selected()
        if r is None:
            return
        try:
            run_service.set_public(current_user(), r["id"], not r["public"]); _refresh()
        except SfincsUiError as exc:
            _notify(exc)

    @render.download(filename=lambda: "sfincs_his.nc")
    def download_his():
        r = _selected()
        if r is None:
            return
        try:
            path = run_service.download_path(current_user(), r["id"], "sfincs_his.nc")
        except SfincsUiError as exc:
            _notify(exc); return
        with open(path, "rb") as fh:
            while chunk := fh.read(1 << 20):
                yield chunk


def _safe(run_id: str) -> str:
    return run_id.replace("-", "_")
```

Home: in `pages/home.py`, `home_server` gains a `project_service` parameter and an `@render.ui examples()` listing `project_service.examples()` names with their template title; `home_ui` places `ui.output_ui("examples")` under a "Example projects" heading, replacing the static "None published yet." text with "Public runs appear here once the Results page ships (milestone 4)."

- [ ] **Step 6: Run the tests to verify they pass**

Run: `cd /home/razinka/sfincs/sfincs_ui && /opt/micromamba/envs/shiny/bin/python -m pytest tests/test_pages_m2.py tests/test_pages.py -q`
Expected: the 4 new tests and the milestone 1 page tests pass (full suite 195).

- [ ] **Step 7: Commit**

```bash
cd /home/razinka/sfincs
git add sfincs_ui/sfincs_ui/pages sfincs_ui/tests/test_pages_m2.py
git commit -m "sfincs_ui: Projects, Setup and Runs pages

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 10: Wire the runner and pages into the app; HTTP integration tests

**Files:**
- Modify: `sfincs_ui/sfincs_ui/app.py`
- Modify: `sfincs_ui/tests/test_pages.py` (the `app` fixture and `create_app` call sites gain nothing; `create_app` keeps its signature)
- Test: `sfincs_ui/tests/test_app_http_m2.py`

**Interfaces:**
- `create_app(config=None, *, environment=None, templates=None, start_runner=True)`: builds `ProjectService`, `JobRunner(reconciler=reconcile)`, `RunService`; calls `project_service.ensure_examples()`; registers the Projects, Setup and Runs nav panels between Home and Admin; passes `active_project` and `active_run` reactive values and `goto` to the page servers; wraps the ASGI stack as `LifespanMiddleware(SessionAuthMiddleware(App))` with `on_startup = runner.start` and `on_shutdown = runner.stop` when `start_runner` is true. The runner and services are exposed as attributes on the returned middleware object: `app.runner`, `app.services = {"projects": ..., "runs": ..., "settings": ..., "auth": ..., "audit": ...}` so tests and the CLI can reach them. The non-admin nav removal from milestone 1 stays; Projects, Setup and Runs stay visible to anonymous visitors (their bodies ask for login), matching the spec's "pages decide what an anonymous visitor may see".

- [ ] **Step 1: Write the failing tests**

`sfincs_ui/tests/test_app_http_m2.py`:

```python
"""Assembled app with the runner: examples seeded, pages served, lifespan hooks wired."""

import re

import httpx
import pytest

from sfincs_ui.services.auth_service import AuthService
from sfincs_ui.services.environment import EnvironmentReport
from tests.fake_template import FakeTemplate


@pytest.fixture
def app(db, tmp_path):
    from sfincs_ui import config
    from sfincs_ui.app import create_app

    cfg = config.Config(workspace=tmp_path, database_url=f"sqlite:///{tmp_path / 'test.db'}")
    config.set_config(cfg)
    AuthService(session_factory=db).create_user("alice", "pw12345678")
    return create_app(cfg, environment=EnvironmentReport(), templates={"fake": FakeTemplate()}, start_runner=False)


async def test_examples_seeded_and_pages_present(app):
    assert [p["name"] for p in app.services["projects"].examples()] == ["Fake example"]
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="https://test") as c:
        r = await c.get("/")
        assert r.status_code == 200
        for panel in ("Projects", "Setup", "Runs", "Admin"):
            assert panel in r.text
        assert "Fake example" in r.text


async def test_lifespan_starts_and_stops_the_runner(app):
    msgs = [{"type": "lifespan.startup"}, {"type": "lifespan.shutdown"}]
    sent = []

    async def receive():
        return msgs.pop(0)

    async def send(m):
        sent.append(m["type"])

    from sfincs_ui.middleware.lifespan import LifespanMiddleware
    assert isinstance(app, LifespanMiddleware)
    app._on_startup = app.runner.start  # the default wiring when start_runner=True; exercised here explicitly
    app._on_shutdown = app.runner.stop
    await app({"type": "lifespan"}, receive, send)
    assert "lifespan.startup.complete" in sent and "lifespan.shutdown.complete" in sent
    assert app.runner.started is False  # stopped again


def test_create_app_with_runner_enabled_wires_hooks(db, tmp_path):
    from sfincs_ui import config
    from sfincs_ui.app import create_app

    cfg = config.Config(workspace=tmp_path, database_url=f"sqlite:///{tmp_path / 'test.db'}")
    app = create_app(cfg, environment=EnvironmentReport(), templates={"fake": FakeTemplate()})
    assert app._on_startup == app.runner.start and app._on_shutdown == app.runner.stop
    assert app.runner._reconciler is not None


async def test_logged_in_user_sees_login_free_shell(app):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="https://test") as c:
        page = await c.get("/login")
        csrf = re.search(r'name="csrf_token" value="([^"]+)"', page.text).group(1)
        r = await c.post("/login", data={"username": "alice", "password": "pw12345678", "csrf_token": csrf})
        assert r.status_code == 302
        assert (await c.get("/api/whoami")).json()["username"] == "alice"
        assert (await c.get("/")).status_code == 200
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd /home/razinka/sfincs/sfincs_ui && /opt/micromamba/envs/shiny/bin/python -m pytest tests/test_app_http_m2.py -q`
Expected: FAIL with `TypeError: create_app() got an unexpected keyword argument 'templates'`

- [ ] **Step 3: Rewrite app.py's assembly**

Replace `build_ui`, `build_server` and `create_app` in `sfincs_ui/sfincs_ui/app.py` with:

```python
def build_ui(config: Config, report: EnvironmentReport) -> ui.Tag:
    return ui.page_navbar(
        ui.nav_panel("Home", home.home_ui("home")),
        ui.nav_panel("Projects", projects.projects_ui("projects")),
        ui.nav_panel("Setup", setup.setup_ui("setup")),
        ui.nav_panel("Runs", runs.runs_ui("runs")),
        ui.nav_panel("Admin", admin.admin_ui("admin")),
        ui.nav_spacer(),
        ui.nav_control(ui.input_dark_mode(id="dark_mode")),
        ui.nav_control(ui.output_ui("user_menu")),
        title="SFINCS UI",
        id="main_nav",
        header=ui.TagList(
            ui.head_content(ui.tags.link(rel="stylesheet", href="sfincs_ui.css"), ui.tags.script(_WS_IDENTITY_JS)),
            _banner(report),
        ),
    )


def build_server(config: Config, services: dict):
    auth_service = services["auth"]

    def server(input, output, session):
        session_token = get_current_session_token()

        def current_user() -> dict | None:
            ws_token = input._wsauth() if "_wsauth" in input else None
            try:
                return resolve_identity(ws_token, session_token, auth_service)
            except Exception:
                logger.warning("identity resolution failed; treating as anonymous", exc_info=True)
                return None

        def goto(panel: str) -> None:
            ui.update_navs("main_nav", selected=panel)

        active_project: reactive.Value[str | None] = reactive.value(None)
        active_run: reactive.Value[str | None] = reactive.value(None)
        hidden = {"admin": False}

        @reactive.effect
        def _hide_admin_for_non_admins():
            if "_wsauth" not in input:
                return
            if not admin._check_admin_access(current_user()) and not hidden["admin"]:
                hidden["admin"] = True
                ui.remove_nav_panel("main_nav", "Admin")

        @render.ui
        def user_menu():
            user = current_user()
            prefix = config.url_prefix
            if user is None:
                return ui.tags.a("Log in", href=f"{prefix}/login", class_="btn btn-sm btn-outline-secondary")
            return ui.span(ui.span(user["username"], class_="me-2"),
                           ui.tags.a("Log out", href=f"{prefix}/logout", class_="btn btn-sm btn-outline-secondary"))

        home.home_server("home", current_user=current_user, project_service=services["projects"])
        projects.projects_server("projects", project_service=services["projects"], current_user=current_user,
                                 active_project=active_project, goto=goto)
        setup.setup_server("setup", project_service=services["projects"], run_service=services["runs"],
                           settings_service=services["settings"], current_user=current_user,
                           active_project=active_project, active_run=active_run, goto=goto)
        runs.runs_server("runs", run_service=services["runs"], current_user=current_user, active_run=active_run)
        admin.admin_server("admin", auth_service=auth_service, audit_service=services["audit"],
                           settings_service=services["settings"], current_user=current_user)

    return server


def create_app(config: Config | None = None, *, environment: EnvironmentReport | None = None,
               templates: dict | None = None, start_runner: bool = True):
    if config is None:
        config = get_config()
    else:
        set_config(config)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    init_db()
    report = environment if environment is not None else check_environment(config)
    for problem in report.problems:
        logger.warning("environment: %s", problem)
    if templates is None:
        from sfincs_ui.templates import TEMPLATES
        templates = TEMPLATES

    auth_service = AuthService()
    audit_service = AuditService()
    settings_service = SettingsService(config)
    project_service = ProjectService(config, templates=templates)
    project_service.ensure_examples()
    runner = JobRunner(config, settings_service, templates=templates, reconciler=reconcile)
    run_service = RunService(config, settings_service, project_service, runner, templates=templates)
    services = {"auth": auth_service, "audit": audit_service, "settings": settings_service,
                "projects": project_service, "runs": run_service}

    shiny_app = App(build_ui(config, report), build_server(config, services), static_assets=Path(__file__).parent / "www")
    authed = SessionAuthMiddleware(shiny_app, auth_service=auth_service, audit_service=audit_service,
                                   root_path=config.url_prefix, session_ttl_hours=config.session_ttl_hours,
                                   use_secure_cookies=config.secure_cookies, trusted_proxies=config.trusted_proxies)
    app = LifespanMiddleware(authed, on_startup=runner.start if start_runner else None,
                             on_shutdown=runner.stop if start_runner else None)
    app.runner = runner
    app.services = services
    return app
```

with the imports `from sfincs_ui.middleware.lifespan import LifespanMiddleware`, `from sfincs_ui.pages import admin, home, projects, runs, setup`, `from sfincs_ui.services.job_runner import JobRunner`, `from sfincs_ui.services.project_service import ProjectService`, `from sfincs_ui.services.reconcile import reconcile`, `from sfincs_ui.services.run_service import RunService`.

The milestone 1 tests that build the app (`tests/test_pages.py`, `tests/test_app_http.py`) keep passing: they call `create_app(cfg, environment=EnvironmentReport())`, which now also seeds the plane-beach example and wires the real runner with `start_runner=True`; since httpx's ASGI transport never sends lifespan events, the runner is never started there. The `test_build_ui_without_problems_has_no_banner` test needs no change.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd /home/razinka/sfincs/sfincs_ui && /opt/micromamba/envs/shiny/bin/python -m pytest -q`
Expected: 199 passed (195 + 4), no leaked processes.

- [ ] **Step 5: Commit**

```bash
cd /home/razinka/sfincs
git add sfincs_ui/sfincs_ui/app.py sfincs_ui/tests/test_app_http_m2.py
git commit -m "sfincs_ui: wire the job runner, services and the three new pages into the app

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 11: End-to-end run with the real solver, READMEs, acceptance

**Files:**
- Test: `sfincs_ui/tests/test_e2e_plane_beach.py`
- Modify: `sfincs_ui/README.md`, `deploy/README.md`

**Interfaces:** none new. This is the spec's "one end-to-end pipeline test on the plane-beach template (seconds): finished run with `sfincs_his.nc` and the expected end level. The only test touching the real binary; skipped when it is absent."

Recorded facts for the assertions: the 100 m plane beach runs in about 0.1 s of solver time; `sfincs_his.nc` has `point_zs(time, station)` with 73 time steps for 6 h at 300 s output; station names in the file are `station_001…` (the `.obs` names are not carried through), so assertions use index 0 (offshore); the final offshore level is 1.998 m for a 2.0 m ramp.

- [ ] **Step 1: Write the test**

`sfincs_ui/tests/test_e2e_plane_beach.py`:

```python
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
```

- [ ] **Step 2: Run it**

Run: `cd /home/razinka/sfincs/sfincs_ui && /opt/micromamba/envs/shiny/bin/python -m pytest tests/test_e2e_plane_beach.py -q -s`
Expected: 1 passed, printing the wall-clock time (a few seconds). Full suite: 200 passed.

- [ ] **Step 3: Measure the acceptance run and write the READMEs**

Measure once, by hand, how long a finer plane beach takes with the real binary so the acceptance step knows how long the operator has to issue the restart. From `sfincs_ui/`, with `SFINCS_UI_WORKSPACE` pointing at a scratch directory, run a 10 m and a 5 m plane beach through the CLI-free path:

```bash
S=/tmp/claude-1000/-home-razinka-sfincs/946ef2e3-64b8-42c9-b324-8e8da9f13c98/scratchpad/pb
for res in 10 5; do mkdir -p $S/$res && echo "{\"resolution_m\": $res, \"duration_hours\": 6, \"boundary_level_m\": 2.0, \"manning\": 0.04}" > $S/$res/settings.json \
 && /opt/micromamba/envs/shiny/bin/python -P sfincs_ui/templates/plane_beach_build.py --run-dir $S/$res --settings $S/$res/settings.json \
 && (cd $S/$res && /usr/bin/time -f "$res m: %e s" env OMP_NUM_THREADS=4 /home/razinka/sfincs/sfincs-linux/bin/sfincs > /dev/null); done
```

Record both durations in `sfincs_ui/README.md` under a new "Acceptance: restart during a run" section:

```markdown
## Acceptance: restart during a run

The milestone 2 gate is a run that survives `systemctl restart sfincs-ui`.
Measured on laguna with 4 threads: a 10 m plane beach takes about <N10> s,
a 5 m one about <N5> s. Pick the resolution that gives you a few minutes:

1. Log in, open the "Plane beach example" (Projects, Clone), set Cell size to 5 m, Save, Launch run with 4 threads.
2. On the Runs page wait until the status is `running` and the progress bar moves.
3. In a shell: `sudo bash deploy/deploy_ui.sh --restart`. The script warns that a simulation is running and restarts anyway.
4. Reload the page, log in again if asked, select the run: the progress bar keeps moving and the run reaches `finished`
   with `exit code unknown` on the simulate stage. `journalctl -u sfincs-ui -n 50` shows `reconcile: run … simulate -> resumed`;
   systemd also logs `Found left-over process … Ignoring`, which is expected with `KillMode=process`.
5. Download `sfincs_his.nc` from the Runs page.
```

Also document in `sfincs_ui/README.md`: the Projects/Setup/Runs pages exist (replace the milestone 1 sentence "Projects, runs and the queue arrive in milestone 2"); the `active-jobs` and `kill-jobs` commands; that run directories live at `<workspace>/<project>/<run>/` with `settings.json`, `sfincs.inp`, `sfincs.inp.orig`, `overrides.diff`, `build.log`, `sfincs.log`. In `deploy/README.md` add `--wait` to the modes table (done in Task 8) and the sentence "Merge to main and push before deploying" stays.

- [ ] **Step 4: Full verification**

```bash
cd /home/razinka/sfincs/sfincs_ui && /opt/micromamba/envs/shiny/bin/python -m pytest -q
cd /home/razinka/sfincs && ps -eo pid,cmd | grep -E 'fake_sfincs|sfincs-linux/bin/sfincs' | grep -v grep | wc -l   # 0
git diff --stat main -- app/ deploy/deploy.sh                                                                  # empty
bash -n deploy/deploy_ui.sh && echo syntax-ok
grep -rniE 'shyfem|tutorial|feedback' sfincs_ui/sfincs_ui/; echo "grep exit $? (1 means clean)"
```

- [ ] **Step 5: Commit**

```bash
cd /home/razinka/sfincs
git add sfincs_ui/tests/test_e2e_plane_beach.py sfincs_ui/README.md deploy/README.md
git commit -m "sfincs_ui: end-to-end plane-beach run with the real solver; milestone 2 README and acceptance

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

- [ ] **Step 6: User-run acceptance (not the executor's)**

After merge and push: `sudo bash deploy/deploy_ui.sh`, then the "Acceptance: restart during a run" steps from the README. The deploy's migrate step upgrades the production database to `0002_projects_runs_jobs` as user `shiny`.

---

## Deferred from this milestone

- Retention, quotas, `subgrid/` deletion, storage by user (milestone 6). The free-space floor is in (Task 7).
- The Setup page's deck.gl map and the Curonian template with its pipeline-script flags (milestone 3). `Template.geometry_layers` exists and the plane beach returns static layers nobody renders yet.
- Results and Compare pages, baselines, `sfincs_viewer/` extraction (milestone 4); `?run=` query routing with them.
- The Playwright pass (spec section 6: log in, create project, launch, wait, open Results) waits for Results in milestone 4; milestone 2's browser check is the manual acceptance.
- `ws_tokens` growth and the maintenance loop (milestone 6).
- The `summary_json` of a cancelled run records nothing; a "cancelled by <user>" audit row would be useful (admin audit of run actions in general is not in the spec; consider for milestone 6).
- Milestone 1 deferred minors still open (see that plan's ledger): CSRF/no-store landed; the rest (settings corrupt-row fallback, update_user `is False` guard, client-IP hop validation, deploy nginx auto-restore) remain.
