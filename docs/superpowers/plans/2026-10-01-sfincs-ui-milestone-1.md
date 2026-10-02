# SFINCS UI Milestone 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship the `sfincs_ui` package skeleton: configuration, SQLite database with Alembic migrations, argon2 session auth with anonymous pass-through, an Admin page (users, queue policy, audit log), the CLI, the `sfincs-ui` systemd unit with `KillMode=process`, and `deploy/deploy_ui.sh`, so that an admin can log in at https://laguna.ku.lt/sfincs-ui/.

**Architecture:** A Shiny for Python app wrapped in one ASGI middleware that resolves the session cookie into a user (or `None`) and handles `/login`, `/logout` and `/api/whoami`; every page renders for anonymous visitors and enforces login inside its own server function. Services are plain Python over SQLAlchemy sessions, testable without Shiny. The app runs as a standalone uvicorn systemd unit on port 8840 behind the existing nginx server block, in the osmose pattern.

**Tech Stack:** Python 3.13 in `/opt/micromamba/envs/shiny` (shiny 1.8.0, sqlalchemy 2.0.50, alembic 1.18.4, argon2-cffi 25.1.0, pydantic-settings 2.14.1, uvicorn 0.49.0, httpx 0.28.1, pytest 9.0.3, pytest-asyncio 1.3.0). Bash for the deploy script. systemd and nginx on laguna.ku.lt.

**Spec:** `docs/superpowers/specs/2026-09-30-sfincs-ui-design.md`. This plan implements milestone 1 of section 6 and the parts of sections 1, 2, 5 that it needs. Read the spec's "Decisions taken" table and section 5 before starting.

## Global Constraints

- **Interpreter.** Every Python command in this plan runs with `/opt/micromamba/envs/shiny/bin/python`. Never `pip install` anything into that env from the dev tree: razinka has no passwordless sudo, and the production deploy installs the prod clone editable into the same env, so a second editable `sfincs_ui` would collide. Tests and local serving import the package from the source tree via `pythonpath = ["."]` in `pyproject.toml`.
- **Test command.** `cd /home/razinka/sfincs/sfincs_ui && /opt/micromamba/envs/shiny/bin/python -m pytest -q`. Run it from `sfincs_ui/`, not from the repo root (the viewer's tests in `app/` import modules by bare name and are run from `app/`).
- **Layout mapping.** Where the spec writes `sfincs_ui/<x>`, this plan means `sfincs_ui/sfincs_ui/<x>`: the outer `sfincs_ui/` is the project directory (`pyproject.toml`, `alembic.ini`, `tests/`, `README.md`), the inner one is the importable package, the SHYFEM UI shape (`/home/razinka/shyfem/shyfem-ui/shyfem_ui/`).
- **No changes to `app/` or `deploy/deploy.sh`** (spec, milestone 1). `git diff --stat main -- app/ deploy/deploy.sh` must be empty at the end.
- **Copied SHYFEM code.** The SHYFEM UI source is at `/home/razinka/shyfem/shyfem-ui/shyfem_ui/`. Copy the files this plan names, apply exactly the listed edits, and finish with the grep gate: `grep -rniE 'shyfem|tutorial|feedback' sfincs_ui/sfincs_ui/` prints nothing.
- **Configuration prefix** is `SFINCS_UI_` (pydantic-settings). Keys from spec section 5: `WORKSPACE`, `DATABASE_URL`, `SFINCS_BIN`, `MODEL_PYTHON`, `CURONIAN_DIR`, `URL_PREFIX`, `PORT`, `MAX_SIMULATIONS`, `MAX_THREADS`, `MIN_FREE_GB`, `RETENTION_DAYS`, `QUOTA_GB`, `UPLOAD_MAX_MB`. Defaults: `MODEL_PYTHON = "micromamba -r /opt/micromamba run -n hydromt-sfincs python"` (a command prefix, never an interpreter path), `PORT = 8840`, `MAX_SIMULATIONS = 1`, `MAX_THREADS = 8`, `MIN_FREE_GB = 100`, `RETENTION_DAYS = 60`, `QUOTA_GB = 20`. Env values are install-time ceilings and defaults; the `settings` table holds admin-chosen values validated at or below the ceilings; `MIN_FREE_GB` and `UPLOAD_MAX_MB` are env-only.
- **Database** is SQLite through SQLAlchemy with Alembic migrations, default file `<WORKSPACE>/sfincs_ui.db`. Migrations are shipped inside the package (`sfincs_ui/sfincs_ui/migrations/`) and `init_db()` builds the Alembic config in code, so it works from an editable install and from the source tree alike. There is **no `create_all()` fallback**: a migration failure must surface.
- **Tables in this milestone:** `users`, `sessions`, `ws_tokens`, `audit_log`, `settings`. `projects`, `runs`, `jobs` are milestone 2's first migration. Milestone 2's planner: the initial revision is `0001_initial`.
- **Service unit** `sfincs-ui.service` runs `uvicorn sfincs_ui.asgi:app --host 127.0.0.1 --port 8840 --root-path /sfincs-ui` as user `shiny`, `KillMode=process` with the comment the spec requires, and reads `EnvironmentFile=/etc/sfincs-ui.env`. **Stated deviation:** the spec says the unit's `Environment=` lines carry the variables; this plan puts the same variables in `/etc/sfincs-ui.env` so the unit and the `sudo -u shiny env …` CLI calls share one source. The file carries `MAMBA_ROOT_PREFIX=/opt/micromamba` and `SFINCS_CURONIAN_DB=/home/razinka/curonian/curonian_db.gpkg` and never overrides `HOME`.
- **Ports in use on 2026-10-01:** 8838 osmose, 8839 econet-py. 8840 is free. The deploy script refuses to install when `ss -ltn` shows the port bound by something other than `sfincs-ui`, when the nginx site proxies to it from a block that is not ours, or when another unit's `ExecStart` names it.
- **nginx** block is inserted before the `# Database Admin Tools` anchor in `/etc/nginx/sites-available/nid4ocean`, exactly as `deploy/deploy.sh` does, with `client_max_body_size <UPLOAD_MAX_MB>m` and `proxy_read_timeout 86400s`. `systemctl reload nginx`, never restart.
- **Cookies** are `Secure; HttpOnly; SameSite=Lax` by default (nginx terminates TLS). Tests use `base_url="https://test"` with httpx so Secure cookies are sent. The deploy smoke test never scripts a login over plain http.
- **Commit after every task** with the message given in the task; end every commit message with `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`.

## Review Focus

Input classes the spec implies but no task's tests exercised at first draft. Each line's test has been added to the owning task.

1. **The only admin demotes or deactivates themself** through the Admin page's role or active toggle. Expected: refused with "Cannot demote or deactivate the last admin"; the copied SHYFEM `update_user` would silently do it and lock everyone out. Test in Task 3 (`test_update_user_refuses_to_strip_last_admin`).
2. **An admin sets a queue value above the environment ceiling** (for example `max_threads = 32` with `SFINCS_UI_MAX_THREADS=16`). Expected: refused with a message naming the ceiling; the table is unchanged. Test in Task 4 (`test_set_above_ceiling_rejected_and_unchanged`).
3. **A request arrives with an expired or forged session cookie.** Expected: the page renders as anonymous (not a 500, not a redirect loop), and the websocket is accepted with `user=None`. Tests in Task 5 (`test_invalid_cookie_is_anonymous`, `test_websocket_anonymous_passes_through`).
4. **The model environment or the binary is missing at startup.** Expected: the app still starts and every page shows a banner naming the missing piece; `create_app` must not hang for a minute on a dead `micromamba`. Tests in Task 6 (`test_missing_binary_reported`, `test_model_python_timeout_reported`) and Task 8 (`test_banner_rendered_when_problems`).
5. **`create-admin` runs twice**, as a re-run of the deploy script would make it. Expected: the second run reports the existing admin and leaves the password untouched. Test in Task 7 (`test_create_admin_twice_is_idempotent`).

## File structure

```
sfincs_ui/                              project directory
  pyproject.toml                        package metadata, pytest config
  alembic.ini                           CLI convenience for autogenerate
  README.md                             how to run, test, deploy
  sfincs_ui/                            the package
    __init__.py                         __version__
    __main__.py                         CLI: migrate, create-admin, preflight, serve
    asgi.py                             `app = create_app()` for uvicorn
    app.py                              create_app, build_ui, build_server
    config.py                           Config (pydantic-settings), get/set/reset
    timeutil.py                         utcnow()
    db/__init__.py, db/base.py          Base, engine, init_db, db_session
    models/__init__.py                  re-exports
    models/user.py                      User, AuthSession, WSAuthToken, roles, validate_username
    models/audit_log.py                 AuditLog
    models/setting.py                   Setting
    migrations/env.py, script.py.mako   Alembic environment
    migrations/versions/0001_initial.py
    middleware/__init__.py
    middleware/client_ip.py             get_client_ip (rightmost-untrusted)
    middleware/session_auth.py          SessionAuthMiddleware, get_current_user
    services/__init__.py
    services/auth_service.py            AuthService (from SHYFEM)
    services/audit_service.py           AuditService (from SHYFEM)
    services/settings_service.py        SettingsService, POLICY_KEYS
    services/environment.py             check_environment, EnvironmentReport
    services/ws_identity.py             resolve_ws_user
    pages/__init__.py
    pages/home.py                       home_ui, home_server
    pages/admin.py                      admin_ui, admin_server, pure helpers
    www/sfincs_ui.css                   small shell CSS
  tests/
    conftest.py                         env isolation, fast argon2, db fixture
    test_config.py
    test_db_init.py
    test_auth_service.py
    test_audit_service.py
    test_settings_service.py
    test_session_auth_middleware.py
    test_environment.py
    test_cli.py
    test_pages.py
    test_app_http.py
deploy/
  deploy_ui.sh                          install / --check / --restart / --uninstall
  sfincs-ui.service.in                  unit template (@PORT@, @PROD_SRC@ placeholders)
  sfincs-ui.env.in                      EnvironmentFile template
  sfincs-ui.nginx                       location block (@PORT@, @UPLOAD_MAX_MB@)
  services-entry-ui.json                toolbox catalogue entry
  README.md                             gains a "SFINCS UI" section
.gitignore                              adds *.egg-info, sfincs_ui/.pytest_cache/
```

---

### Task 1: Project skeleton and configuration

**Files:**
- Create: `sfincs_ui/pyproject.toml`
- Create: `sfincs_ui/sfincs_ui/__init__.py`
- Create: `sfincs_ui/sfincs_ui/config.py`
- Create: `sfincs_ui/sfincs_ui/timeutil.py`
- Create: `sfincs_ui/tests/__init__.py` (empty)
- Create: `sfincs_ui/tests/conftest.py`
- Test: `sfincs_ui/tests/test_config.py`
- Modify: `.gitignore`

**Interfaces:**
- Produces: `sfincs_ui.config.Config` with the fields below; `get_config() -> Config`, `set_config(cfg)`, `reset_config()`; `Config.database_url_resolved -> str`; `Config.model_python_argv -> list[str]`; `Config.repo_root -> Path` (the `sfincs` checkout containing `curonian/`). `sfincs_ui.timeutil.utcnow() -> datetime` (naive UTC).

- [ ] **Step 1: Write the project metadata**

`sfincs_ui/pyproject.toml`:

```toml
[build-system]
requires = ["setuptools>=61.0", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "sfincs-ui"
version = "0.1.0"
description = "Build, run and inspect SFINCS models from the browser (laguna.ku.lt)"
readme = "README.md"
requires-python = ">=3.11"
license = {text = "GPL-3.0"}
dependencies = [
    "shiny>=1.8.0",
    "sqlalchemy>=2.0",
    "alembic>=1.13",
    "argon2-cffi>=23.0",
    "pydantic>=2.0",
    "pydantic-settings>=2.0",
    "uvicorn>=0.30",
]

[project.optional-dependencies]
dev = ["pytest>=8.0", "pytest-asyncio>=0.23", "httpx>=0.27"]

[tool.setuptools.packages.find]
where = ["."]
include = ["sfincs_ui*"]

[tool.setuptools.package-data]
sfincs_ui = ["migrations/*.py", "migrations/*.mako", "migrations/versions/*.py", "www/*"]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
pythonpath = ["."]
filterwarnings = ["error:datetime.datetime.utcnow:DeprecationWarning"]
```

`sfincs_ui/sfincs_ui/__init__.py`:

```python
"""SFINCS UI: build, run and inspect SFINCS models from the browser."""

__version__ = "0.1.0"
```

`sfincs_ui/sfincs_ui/timeutil.py`:

```python
"""Clock helper shared by services, models and tests."""

from __future__ import annotations

from datetime import datetime, timezone


def utcnow() -> datetime:
    """Current UTC time as a naive datetime.

    The DateTime columns are filled by ``server_default=func.now()`` (SQLite
    CURRENT_TIMESTAMP, UTC, no tzinfo), so in-memory timestamps must be naive
    UTC too; comparing an aware value against them raises.
    """
    return datetime.now(timezone.utc).replace(tzinfo=None)
```

Append to `.gitignore`:

```
*.egg-info/
sfincs_ui/.pytest_cache/
```

- [ ] **Step 2: Write the failing config tests**

`sfincs_ui/tests/conftest.py` (the argon2 and db fixtures are added in Tasks 2 and 3; start with env isolation):

```python
"""Shared fixtures: environment isolation, fast argon2, isolated database."""

from __future__ import annotations

import os

import pytest


@pytest.fixture(autouse=True, scope="session")
def _isolate_env(tmp_path_factory):
    """Strip ambient SFINCS_UI_* variables and pin a throwaway workspace.

    Config() reads the environment on construction. Without this a developer
    shell that exports the production workspace would make the suite write
    into the real database.
    """
    for key in list(os.environ):
        if key.startswith("SFINCS_UI_"):
            os.environ.pop(key)
    ws = tmp_path_factory.mktemp("workspace")
    os.environ["SFINCS_UI_WORKSPACE"] = str(ws)
    yield


@pytest.fixture(autouse=True)
def _reset_config():
    """Every test starts without a cached Config."""
    from sfincs_ui import config

    config.reset_config()
    yield
    config.reset_config()
```

`sfincs_ui/tests/test_config.py`:

```python
from pathlib import Path

import pytest
from pydantic import ValidationError

from sfincs_ui.config import Config, get_config, reset_config, set_config


def test_workspace_is_required(monkeypatch):
    monkeypatch.delenv("SFINCS_UI_WORKSPACE")
    with pytest.raises(ValidationError):
        Config()


def test_defaults_match_spec(tmp_path):
    cfg = Config(workspace=tmp_path)
    assert cfg.port == 8840
    assert cfg.max_simulations == 1
    assert cfg.max_threads == 8
    assert cfg.min_free_gb == 100
    assert cfg.retention_days == 60
    assert cfg.quota_gb == 20
    assert cfg.upload_max_mb == 500
    assert cfg.model_python == "micromamba -r /opt/micromamba run -n hydromt-sfincs python"
    assert cfg.url_prefix == ""
    assert cfg.secure_cookies is True
    assert cfg.session_ttl_hours == 24
    assert cfg.trusted_proxies == ["127.0.0.0/8"]


def test_database_url_defaults_under_workspace(tmp_path):
    cfg = Config(workspace=tmp_path)
    assert cfg.database_url_resolved == f"sqlite:///{tmp_path / 'sfincs_ui.db'}"


def test_explicit_database_url_wins(tmp_path):
    cfg = Config(workspace=tmp_path, database_url="sqlite:///elsewhere.db")
    assert cfg.database_url_resolved == "sqlite:///elsewhere.db"


def test_model_python_is_split_as_a_command_prefix(tmp_path):
    cfg = Config(workspace=tmp_path, model_python="micromamba -r /opt/micromamba run -n hydromt-sfincs python")
    assert cfg.model_python_argv == ["micromamba", "-r", "/opt/micromamba", "run", "-n", "hydromt-sfincs", "python"]


def test_env_prefix_is_read(monkeypatch, tmp_path):
    monkeypatch.setenv("SFINCS_UI_PORT", "8899")
    monkeypatch.setenv("SFINCS_UI_URL_PREFIX", "/sfincs-ui")
    cfg = Config(workspace=tmp_path)
    assert cfg.port == 8899
    assert cfg.url_prefix == "/sfincs-ui"


def test_url_prefix_must_start_with_slash_and_not_end_with_one(tmp_path):
    with pytest.raises(ValidationError):
        Config(workspace=tmp_path, url_prefix="sfincs-ui")
    with pytest.raises(ValidationError):
        Config(workspace=tmp_path, url_prefix="/sfincs-ui/")


def test_positive_limits_enforced(tmp_path):
    with pytest.raises(ValidationError):
        Config(workspace=tmp_path, max_threads=0)
    with pytest.raises(ValidationError):
        Config(workspace=tmp_path, port=80)


def test_defaults_point_at_this_checkout(tmp_path):
    cfg = Config(workspace=tmp_path)
    assert cfg.repo_root == Path(__file__).resolve().parents[2]
    assert cfg.curonian_dir == cfg.repo_root / "curonian"
    assert cfg.sfincs_bin == cfg.repo_root / "sfincs-linux" / "bin" / "sfincs"


def test_get_config_caches_and_reset_clears(tmp_path):
    a = get_config()
    assert a is get_config()
    reset_config()
    assert get_config() is not a
    custom = Config(workspace=tmp_path, port=8841)
    set_config(custom)
    assert get_config() is custom
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `cd /home/razinka/sfincs/sfincs_ui && /opt/micromamba/envs/shiny/bin/python -m pytest tests/test_config.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'sfincs_ui.config'`

- [ ] **Step 4: Write the configuration module**

`sfincs_ui/sfincs_ui/config.py`:

```python
"""Configuration from SFINCS_UI_* environment variables.

Environment values are install-time ceilings and defaults. The ``settings``
table (services/settings_service.py) holds admin-chosen values validated at
or below these ceilings. MIN_FREE_GB and UPLOAD_MAX_MB are env-only.
"""

from __future__ import annotations

import shlex
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# sfincs_ui/sfincs_ui/config.py -> parents[2] is the sfincs checkout.
REPO_ROOT = Path(__file__).resolve().parents[2]


class Config(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="SFINCS_UI_", extra="ignore")

    workspace: Path = Field(description="Directory that holds every project and run the UI creates")
    database_url: str | None = Field(default=None, description="SQLAlchemy URL; default sqlite under the workspace")
    sfincs_bin: Path = Field(default=REPO_ROOT / "sfincs-linux" / "bin" / "sfincs")
    model_python: str = Field(
        default="micromamba -r /opt/micromamba run -n hydromt-sfincs python",
        description="Command prefix that runs python in the model env (not an interpreter path)",
    )
    curonian_dir: Path = Field(default=REPO_ROOT / "curonian")
    url_prefix: str = Field(default="", description="Public mount path, e.g. /sfincs-ui; empty at the root")
    port: int = Field(default=8840, ge=1024, le=65535)
    max_simulations: int = Field(default=1, ge=1)
    max_threads: int = Field(default=8, ge=1)
    min_free_gb: int = Field(default=100, ge=0)
    retention_days: int = Field(default=60, ge=1)
    quota_gb: int = Field(default=20, ge=1)
    upload_max_mb: int = Field(default=500, ge=1)
    session_ttl_hours: int = Field(default=24, ge=1)
    secure_cookies: bool = Field(default=True, description="nginx terminates TLS; set false only for plain-http dev")
    trusted_proxies: list[str] = Field(default=["127.0.0.0/8"])

    @field_validator("url_prefix")
    @classmethod
    def _prefix_shape(cls, v: str) -> str:
        if v == "":
            return v
        if not v.startswith("/") or v.endswith("/"):
            raise ValueError("url_prefix must start with '/' and not end with one, e.g. /sfincs-ui")
        return v

    @property
    def repo_root(self) -> Path:
        return REPO_ROOT

    @property
    def database_url_resolved(self) -> str:
        if self.database_url:
            return self.database_url
        return f"sqlite:///{self.workspace / 'sfincs_ui.db'}"

    @property
    def model_python_argv(self) -> list[str]:
        return shlex.split(self.model_python)


_config: Config | None = None


def get_config() -> Config:
    global _config
    if _config is None:
        _config = Config()
    return _config


def set_config(config: Config) -> None:
    global _config
    _config = config


def reset_config() -> None:
    global _config
    _config = None
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `cd /home/razinka/sfincs/sfincs_ui && /opt/micromamba/envs/shiny/bin/python -m pytest tests/test_config.py -q`
Expected: 10 passed

- [ ] **Step 6: Commit**

```bash
cd /home/razinka/sfincs
git add .gitignore sfincs_ui/pyproject.toml sfincs_ui/sfincs_ui/__init__.py sfincs_ui/sfincs_ui/config.py sfincs_ui/sfincs_ui/timeutil.py sfincs_ui/tests/__init__.py sfincs_ui/tests/conftest.py sfincs_ui/tests/test_config.py
git commit -m "sfincs_ui: package skeleton and SFINCS_UI_* configuration

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 2: Database base, models and the initial migration

**Files:**
- Create: `sfincs_ui/sfincs_ui/db/__init__.py`
- Create: `sfincs_ui/sfincs_ui/db/base.py`
- Create: `sfincs_ui/sfincs_ui/models/__init__.py`
- Create: `sfincs_ui/sfincs_ui/models/user.py`
- Create: `sfincs_ui/sfincs_ui/models/audit_log.py`
- Create: `sfincs_ui/sfincs_ui/models/setting.py`
- Create: `sfincs_ui/sfincs_ui/migrations/env.py`
- Create: `sfincs_ui/sfincs_ui/migrations/script.py.mako`
- Create: `sfincs_ui/sfincs_ui/migrations/versions/0001_initial.py`
- Create: `sfincs_ui/alembic.ini`
- Modify: `sfincs_ui/tests/conftest.py` (add the `db` fixture)
- Test: `sfincs_ui/tests/test_db_init.py`

**Interfaces:**
- Consumes: `sfincs_ui.config.get_config()` (Task 1).
- Produces: `sfincs_ui.db.base.Base`, `get_engine()`, `get_session_factory()`, `reset_engine()`, `init_db()`, `alembic_config(url) -> alembic.config.Config`, `db_session()` context manager. Models `User` (table `users`: id, username, display_name, email, password_hash, role, is_active, created_at, updated_at), `AuthSession` (table `sessions`: id, token, user_id, created_at, expires_at, ip_address), `WSAuthToken` (table `ws_tokens`: id, token, session_token, user_id, created_at, expires_at), `AuditLog` (table `audit_log`: id, timestamp, user_id, username, action, target, detail_json, ip_address), `Setting` (table `settings`: key, value_json, updated_at). Constants `ROLE_ADMIN = "admin"`, `ROLE_USER = "user"`, `validate_username(str)`. Test fixture `db` yielding a session factory bound to a fresh migrated SQLite file.

- [ ] **Step 1: Write the failing migration test**

`sfincs_ui/tests/test_db_init.py`:

```python
"""init_db() must run the real Alembic migrations to head; no create_all fallback."""

from alembic.script import ScriptDirectory
from sqlalchemy import inspect, text

from sfincs_ui.db import base


def _head_revision() -> str:
    cfg = base.alembic_config("sqlite://")
    return ScriptDirectory.from_config(cfg).get_current_head()


def test_fresh_db_is_migrated_to_head(db):
    engine = base.get_engine()
    tables = set(inspect(engine).get_table_names())
    assert {"users", "sessions", "ws_tokens", "audit_log", "settings", "alembic_version"} <= tables
    with engine.connect() as conn:
        version = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
    assert version == _head_revision() == "0001_initial"


def test_init_db_is_idempotent(db):
    base.init_db()
    base.init_db()
    assert "users" in inspect(base.get_engine()).get_table_names()


def test_sqlite_pragmas_applied(db):
    with base.get_engine().connect() as conn:
        assert conn.execute(text("PRAGMA foreign_keys")).scalar() == 1
        assert conn.execute(text("PRAGMA journal_mode")).scalar().lower() == "wal"


def test_every_model_module_is_imported_by_env_py():
    """Autogenerate silently proposes dropping tables of models env.py does not import."""
    import re
    from pathlib import Path

    pkg = Path(base.__file__).resolve().parents[1]
    models = {p.stem for p in (pkg / "models").glob("*.py") if p.stem != "__init__"}
    env_src = (pkg / "migrations" / "env.py").read_text()
    imported = set(re.findall(r"from sfincs_ui\.models import (\w+)", env_src))
    assert models <= imported, f"env.py misses model imports: {sorted(models - imported)}"
```

Add to `sfincs_ui/tests/conftest.py`:

```python
@pytest.fixture
def db(tmp_path, monkeypatch):
    """A migrated SQLite database in tmp_path; returns the session factory.

    Points the global engine at the temp file so services built without an
    explicit session_factory also use it.
    """
    from sfincs_ui import config
    from sfincs_ui.db import base

    cfg = config.Config(workspace=tmp_path, database_url=f"sqlite:///{tmp_path / 'test.db'}")
    config.set_config(cfg)
    base.reset_engine()
    base.init_db()
    yield base.get_session_factory()
    base.reset_engine()
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd /home/razinka/sfincs/sfincs_ui && /opt/micromamba/envs/shiny/bin/python -m pytest tests/test_db_init.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'sfincs_ui.db'`

- [ ] **Step 3: Write the db base**

`sfincs_ui/sfincs_ui/db/__init__.py`:

```python
from sfincs_ui.db.base import Base, db_session, get_engine, get_session_factory, init_db, reset_engine

__all__ = ["Base", "db_session", "get_engine", "get_session_factory", "init_db", "reset_engine"]
```

`sfincs_ui/sfincs_ui/db/base.py`:

```python
"""SQLAlchemy engine, session factory and Alembic-driven schema setup."""

from __future__ import annotations

import logging
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

from alembic import command
from alembic.config import Config as AlembicConfig
from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from sfincs_ui.config import get_config

logger = logging.getLogger(__name__)

MIGRATIONS_DIR = Path(__file__).resolve().parents[1] / "migrations"


class Base(DeclarativeBase):
    pass


_engine = None
_SessionLocal = None


def get_engine():
    global _engine
    if _engine is None:
        url = get_config().database_url_resolved
        if url.startswith("sqlite"):
            _engine = create_engine(url, connect_args={"check_same_thread": False})

            @event.listens_for(_engine, "connect")
            def _set_sqlite_pragmas(dbapi_conn, _record):
                # busy_timeout: concurrent writers wait instead of raising
                # "database is locked"; WAL lets readers run beside a writer;
                # foreign keys are off in SQLite unless set per connection.
                cur = dbapi_conn.cursor()
                cur.execute("PRAGMA busy_timeout=5000")
                cur.execute("PRAGMA journal_mode=WAL")
                cur.execute("PRAGMA foreign_keys=ON")
                cur.close()

        else:
            _engine = create_engine(url, pool_pre_ping=True)
    return _engine


def get_session_factory():
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=get_engine())
    return _SessionLocal


def reset_engine() -> None:
    """Drop the cached engine and factory (tests, or after set_config)."""
    global _engine, _SessionLocal
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _SessionLocal = None


def alembic_config(url: str) -> AlembicConfig:
    """Alembic configuration built in code: no ini file to locate.

    Works identically from the source tree and from an editable install.
    """
    cfg = AlembicConfig()
    cfg.set_main_option("script_location", str(MIGRATIONS_DIR))
    cfg.set_main_option("sqlalchemy.url", url)
    return cfg


def init_db() -> None:
    """Migrate the configured database to head. Raises on failure."""
    url = get_config().database_url_resolved
    if url.startswith("sqlite:///"):
        Path(url[len("sqlite:///"):]).parent.mkdir(parents=True, exist_ok=True)
    command.upgrade(alembic_config(url), "head")
    logger.info("database migrated to head: %s", url)


@contextmanager
def db_session() -> Generator[Session, None, None]:
    session = get_session_factory()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
```

- [ ] **Step 4: Write the models**

`sfincs_ui/sfincs_ui/models/user.py`:

```python
"""Users, login sessions and websocket tokens."""

from __future__ import annotations

import re
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from sfincs_ui.db.base import Base

ROLE_ADMIN = "admin"
ROLE_USER = "user"
ROLES = (ROLE_ADMIN, ROLE_USER)

# A username appears in audit rows and later in workspace paths, so it is a
# single safe path segment: letters/digits/underscore first, then also . and -.
USERNAME_RE = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_.-]*$")
_MAX_USERNAME_LEN = 64


def validate_username(username: str) -> None:
    if (
        not username
        or len(username) > _MAX_USERNAME_LEN
        or username in (".", "..")
        or not USERNAME_RE.match(username)
    ):
        raise ValueError(
            "Username must be 1-64 characters, start with a letter, digit or underscore, "
            "and contain only letters, digits, dots, hyphens and underscores."
        )


def _is_expired(expires: datetime) -> bool:
    now = datetime.now(timezone.utc)
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    return now >= expires


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    display_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True, unique=True)
    password_hash: Mapped[str] = mapped_column(String(512), nullable=False)
    role: Mapped[str] = mapped_column(String(16), nullable=False, default=ROLE_USER)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )

    sessions: Mapped[list["AuthSession"]] = relationship(
        "AuthSession", back_populates="user", cascade="all, delete-orphan"
    )

    @property
    def is_admin(self) -> bool:
        return self.role == ROLE_ADMIN


class AuthSession(Base):
    __tablename__ = "sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    token: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)

    user: Mapped["User"] = relationship("User", back_populates="sessions")

    @property
    def is_expired(self) -> bool:
        return _is_expired(self.expires_at)


class WSAuthToken(Base):
    """Bridges the HTTP session into the Shiny websocket scope.

    Distinct from the cookie value; its validity is inherited from the owning
    AuthSession (dies on logout and on session expiry).
    """

    __tablename__ = "ws_tokens"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    token: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    session_token: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    @property
    def is_expired(self) -> bool:
        return _is_expired(self.expires_at)
```

`sfincs_ui/sfincs_ui/models/audit_log.py`:

```python
"""Audit log: who did what, to which target, when."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from sfincs_ui.db.base import Base


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False, index=True
    )
    # user_id is nullable and SET NULL on delete; username is kept so a row
    # still reads after its user is removed.
    user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    username: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    action: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    target: Mapped[str | None] = mapped_column(String(255), nullable=True)
    detail_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
```

`sfincs_ui/sfincs_ui/models/setting.py`:

```python
"""Admin-chosen settings (queue policy, retention, quota) as JSON values."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from sfincs_ui.db.base import Base


class Setting(Base):
    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value_json: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )
```

`sfincs_ui/sfincs_ui/models/__init__.py`:

```python
from sfincs_ui.models.audit_log import AuditLog
from sfincs_ui.models.setting import Setting
from sfincs_ui.models.user import ROLE_ADMIN, ROLE_USER, ROLES, AuthSession, User, WSAuthToken, validate_username

__all__ = [
    "AuditLog", "Setting", "AuthSession", "User", "WSAuthToken",
    "ROLE_ADMIN", "ROLE_USER", "ROLES", "validate_username",
]
```

- [ ] **Step 5: Write the Alembic environment and the initial revision**

`sfincs_ui/sfincs_ui/migrations/env.py`:

```python
"""Alembic environment. Imports every model module so autogenerate sees all tables."""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from sfincs_ui.db.base import Base
from sfincs_ui.models import audit_log  # noqa: F401
from sfincs_ui.models import setting  # noqa: F401
from sfincs_ui.models import user  # noqa: F401

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name, disable_existing_loggers=False)

target_metadata = Base.metadata

if not config.get_main_option("sqlalchemy.url"):
    from sfincs_ui.config import get_config

    config.set_main_option("sqlalchemy.url", get_config().database_url_resolved)


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}), prefix="sqlalchemy.", poolclass=pool.NullPool
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata, render_as_batch=True)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
```

`sfincs_ui/sfincs_ui/migrations/script.py.mako`:

```mako
"""${message}

Revision ID: ${up_revision}
Revises: ${down_revision | comma,n}
Create Date: ${create_date}
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
${imports if imports else ""}

revision: str = ${repr(up_revision)}
down_revision: Union[str, Sequence[str], None] = ${repr(down_revision)}
branch_labels: Union[str, Sequence[str], None] = ${repr(branch_labels)}
depends_on: Union[str, Sequence[str], None] = ${repr(depends_on)}


def upgrade() -> None:
    ${upgrades if upgrades else "pass"}


def downgrade() -> None:
    ${downgrades if downgrades else "pass"}
```

`sfincs_ui/sfincs_ui/migrations/versions/0001_initial.py`:

```python
"""initial schema: users, sessions, ws_tokens, audit_log, settings

Revision ID: 0001_initial
Revises:
Create Date: 2026-10-01
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0001_initial"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_NOW = sa.text("(CURRENT_TIMESTAMP)")


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("username", sa.String(64), nullable=False),
        sa.Column("display_name", sa.String(255), nullable=True),
        sa.Column("email", sa.String(255), nullable=True),
        sa.Column("password_hash", sa.String(512), nullable=False),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=_NOW, nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=_NOW, nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("username"),
        sa.UniqueConstraint("email"),
    )
    op.create_table(
        "sessions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("token", sa.String(255), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=_NOW, nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("ip_address", sa.String(45), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_sessions_token", "sessions", ["token"], unique=True)
    op.create_table(
        "ws_tokens",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("token", sa.String(255), nullable=False),
        sa.Column("session_token", sa.String(255), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=_NOW, nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_ws_tokens_token", "ws_tokens", ["token"], unique=True)
    op.create_index("ix_ws_tokens_session_token", "ws_tokens", ["session_token"])
    op.create_table(
        "audit_log",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("timestamp", sa.DateTime(), server_default=_NOW, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("username", sa.String(64), nullable=False),
        sa.Column("action", sa.String(64), nullable=False),
        sa.Column("target", sa.String(255), nullable=True),
        sa.Column("detail_json", sa.Text(), nullable=True),
        sa.Column("ip_address", sa.String(45), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_audit_log_timestamp", "audit_log", ["timestamp"])
    op.create_index("ix_audit_log_username", "audit_log", ["username"])
    op.create_index("ix_audit_log_action", "audit_log", ["action"])
    op.create_table(
        "settings",
        sa.Column("key", sa.String(64), nullable=False),
        sa.Column("value_json", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=_NOW, nullable=False),
        sa.PrimaryKeyConstraint("key"),
    )


def downgrade() -> None:
    op.drop_table("settings")
    op.drop_table("audit_log")
    op.drop_table("ws_tokens")
    op.drop_table("sessions")
    op.drop_table("users")
```

`sfincs_ui/alembic.ini` (only for `alembic revision --autogenerate` from the project directory; the app never reads it):

```ini
[alembic]
script_location = %(here)s/sfincs_ui/migrations
prepend_sys_path = .

[loggers]
keys = root,sqlalchemy,alembic

[handlers]
keys = console

[formatters]
keys = generic

[logger_root]
level = WARNING
handlers = console
qualname =

[logger_sqlalchemy]
level = WARNING
handlers =
qualname = sqlalchemy.engine

[logger_alembic]
level = INFO
handlers =
qualname = alembic

[handler_console]
class = StreamHandler
args = (sys.stderr,)
level = NOTSET
formatter = generic

[formatter_generic]
format = %(levelname)-5.5s [%(name)s] %(message)s
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `cd /home/razinka/sfincs/sfincs_ui && /opt/micromamba/envs/shiny/bin/python -m pytest tests/test_db_init.py tests/test_config.py -q`
Expected: 14 passed

- [ ] **Step 7: Check autogenerate sees nothing to do**

Run from `sfincs_ui/`:

```bash
export SFINCS_UI_WORKSPACE=/tmp/claude-1000/-home-razinka-sfincs/946ef2e3-64b8-42c9-b324-8e8da9f13c98/scratchpad/ag
mkdir -p "$SFINCS_UI_WORKSPACE"
/opt/micromamba/envs/shiny/bin/python -c "from sfincs_ui.db import base; base.init_db()"
/opt/micromamba/envs/shiny/bin/python -m alembic -c alembic.ini check
```

Expected: `No new upgrade operations detected.` If it reports differences, the hand-written revision drifted from the models; fix the revision, not the models.

- [ ] **Step 8: Commit**

```bash
cd /home/razinka/sfincs
git add sfincs_ui/alembic.ini sfincs_ui/sfincs_ui/db sfincs_ui/sfincs_ui/models sfincs_ui/sfincs_ui/migrations sfincs_ui/tests/conftest.py sfincs_ui/tests/test_db_init.py
git commit -m "sfincs_ui: SQLAlchemy models and the initial Alembic migration

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 3: Auth and audit services (copied from SHYFEM UI)

**Files:**
- Create: `sfincs_ui/sfincs_ui/services/__init__.py` (empty)
- Create: `sfincs_ui/sfincs_ui/services/auth_service.py` (copy of `/home/razinka/shyfem/shyfem-ui/shyfem_ui/services/auth_service.py`, edited)
- Create: `sfincs_ui/sfincs_ui/services/audit_service.py` (copy of `/home/razinka/shyfem/shyfem-ui/shyfem_ui/services/audit_service.py`, edited)
- Create: `sfincs_ui/sfincs_ui/services/ws_identity.py` (copy of `.../services/ws_identity.py`, imports only)
- Modify: `sfincs_ui/tests/conftest.py` (fast argon2 fixture)
- Test: `sfincs_ui/tests/test_auth_service.py`, `sfincs_ui/tests/test_audit_service.py`

**Interfaces:**
- Consumes: models and `get_session_factory()` from Task 2.
- Produces: `AuthService(session_factory=None)` with `hash_password`, `verify_password`, `create_user(username, password, role="user", display_name=None, email=None) -> dict`, `list_users() -> list[dict]`, `update_user(user_id, **fields) -> dict | None` (fields: display_name, email, role, is_active), `delete_user(user_id) -> bool`, `reset_password(user_id, new_password) -> bool`, `authenticate(username, password) -> dict | None`, `create_session(user_id, ttl_hours=24, ip_address=None) -> str`, `validate_session(token) -> dict | None`, `delete_session(token) -> bool`, `cleanup_expired_sessions() -> int`, `create_ws_token(user_id, session_token, ttl_hours=24) -> str`, `validate_ws_token(token) -> dict | None`, `ensure_admin(username, password, email=None) -> tuple[dict, bool]` (the dict and whether it was created). User dicts have keys `id, username, display_name, email, role, is_active`. `AuditService(session_factory=None)` with `log(username, action, target=None, detail=None, ip_address=None, user_id=None)`, `query(*, username=None, action=None, since=None, limit=200, offset=0) -> list[dict]`, `count(*, username=None, action=None) -> int`, `distinct_actions() -> list[str]`. `resolve_ws_user(token, auth_service) -> dict | None`.

- [ ] **Step 1: Add the fast-argon2 fixture**

Append to `sfincs_ui/tests/conftest.py`:

```python
@pytest.fixture(autouse=True, scope="session")
def _fast_argon2():
    """Cheap argon2 parameters for the suite; production keeps the library defaults."""
    from argon2 import PasswordHasher

    from sfincs_ui.services import auth_service

    cheap = PasswordHasher(time_cost=1, memory_cost=8 * 1024, parallelism=1)
    auth_service._ph = cheap
    auth_service._DUMMY_HASH = cheap.hash("x")
    yield
```

- [ ] **Step 2: Write the failing auth tests**

`sfincs_ui/tests/test_auth_service.py`:

```python
import pytest

from sfincs_ui.services.auth_service import AuthService


@pytest.fixture
def auth(db):
    return AuthService(session_factory=db)


def test_create_and_authenticate(auth):
    u = auth.create_user("alice", "correct horse", role="user", email="a@example.org")
    assert u["username"] == "alice" and u["role"] == "user" and u["is_active"] is True
    assert auth.authenticate("alice", "correct horse")["id"] == u["id"]
    assert auth.authenticate("alice", "wrong") is None
    assert auth.authenticate("nobody", "x") is None


def test_email_is_optional(auth):
    u = auth.create_user("bob", "password123")
    assert u["email"] is None


def test_duplicate_username_rejected(auth):
    auth.create_user("alice", "pw12345678")
    with pytest.raises(ValueError):
        auth.create_user("alice", "pw12345678")


def test_unsafe_username_rejected(auth):
    for bad in ["", "..", "a/b", "-dash", "x" * 65]:
        with pytest.raises(ValueError):
            auth.create_user(bad, "pw12345678")


def test_inactive_user_cannot_log_in(auth):
    u = auth.create_user("carol", "pw12345678")
    auth.update_user(u["id"], is_active=False)
    assert auth.authenticate("carol", "pw12345678") is None


def test_session_round_trip_and_logout(auth):
    u = auth.create_user("dave", "pw12345678")
    tok = auth.create_session(u["id"], ttl_hours=1, ip_address="10.0.0.1")
    assert auth.validate_session(tok)["username"] == "dave"
    assert auth.delete_session(tok) is True
    assert auth.validate_session(tok) is None
    assert auth.validate_session("forged") is None


def test_expired_session_is_removed(auth):
    u = auth.create_user("erin", "pw12345678")
    tok = auth.create_session(u["id"], ttl_hours=0)
    assert auth.validate_session(tok) is None
    assert auth.cleanup_expired_sessions() == 0  # already purged by validate


def test_ws_token_inherits_session_validity(auth):
    u = auth.create_user("frank", "pw12345678")
    sess = auth.create_session(u["id"])
    ws = auth.create_ws_token(u["id"], sess)
    assert auth.validate_ws_token(ws)["username"] == "frank"
    auth.delete_session(sess)
    assert auth.validate_ws_token(ws) is None


def test_delete_last_admin_refused(auth):
    admin, _ = auth.ensure_admin("root", "pw12345678")
    with pytest.raises(ValueError):
        auth.delete_user(admin["id"])
    # an inactive second admin does not count as a usable replacement
    other = auth.create_user("other", "pw12345678", role="admin")
    auth.update_user(other["id"], is_active=False)
    with pytest.raises(ValueError):
        auth.delete_user(admin["id"])


def test_update_user_refuses_to_strip_last_admin(auth):
    """Review Focus 1: the only admin must not demote or deactivate themself."""
    admin, _ = auth.ensure_admin("root", "pw12345678")
    with pytest.raises(ValueError, match="last admin"):
        auth.update_user(admin["id"], role="user")
    with pytest.raises(ValueError, match="last admin"):
        auth.update_user(admin["id"], is_active=False)
    assert auth.list_users()[0]["role"] == "admin"
    second = auth.create_user("second", "pw12345678", role="admin")
    assert auth.update_user(admin["id"], role="user")["role"] == "user"
    assert auth.list_users()[1]["id"] == second["id"]


def test_ensure_admin_is_idempotent(auth):
    first, created = auth.ensure_admin("root", "pw12345678")
    assert created is True
    again, created_again = auth.ensure_admin("root", "another-password")
    assert created_again is False and again["id"] == first["id"]
    assert auth.authenticate("root", "pw12345678") is not None
    assert auth.authenticate("root", "another-password") is None


def test_reset_password(auth):
    u = auth.create_user("gina", "old-password")
    assert auth.reset_password(u["id"], "new-password") is True
    assert auth.authenticate("gina", "new-password") is not None
    assert auth.reset_password(999, "x") is False


def test_delete_user_removes_sessions_and_tokens(auth, db):
    from sfincs_ui.models import AuthSession, WSAuthToken

    u = auth.create_user("hank", "pw12345678")
    sess = auth.create_session(u["id"])
    auth.create_ws_token(u["id"], sess)
    assert auth.delete_user(u["id"]) is True
    s = db()
    try:
        assert s.query(AuthSession).count() == 0
        assert s.query(WSAuthToken).count() == 0
    finally:
        s.close()
```

`sfincs_ui/tests/test_audit_service.py`:

```python
import json

from sfincs_ui.services.audit_service import AuditService


def test_log_and_query(db):
    svc = AuditService(session_factory=db)
    svc.log("alice", "login_success", ip_address="10.0.0.1")
    svc.log("alice", "settings_update", target="max_threads", detail={"old": 8, "new": 12})
    svc.log("bob", "login_failed")
    rows = svc.query()
    assert [r["action"] for r in rows] == ["login_failed", "settings_update", "login_success"]
    assert svc.count() == 3
    assert svc.count(username="alice") == 2
    assert svc.query(action="settings_update")[0]["target"] == "max_threads"
    assert json.loads(svc.query(action="settings_update")[0]["detail"]) == {"old": 8, "new": 12}
    assert svc.distinct_actions() == ["login_failed", "login_success", "settings_update"]


def test_string_detail_is_kept_verbatim(db):
    svc = AuditService(session_factory=db)
    svc.log("alice", "note", detail="plain text")
    assert svc.query()[0]["detail"] == "plain text"


def test_user_id_survives_user_deletion(db):
    from sfincs_ui.services.auth_service import AuthService

    auth = AuthService(session_factory=db)
    u = auth.create_user("ivy", "pw12345678")
    svc = AuditService(session_factory=db)
    svc.log("ivy", "login_success", user_id=u["id"])
    auth.delete_user(u["id"])
    row = svc.query()[0]
    assert row["username"] == "ivy" and row["user_id"] is None
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `cd /home/razinka/sfincs/sfincs_ui && /opt/micromamba/envs/shiny/bin/python -m pytest tests/test_auth_service.py tests/test_audit_service.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'sfincs_ui.services'`

- [ ] **Step 4: Copy and edit auth_service.py**

```bash
mkdir -p /home/razinka/sfincs/sfincs_ui/sfincs_ui/services
touch /home/razinka/sfincs/sfincs_ui/sfincs_ui/services/__init__.py
cp /home/razinka/shyfem/shyfem-ui/shyfem_ui/services/auth_service.py /home/razinka/sfincs/sfincs_ui/sfincs_ui/services/auth_service.py
cp /home/razinka/shyfem/shyfem-ui/shyfem_ui/services/ws_identity.py /home/razinka/sfincs/sfincs_ui/sfincs_ui/services/ws_identity.py
```

Apply these edits to `auth_service.py` (the file is 577 lines; every edit is a deletion or a rename, except the two guards):

1. Replace every `shyfem_ui.` with `sfincs_ui.`. The import line becomes `from sfincs_ui.models.user import ROLE_ADMIN, ROLES, AuthSession, User, WSAuthToken, validate_username`.
2. `create_user`: drop the `user_data_root` parameter and its docstring lines; delete the `from shyfem_ui.models.user import ROLE_TUTORIAL` import and the `if role != ROLE_TUTORIAL and not email: raise` block; delete the `if user_data_root and role != ROLE_TUTORIAL:` home-directory block. Add, right after `validate_username(username)`: `if role not in ROLES: raise ValueError(f"role must be one of {ROLES}")`.
3. `update_user`: after loading `user` and before the `setattr` loop insert the last-admin guard:

```python
            demoting = kwargs.get("role", user.role) != ROLE_ADMIN
            deactivating = kwargs.get("is_active", user.is_active) is False
            if user.role == ROLE_ADMIN and (demoting or deactivating):
                others = (
                    session.query(User)
                    .filter(User.role == ROLE_ADMIN, User.is_active.is_(True), User.id != user.id)
                    .count()
                )
                if others == 0:
                    raise ValueError("Cannot demote or deactivate the last admin")
            if "role" in kwargs and kwargs["role"] not in ROLES:
                raise ValueError(f"role must be one of {ROLES}")
```

4. `delete_user`: delete the `from shyfem_ui.models.user import ProjectPermission` import, the `from shyfem_ui.models.project import Job, Project` and `from shyfem_ui.models.workflow import Workflow` imports, and the four `session.query(ProjectPermission|Project|Job|Workflow)...` lines. Keep `session.query(WSAuthToken).filter_by(user_id=user_id).delete()` (sessions go through the FK cascade). Change the last-admin check to count **active** admins, matching the `update_user` guard: `admin_count = session.query(User).filter(User.role == ROLE_ADMIN, User.is_active.is_(True)).count()`; otherwise one active plus one deactivated admin still permits deleting the only usable admin.
5. Delete the whole `ensure_user` method (tutorial bootstrap).
6. `ensure_admin`: return `(self._user_to_dict(admin), False)` when an admin exists and `(created_dict, True)` after creating one; drop the `f"{username}@localhost"` email fallback (pass `email` through, it is nullable now). Update its docstring: "Returns the admin dict and whether it was created."
7. `_user_to_dict`: unchanged.
8. Module docstring: `"""Authentication service: argon2 password hashing, sessions, user CRUD."""`.

`ws_identity.py`: no code change beyond the docstring's first line, which should read `"""Websocket identity resolver (pure wrapper around AuthService.validate_ws_token)."""`.

- [ ] **Step 5: Copy and edit audit_service.py**

```bash
cp /home/razinka/shyfem/shyfem-ui/shyfem_ui/services/audit_service.py /home/razinka/sfincs/sfincs_ui/sfincs_ui/services/audit_service.py
```

Edits:

1. Replace `shyfem_ui.` with `sfincs_ui.`; drop the `timeutil` import and the whole `cleanup_old_logs` method (retention is milestone 6).
2. `log` signature becomes `log(self, username, action, target=None, detail=None, ip_address=None, user_id=None)`. Build the row as `AuditLog(username=username, action=action, target=target, detail_json=_encode(detail), ip_address=ip_address, user_id=user_id)` where, at module level:

```python
import json


def _encode(detail) -> str | None:
    if detail is None:
        return None
    if isinstance(detail, str):
        return detail
    return json.dumps(detail, default=str)
```

3. `query`: order by `AuditLog.timestamp.desc(), AuditLog.id.desc()` (CURRENT_TIMESTAMP has one-second resolution, so rows written in the same second need the id to keep insertion order); the returned dicts gain `"user_id": r.user_id` and `"target": r.target or ""`, and `"detail": r.detail_json or ""` replaces `r.detail`.
4. Docstring: `"""Audit logging service: records user actions to the database."""`.

- [ ] **Step 6: Run the tests to verify they pass, then the grep gate**

Run: `cd /home/razinka/sfincs/sfincs_ui && /opt/micromamba/envs/shiny/bin/python -m pytest tests/test_auth_service.py tests/test_audit_service.py -q`
Expected: 16 passed

Run: `grep -rniE 'shyfem|tutorial|feedback|user_data_root|home_dir' sfincs_ui/sfincs_ui/services/`
Expected: no output

- [ ] **Step 7: Commit**

```bash
cd /home/razinka/sfincs
git add sfincs_ui/sfincs_ui/services sfincs_ui/tests/conftest.py sfincs_ui/tests/test_auth_service.py sfincs_ui/tests/test_audit_service.py
git commit -m "sfincs_ui: auth and audit services from SHYFEM UI, with a last-admin guard

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 4: Settings service (admin values under environment ceilings)

**Files:**
- Create: `sfincs_ui/sfincs_ui/services/settings_service.py`
- Test: `sfincs_ui/tests/test_settings_service.py`

**Interfaces:**
- Consumes: `Config` (Task 1), `Setting` model and `get_session_factory()` (Task 2).
- Produces: `POLICY_KEYS = ("max_simulations", "max_threads", "retention_days", "quota_gb")`; `PolicyRow(key, label, value, ceiling, explanation)` dataclass; `SettingsService(config, session_factory=None)` with `ceiling(key) -> int`, `get(key) -> int`, `effective() -> dict[str, int]`, `rows() -> list[PolicyRow]`, `set(key, value) -> int` (raises `ValueError` naming the ceiling or the floor of 1; unknown key raises `KeyError`).

- [ ] **Step 1: Write the failing tests**

`sfincs_ui/tests/test_settings_service.py`:

```python
import pytest

from sfincs_ui.config import Config
from sfincs_ui.services.settings_service import POLICY_KEYS, SettingsService


@pytest.fixture
def svc(db, tmp_path):
    cfg = Config(workspace=tmp_path, max_simulations=2, max_threads=16, retention_days=90, quota_gb=50)
    return SettingsService(cfg, session_factory=db)


def test_env_values_are_defaults_and_ceilings(svc):
    assert svc.effective() == {"max_simulations": 2, "max_threads": 16, "retention_days": 90, "quota_gb": 50}
    for key in POLICY_KEYS:
        assert svc.ceiling(key) == svc.get(key)


def test_admin_value_below_ceiling_is_stored_and_read_back(svc):
    assert svc.set("max_threads", 12) == 12
    assert svc.get("max_threads") == 12
    assert svc.effective()["max_threads"] == 12
    assert svc.set("max_threads", 16) == 16  # equal to the ceiling is allowed


def test_set_above_ceiling_rejected_and_unchanged(svc):
    """Review Focus 2."""
    svc.set("max_threads", 12)
    with pytest.raises(ValueError, match="16"):
        svc.set("max_threads", 32)
    assert svc.get("max_threads") == 12


def test_set_below_one_rejected(svc):
    with pytest.raises(ValueError):
        svc.set("max_simulations", 0)


def test_unknown_key_rejected(svc):
    with pytest.raises(KeyError):
        svc.set("min_free_gb", 10)  # env-only by spec


def test_rows_describe_each_policy(svc):
    svc.set("quota_gb", 10)
    rows = {r.key: r for r in svc.rows()}
    assert set(rows) == set(POLICY_KEYS)
    assert rows["quota_gb"].value == 10 and rows["quota_gb"].ceiling == 50
    assert rows["max_threads"].label and rows["max_threads"].explanation


def test_stale_stored_value_above_a_lowered_ceiling_is_clamped(svc, db, tmp_path):
    svc.set("max_threads", 16)
    lowered = SettingsService(Config(workspace=tmp_path, max_threads=8), session_factory=db)
    assert lowered.get("max_threads") == 8
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd /home/razinka/sfincs/sfincs_ui && /opt/micromamba/envs/shiny/bin/python -m pytest tests/test_settings_service.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'sfincs_ui.services.settings_service'`

- [ ] **Step 3: Write the service**

`sfincs_ui/sfincs_ui/services/settings_service.py`:

```python
"""Admin-chosen queue policy, retention and quota, bounded by the environment.

Precedence (spec section 5): SFINCS_UI_* values are install-time ceilings and
defaults; the ``settings`` table holds admin-chosen values validated at or
below the ceilings; readers take the table value when present, else the env
value. A stored value above a later-lowered ceiling reads as the ceiling.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from sfincs_ui.config import Config
from sfincs_ui.models.setting import Setting

POLICY_KEYS = ("max_simulations", "max_threads", "retention_days", "quota_gb")

_META = {
    "max_simulations": ("Simulations at once", "How many SFINCS solvers may run concurrently."),
    "max_threads": ("Threads per run", "OpenMP threads a user may request for one simulation."),
    "retention_days": ("Retention (days)", "Unpinned run directories older than this are deleted."),
    "quota_gb": ("Quota per user (GB)", "Total size of a user's run directories."),
}


@dataclass(frozen=True)
class PolicyRow:
    key: str
    label: str
    value: int
    ceiling: int
    explanation: str


class SettingsService:
    def __init__(self, config: Config, session_factory=None):
        if session_factory is None:
            from sfincs_ui.db.base import get_session_factory

            session_factory = get_session_factory()
        self._config = config
        self._session_factory = session_factory

    def ceiling(self, key: str) -> int:
        if key not in POLICY_KEYS:
            raise KeyError(key)
        return int(getattr(self._config, key))

    def _stored(self) -> dict[str, int]:
        session = self._session_factory()
        try:
            rows = session.query(Setting).filter(Setting.key.in_(POLICY_KEYS)).all()
            return {r.key: int(json.loads(r.value_json)) for r in rows}
        finally:
            session.close()

    def get(self, key: str) -> int:
        ceiling = self.ceiling(key)
        stored = self._stored().get(key)
        if stored is None:
            return ceiling
        return min(stored, ceiling)

    def effective(self) -> dict[str, int]:
        stored = self._stored()
        return {k: min(stored.get(k, self.ceiling(k)), self.ceiling(k)) for k in POLICY_KEYS}

    def rows(self) -> list[PolicyRow]:
        eff = self.effective()
        return [
            PolicyRow(key=k, label=_META[k][0], value=eff[k], ceiling=self.ceiling(k), explanation=_META[k][1])
            for k in POLICY_KEYS
        ]

    def set(self, key: str, value: int) -> int:
        ceiling = self.ceiling(key)
        value = int(value)
        if value < 1:
            raise ValueError(f"{_META[key][0]} must be at least 1")
        if value > ceiling:
            raise ValueError(f"{_META[key][0]} may not exceed the server ceiling of {ceiling}")
        session = self._session_factory()
        try:
            row = session.get(Setting, key)
            if row is None:
                session.add(Setting(key=key, value_json=json.dumps(value)))
            else:
                row.value_json = json.dumps(value)
            session.commit()
            return value
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd /home/razinka/sfincs/sfincs_ui && /opt/micromamba/envs/shiny/bin/python -m pytest tests/test_settings_service.py -q`
Expected: 7 passed

- [ ] **Step 5: Commit**

```bash
cd /home/razinka/sfincs
git add sfincs_ui/sfincs_ui/services/settings_service.py sfincs_ui/tests/test_settings_service.py
git commit -m "sfincs_ui: settings service with environment ceilings

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 5: Session middleware with anonymous pass-through

**Files:**
- Create: `sfincs_ui/sfincs_ui/middleware/__init__.py` (empty)
- Create: `sfincs_ui/sfincs_ui/middleware/client_ip.py`
- Create: `sfincs_ui/sfincs_ui/middleware/session_auth.py`
- Test: `sfincs_ui/tests/test_session_auth_middleware.py`

**Interfaces:**
- Consumes: `AuthService`, `AuditService` (Task 3).
- Produces: `SessionAuthMiddleware(app, auth_service, audit_service=None, root_path="", session_ttl_hours=24, use_secure_cookies=True, trusted_proxies=None)`; `get_current_user() -> dict | None` (contextvar for the current ASGI scope, HTTP and websocket); constants `SESSION_COOKIE = "sfincs_ui_session"`, `CSRF_COOKIE = "sfincs_ui_csrf"`; `get_client_ip(scope, trusted_proxies) -> str`. Routes handled by the middleware: `GET /login`, `POST /login`, `GET /logout` (confirm page), `POST /logout`, `GET /api/whoami` (200 always; anonymous gets `{"username": null, "role": null, "ws_token": null}`). Every other HTTP and websocket scope passes through with the user set or `None`.

This differs from SHYFEM in exactly one policy: **nothing is redirected to `/login`**. Pages decide what an anonymous visitor may see. The ws-token bridge is kept because the spec says so and because it costs one route; under direct uvicorn the cookie also reaches the websocket scope, so `get_current_user()` works there too and `current_user()` in the app (Task 8) falls back to it.

- [ ] **Step 1: Write the failing tests**

`sfincs_ui/tests/test_session_auth_middleware.py`:

```python
from unittest.mock import AsyncMock, MagicMock

import pytest

from sfincs_ui.middleware.client_ip import get_client_ip
from sfincs_ui.middleware.session_auth import (
    CSRF_COOKIE,
    SESSION_COOKIE,
    SessionAuthMiddleware,
    get_current_user,
)

USER = {"id": 1, "username": "alice", "display_name": None, "email": None, "role": "user", "is_active": True}


def _scope(method="GET", path="/", cookies="", root_path="", type_="http", client=("203.0.113.5", 1234), headers=None):
    hdrs = list(headers or [])
    if cookies:
        hdrs.append((b"cookie", cookies.encode()))
    scope = {"type": type_, "path": path, "headers": hdrs, "client": client}
    if type_ == "http":
        scope["method"] = method
    if root_path:
        scope["root_path"] = root_path
    return scope


def _capture():
    seen = {}

    async def app(scope, receive, send):
        seen["user"] = get_current_user()
        seen["called"] = True

    return app, seen


def _responses(send):
    return [c[0][0] for c in send.call_args_list]


class TestPassThrough:
    async def test_no_cookie_is_anonymous_not_redirect(self):
        app, seen = _capture()
        mw = SessionAuthMiddleware(app, MagicMock())
        await mw(_scope(path="/"), AsyncMock(), AsyncMock())
        assert seen["called"] and seen["user"] is None

    async def test_valid_cookie_sets_user(self):
        auth = MagicMock(); auth.validate_session.return_value = USER
        app, seen = _capture()
        await SessionAuthMiddleware(app, auth)(_scope(cookies=f"{SESSION_COOKIE}=tok"), AsyncMock(), AsyncMock())
        auth.validate_session.assert_called_once_with("tok")
        assert seen["user"] == USER

    async def test_invalid_cookie_is_anonymous(self):
        """Review Focus 3: a forged or expired cookie renders the page as anonymous."""
        auth = MagicMock(); auth.validate_session.return_value = None
        app, seen = _capture()
        await SessionAuthMiddleware(app, auth)(_scope(cookies=f"{SESSION_COOKIE}=stale"), AsyncMock(), AsyncMock())
        assert seen["called"] and seen["user"] is None

    async def test_websocket_anonymous_passes_through(self):
        """Review Focus 3: the websocket is accepted with user=None, never closed with 4001."""
        auth = MagicMock(); auth.validate_session.return_value = None
        app, seen = _capture()
        send = AsyncMock()
        await SessionAuthMiddleware(app, auth)(_scope(type_="websocket"), AsyncMock(), send)
        assert seen["called"] and seen["user"] is None
        assert not any(m.get("type") == "websocket.close" for m in _responses(send))

    async def test_websocket_with_cookie_sets_user(self):
        auth = MagicMock(); auth.validate_session.return_value = USER
        app, seen = _capture()
        await SessionAuthMiddleware(app, auth)(_scope(type_="websocket", cookies=f"{SESSION_COOKIE}=tok"), AsyncMock(), AsyncMock())
        assert seen["user"] == USER

    async def test_lifespan_passes_through(self):
        app, seen = _capture()
        await SessionAuthMiddleware(app, MagicMock())({"type": "lifespan"}, AsyncMock(), AsyncMock())
        assert seen["called"]

    async def test_contextvar_is_reset_after_request(self):
        auth = MagicMock(); auth.validate_session.return_value = USER
        app, _ = _capture()
        await SessionAuthMiddleware(app, auth)(_scope(cookies=f"{SESSION_COOKIE}=tok"), AsyncMock(), AsyncMock())
        assert get_current_user() is None


class TestRootPath:
    async def test_login_route_matches_with_root_path_in_scope_path(self):
        """uvicorn --root-path /sfincs-ui delivers path=/sfincs-ui/login."""
        send = AsyncMock()
        inner = AsyncMock()
        await SessionAuthMiddleware(inner, MagicMock())(_scope(path="/sfincs-ui/login", root_path="/sfincs-ui"), AsyncMock(), send)
        inner.assert_not_called()
        assert _responses(send)[0]["status"] == 200 and b"csrf_token" in _responses(send)[1]["body"]

    async def test_login_route_matches_without_root_path_in_scope_path(self):
        send = AsyncMock()
        inner = AsyncMock()
        await SessionAuthMiddleware(inner, MagicMock())(_scope(path="/login", root_path="/sfincs-ui"), AsyncMock(), send)
        inner.assert_not_called()
        assert _responses(send)[0]["status"] == 200

    async def test_whoami_under_root_path(self):
        auth = MagicMock(); auth.validate_session.return_value = None
        send = AsyncMock()
        await SessionAuthMiddleware(AsyncMock(), auth, root_path="/sfincs-ui")(_scope(path="/sfincs-ui/api/whoami", root_path="/sfincs-ui"), AsyncMock(), send)
        assert dict(_responses(send)[0]["headers"])[b"content-type"] == b"application/json"


class TestLogin:
    async def test_get_login_serves_form_with_csrf_cookie(self):
        send = AsyncMock()
        await SessionAuthMiddleware(AsyncMock(), MagicMock(), root_path="/sfincs-ui")(_scope(path="/login"), AsyncMock(), send)
        start, body = _responses(send)
        assert start["status"] == 200
        headers = dict(start["headers"])
        assert headers[b"content-type"].startswith(b"text/html")
        cookie = headers[b"set-cookie"].decode()
        assert cookie.startswith(f"{CSRF_COOKIE}=") and "Path=/sfincs-ui" in cookie and "Secure" in cookie
        assert b'action="/sfincs-ui/login"' in body["body"] and b"SFINCS" in body["body"]

    async def test_post_login_success_sets_cookie_and_redirects(self):
        auth = MagicMock()
        auth.authenticate.return_value = USER
        auth.create_session.return_value = "newtok"
        audit = MagicMock()
        mw = SessionAuthMiddleware(AsyncMock(), auth, audit_service=audit, root_path="/sfincs-ui", session_ttl_hours=2)
        receive = AsyncMock(return_value={"type": "http.request", "body": b"username=alice&password=pw&csrf_token=abc", "more_body": False})
        send = AsyncMock()
        await mw(_scope(method="POST", path="/login", cookies=f"{CSRF_COOKIE}=abc"), receive, send)
        start = _responses(send)[0]
        assert start["status"] == 302
        headers = dict(start["headers"])
        assert headers[b"location"] == b"/sfincs-ui/"
        cookie = headers[b"set-cookie"].decode()
        assert cookie.startswith(f"{SESSION_COOKIE}=newtok") and "HttpOnly" in cookie and "SameSite=Lax" in cookie
        assert "Max-Age=7200" in cookie and "Secure" in cookie
        auth.create_session.assert_called_once_with(1, ttl_hours=2, ip_address="203.0.113.5")
        auth.cleanup_expired_sessions.assert_called_once()
        assert audit.log.call_args.kwargs["action"] == "login_success"

    async def test_post_login_bad_password_rerenders_with_error_and_audits(self):
        auth = MagicMock(); auth.authenticate.return_value = None
        audit = MagicMock()
        mw = SessionAuthMiddleware(AsyncMock(), auth, audit_service=audit)
        receive = AsyncMock(return_value={"type": "http.request", "body": b"username=alice&password=bad&csrf_token=abc", "more_body": False})
        send = AsyncMock()
        await mw(_scope(method="POST", path="/login", cookies=f"{CSRF_COOKIE}=abc"), receive, send)
        start, body = _responses(send)
        assert start["status"] == 200 and b"Invalid username or password" in body["body"]
        assert audit.log.call_args.kwargs["action"] == "login_failed"
        auth.create_session.assert_not_called()

    async def test_post_login_csrf_mismatch_rejected(self):
        auth = MagicMock()
        mw = SessionAuthMiddleware(AsyncMock(), auth)
        receive = AsyncMock(return_value={"type": "http.request", "body": b"username=alice&password=pw&csrf_token=zzz", "more_body": False})
        send = AsyncMock()
        await mw(_scope(method="POST", path="/login", cookies=f"{CSRF_COOKIE}=abc"), receive, send)
        start, body = _responses(send)
        assert start["status"] == 200 and b"Invalid request" in body["body"]
        auth.authenticate.assert_not_called()

    async def test_post_login_body_in_chunks(self):
        auth = MagicMock(); auth.authenticate.return_value = USER; auth.create_session.return_value = "t"
        mw = SessionAuthMiddleware(AsyncMock(), auth)
        chunks = [
            {"type": "http.request", "body": b"username=alice&pass", "more_body": True},
            {"type": "http.request", "body": b"word=pw&csrf_token=abc", "more_body": False},
        ]
        receive = AsyncMock(side_effect=chunks)
        await mw(_scope(method="POST", path="/login", cookies=f"{CSRF_COOKIE}=abc"), receive, AsyncMock())
        auth.authenticate.assert_called_once_with("alice", "pw")


class TestLogout:
    async def test_get_logout_is_a_confirm_page(self):
        auth = MagicMock()
        send = AsyncMock()
        await SessionAuthMiddleware(AsyncMock(), auth)(_scope(path="/logout", cookies=f"{SESSION_COOKIE}=tok"), AsyncMock(), send)
        start, body = _responses(send)
        assert start["status"] == 200 and b'method="post"' in body["body"]
        auth.delete_session.assert_not_called()

    async def test_post_logout_deletes_session_and_clears_cookie(self):
        auth = MagicMock(); auth.validate_session.return_value = USER
        audit = MagicMock()
        send = AsyncMock()
        await SessionAuthMiddleware(AsyncMock(), auth, audit_service=audit, root_path="/p")(
            _scope(method="POST", path="/logout", cookies=f"{SESSION_COOKIE}=tok"), AsyncMock(), send
        )
        auth.delete_session.assert_called_once_with("tok")
        start = _responses(send)[0]
        headers = dict(start["headers"])
        assert start["status"] == 302 and headers[b"location"] == b"/p/"
        assert "Max-Age=0" in headers[b"set-cookie"].decode()
        assert audit.log.call_args.kwargs["action"] == "logout"


class TestWhoami:
    async def test_anonymous_gets_nulls_not_401(self):
        auth = MagicMock(); auth.validate_session.return_value = None
        send = AsyncMock()
        await SessionAuthMiddleware(AsyncMock(), auth)(_scope(path="/api/whoami"), AsyncMock(), send)
        start, body = _responses(send)
        assert start["status"] == 200
        import json
        assert json.loads(body["body"]) == {"username": None, "display_name": None, "role": None, "ws_token": None}

    async def test_logged_in_gets_ws_token(self):
        auth = MagicMock(); auth.validate_session.return_value = USER; auth.create_ws_token.return_value = "wst"
        send = AsyncMock()
        await SessionAuthMiddleware(AsyncMock(), auth)(_scope(path="/api/whoami", cookies=f"{SESSION_COOKIE}=tok"), AsyncMock(), send)
        import json
        data = json.loads(_responses(send)[1]["body"])
        assert data["username"] == "alice" and data["role"] == "user" and data["ws_token"] == "wst"
        auth.create_ws_token.assert_called_once_with(1, "tok")


class TestClientIp:
    def test_untrusted_peer_ignores_forwarded_for(self):
        scope = _scope(headers=[(b"x-forwarded-for", b"1.2.3.4")], client=("203.0.113.5", 1))
        assert get_client_ip(scope, ["127.0.0.0/8"]) == "203.0.113.5"

    def test_trusted_proxy_yields_rightmost_untrusted(self):
        scope = _scope(headers=[(b"x-forwarded-for", b"9.9.9.9, 1.2.3.4, 127.0.0.2")], client=("127.0.0.1", 1))
        assert get_client_ip(scope, ["127.0.0.0/8"]) == "1.2.3.4"

    def test_no_client_is_unknown(self):
        assert get_client_ip({"headers": []}, []) == "unknown"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd /home/razinka/sfincs/sfincs_ui && /opt/micromamba/envs/shiny/bin/python -m pytest tests/test_session_auth_middleware.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'sfincs_ui.middleware'`

- [ ] **Step 3: Write client_ip.py**

`sfincs_ui/sfincs_ui/middleware/client_ip.py`:

```python
"""Client IP for audit rows: trust X-Forwarded-For only from configured proxies."""

from __future__ import annotations

import ipaddress


def get_client_ip(scope: dict, trusted_proxies: list[str]) -> str:
    """Rightmost-untrusted walk of X-Forwarded-For.

    nginx on this host appends the real client to X-Forwarded-For and connects
    from 127.0.0.1. Walking from the right, skip every address inside a
    trusted network and return the first one that is not; if all are trusted,
    return the leftmost. An untrusted peer's header is attacker-controlled and
    is ignored in favour of the socket peer.
    """
    client = scope.get("client")
    peer = client[0] if client else "unknown"
    if not trusted_proxies:
        return peer
    try:
        networks = [ipaddress.ip_network(c, strict=False) for c in trusted_proxies]
        peer_ip = ipaddress.ip_address(peer)
    except ValueError:
        return peer
    if not any(peer_ip in n for n in networks):
        return peer
    forwarded = b""
    for name, value in scope.get("headers", []):
        if name == b"x-forwarded-for":
            forwarded = value
            break
    hops = [h.strip() for h in forwarded.decode("latin-1").split(",") if h.strip()]
    if not hops:
        return peer
    for hop in reversed(hops):
        try:
            if not any(ipaddress.ip_address(hop) in n for n in networks):
                return hop
        except ValueError:
            return hop
    return hops[0]
```

- [ ] **Step 4: Write session_auth.py**

`sfincs_ui/sfincs_ui/middleware/session_auth.py`:

```python
"""Cookie-session middleware for the SFINCS UI ASGI app.

Reads the ``sfincs_ui_session`` cookie, resolves it through AuthService and
publishes the user (or None) to the request through a contextvar. Unlike the
SHYFEM UI original this never redirects: anonymous visitors reach every page
with ``user=None`` and the pages decide what they may see (spec section 5).
The middleware owns /login, /logout and /api/whoami; the last one also mints
the websocket token that bridges the HTTP identity into the Shiny session.
"""

from __future__ import annotations

import contextvars
import json
import logging
import secrets
import urllib.parse
from html import escape

from sfincs_ui.middleware.client_ip import get_client_ip

logger = logging.getLogger(__name__)

SESSION_COOKIE = "sfincs_ui_session"
CSRF_COOKIE = "sfincs_ui_csrf"
_MAX_FORM_BODY = 16 * 1024

_user_var: contextvars.ContextVar[dict | None] = contextvars.ContextVar("sfincs_ui_user", default=None)


def get_current_user() -> dict | None:
    """The user resolved for the current ASGI scope, or None."""
    return _user_var.get()


def _parse_cookie(raw: bytes) -> dict[str, str]:
    out: dict[str, str] = {}
    for part in raw.decode("latin-1").split(";"):
        part = part.strip()
        if not part:
            continue
        name, _, value = part.partition("=")
        out[name.strip()] = value.strip()
    return out


def _cookie_header(scope) -> dict[str, str]:
    for name, value in scope.get("headers", []):
        if name == b"cookie":
            return _parse_cookie(value)
    return {}


def _strip_root(path: str, root_path: str) -> str:
    """Path relative to the mount.

    uvicorn 0.49 (this host) puts ``--root-path`` in front of ``scope["path"]``
    (measured 2026-10-01: a request for /login with --root-path /sfincs-ui
    arrives as path=/sfincs-ui/login, root_path=/sfincs-ui). Older servers and
    test transports deliver /login. Accept both.
    """
    if root_path and (path == root_path or path.startswith(root_path + "/")):
        return path[len(root_path):] or "/"
    return path


_LOGIN_HTML = """<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Sign in - SFINCS UI</title>
<style>
 body{{font-family:system-ui,sans-serif;background:#0b3d5b;color:#fff;display:flex;min-height:100vh;align-items:center;justify-content:center;margin:0}}
 .card{{background:rgba(255,255,255,.1);border:1px solid rgba(255,255,255,.25);border-radius:12px;padding:32px;width:min(380px,92vw)}}
 h1{{font-size:1.4rem;margin:0 0 4px}} p{{margin:0 0 20px;opacity:.8;font-size:.9rem}}
 label{{display:block;font-size:.85rem;margin:12px 0 4px}} input{{width:100%;padding:9px;border-radius:6px;border:1px solid rgba(255,255,255,.3);background:rgba(255,255,255,.12);color:#fff;box-sizing:border-box}}
 button{{margin-top:18px;width:100%;padding:10px;border:0;border-radius:6px;background:#2d9cba;color:#fff;font-weight:600;cursor:pointer}}
 .err{{background:rgba(220,53,69,.25);border:1px solid rgba(220,53,69,.6);padding:8px 10px;border-radius:6px;font-size:.85rem;margin-bottom:8px}}
 a{{color:#cfe9f3}}
</style></head><body><div class="card">
<h1>SFINCS UI</h1><p>Build, run and inspect Curonian Lagoon flood models.</p>
{error}
<form method="post" action="{login_action}">
<input type="hidden" name="csrf_token" value="{csrf_token}">
<label for="username">Username</label><input id="username" name="username" type="text" required autofocus autocomplete="username">
<label for="password">Password</label><input id="password" name="password" type="password" required autocomplete="current-password">
<button type="submit">Sign in</button>
</form>
<p style="margin-top:16px"><a href="{home}">Back to the public pages</a></p>
</div></body></html>
"""

_LOGOUT_HTML = """<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"><title>Log out - SFINCS UI</title></head>
<body style="font-family:system-ui,sans-serif;padding:2rem">
<p>Log out of SFINCS UI?</p>
<form method="post" action="{logout_action}"><button type="submit">Log out</button></form>
<p><a href="{home}">Cancel</a></p>
</body></html>
"""


class SessionAuthMiddleware:
    def __init__(
        self,
        app,
        auth_service,
        audit_service=None,
        root_path: str = "",
        session_ttl_hours: int = 24,
        use_secure_cookies: bool = True,
        trusted_proxies: list[str] | None = None,
    ):
        self.app = app
        self.auth_service = auth_service
        self.audit_service = audit_service
        self.root_path = root_path.rstrip("/")
        self.session_ttl_hours = session_ttl_hours
        self.use_secure_cookies = use_secure_cookies
        self.trusted_proxies = trusted_proxies or []

    async def __call__(self, scope, receive, send):
        if scope["type"] not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return

        root_path = scope.get("root_path", "") or self.root_path
        session_token = _cookie_header(scope).get(SESSION_COOKIE)

        if scope["type"] == "http":
            path, method = _strip_root(scope.get("path", "/"), root_path), scope.get("method", "GET")
            if path == "/login" and method == "GET":
                await self._serve_login(send, root_path)
                return
            if path == "/login" and method == "POST":
                await self._handle_login(scope, receive, send, root_path)
                return
            if path == "/logout" and method == "GET":
                await self._serve_html(send, _LOGOUT_HTML.format(logout_action=f"{root_path}/logout", home=f"{root_path}/"))
                return
            if path == "/logout" and method == "POST":
                await self._handle_logout(scope, session_token, send, root_path)
                return
            if path == "/api/whoami" and method == "GET":
                await self._handle_whoami(session_token, send)
                return

        user = self.auth_service.validate_session(session_token) if session_token else None
        token = _user_var.set(user)
        try:
            await self.app(scope, receive, send)
        finally:
            _user_var.reset(token)

    # -- helpers ---------------------------------------------------------

    def _audit(self, username, action, ip_address=None, user_id=None):
        if self.audit_service is None:
            return
        try:
            self.audit_service.log(username=username, action=action, ip_address=ip_address, user_id=user_id)
        except Exception:
            logger.exception("audit write failed")

    def _cookie(self, name: str, value: str, root_path: str, max_age: int) -> bytes:
        parts = [f"{name}={value}", f"Path={root_path or '/'}", "HttpOnly", "SameSite=Lax", f"Max-Age={max_age}"]
        if self.use_secure_cookies:
            parts.append("Secure")
        return "; ".join(parts).encode()

    @staticmethod
    async def _serve_html(send, html: str, status: int = 200, extra_headers=()):
        body = html.encode()
        await send({
            "type": "http.response.start",
            "status": status,
            "headers": [(b"content-type", b"text/html; charset=utf-8"), (b"content-length", str(len(body)).encode()), *extra_headers],
        })
        await send({"type": "http.response.body", "body": body})

    @staticmethod
    async def _redirect(send, location: str, extra_headers=()):
        await send({"type": "http.response.start", "status": 302, "headers": [(b"location", location.encode()), *extra_headers]})
        await send({"type": "http.response.body", "body": b""})

    @staticmethod
    async def _json(send, obj: dict):
        body = json.dumps(obj).encode()
        await send({
            "type": "http.response.start",
            "status": 200,
            "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode())],
        })
        await send({"type": "http.response.body", "body": body})

    async def _serve_login(self, send, root_path: str, error: str = ""):
        csrf = secrets.token_urlsafe(32)
        html = _LOGIN_HTML.format(
            error=f'<div class="err" role="alert">{escape(error)}</div>' if error else "",
            login_action=f"{root_path}/login",
            csrf_token=csrf,
            home=f"{root_path}/",
        )
        await self._serve_html(send, html, extra_headers=[(b"set-cookie", self._cookie(CSRF_COOKIE, csrf, root_path, 600))])

    async def _read_form(self, receive) -> dict[str, str]:
        body = b""
        while True:
            message = await receive()
            body += message.get("body", b"")
            if len(body) > _MAX_FORM_BODY:
                return {}
            if not message.get("more_body", False):
                break
        parsed = urllib.parse.parse_qs(body.decode("utf-8", errors="replace"))
        return {k: v[0] for k, v in parsed.items()}

    async def _handle_login(self, scope, receive, send, root_path: str):
        form = await self._read_form(receive)
        ip = get_client_ip(scope, self.trusted_proxies)
        form_csrf = form.get("csrf_token", "")
        cookie_csrf = _cookie_header(scope).get(CSRF_COOKIE, "")
        if not form_csrf or not cookie_csrf or not secrets.compare_digest(form_csrf, cookie_csrf):
            await self._serve_login(send, root_path, error="Invalid request. Please try again.")
            return
        username, password = form.get("username", ""), form.get("password", "")
        user = self.auth_service.authenticate(username, password)
        if user is None:
            self._audit(username or "<empty>", "login_failed", ip_address=ip)
            await self._serve_login(send, root_path, error="Invalid username or password.")
            return
        self._audit(user["username"], "login_success", ip_address=ip, user_id=user["id"])
        token = self.auth_service.create_session(user["id"], ttl_hours=self.session_ttl_hours, ip_address=ip)
        try:
            self.auth_service.cleanup_expired_sessions()
        except Exception:
            logger.exception("expired-session cleanup failed")
        cookie = self._cookie(SESSION_COOKIE, token, root_path, self.session_ttl_hours * 3600)
        await self._redirect(send, f"{root_path}/", extra_headers=[(b"set-cookie", cookie)])

    async def _handle_logout(self, scope, session_token, send, root_path: str):
        user = self.auth_service.validate_session(session_token) if session_token else None
        if session_token:
            self.auth_service.delete_session(session_token)
        self._audit(
            (user or {}).get("username", "unknown"), "logout",
            ip_address=get_client_ip(scope, self.trusted_proxies), user_id=(user or {}).get("id"),
        )
        cookie = self._cookie(SESSION_COOKIE, "", root_path, 0)
        await self._redirect(send, f"{root_path}/", extra_headers=[(b"set-cookie", cookie)])

    async def _handle_whoami(self, session_token, send):
        user = self.auth_service.validate_session(session_token) if session_token else None
        if user is None:
            await self._json(send, {"username": None, "display_name": None, "role": None, "ws_token": None})
            return
        ws_token = self.auth_service.create_ws_token(user["id"], session_token)
        await self._json(send, {
            "username": user["username"], "display_name": user.get("display_name"),
            "role": user["role"], "ws_token": ws_token,
        })
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `cd /home/razinka/sfincs/sfincs_ui && /opt/micromamba/envs/shiny/bin/python -m pytest tests/test_session_auth_middleware.py -q`
Expected: 22 passed

- [ ] **Step 6: Commit**

```bash
cd /home/razinka/sfincs
git add sfincs_ui/sfincs_ui/middleware sfincs_ui/tests/test_session_auth_middleware.py
git commit -m "sfincs_ui: session middleware with anonymous pass-through and ws-token bridge

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 6: Environment check (startup banner and deploy preflight)

**Files:**
- Create: `sfincs_ui/sfincs_ui/services/environment.py`
- Test: `sfincs_ui/tests/test_environment.py`

**Interfaces:**
- Consumes: `Config` (Task 1).
- Produces: `EnvironmentReport(problems: list[str], checked_at: datetime)` with `.ok`; `check_environment(config, *, deep=False, runner=subprocess.run) -> EnvironmentReport`. `runner` has `subprocess.run`'s signature and is injected by tests. Shallow checks (startup): binary exists, is executable and prints the SFINCS banner within 15 s; the model-python prefix imports `hydromt_sfincs` and `rasterio` within 120 s; `curonian_dir` holds `build_model.py` and `validate.py`; the workspace exists and is writable. Deep checks (deploy preflight, `python -m sfincs_ui preflight`): additionally the model env opens `inputs/lagoon_bathy_50m.tif` with rasterio; the gauge database named by `SFINCS_CURONIAN_DB` (default `/home/razinka/curonian/curonian_db.gpkg`) opens read-only with `sqlite3` from the UI process (not through `common.read_table`: `curonian/common.py` still resolves the path under `Path.home()`, which is `/home/shiny` for the service user; the env-var rewrite is milestone 3); `inputs/<event>/era5_grid.nc` and `inputs/<event>/gtsm/` are readable for `xaver_2013` and `april_2013`; the three absolute catalogue paths listed in `curonian/data_catalog.yml` under `path:` are readable.

Behaviour recorded on 2026-10-01: running `sfincs-linux/bin/sfincs` in an empty directory prints the `------------ Welcome to SFINCS ------------` banner to stdout, writes `sfincs.log` into the cwd and exits with status 2 (`STOP 2`). The check therefore runs the binary in a fresh temporary directory, requires the banner in stdout, and ignores the exit code.

- [ ] **Step 1: Write the failing tests**

`sfincs_ui/tests/test_environment.py`:

```python
import os
import stat
import subprocess
from pathlib import Path

import pytest

from sfincs_ui.config import Config
from sfincs_ui.services.environment import check_environment

BANNER = b"------------ Welcome to SFINCS ------------\n"


def _fake_runner(responses):
    """Return a subprocess.run stand-in keyed on argv[0] / argv[-1]."""
    calls = []

    def run(argv, **kwargs):
        calls.append((argv, kwargs))
        for key, outcome in responses.items():
            if key in argv or key == argv[0]:
                if isinstance(outcome, Exception):
                    raise outcome
                return subprocess.CompletedProcess(argv, outcome[0], stdout=outcome[1], stderr=b"")
        return subprocess.CompletedProcess(argv, 0, stdout=b"", stderr=b"")

    run.calls = calls
    return run


@pytest.fixture
def layout(tmp_path):
    ws = tmp_path / "ws"; ws.mkdir()
    cur = tmp_path / "curonian"; cur.mkdir()
    (cur / "build_model.py").write_text("")
    (cur / "validate.py").write_text("")
    binary = tmp_path / "sfincs"
    binary.write_text("#!/bin/sh\necho x\n")
    binary.chmod(binary.stat().st_mode | stat.S_IEXEC)
    return Config(workspace=ws, curonian_dir=cur, sfincs_bin=binary, model_python="fake-python")


def test_all_good_shallow(layout):
    runner = _fake_runner({str(layout.sfincs_bin): (2, BANNER), "fake-python": (0, b"")})
    report = check_environment(layout, runner=runner)
    assert report.ok and report.problems == []
    bin_call = next(c for c in runner.calls if c[0][0] == str(layout.sfincs_bin))
    assert Path(bin_call[1]["cwd"]).exists() is False  # temp dir removed afterwards
    assert bin_call[1]["timeout"] == 15


def test_missing_binary_reported(layout):
    """Review Focus 4."""
    cfg = layout.model_copy(update={"sfincs_bin": layout.workspace / "nope"})
    report = check_environment(cfg, runner=_fake_runner({"fake-python": (0, b"")}))
    assert not report.ok
    assert any("nope" in p and "binary" in p.lower() for p in report.problems)


def test_binary_without_banner_reported(layout):
    runner = _fake_runner({str(layout.sfincs_bin): (0, b"something else"), "fake-python": (0, b"")})
    report = check_environment(layout, runner=runner)
    assert any("banner" in p.lower() for p in report.problems)


def test_model_python_timeout_reported(layout):
    """Review Focus 4: a dead micromamba must not hang startup."""
    runner = _fake_runner({
        str(layout.sfincs_bin): (2, BANNER),
        "fake-python": subprocess.TimeoutExpired(cmd="fake-python", timeout=120),
    })
    report = check_environment(layout, runner=runner)
    assert any("model environment" in p.lower() and "timed out" in p.lower() for p in report.problems)


def test_model_python_import_failure_reported(layout):
    runner = _fake_runner({str(layout.sfincs_bin): (2, BANNER), "fake-python": (1, b"")})
    report = check_environment(layout, runner=runner)
    assert any("hydromt_sfincs" in p for p in report.problems)


def test_model_python_not_found_reported(layout):
    runner = _fake_runner({str(layout.sfincs_bin): (2, BANNER), "fake-python": FileNotFoundError("fake-python")})
    report = check_environment(layout, runner=runner)
    assert any("fake-python" in p for p in report.problems)


def test_curonian_dir_without_scripts_reported(layout, tmp_path):
    cfg = layout.model_copy(update={"curonian_dir": tmp_path / "empty"})
    (tmp_path / "empty").mkdir()
    report = check_environment(cfg, runner=_fake_runner({str(layout.sfincs_bin): (2, BANNER)}))
    assert any("build_model.py" in p for p in report.problems)


def test_unwritable_workspace_reported(layout):
    if os.geteuid() == 0:
        pytest.skip("root ignores permission bits")
    layout.workspace.chmod(0o500)
    try:
        report = check_environment(layout, runner=_fake_runner({str(layout.sfincs_bin): (2, BANNER)}))
    finally:
        layout.workspace.chmod(0o700)
    assert any("workspace" in p.lower() and "writable" in p.lower() for p in report.problems)


def test_deep_checks_inputs_and_catalogue(layout, tmp_path, monkeypatch):
    cur = layout.curonian_dir
    (cur / "inputs" / "xaver_2013" / "gtsm").mkdir(parents=True)
    (cur / "inputs" / "xaver_2013" / "era5_grid.nc").write_bytes(b"")
    (cur / "inputs" / "april_2013").mkdir()
    (cur / "inputs" / "lagoon_bathy_50m.tif").write_bytes(b"")
    (cur / "data_catalog.yml").write_text("a:\n  path: /nonexistent/one.tif\nb:\n  path: relative/ok.nc\n")
    monkeypatch.setenv("SFINCS_CURONIAN_DB", str(tmp_path / "missing.gpkg"))
    runner = _fake_runner({str(layout.sfincs_bin): (2, BANNER), "fake-python": (0, b"")})
    report = check_environment(layout, deep=True, runner=runner)
    joined = "\n".join(report.problems)
    assert "april_2013/era5_grid.nc" in joined and "april_2013/gtsm" in joined
    assert "/nonexistent/one.tif" in joined
    assert "relative/ok.nc" not in joined
    assert "missing.gpkg" in joined and "gauge database" in joined.lower()
    # deep mode asked the model env to open the GeoTIFF
    snippets = [c[0][-1] for c in runner.calls if c[0][0] == "fake-python"]
    assert any("rasterio.open" in s for s in snippets)


def test_deep_gauge_database_opens_read_only(layout, tmp_path, monkeypatch):
    import sqlite3

    db = tmp_path / "gauges.gpkg"
    sqlite3.connect(db).close()
    monkeypatch.setenv("SFINCS_CURONIAN_DB", str(db))
    (layout.curonian_dir / "inputs").mkdir()
    runner = _fake_runner({str(layout.sfincs_bin): (2, BANNER), "fake-python": (0, b"")})
    report = check_environment(layout, deep=True, runner=runner)
    assert not any("gauge database" in p.lower() for p in report.problems)


def test_real_binary_prints_banner_if_present():
    """Runs the actual solver when this checkout has it; skipped elsewhere."""
    cfg = Config(workspace=Path("/tmp"))
    if not cfg.sfincs_bin.exists():
        pytest.skip("no sfincs binary in this checkout")
    runner_calls = []

    def runner(argv, **kw):
        runner_calls.append(argv)
        if argv[0] == str(cfg.sfincs_bin):
            return subprocess.run(argv, **kw)
        return subprocess.CompletedProcess(argv, 0, stdout=b"", stderr=b"")

    report = check_environment(cfg.model_copy(update={"workspace": cfg.repo_root / "sfincs_ui"}), runner=runner)
    assert not any("banner" in p.lower() for p in report.problems)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd /home/razinka/sfincs/sfincs_ui && /opt/micromamba/envs/shiny/bin/python -m pytest tests/test_environment.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'sfincs_ui.services.environment'`

- [ ] **Step 3: Write the service**

`sfincs_ui/sfincs_ui/services/environment.py`:

```python
"""Is this host able to build and run a SFINCS model?

Shallow checks run once at startup and feed the banner shown on every page
when something is missing (spec section 5, Errors). Deep checks are the deploy
preflight the spec lists under "Preflight", run as user shiny by
``python -m sfincs_ui preflight``. ``runner`` is injectable so tests never
shell out.
"""

from __future__ import annotations

import os
import re
import sqlite3
import subprocess
import tempfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from sfincs_ui.config import Config
from sfincs_ui.timeutil import utcnow

BINARY_TIMEOUT_S = 15
MODEL_ENV_TIMEOUT_S = 120
BANNER = "Welcome to SFINCS"
EVENTS = ("xaver_2013", "april_2013")

_IMPORT_SNIPPET = "import hydromt_sfincs, rasterio"
_GEOTIFF_SNIPPET = "import rasterio; rasterio.open({path!r}).close()"
DEFAULT_GAUGE_DB = "/home/razinka/curonian/curonian_db.gpkg"


@dataclass
class EnvironmentReport:
    problems: list[str] = field(default_factory=list)
    checked_at: datetime = field(default_factory=utcnow)

    @property
    def ok(self) -> bool:
        return not self.problems


def _run_model_python(config: Config, snippet: str, runner, label: str, problems: list[str]) -> None:
    argv = [*config.model_python_argv, "-c", snippet]
    try:
        proc = runner(argv, cwd=str(config.curonian_dir), capture_output=True, timeout=MODEL_ENV_TIMEOUT_S)
    except subprocess.TimeoutExpired:
        problems.append(f"Model environment check ({label}) timed out after {MODEL_ENV_TIMEOUT_S} s: {config.model_python}")
        return
    except (OSError, FileNotFoundError) as exc:
        problems.append(f"Model environment command cannot start: {config.model_python} ({exc})")
        return
    if proc.returncode != 0:
        tail = (proc.stderr or b"").decode(errors="replace").strip().splitlines()[-1:] or [""]
        problems.append(f"Model environment cannot {label}: exit {proc.returncode} {tail[0]}".rstrip())


def _check_binary(config: Config, runner, problems: list[str]) -> None:
    binary = config.sfincs_bin
    if not binary.exists():
        problems.append(f"SFINCS binary not found at {binary}")
        return
    if not os.access(binary, os.X_OK):
        problems.append(f"SFINCS binary is not executable: {binary}")
        return
    with tempfile.TemporaryDirectory(prefix="sfincs-ui-bincheck-") as tmp:
        try:
            proc = runner([str(binary)], cwd=tmp, capture_output=True, timeout=BINARY_TIMEOUT_S)
        except subprocess.TimeoutExpired:
            problems.append(f"SFINCS binary did not exit within {BINARY_TIMEOUT_S} s in an empty directory: {binary}")
            return
        except OSError as exc:
            problems.append(f"SFINCS binary failed to start: {binary} ({exc})")
            return
    if BANNER not in (proc.stdout or b"").decode(errors="replace"):
        problems.append(f"SFINCS binary ran but printed no SFINCS banner: {binary}")


def _check_dirs(config: Config, problems: list[str]) -> None:
    for script in ("build_model.py", "validate.py"):
        if not (config.curonian_dir / script).is_file():
            problems.append(f"Curonian model directory lacks {script}: {config.curonian_dir}")
    ws = config.workspace
    if not ws.is_dir():
        problems.append(f"Workspace does not exist: {ws}")
    elif not os.access(ws, os.W_OK):
        problems.append(f"Workspace is not writable by this user: {ws}")


def _check_deep(config: Config, runner, problems: list[str]) -> None:
    inputs = config.curonian_dir / "inputs"
    tif = inputs / "lagoon_bathy_50m.tif"
    for rel in ["lagoon_bathy_50m.tif", *(f"{e}/era5_grid.nc" for e in EVENTS), *(f"{e}/gtsm" for e in EVENTS)]:
        if not os.access(inputs / rel, os.R_OK):
            problems.append(f"Input not readable: inputs/{rel}")
    catalogue = config.curonian_dir / "data_catalog.yml"
    if catalogue.is_file():
        for m in re.finditer(r"^\s*path:\s*(/\S+)", catalogue.read_text(), re.M):
            if not os.access(m.group(1), os.R_OK):
                problems.append(f"Catalogue path not readable: {m.group(1)}")
    if tif.is_file():
        _run_model_python(config, _GEOTIFF_SNIPPET.format(path=str(tif)), runner, "open a GeoTIFF with rasterio", problems)
    # The gauge database is read by validate.py and export_map_cache (milestone
    # 3 routes them through SFINCS_CURONIAN_DB). Open it read-only here so a
    # path the service user cannot read is caught at deploy time.
    gauge_db = os.environ.get("SFINCS_CURONIAN_DB", DEFAULT_GAUGE_DB)
    try:
        sqlite3.connect(f"file:{gauge_db}?mode=ro", uri=True).close()
    except sqlite3.Error as exc:
        problems.append(f"Gauge database cannot be opened read-only: {gauge_db} ({exc})")


def check_environment(config: Config, *, deep: bool = False, runner=subprocess.run) -> EnvironmentReport:
    problems: list[str] = []
    _check_binary(config, runner, problems)
    _run_model_python(config, _IMPORT_SNIPPET, runner, "import hydromt_sfincs and rasterio", problems)
    _check_dirs(config, problems)
    if deep:
        _check_deep(config, runner, problems)
    return EnvironmentReport(problems=problems)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd /home/razinka/sfincs/sfincs_ui && /opt/micromamba/envs/shiny/bin/python -m pytest tests/test_environment.py -q`
Expected: 11 passed (the last one runs the real binary, about a second)

- [ ] **Step 5: Commit**

```bash
cd /home/razinka/sfincs
git add sfincs_ui/sfincs_ui/services/environment.py sfincs_ui/tests/test_environment.py
git commit -m "sfincs_ui: environment check for the startup banner and the deploy preflight

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 7: Command-line entry point

**Files:**
- Create: `sfincs_ui/sfincs_ui/__main__.py`
- Create: `sfincs_ui/sfincs_ui/asgi.py`
- Test: `sfincs_ui/tests/test_cli.py`

**Interfaces:**
- Consumes: `init_db` (Task 2), `AuthService` (Task 3), `check_environment` (Task 6), `create_app` (Task 8; `asgi.py` imports it lazily so this task can land first).
- Produces: `python -m sfincs_ui migrate | create-admin [--username U] [--email E] | preflight | serve [--host H] [--port P] [--reload]`; `main(argv=None) -> int`. `create-admin` reads the password from `SFINCS_UI_ADMIN_PASSWORD` when set, else prompts twice with `getpass`. `sfincs_ui.asgi:app` is the uvicorn target.

- [ ] **Step 1: Write the failing tests**

`sfincs_ui/tests/test_cli.py`:

```python
import pytest

from sfincs_ui import __main__ as cli
from sfincs_ui.services.auth_service import AuthService
from sfincs_ui.services.environment import EnvironmentReport


def test_migrate_creates_schema(db, capsys):
    assert cli.main(["migrate"]) == 0
    assert "0001_initial" in capsys.readouterr().out


def test_create_admin_from_env(db, monkeypatch, capsys):
    monkeypatch.setenv("SFINCS_UI_ADMIN_PASSWORD", "pw12345678")
    assert cli.main(["create-admin", "--username", "root", "--email", "r@example.org"]) == 0
    assert "created admin 'root'" in capsys.readouterr().out
    assert AuthService(session_factory=db).authenticate("root", "pw12345678")["role"] == "admin"


def test_create_admin_twice_is_idempotent(db, monkeypatch, capsys):
    """Review Focus 5: a re-run of the deploy script must not reset the password."""
    monkeypatch.setenv("SFINCS_UI_ADMIN_PASSWORD", "first-password")
    cli.main(["create-admin", "--username", "root"])
    monkeypatch.setenv("SFINCS_UI_ADMIN_PASSWORD", "second-password")
    assert cli.main(["create-admin", "--username", "root"]) == 0
    assert "already exists" in capsys.readouterr().out
    auth = AuthService(session_factory=db)
    assert auth.authenticate("root", "first-password") is not None
    assert auth.authenticate("root", "second-password") is None


def test_create_admin_prompts_when_env_absent(db, monkeypatch):
    monkeypatch.delenv("SFINCS_UI_ADMIN_PASSWORD", raising=False)
    answers = iter(["pw12345678", "pw12345678"])
    monkeypatch.setattr(cli.getpass, "getpass", lambda prompt="": next(answers))
    assert cli.main(["create-admin", "--username", "root"]) == 0


def test_create_admin_rejects_short_or_mismatched_password(db, monkeypatch, capsys):
    monkeypatch.setenv("SFINCS_UI_ADMIN_PASSWORD", "short")
    assert cli.main(["create-admin", "--username", "root"]) == 2
    assert "at least 8" in capsys.readouterr().err
    monkeypatch.delenv("SFINCS_UI_ADMIN_PASSWORD")
    answers = iter(["pw12345678", "different1"])
    monkeypatch.setattr(cli.getpass, "getpass", lambda prompt="": next(answers))
    assert cli.main(["create-admin", "--username", "root"]) == 2


def test_preflight_exit_codes(db, monkeypatch, capsys):
    monkeypatch.setattr(cli, "check_environment", lambda cfg, deep: EnvironmentReport(problems=[]))
    assert cli.main(["preflight"]) == 0
    assert "preflight OK" in capsys.readouterr().out
    monkeypatch.setattr(cli, "check_environment", lambda cfg, deep: EnvironmentReport(problems=["SFINCS binary not found at /x"]))
    assert cli.main(["preflight"]) == 1
    assert "/x" in capsys.readouterr().err


def test_preflight_uses_deep_checks(db, monkeypatch):
    seen = {}

    def fake(cfg, deep):
        seen["deep"] = deep
        return EnvironmentReport()

    monkeypatch.setattr(cli, "check_environment", fake)
    cli.main(["preflight"])
    assert seen["deep"] is True


def test_serve_passes_config_to_uvicorn(db, monkeypatch, tmp_path):
    from sfincs_ui import config

    config.set_config(config.Config(workspace=tmp_path, port=8899, url_prefix="/sfincs-ui"))
    seen = {}
    monkeypatch.setattr(cli.uvicorn, "run", lambda target, **kw: seen.update(target=target, **kw))
    assert cli.main(["serve"]) == 0
    assert seen["target"] == "sfincs_ui.asgi:app"
    assert seen["port"] == 8899 and seen["host"] == "127.0.0.1" and seen["root_path"] == "/sfincs-ui"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd /home/razinka/sfincs/sfincs_ui && /opt/micromamba/envs/shiny/bin/python -m pytest tests/test_cli.py -q`
Expected: FAIL with `ImportError: cannot import name '__main__'` or `AttributeError` on `cli.main`

- [ ] **Step 3: Write the CLI and the ASGI entry**

`sfincs_ui/sfincs_ui/asgi.py`:

```python
"""uvicorn target: ``uvicorn sfincs_ui.asgi:app``."""

from sfincs_ui.app import create_app

app = create_app()
```

`sfincs_ui/sfincs_ui/__main__.py`:

```python
"""``python -m sfincs_ui``: migrate, create-admin, preflight, serve."""

from __future__ import annotations

import argparse
import getpass
import logging
import os
import sys

import uvicorn

from sfincs_ui.config import get_config
from sfincs_ui.services.environment import check_environment

MIN_PASSWORD_LEN = 8


def _cmd_migrate(_args) -> int:
    from sqlalchemy import text

    from sfincs_ui.db import base

    base.init_db()
    with base.get_engine().connect() as conn:
        version = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
    print(f"database at {get_config().database_url_resolved} is at revision {version}")
    return 0


def _read_password() -> str | None:
    env = os.environ.get("SFINCS_UI_ADMIN_PASSWORD")
    if env is not None:
        if len(env) < MIN_PASSWORD_LEN:
            print(f"error: password must be at least {MIN_PASSWORD_LEN} characters", file=sys.stderr)
            return None
        return env
    first = getpass.getpass("Admin password: ")
    second = getpass.getpass("Repeat password: ")
    if first != second:
        print("error: passwords do not match", file=sys.stderr)
        return None
    if len(first) < MIN_PASSWORD_LEN:
        print(f"error: password must be at least {MIN_PASSWORD_LEN} characters", file=sys.stderr)
        return None
    return first


def _cmd_create_admin(args) -> int:
    from sfincs_ui.db import base
    from sfincs_ui.services.auth_service import AuthService

    base.init_db()
    auth = AuthService()
    existing = [u for u in auth.list_users() if u["role"] == "admin"]
    if existing:
        print(f"admin '{existing[0]['username']}' already exists; nothing changed")
        return 0
    password = _read_password()
    if password is None:
        return 2
    user, created = auth.ensure_admin(args.username, password, email=args.email)
    print(f"created admin '{user['username']}'" if created else f"admin '{user['username']}' already exists")
    return 0


def _cmd_preflight(_args) -> int:
    report = check_environment(get_config(), deep=True)
    if report.ok:
        print("preflight OK")
        return 0
    for p in report.problems:
        print(f"preflight: {p}", file=sys.stderr)
    return 1


def _cmd_serve(args) -> int:
    cfg = get_config()
    uvicorn.run(
        "sfincs_ui.asgi:app",
        host=args.host,
        port=args.port or cfg.port,
        root_path=cfg.url_prefix,
        reload=args.reload,
        log_level="info",
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    parser = argparse.ArgumentParser(prog="python -m sfincs_ui", description="SFINCS UI maintenance commands")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("migrate", help="create or upgrade the database schema").set_defaults(func=_cmd_migrate)
    p = sub.add_parser("create-admin", help="create the first admin account (no-op when one exists)")
    p.add_argument("--username", default="admin")
    p.add_argument("--email", default=None)
    p.set_defaults(func=_cmd_create_admin)
    sub.add_parser("preflight", help="verify binary, model env, inputs and workspace").set_defaults(func=_cmd_preflight)
    p = sub.add_parser("serve", help="run the app with uvicorn")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=None)
    p.add_argument("--reload", action="store_true")
    p.set_defaults(func=_cmd_serve)
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd /home/razinka/sfincs/sfincs_ui && /opt/micromamba/envs/shiny/bin/python -m pytest tests/test_cli.py -q`
Expected: 8 passed (`asgi.py` is not imported by these tests; `create_app` arrives in Task 8)

- [ ] **Step 5: Commit**

```bash
cd /home/razinka/sfincs
git add sfincs_ui/sfincs_ui/__main__.py sfincs_ui/sfincs_ui/asgi.py sfincs_ui/tests/test_cli.py
git commit -m "sfincs_ui: CLI with migrate, create-admin, preflight and serve

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 8: Application shell, Home page and Admin page

**Files:**
- Create: `sfincs_ui/sfincs_ui/pages/__init__.py` (empty)
- Create: `sfincs_ui/sfincs_ui/pages/home.py`
- Create: `sfincs_ui/sfincs_ui/pages/admin.py`
- Create: `sfincs_ui/sfincs_ui/app.py`
- Create: `sfincs_ui/sfincs_ui/www/sfincs_ui.css`
- Test: `sfincs_ui/tests/test_pages.py`

**Interfaces:**
- Consumes: `Config`, `init_db`, `AuthService`, `AuditService`, `SettingsService`, `check_environment`, `SessionAuthMiddleware`, `get_current_user`, `resolve_ws_user`.
- Produces: `create_app(config=None, *, environment: EnvironmentReport | None = None)` returning the wrapped ASGI app (tests pass a ready `EnvironmentReport` so startup never shells out); `build_ui(config, report) -> Tag`; `home.home_ui(id)`, `home.home_server(id, current_user)`; `admin.admin_ui(id)`, `admin.admin_server(id, auth_service, audit_service, settings_service, current_user)`; pure helpers in `admin.py`: `_validate_create_user_form(username, password, role, email) -> list[str]`, `_build_user_table_data(users) -> list[dict]`, `_check_admin_access(user) -> bool`, `_role_badge(role) -> str`, `_active_badge(flag) -> str`. `current_user` is a zero-arg callable returning the server-validated user dict or `None`; every mutation in a page server calls it, never a client-pushed signal.

Shell decisions: `ui.page_navbar` with `id="main_nav"`, panels Home and Admin, `ui.nav_spacer()`, `ui.nav_control(ui.input_dark_mode(id="dark_mode"))` for the theme toggle (Shiny's own, persists in localStorage), and `ui.nav_control(ui.output_ui("user_menu"))` for "Log in" or "username · Log out". The environment banner is the navbar `header`. For a visitor who is not an admin the server calls `ui.remove_nav_panel("main_nav", "Admin")` once the identity resolves; the Admin page body also refuses to render for non-admins, so removal is cosmetic and the body is the gate. A 12-line script fetches `api/whoami` (relative URL, so it works under the prefix) and pushes `ws_token` into `input._wsauth`.

- [ ] **Step 1: Write the failing tests**

`sfincs_ui/tests/test_pages.py`:

```python
import httpx
import pytest

from sfincs_ui.config import Config
from sfincs_ui.pages import admin
from sfincs_ui.services.environment import EnvironmentReport


class TestAdminHelpers:
    def test_validate_create_user_form(self):
        assert admin._validate_create_user_form("alice", "pw12345678", "user", "a@b.org") == []
        errs = admin._validate_create_user_form("", "short", "boss", "not-an-email")
        assert any("Username" in e for e in errs)
        assert any("8 characters" in e for e in errs)
        assert any("Role" in e for e in errs)
        assert any("Email" in e for e in errs)
        assert admin._validate_create_user_form("alice", "pw12345678", "admin", "") == []  # email optional

    def test_build_user_table_data_fills_defaults(self):
        rows = admin._build_user_table_data([{"id": 1, "username": "a", "role": "user"}])
        assert rows[0] == {"id": 1, "username": "a", "display_name": "a", "email": "-", "role": "user", "is_active": True}

    def test_check_admin_access(self):
        assert admin._check_admin_access(None) is False
        assert admin._check_admin_access({"role": "user"}) is False
        assert admin._check_admin_access({"role": "admin"}) is True

    def test_badges(self):
        assert "bg-danger" in admin._role_badge("admin") and "bg-primary" in admin._role_badge("user")
        assert "Active" in admin._active_badge(True) and "Inactive" in admin._active_badge(False)


class TestRendering:
    def test_admin_ui_renders_three_tabs(self):
        html = str(admin.admin_ui("admin"))
        for label in ("Users", "Queue policy", "Audit log"):
            assert label in html
        for input_id in ("admin-create_user_btn", "admin-policy_save", "admin-log_refresh_btn"):
            assert input_id in html

    def test_build_ui_without_problems_has_no_banner(self, tmp_path):
        from sfincs_ui.app import build_ui

        html = str(build_ui(Config(workspace=tmp_path), EnvironmentReport()))
        assert "SFINCS UI" in html and "env-banner" not in html
        assert 'id="main_nav"' in html and "dark_mode" in html

    def test_banner_rendered_when_problems(self, tmp_path):
        """Review Focus 4."""
        from sfincs_ui.app import build_ui

        report = EnvironmentReport(problems=["SFINCS binary not found at /nope/sfincs"])
        html = str(build_ui(Config(workspace=tmp_path), report))
        assert "env-banner" in html and "/nope/sfincs" in html


@pytest.fixture
def app(db, tmp_path):
    from sfincs_ui import config
    from sfincs_ui.app import create_app

    cfg = config.Config(workspace=tmp_path, database_url=f"sqlite:///{tmp_path / 'test.db'}", url_prefix="")
    return create_app(cfg, environment=EnvironmentReport())


async def test_create_app_serves_home_anonymously(app):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="https://test") as c:
        r = await c.get("/")
        assert r.status_code == 200 and "SFINCS UI" in r.text
        r = await c.get("/api/whoami")
        assert r.json()["username"] is None
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd /home/razinka/sfincs/sfincs_ui && /opt/micromamba/envs/shiny/bin/python -m pytest tests/test_pages.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'sfincs_ui.pages'`

- [ ] **Step 3: Write the Home page**

`sfincs_ui/sfincs_ui/pages/home.py`:

```python
"""Home: what the tool does, how to get an account, where the public runs will appear."""

from __future__ import annotations

from shiny import module, render, ui

_ABOUT = ui.markdown(
    """
**SFINCS UI** lets a logged-in user create a SFINCS project from a template,
edit its settings, launch a simulation on this server, watch it run, and
inspect and compare the results. The first template is the Curonian Lagoon
model whose published hindcasts are in the read-only viewer at
[/sfincs/](/sfincs/).

Accounts are created by an administrator; there is no self-registration.
Visitors without an account can open runs their owners marked public and the
published baselines once the Results page ships (milestone 4).
"""
)


@module.ui
def home_ui() -> ui.Tag:
    return ui.div(
        ui.h2("SFINCS UI"),
        _ABOUT,
        ui.hr(),
        ui.h5("Public runs and baselines"),
        ui.p("None published yet.", class_="text-muted"),
        ui.output_ui("greeting"),
        class_="container py-3",
    )


@module.server
def home_server(input, output, session, current_user):
    @render.ui
    def greeting():
        user = current_user()
        if user is None:
            return ui.p("Log in to create projects and launch runs.", class_="text-muted")
        return ui.p(f"Signed in as {user['username']} ({user['role']}).", class_="text-muted")
```

- [ ] **Step 4: Write the Admin page**

`sfincs_ui/sfincs_ui/pages/admin.py`:

```python
"""Admin: users and roles, queue policy, audit log.

Authorization comes from ``current_user()``, the server-validated identity,
on every render and every mutation. Nothing here trusts a client-side signal.
"""

from __future__ import annotations

import logging
import re

from shiny import module, reactive, render, ui

from sfincs_ui.models.user import ROLE_ADMIN, ROLE_USER, ROLES, validate_username
from sfincs_ui.services.audit_service import AuditService
from sfincs_ui.services.auth_service import AuthService
from sfincs_ui.services.settings_service import POLICY_KEYS, SettingsService

logger = logging.getLogger(__name__)

_LOG_PAGE = 50


# -- pure helpers (tested without Shiny) -------------------------------------

def _validate_create_user_form(username: str, password: str, role: str, email: str | None = None) -> list[str]:
    errors: list[str] = []
    try:
        validate_username((username or "").strip())
    except ValueError as exc:
        errors.append(f"Username: {exc}")
    if not password:
        errors.append("Password is required")
    elif len(password) < 8:
        errors.append("Password must be at least 8 characters")
    if role not in ROLES:
        errors.append(f"Role must be one of: {', '.join(ROLES)}")
    if email and not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email.strip()):
        errors.append("Email address is not valid")
    return errors


def _build_user_table_data(users: list[dict]) -> list[dict]:
    return [
        {
            "id": u["id"],
            "username": u["username"],
            "display_name": u.get("display_name") or u["username"],
            "email": u.get("email") or "-",
            "role": u["role"],
            "is_active": u.get("is_active", True),
        }
        for u in users
    ]


def _check_admin_access(user: dict | None) -> bool:
    return bool(user) and user.get("role") == ROLE_ADMIN


def _role_badge(role: str) -> str:
    cls = "bg-danger" if role == ROLE_ADMIN else "bg-primary"
    return f'<span class="badge {cls}">{role}</span>'


def _active_badge(is_active: bool) -> str:
    return '<span class="badge bg-success">Active</span>' if is_active else '<span class="badge bg-secondary">Inactive</span>'


# -- UI ----------------------------------------------------------------------

@module.ui
def admin_ui() -> ui.Tag:
    users_tab = ui.row(
        ui.column(3, ui.div(ui.output_ui("user_summary"), ui.hr(),
                            ui.input_action_button("create_user_btn", "Create user", class_="btn-primary w-100"),
                            class_="card p-3")),
        ui.column(9, ui.div(ui.output_ui("user_table"), class_="card p-3")),
        class_="mt-3",
    )
    policy_tab = ui.div(
        ui.p("Values an administrator may set, each bounded by the server's SFINCS_UI_* ceiling.", class_="text-muted"),
        ui.output_ui("policy_form"),
        ui.input_action_button("policy_save", "Save policy", class_="btn-primary mt-2"),
        class_="card p-3 mt-3",
    )
    log_tab = ui.row(
        ui.column(3, ui.div(ui.h6("Filters"),
                            ui.input_select("log_user_filter", "User", choices={"": "All users"}),
                            ui.input_select("log_action_filter", "Action", choices={"": "All actions"}),
                            ui.input_action_button("log_refresh_btn", "Refresh", class_="btn-outline-secondary w-100 mt-2"),
                            ui.hr(), ui.output_ui("log_summary"), class_="card p-3")),
        ui.column(9, ui.div(ui.output_ui("log_table"),
                            ui.div(ui.input_action_button("log_prev_btn", "Previous", class_="btn-sm btn-outline-secondary me-2"),
                                   ui.output_ui("log_page_info"),
                                   ui.input_action_button("log_next_btn", "Next", class_="btn-sm btn-outline-secondary ms-2"),
                                   class_="d-flex align-items-center justify-content-center mt-3"),
                            class_="card p-3")),
        class_="mt-3",
    )
    return ui.div(
        ui.output_ui("gate"),
        ui.navset_tab(
            ui.nav_panel("Users", users_tab),
            ui.nav_panel("Queue policy", policy_tab),
            ui.nav_panel("Audit log", log_tab),
            id="admin_tabs",
        ),
        class_="container py-3",
    )


# -- server ------------------------------------------------------------------

@module.server
def admin_server(input, output, session, auth_service: AuthService, audit_service: AuditService,
                 settings_service: SettingsService, current_user):
    users_data: reactive.Value[list[dict]] = reactive.value([])
    log_offset: reactive.Value[int] = reactive.value(0)
    log_tick: reactive.Value[int] = reactive.value(0)
    registered: set[int] = set()

    def _is_admin() -> bool:
        return _check_admin_access(current_user())

    def _actor() -> dict:
        return current_user() or {"username": "unknown", "id": None}

    def _audit(action: str, target: str | None = None, detail=None) -> None:
        a = _actor()
        audit_service.log(a["username"], action, target=target, detail=detail, user_id=a.get("id"))

    def _refresh_users() -> None:
        users_data.set(auth_service.list_users())

    def _notify_error(exc: Exception) -> None:
        ui.notification_show(str(exc), type="error", duration=8)

    @render.ui
    def gate():
        if _is_admin():
            return None
        return ui.div("Administrator access required.", class_="alert alert-warning")

    # Users ------------------------------------------------------------------

    @reactive.effect
    def _load_users():
        if _is_admin():
            _refresh_users()

    @render.ui
    def user_summary():
        if not _is_admin():
            return None
        users = users_data.get()
        admins = sum(1 for u in users if u["role"] == ROLE_ADMIN)
        return ui.div(ui.h6("Accounts"), ui.p(f"{len(users)} users, {admins} admins"))

    @render.ui
    def user_table():
        if not _is_admin():
            return None
        rows = _build_user_table_data(users_data.get())
        if not rows:
            return ui.p("No users yet.", class_="text-muted")
        body = []
        for r in rows:
            uid = r["id"]
            body.append(ui.tags.tr(
                ui.tags.td(r["username"]), ui.tags.td(r["display_name"]), ui.tags.td(r["email"]),
                ui.tags.td(ui.HTML(_role_badge(r["role"]))), ui.tags.td(ui.HTML(_active_badge(r["is_active"]))),
                ui.tags.td(
                    ui.input_action_button(f"reset_pw_{uid}", "Reset password", class_="btn-sm btn-outline-secondary me-1"),
                    ui.input_action_button(f"toggle_active_{uid}", "Deactivate" if r["is_active"] else "Activate", class_="btn-sm btn-outline-secondary me-1"),
                    ui.input_action_button(f"toggle_role_{uid}", "Make user" if r["role"] == ROLE_ADMIN else "Make admin", class_="btn-sm btn-outline-secondary me-1"),
                    ui.input_action_button(f"delete_user_{uid}", "Delete", class_="btn-sm btn-outline-danger"),
                ),
            ))
        return ui.tags.table(
            ui.tags.thead(ui.tags.tr(*[ui.tags.th(h) for h in ("Username", "Name", "Email", "Role", "Status", "Actions")])),
            ui.tags.tbody(*body), class_="table table-sm align-middle",
        )

    def _register_user_actions(uid: int) -> None:
        @reactive.effect
        @reactive.event(input[f"reset_pw_{uid}"])
        def _reset_pw():
            if not _is_admin():
                return
            ui.modal_show(ui.modal(
                ui.input_password(f"new_pw_{uid}", "New password (at least 8 characters)"),
                title="Reset password",
                footer=ui.div(ui.modal_button("Cancel"), ui.input_action_button(f"confirm_reset_pw_{uid}", "Reset", class_="btn-primary")),
                easy_close=True,
            ))

        @reactive.effect
        @reactive.event(input[f"confirm_reset_pw_{uid}"])
        def _do_reset_pw():
            if not _is_admin():
                return
            pw = input[f"new_pw_{uid}"]() or ""
            if len(pw) < 8:
                ui.notification_show("Password must be at least 8 characters", type="error")
                return
            auth_service.reset_password(uid, pw)
            _audit("reset_password", target=f"user:{uid}")
            ui.modal_remove()
            ui.notification_show("Password reset", type="message")

        @reactive.effect
        @reactive.event(input[f"toggle_active_{uid}"])
        def _toggle_active():
            if not _is_admin():
                return
            user = next((u for u in users_data.get() if u["id"] == uid), None)
            if user is None:
                return
            try:
                auth_service.update_user(uid, is_active=not user["is_active"])
                _audit("toggle_active", target=f"user:{uid}", detail={"is_active": not user["is_active"]})
                _refresh_users()
            except ValueError as exc:
                _notify_error(exc)

        @reactive.effect
        @reactive.event(input[f"toggle_role_{uid}"])
        def _toggle_role():
            if not _is_admin():
                return
            user = next((u for u in users_data.get() if u["id"] == uid), None)
            if user is None:
                return
            new_role = ROLE_USER if user["role"] == ROLE_ADMIN else ROLE_ADMIN
            try:
                auth_service.update_user(uid, role=new_role)
                _audit("change_role", target=f"user:{uid}", detail={"role": new_role})
                _refresh_users()
            except ValueError as exc:
                _notify_error(exc)

        @reactive.effect
        @reactive.event(input[f"delete_user_{uid}"])
        def _delete_user():
            if not _is_admin():
                return
            ui.modal_show(ui.modal(
                ui.p("Delete this account? Their sessions end immediately."),
                title="Delete user",
                footer=ui.div(ui.modal_button("Cancel"), ui.input_action_button(f"confirm_delete_{uid}", "Delete", class_="btn-danger")),
                easy_close=True,
            ))

        @reactive.effect
        @reactive.event(input[f"confirm_delete_{uid}"])
        def _do_delete_user():
            if not _is_admin():
                return
            try:
                auth_service.delete_user(uid)
                _audit("delete_user", target=f"user:{uid}")
                _refresh_users()
                ui.modal_remove()
            except ValueError as exc:
                _notify_error(exc)

    @reactive.effect
    def _register_all_user_actions():
        for u in users_data.get():
            if u["id"] not in registered:
                registered.add(u["id"])
                _register_user_actions(u["id"])

    @reactive.effect
    @reactive.event(input.create_user_btn)
    def _show_create_modal():
        if not _is_admin():
            return
        ui.modal_show(ui.modal(
            ui.input_text("new_username", "Username"),
            ui.input_text("new_display_name", "Display name (optional)"),
            ui.input_text("new_email", "Email (optional)"),
            ui.input_password("new_password", "Password (at least 8 characters)"),
            ui.input_select("new_role", "Role", choices={ROLE_USER: "user", ROLE_ADMIN: "admin"}),
            ui.output_ui("create_user_errors"),
            title="Create user",
            footer=ui.div(ui.modal_button("Cancel"), ui.input_action_button("confirm_create_user", "Create", class_="btn-primary")),
            easy_close=True,
        ))

    create_errors: reactive.Value[list[str]] = reactive.value([])

    @render.ui
    def create_user_errors():
        errs = create_errors.get()
        return ui.div(*[ui.p(e, class_="text-danger small mb-1") for e in errs]) if errs else None

    @reactive.effect
    @reactive.event(input.confirm_create_user)
    def _do_create_user():
        if not _is_admin():
            return
        username, password = (input.new_username() or "").strip(), input.new_password() or ""
        role, email = input.new_role(), (input.new_email() or "").strip() or None
        errs = _validate_create_user_form(username, password, role, email)
        if errs:
            create_errors.set(errs)
            return
        try:
            auth_service.create_user(username, password, role=role, display_name=(input.new_display_name() or "").strip() or None, email=email)
        except ValueError as exc:
            create_errors.set([str(exc)])
            return
        create_errors.set([])
        _audit("create_user", target=f"user:{username}", detail={"role": role})
        _refresh_users()
        ui.modal_remove()
        ui.notification_show(f"Created {username}", type="message")

    # Queue policy -----------------------------------------------------------

    @render.ui
    def policy_form():
        if not _is_admin():
            return None
        fields = []
        for row in settings_service.rows():
            fields.append(ui.div(
                ui.input_numeric(f"policy_{row.key}", f"{row.label} (ceiling {row.ceiling})", row.value, min=1, max=row.ceiling, step=1),
                ui.p(row.explanation, class_="text-muted small"),
            ))
        return ui.div(*fields)

    @reactive.effect
    @reactive.event(input.policy_save)
    def _save_policy():
        if not _is_admin():
            return
        before = settings_service.effective()
        changed = {}
        try:
            for key in POLICY_KEYS:
                value = input[f"policy_{key}"]()
                if value is None:
                    raise ValueError(f"{key} is empty")
                if int(value) != before[key]:
                    settings_service.set(key, int(value))
                    changed[key] = {"old": before[key], "new": int(value)}
        except (ValueError, TypeError) as exc:
            _notify_error(exc)
            return
        if changed:
            _audit("settings_update", target="queue_policy", detail=changed)
        ui.notification_show("Policy saved" if changed else "No changes", type="message")

    # Audit log --------------------------------------------------------------

    @reactive.effect
    def _populate_log_filters():
        if not _is_admin():
            return
        log_tick.get()
        users = {"": "All users", **{u["username"]: u["username"] for u in auth_service.list_users()}}
        actions = {"": "All actions", **{a: a for a in audit_service.distinct_actions()}}
        ui.update_select("log_user_filter", choices=users, selected=input.log_user_filter() or "")
        ui.update_select("log_action_filter", choices=actions, selected=input.log_action_filter() or "")

    @reactive.effect
    @reactive.event(input.log_refresh_btn)
    def _on_log_refresh():
        log_tick.set(log_tick.get() + 1)

    @reactive.effect
    @reactive.event(input.log_user_filter, input.log_action_filter)
    def _on_filter_change():
        log_offset.set(0)

    @reactive.effect
    @reactive.event(input.log_prev_btn)
    def _prev():
        log_offset.set(max(0, log_offset.get() - _LOG_PAGE))

    @reactive.effect
    @reactive.event(input.log_next_btn)
    def _next():
        log_offset.set(log_offset.get() + _LOG_PAGE)

    def _filters():
        return {"username": input.log_user_filter() or None, "action": input.log_action_filter() or None}

    @render.ui
    def log_summary():
        if not _is_admin():
            return None
        log_tick.get()
        return ui.p(f"{audit_service.count(**_filters())} entries")

    @render.ui
    def log_page_info():
        if not _is_admin():
            return None
        log_tick.get()
        total = audit_service.count(**_filters())
        start = log_offset.get()
        return ui.span(f"{min(start + 1, total)}-{min(start + _LOG_PAGE, total)} of {total}", class_="small text-muted")

    @render.ui
    def log_table():
        if not _is_admin():
            return None
        log_tick.get()
        rows = audit_service.query(limit=_LOG_PAGE, offset=log_offset.get(), **_filters())
        if not rows:
            return ui.p("No entries.", class_="text-muted")
        return ui.tags.table(
            ui.tags.thead(ui.tags.tr(*[ui.tags.th(h) for h in ("Time (UTC)", "User", "Action", "Target", "Detail", "IP")])),
            ui.tags.tbody(*[ui.tags.tr(*[ui.tags.td(r[k]) for k in ("timestamp", "username", "action", "target", "detail", "ip_address")]) for r in rows]),
            class_="table table-sm",
        )
```

- [ ] **Step 5: Write the shell and create_app**

`sfincs_ui/sfincs_ui/www/sfincs_ui.css`:

```css
.env-banner { border-radius: 0; margin-bottom: 0; }
.navbar .form-check { margin: 0 .5rem; }
```

`sfincs_ui/sfincs_ui/app.py`:

```python
"""Assemble the SFINCS UI: Shiny app inside the session middleware."""

from __future__ import annotations

import logging
from pathlib import Path

from shiny import App, reactive, render, ui

from sfincs_ui.config import Config, get_config, set_config
from sfincs_ui.db.base import init_db
from sfincs_ui.middleware.session_auth import SessionAuthMiddleware, get_current_user
from sfincs_ui.pages import admin, home
from sfincs_ui.services.audit_service import AuditService
from sfincs_ui.services.auth_service import AuthService
from sfincs_ui.services.environment import EnvironmentReport, check_environment
from sfincs_ui.services.settings_service import SettingsService
from sfincs_ui.services.ws_identity import resolve_ws_user

logger = logging.getLogger(__name__)

_WS_IDENTITY_JS = """
document.addEventListener('DOMContentLoaded', function () {
  fetch('api/whoami').then(function (r) { return r.json(); }).then(function (data) {
    if (data.ws_token && window.Shiny && window.Shiny.setInputValue) {
      window.Shiny.setInputValue('_wsauth', data.ws_token, {priority: 'event'});
    }
  }).catch(function () {});
});
"""


def _banner(report: EnvironmentReport):
    if report.ok:
        return None
    return ui.div(
        ui.tags.strong("This server cannot run models right now: "),
        ui.tags.ul(*[ui.tags.li(p) for p in report.problems], class_="mb-0"),
        class_="alert alert-danger env-banner",
        role="alert",
    )


def build_ui(config: Config, report: EnvironmentReport) -> ui.Tag:
    return ui.page_navbar(
        ui.nav_panel("Home", home.home_ui("home")),
        ui.nav_panel("Admin", admin.admin_ui("admin")),
        ui.nav_spacer(),
        ui.nav_control(ui.input_dark_mode(id="dark_mode")),
        ui.nav_control(ui.output_ui("user_menu")),
        title="SFINCS UI",
        id="main_nav",
        header=ui.TagList(
            ui.head_content(
                ui.tags.link(rel="stylesheet", href="sfincs_ui.css"),
                ui.tags.script(_WS_IDENTITY_JS),
            ),
            _banner(report),
        ),
    )


def build_server(config: Config, auth_service: AuthService, audit_service: AuditService,
                 settings_service: SettingsService):
    def server(input, output, session):
        ws_user: reactive.Value[dict | None] = reactive.value(None)

        @reactive.effect
        def _resolve_identity():
            token = input._wsauth() if "_wsauth" in input else None
            try:
                ws_user.set(resolve_ws_user(token, auth_service))
            except Exception:
                logger.warning("ws identity resolution failed; treating as anonymous", exc_info=True)
                ws_user.set(None)

        def current_user() -> dict | None:
            # The ws-token bridge first; under direct uvicorn the cookie also
            # reaches the websocket scope, so fall back to it.
            return ws_user.get() or get_current_user()

        hidden = {"admin": False}

        @reactive.effect
        def _hide_admin_for_non_admins():
            # Under direct uvicorn the cookie reaches the websocket scope, so
            # get_current_user() already names an admin at the first flush;
            # the panel is removed once and only for everyone else. The Admin
            # body gates itself too, so this is presentation, not security.
            if not admin._check_admin_access(current_user()) and not hidden["admin"]:
                hidden["admin"] = True
                ui.remove_nav_panel("main_nav", "Admin")

        @render.ui
        def user_menu():
            user = current_user()
            prefix = config.url_prefix
            if user is None:
                return ui.tags.a("Log in", href=f"{prefix}/login", class_="btn btn-sm btn-outline-light")
            return ui.span(
                ui.span(user["username"], class_="me-2 text-light"),
                ui.tags.a("Log out", href=f"{prefix}/logout", class_="btn btn-sm btn-outline-light"),
            )

        home.home_server("home", current_user=current_user)
        admin.admin_server("admin", auth_service=auth_service, audit_service=audit_service,
                           settings_service=settings_service, current_user=current_user)

    return server


def create_app(config: Config | None = None, *, environment: EnvironmentReport | None = None):
    if config is None:
        config = get_config()
    else:
        set_config(config)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    init_db()
    report = environment if environment is not None else check_environment(config)
    for problem in report.problems:
        logger.warning("environment: %s", problem)

    auth_service = AuthService()
    audit_service = AuditService()
    settings_service = SettingsService(config)

    app = App(build_ui(config, report), build_server(config, auth_service, audit_service, settings_service),
              static_assets=Path(__file__).parent / "www")
    return SessionAuthMiddleware(
        app,
        auth_service=auth_service,
        audit_service=audit_service,
        root_path=config.url_prefix,
        session_ttl_hours=config.session_ttl_hours,
        use_secure_cookies=config.secure_cookies,
        trusted_proxies=config.trusted_proxies,
    )
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `cd /home/razinka/sfincs/sfincs_ui && /opt/micromamba/envs/shiny/bin/python -m pytest tests/test_pages.py -q`
Expected: 8 passed

- [ ] **Step 7: Smoke the real app once by hand**

Run (from `sfincs_ui/`, two shells or background):

```bash
mkdir -p /tmp/claude-1000/-home-razinka-sfincs/946ef2e3-64b8-42c9-b324-8e8da9f13c98/scratchpad/ws
export SFINCS_UI_WORKSPACE=/tmp/claude-1000/-home-razinka-sfincs/946ef2e3-64b8-42c9-b324-8e8da9f13c98/scratchpad/ws
export SFINCS_UI_SECURE_COOKIES=false SFINCS_UI_PORT=8899 SFINCS_UI_URL_PREFIX=/sfincs-ui   # the production shape: uvicorn gets --root-path
SFINCS_UI_ADMIN_PASSWORD=devpassword1 /opt/micromamba/envs/shiny/bin/python -m sfincs_ui create-admin --username admin
/opt/micromamba/envs/shiny/bin/python -m sfincs_ui serve &
sleep 8
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8899/            # 200
curl -s http://127.0.0.1:8899/login | grep -c 'csrf_token'                  # 1
curl -s -c /tmp/claude-1000/cj -b /tmp/claude-1000/cj http://127.0.0.1:8899/login > /dev/null
CSRF=$(grep sfincs_ui_csrf /tmp/claude-1000/cj | awk '{print $7}')
curl -s -o /dev/null -w '%{http_code}\n' -c /tmp/claude-1000/cj -b /tmp/claude-1000/cj -d "username=admin&password=devpassword1&csrf_token=$CSRF" http://127.0.0.1:8899/login   # 302
curl -s -b /tmp/claude-1000/cj http://127.0.0.1:8899/api/whoami            # {"username": "admin", ..., "ws_token": "..."}
kill %1
```

Expected: the four codes and the whoami JSON as commented, with `--root-path /sfincs-ui` in effect (the `serve` command passes `root_path=config.url_prefix`), which proves the middleware strips the prefix uvicorn prepends to `scope["path"]`. If the websocket identity does not reach the Admin page in a browser later, the first thing to check is the `_wsauth` input (open the page, run `fetch('api/whoami')` in the console).

- [ ] **Step 8: Commit**

```bash
cd /home/razinka/sfincs
git add sfincs_ui/sfincs_ui/pages sfincs_ui/sfincs_ui/app.py sfincs_ui/sfincs_ui/www sfincs_ui/tests/test_pages.py
git commit -m "sfincs_ui: application shell with Home and Admin pages

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 9: HTTP integration tests of the assembled app

**Files:**
- Test: `sfincs_ui/tests/test_app_http.py`

**Interfaces:**
- Consumes: `create_app` (Task 8), `AuthService` (Task 3), the `db` fixture.
- Produces: nothing new; this task pins the login round trip through the real middleware, the real database and the real Shiny app over httpx's ASGI transport.

- [ ] **Step 1: Write the tests**

`sfincs_ui/tests/test_app_http.py`:

```python
"""Login round trip through the assembled ASGI app (no browser)."""

import re

import httpx
import pytest

from sfincs_ui.services.auth_service import AuthService
from sfincs_ui.services.environment import EnvironmentReport


@pytest.fixture
def app(db, tmp_path):
    from sfincs_ui import config
    from sfincs_ui.app import create_app

    cfg = config.Config(workspace=tmp_path, database_url=f"sqlite:///{tmp_path / 'test.db'}")
    AuthService(session_factory=db).ensure_admin("root", "pw12345678")
    AuthService(session_factory=db).create_user("plain", "pw12345678")
    return create_app(cfg, environment=EnvironmentReport())


@pytest.fixture
def client(app):
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="https://test")


async def _login(client, username, password):
    page = await client.get("/login")
    csrf = re.search(r'name="csrf_token" value="([^"]+)"', page.text).group(1)
    return await client.post("/login", data={"username": username, "password": password, "csrf_token": csrf})


async def test_anonymous_home_and_whoami(client):
    async with client as c:
        assert (await c.get("/")).status_code == 200
        assert (await c.get("/api/whoami")).json()["role"] is None


async def test_login_sets_secure_cookie_and_identifies_user(client):
    async with client as c:
        r = await _login(c, "root", "pw12345678")
        assert r.status_code == 302 and r.headers["location"] == "/"
        set_cookie = r.headers["set-cookie"]
        assert "Secure" in set_cookie and "HttpOnly" in set_cookie
        who = (await c.get("/api/whoami")).json()
        assert who["username"] == "root" and who["role"] == "admin" and who["ws_token"]


async def test_bad_password_leaves_client_anonymous_and_is_audited(client, db):
    from sfincs_ui.services.audit_service import AuditService

    async with client as c:
        r = await _login(c, "root", "wrong")
        assert r.status_code == 200 and "Invalid username or password" in r.text
        assert (await c.get("/api/whoami")).json()["username"] is None
    assert AuditService(session_factory=db).query(action="login_failed")[0]["username"] == "root"


async def test_logout_clears_session(client):
    async with client as c:
        await _login(c, "plain", "pw12345678")
        assert (await c.get("/api/whoami")).json()["username"] == "plain"
        confirm = await c.get("/logout")
        assert confirm.status_code == 200 and "Log out" in confirm.text
        r = await c.post("/logout")
        assert r.status_code == 302
        assert (await c.get("/api/whoami")).json()["username"] is None


async def test_ws_token_resolves_to_the_same_user(client, db):
    async with client as c:
        await _login(c, "plain", "pw12345678")
        tok = (await c.get("/api/whoami")).json()["ws_token"]
    assert AuthService(session_factory=db).validate_ws_token(tok)["username"] == "plain"


async def test_static_asset_is_served(client):
    async with client as c:
        r = await c.get("/sfincs_ui.css")
        assert r.status_code == 200 and "env-banner" in r.text
```

- [ ] **Step 2: Run the whole suite**

Run: `cd /home/razinka/sfincs/sfincs_ui && /opt/micromamba/envs/shiny/bin/python -m pytest -q`
Expected: 92 passed. If `test_static_asset_is_served` fails with 404, the `static_assets` path in `create_app` is wrong; it must be the package's `www` directory.

- [ ] **Step 3: Commit**

```bash
cd /home/razinka/sfincs
git add sfincs_ui/tests/test_app_http.py
git commit -m "sfincs_ui: HTTP integration tests for the login round trip

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 10: Deployment: unit, nginx block, catalogue entry and deploy_ui.sh

**Files:**
- Create: `deploy/sfincs-ui.service.in`
- Create: `deploy/sfincs-ui.env.in`
- Create: `deploy/sfincs-ui.nginx`
- Create: `deploy/services-entry-ui.json`
- Create: `deploy/deploy_ui.sh`
- Modify: `deploy/README.md` (append a section)

**Interfaces:**
- Consumes: `python -m sfincs_ui migrate | create-admin | preflight` (Task 7), `sfincs_ui.asgi:app` (Task 7/8).
- Produces: `sudo bash deploy/deploy_ui.sh` (install or update), `--check` (no root), `--restart`, `--uninstall`. Prod clone at `/srv/shiny-server/sfincs-ui-src`, workspace at `/srv/sfincs-ui/workspace`, unit `sfincs-ui.service`, env file `/etc/sfincs-ui.env`, nginx `location /sfincs-ui/`, catalogue id `sfincs-ui`.

**What the executor can run:** `bash -n deploy/deploy_ui.sh`, `bash deploy/deploy_ui.sh --check` (no root), and the Python snippets inside the script against copies of the config files in the scratchpad. **What only the user can run:** every root step (`! sudo bash deploy/deploy_ui.sh`), and the acceptance step "log in at https://laguna.ku.lt/sfincs-ui/". Do not fake those; mark them for the user.

Milestone 2 adds, at the marked line, the check of the `jobs` table for an active simulate stage before the restart and the explicit kill of detached stages in `--uninstall` (spec section 3). In milestone 1 there are no jobs, so the restart is unconditional.

- [ ] **Step 1: Write the unit template**

`deploy/sfincs-ui.service.in` (`@PORT@`, `@PROD_SRC@`, `@URL_PREFIX@` are substituted by the script):

```ini
# /etc/systemd/system/sfincs-ui.service -- SFINCS UI on laguna.ku.lt.
# Installed by deploy/deploy_ui.sh from deploy/sfincs-ui.service.in; do not edit here.
#
# Standalone uvicorn as user shiny, nginx proxies /sfincs-ui/ to it. Not Shiny
# Server: that reaps an app a few seconds after its last client leaves and
# restarts it on every deploy, the wrong lifetime for hour-long model runs.
#
# KillMode=process: `man systemd.kill` calls this "not recommended" because
# children of the main process survive a stop. That is the point here. Every
# model stage (build, simulate, validate, export) is launched detached in its
# own session and recorded in the jobs table with its pid and /proc start
# time; on the next start the queue reconciles it (spec section 3). With the
# default control-group mode a `systemctl restart` on deploy would SIGKILL a
# 45-minute SFINCS run. TimeoutStopSec therefore applies to uvicorn alone.

[Unit]
Description=SFINCS UI (Python Shiny, direct uvicorn)
After=network.target

[Service]
Type=simple
User=shiny
Group=shiny
WorkingDirectory=@PROD_SRC@/sfincs_ui
EnvironmentFile=/etc/sfincs-ui.env
Environment=PYTHONUNBUFFERED=1
ExecStart=/opt/micromamba/envs/shiny/bin/python3 -m uvicorn sfincs_ui.asgi:app --host 127.0.0.1 --port @PORT@ --root-path @URL_PREFIX@
Restart=always
RestartSec=5
KillMode=process
TimeoutStopSec=20

[Install]
WantedBy=multi-user.target
```

- [ ] **Step 2: Write the environment file template**

`deploy/sfincs-ui.env.in` (`@UPLOAD_MAX_MB@`, `@PORT@`, `@URL_PREFIX@` substituted; other values are the install-time ceilings from spec sections 3 and 5):

```bash
# /etc/sfincs-ui.env -- read by sfincs-ui.service and by deploy_ui.sh when it
# runs `python -m sfincs_ui ...` as user shiny. Installed from
# deploy/sfincs-ui.env.in; edit the template and redeploy.
#
# SFINCS_UI_* values are ceilings and defaults; admins lower them in the UI.
# MIN_FREE_GB and UPLOAD_MAX_MB are env-only. HOME is deliberately not set.
# micromamba is named by absolute path: the unit's PATH is systemd's default
# and sudo's secure_path differs from a login shell (both include
# /usr/local/bin on this host as of 2026-10-01, but pinning removes the doubt).
SFINCS_UI_WORKSPACE=/srv/sfincs-ui/workspace
SFINCS_UI_CURONIAN_DIR=/home/razinka/sfincs/curonian
SFINCS_UI_SFINCS_BIN=/home/razinka/sfincs/sfincs-linux/bin/sfincs
SFINCS_UI_MODEL_PYTHON=/usr/local/bin/micromamba -r /opt/micromamba run -n hydromt-sfincs python
SFINCS_UI_URL_PREFIX=@URL_PREFIX@
SFINCS_UI_PORT=@PORT@
SFINCS_UI_MAX_SIMULATIONS=1
SFINCS_UI_MAX_THREADS=16
SFINCS_UI_MIN_FREE_GB=100
SFINCS_UI_RETENTION_DAYS=60
SFINCS_UI_QUOTA_GB=20
SFINCS_UI_UPLOAD_MAX_MB=@UPLOAD_MAX_MB@
MAMBA_ROOT_PREFIX=/opt/micromamba
SFINCS_CURONIAN_DB=/home/razinka/curonian/curonian_db.gpkg
```

Note on `SFINCS_UI_MAX_THREADS=16`: the spec's default cap is 8 with "an admin may raise the cap to 16". The env value is the ceiling, so it is set to 16 here and the `settings` table's admin value starts at the ceiling. Milestone 2's queue reads `SettingsService.get("max_threads")`; if an 8-thread default is wanted, the admin lowers it on the Queue policy tab, or milestone 2 seeds `settings` with 8 at first launch. Record whichever is chosen in that plan.

- [ ] **Step 3: Write the nginx block**

`deploy/sfincs-ui.nginx` (`@PORT@`, `@UPLOAD_MAX_MB@` substituted):

```nginx
# SFINCS UI -- nginx location blocks, installed by deploy/deploy_ui.sh before
# the "Database Admin Tools" anchor of /etc/nginx/sites-available/nid4ocean.
# Copied from the /osmose/ block (direct uvicorn): proxy_pass's trailing slash
# strips the prefix, which the app learns from --root-path. client_max_body_size
# is raised above the site default of 50 MB because HEC-RAS geometry and DEM
# uploads (milestone 5) are larger; proxy_read_timeout matches the other model
# panels so an idle websocket is not culled while a user reads a results page.

    # =========================================================================
    # SFINCS UI -- build, run and inspect SFINCS models (direct uvicorn on port @PORT@)
    # =========================================================================

    location /sfincs-ui/ {
        proxy_pass http://127.0.0.1:@PORT@/;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection $connection_upgrade;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Forwarded-Prefix /sfincs-ui;
        proxy_cache_bypass $http_upgrade;
        proxy_read_timeout 86400s;
        proxy_buffering off;
        client_max_body_size @UPLOAD_MAX_MB@m;
    }

    location = /sfincs-ui {
        return 301 /sfincs-ui/;
    }
```

- [ ] **Step 4: Write the catalogue entry**

`deploy/services-entry-ui.json`:

```json
{
  "id": "sfincs-ui",
  "title": "SFINCS UI",
  "path": "/sfincs-ui/",
  "description": "Build, run and inspect SFINCS compound-flood models of the Curonian Lagoon from the browser. Login required to launch runs; published runs are open to everyone.",
  "icon": "model",
  "tag": "Shiny",
  "tagClass": "shiny",
  "language": "Python",
  "visible": false,
  "order": 14,
  "svg": "<svg width=\"22\" height=\"22\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"2\"><path d=\"M3 12l4-5 4 4 3-3 7 6\"/><path d=\"M2 17c2-2 4-2 6 0s4 2 6 0 4-2 6 0\"/><circle cx=\"18\" cy=\"6\" r=\"2.5\"/></svg>"
}
```

- [ ] **Step 5: Write deploy_ui.sh**

`deploy/deploy_ui.sh`:

```bash
#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# deploy_ui.sh -- publish SFINCS UI on laguna.ku.lt as a standalone uvicorn
# systemd unit behind nginx (the osmose pattern; see spec section 5).
#
#   https://laguna.ku.lt/sfincs-ui/
#
# Usage:
#   sudo bash deploy/deploy_ui.sh              # install or update (idempotent)
#   bash deploy/deploy_ui.sh --check           # report state, change nothing, no root
#   sudo bash deploy/deploy_ui.sh --restart    # restart the service only
#   sudo bash deploy/deploy_ui.sh --uninstall  # remove unit, nginx block, entry, clone
#
# Prod runs from its OWN git clone, never a symlink to the dev tree: a
# long-running uvicorn process must not see its source edited underneath it
# (see /srv/shiny-server/osmose-src/deploy.sh for the failure). The clone is
# pip-installed editable into the shared shiny env, so the running process
# reads the clone, which changes only here, followed by a restart.
#
# The clone cannot build a Curonian model (binary, inputs and catalogue paths
# are gitignored or machine-specific), so CURONIAN_DIR and SFINCS_BIN point
# at the dev checkout, like the viewer's SFINCS_DATA_DIR already does.
# ---------------------------------------------------------------------------
set -euo pipefail

APP_NAME="sfincs-ui"
URL_PREFIX="/sfincs-ui"
PUBLIC_URL="https://laguna.ku.lt${URL_PREFIX}/"
PORT="${SFINCS_UI_PORT:-8840}"
UPLOAD_MAX_MB="${SFINCS_UI_UPLOAD_MAX_MB:-500}"
ADMIN_USERNAME="${SFINCS_UI_ADMIN_USERNAME:-admin}"

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEPLOY_DIR="${REPO_ROOT}/deploy"
REPO_URL="${SFINCS_UI_REPO_URL:-https://github.com/razinkele/sfincs.git}"
DEPLOY_REF="${SFINCS_UI_DEPLOY_REF:-origin/main}"

SHINY_ROOT="/srv/shiny-server"
PROD_SRC="${SHINY_ROOT}/${APP_NAME}-src"
SHINY_PYTHON="/opt/micromamba/envs/shiny/bin/python3"
SHINY_PIP="/opt/micromamba/envs/shiny/bin/pip"
PIP_INSTALL=("$SHINY_PIP" install --root-user-action=ignore --quiet)
WORKSPACE="/srv/sfincs-ui/workspace"
ENV_FILE="/etc/${APP_NAME}.env"
SERVICE_NAME="${APP_NAME}"
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"
NGINX_CONF="/etc/nginx/sites-available/nid4ocean"
SERVICES_JSON="/var/www/html/services.json"
SERVICES_MD="/etc/nginx/sites-available/SERVICES.md"
NGINX_MARKER="location ${URL_PREFIX}/ {"

STAMP="$(date +%Y%m%d_%H%M%S)"
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
info() { echo -e "${GREEN}[+]${NC} $*"; }
warn() { echo -e "${YELLOW}[!]${NC} $*"; }
fail() { echo -e "${RED}[x]${NC} $*" >&2; exit 1; }

MODE="${1:-install}"
need_root() { [[ "$(id -u)" -eq 0 ]] || fail "must run as root:  sudo bash deploy/deploy_ui.sh ${*:-}"; }

# Run a sfincs_ui CLI command as the service user with the unit's environment,
# never as root, so the SQLite file and its -wal/-shm companions stay writable
# by the service.
# EXTRA_ENV holds additional KEY=VALUE items for one call (the admin password).
# Each line of the env file is one array element, so values with spaces such as
# SFINCS_UI_MODEL_PYTHON survive; never word-split the file into `env`.
EXTRA_ENV=()
as_shiny() {
    local -a env_args=()
    while IFS= read -r line; do
        [[ -z "$line" || "$line" == \#* ]] && continue
        env_args+=("$line")
    done < "$ENV_FILE"
    sudo -u shiny env "${env_args[@]}" "${EXTRA_ENV[@]}" "$SHINY_PYTHON" -m sfincs_ui "$@"
}

render_template() {  # render_template <template> <dest>
    sed -e "s|@PORT@|${PORT}|g" -e "s|@PROD_SRC@|${PROD_SRC}|g" \
        -e "s|@URL_PREFIX@|${URL_PREFIX}|g" -e "s|@UPLOAD_MAX_MB@|${UPLOAD_MAX_MB}|g" "$1" > "$2"
}

# ---------------------------------------------------------------------------
# --check
# ---------------------------------------------------------------------------
if [[ "$MODE" == "--check" ]]; then
    echo "SFINCS UI deployment state"
    echo "  prod clone     : $([[ -d $PROD_SRC/.git ]] && echo "present  $(git -C "$PROD_SRC" rev-parse --short HEAD 2>/dev/null)" || echo "ABSENT   $PROD_SRC")"
    echo "  unit           : $(systemctl is-enabled "$SERVICE_NAME" 2>/dev/null || echo absent) / $(systemctl is-active "$SERVICE_NAME" 2>/dev/null || echo inactive)"
    echo "  port ${PORT}      : $(ss -ltn 2>/dev/null | grep -q ":${PORT} " && echo bound || echo free)"
    echo "  nginx          : $(grep -qF "$NGINX_MARKER" "$NGINX_CONF" 2>/dev/null && echo registered || echo "NOT registered")"
    echo "  env file       : $([[ -f $ENV_FILE ]] && echo present || echo ABSENT)"
    echo "  workspace      : $([[ -d $WORKSPACE ]] && echo "present  owner $(stat -c %U "$WORKSPACE")" || echo ABSENT)"
    echo "  catalogue      : $("$SHINY_PYTHON" - "$SERVICES_JSON" "$APP_NAME" <<'PY'
import json, sys
try:
    data = json.load(open(sys.argv[1]))
except Exception as exc:
    print(f"unreadable ({exc})"); raise SystemExit
for cat in data["categories"]:
    for svc in cat["services"]:
        if svc["id"] == sys.argv[2]:
            print(f"present in '{cat['id']}', visible={svc.get('visible')}"); raise SystemExit
print("ABSENT")
PY
)"
    echo "  live URL       : $(curl -sk -o /dev/null -w '%{http_code}' "$PUBLIC_URL" || echo unreachable)"
    exit 0
fi

# ---------------------------------------------------------------------------
# --restart
# ---------------------------------------------------------------------------
if [[ "$MODE" == "--restart" ]]; then
    need_root --restart
    # MILESTONE 2: check the jobs table for an active simulate stage here and
    # wait for it or warn (spec section 3); detached stages survive the restart
    # thanks to KillMode=process, but the queue must be told to reconcile.
    systemctl restart "$SERVICE_NAME" && info "restarted ${SERVICE_NAME}"
    exit 0
fi

# ---------------------------------------------------------------------------
# --uninstall
# ---------------------------------------------------------------------------
if [[ "$MODE" == "--uninstall" ]]; then
    need_root --uninstall
    # MILESTONE 2: kill detached model stages explicitly first; systemctl stop
    # no longer does with KillMode=process.
    if systemctl is-active --quiet "$SERVICE_NAME" 2>/dev/null; then systemctl stop "$SERVICE_NAME"; fi
    if [[ -f "$SERVICE_FILE" ]]; then
        systemctl disable "$SERVICE_NAME" 2>/dev/null || true
        rm -f "$SERVICE_FILE"; systemctl daemon-reload
        info "removed ${SERVICE_FILE}"
    fi
    if grep -qF "$NGINX_MARKER" "$NGINX_CONF"; then
        cp -a "$NGINX_CONF" "${NGINX_CONF}.bak.${STAMP}"
        "$SHINY_PYTHON" - "$NGINX_CONF" "$URL_PREFIX" <<'PY'
import re, sys
p, prefix = sys.argv[1], sys.argv[2]
t = open(p).read()
pat = r"\n *# ={10,}\n *# SFINCS UI.*?\n *location = " + re.escape(prefix) + r" \{\n.*?\n *\}\n\n"
t2 = re.sub(pat, "\n", t, count=1, flags=re.S)
if t2 == t: raise SystemExit("nginx block not found in the expected shape; remove it by hand")
open(p, "w").write(t2)
PY
        nginx -t && systemctl reload nginx
        info "nginx block removed (backup ${NGINX_CONF}.bak.${STAMP})"
    fi
    if [[ -f "$SERVICES_JSON" ]]; then
        cp -a "$SERVICES_JSON" "${SERVICES_JSON}.bak-${STAMP}"
        "$SHINY_PYTHON" - "$SERVICES_JSON" "$APP_NAME" <<'PY'
import json, sys
p, app_id = sys.argv[1], sys.argv[2]
data = json.load(open(p))
for cat in data["categories"]:
    cat["services"] = [s for s in cat["services"] if s["id"] != app_id]
json.dump(data, open(p, "w"), indent=2, ensure_ascii=False)
PY
        info "catalogue entry removed"
    fi
    "$SHINY_PIP" uninstall --root-user-action=ignore -y sfincs-ui >/dev/null 2>&1 || true
    rm -rf "$PROD_SRC"; rm -f "$ENV_FILE"
    info "uninstalled. Workspace ${WORKSPACE} (database and runs) was kept; remove it by hand if wanted."
    exit 0
fi

# ---------------------------------------------------------------------------
# install / update
# ---------------------------------------------------------------------------
need_root
info "Preflight (deployer side)"
[[ -x "$SHINY_PYTHON" ]]  || fail "shiny python missing: ${SHINY_PYTHON}"
[[ -f "$NGINX_CONF" ]]    || fail "nginx config missing: ${NGINX_CONF}"
[[ -f "$SERVICES_JSON" ]] || fail "toolbox catalogue missing: ${SERVICES_JSON}"
command -v git >/dev/null || fail "git is required for the prod clone"
id shiny >/dev/null 2>&1  || fail "service user 'shiny' does not exist"
for f in sfincs-ui.service.in sfincs-ui.env.in sfincs-ui.nginx services-entry-ui.json; do
    [[ -f "${DEPLOY_DIR}/${f}" ]] || fail "missing ${DEPLOY_DIR}/${f}"
done

# --- port refusals: a failed publish must never leave /sfincs-ui/ proxying
#     into another app --------------------------------------------------------
if ss -ltn 2>/dev/null | grep -q ":${PORT} " && ! systemctl is-active --quiet "$SERVICE_NAME" 2>/dev/null; then
    fail "port ${PORT} is bound by something other than ${SERVICE_NAME}; pick another with SFINCS_UI_PORT"
fi
if grep -q "127.0.0.1:${PORT}/" "$NGINX_CONF" && ! grep -qF "$NGINX_MARKER" "$NGINX_CONF"; then
    fail "nginx already proxies to port ${PORT} from another location block"
fi
OTHER_UNIT="$(grep -l -- "--port ${PORT}\b" /etc/systemd/system/*.service 2>/dev/null | grep -v "${SERVICE_NAME}.service" || true)"
[[ -z "$OTHER_UNIT" ]] || fail "another unit names port ${PORT}: ${OTHER_UNIT}"
info "port ${PORT} is ours"

# --- prod clone ------------------------------------------------------------
git config --global --add safe.directory "$PROD_SRC" 2>/dev/null || true
if [[ -d "${PROD_SRC}/.git" ]]; then
    git -C "$PROD_SRC" fetch --quiet --prune origin
elif [[ -e "$PROD_SRC" ]]; then
    fail "${PROD_SRC} exists but is not a git clone; remove it by hand"
else
    git clone --quiet "$REPO_URL" "$PROD_SRC"
fi
git -C "$PROD_SRC" checkout --quiet --force --detach "$DEPLOY_REF"
DEPLOYED_SHA="$(git -C "$PROD_SRC" rev-parse --short HEAD)"
chown -R shiny:shiny "$PROD_SRC"
info "prod clone at ${DEPLOY_REF} (${DEPLOYED_SHA})"

# --- install the package into the shiny env --------------------------------
"${PIP_INSTALL[@]}" -e "${PROD_SRC}/sfincs_ui"
"$SHINY_PYTHON" - <<'PY'
import sys
from importlib.metadata import version
from packaging.version import Version
floors = {"shiny": "1.8.0", "sqlalchemy": "2.0", "alembic": "1.13", "argon2-cffi": "23.0",
          "pydantic-settings": "2.0", "uvicorn": "0.30"}
bad = [f"{p} {version(p)} < {f}" for p, f in floors.items() if Version(version(p)) < Version(f)]
if bad: print("DEPENDENCY FLOOR CHECK FAILED:", "; ".join(bad)); sys.exit(1)
import sfincs_ui; print("sfincs_ui", sfincs_ui.__version__, "importable from", sfincs_ui.__file__)
PY
info "package installed"

# --- workspace and environment file ----------------------------------------
mkdir -p "$WORKSPACE"
chown shiny:shiny /srv/sfincs-ui "$WORKSPACE"
chmod 750 "$WORKSPACE"
[[ -f "$ENV_FILE" ]] && cp -a "$ENV_FILE" "${ENV_FILE}.bak.${STAMP}"
render_template "${DEPLOY_DIR}/sfincs-ui.env.in" "$ENV_FILE"
chmod 644 "$ENV_FILE"
info "workspace ${WORKSPACE} and ${ENV_FILE} in place"

# --- preflight as the service user -----------------------------------------
info "Preflight (as user shiny, unit environment)"
as_shiny preflight || fail "preflight failed; fix the reported paths before publishing"

# --- migrations and the first admin, as shiny ------------------------------
as_shiny migrate
if [[ -n "${SFINCS_UI_ADMIN_PASSWORD:-}" ]]; then
    EXTRA_ENV=("SFINCS_UI_ADMIN_PASSWORD=${SFINCS_UI_ADMIN_PASSWORD}")
fi
as_shiny create-admin --username "$ADMIN_USERNAME"
EXTRA_ENV=()
for f in "${WORKSPACE}"/sfincs_ui.db "${WORKSPACE}"/sfincs_ui.db-wal "${WORKSPACE}"/sfincs_ui.db-shm; do
    [[ -e "$f" ]] && [[ "$(stat -c %U "$f")" != "shiny" ]] && fail "${f} is owned by $(stat -c %U "$f"), not shiny"
done
info "database migrated and owned by shiny"

# --- systemd unit ----------------------------------------------------------
render_template "${DEPLOY_DIR}/sfincs-ui.service.in" "$SERVICE_FILE"
systemctl daemon-reload
systemctl enable "$SERVICE_NAME" >/dev/null 2>&1
# MILESTONE 2: before restarting, check the jobs table for an active simulate
# stage and wait for it or warn (spec section 3).
systemctl restart "$SERVICE_NAME"
CODE="000"
for _ in $(seq 1 20); do
    CODE="$(curl -s -m 5 -o /dev/null -w '%{http_code}' "http://127.0.0.1:${PORT}/" || echo 000)"
    [[ "$CODE" == "200" ]] && break
    sleep 2
done
[[ "$CODE" == "200" ]] || fail "service did not answer on port ${PORT} (HTTP ${CODE}); see: journalctl -u ${SERVICE_NAME} -n 40"
info "service ${SERVICE_NAME} is up on port ${PORT}"

# --- nginx -----------------------------------------------------------------
if grep -qF "$NGINX_MARKER" "$NGINX_CONF"; then
    info "nginx already registers ${URL_PREFIX}/"
else
    cp -a "$NGINX_CONF" "${NGINX_CONF}.bak.${STAMP}"
    RENDERED_NGINX="$(mktemp)"; render_template "${DEPLOY_DIR}/sfincs-ui.nginx" "$RENDERED_NGINX"
    "$SHINY_PYTHON" - "$NGINX_CONF" "$RENDERED_NGINX" <<'PY'
import sys
conf_path, block_path = sys.argv[1], sys.argv[2]
text = open(conf_path).read()
block = open(block_path).read()
block = block[block.index("    # ="):].rstrip() + "\n\n"
anchor = "    # =========================================================================\n    # Database Admin Tools"
if anchor not in text:
    raise SystemExit("anchor 'Database Admin Tools' not found in nginx config")
open(conf_path, "w").write(text.replace(anchor, block + anchor, 1))
PY
    rm -f "$RENDERED_NGINX"
    info "nginx block installed (backup ${NGINX_CONF}.bak.${STAMP})"
fi
nginx -t || fail "nginx config test FAILED; restore ${NGINX_CONF}.bak.${STAMP}"
systemctl reload nginx

# --- smoke test over HTTPS (no login over plain http; cookies are Secure) ---
CODE=""
for _ in $(seq 1 15); do
    CODE="$(curl -sk -o /dev/null -w '%{http_code}' "$PUBLIC_URL" || true)"
    [[ "$CODE" == "200" ]] && break
    sleep 1
done
[[ "$CODE" == "200" ]] || fail "${PUBLIC_URL} returned HTTP ${CODE:-none}; catalogue entry left hidden"
PAGE="$(curl -sk "$PUBLIC_URL" || true)"
grep -q "SFINCS UI" <<<"$PAGE" || fail "page served but does not look like SFINCS UI"
LOGIN_CODE="$(curl -sk -o /dev/null -w '%{http_code}' "${PUBLIC_URL}login" || true)"
[[ "$LOGIN_CODE" == "200" ]] || fail "${PUBLIC_URL}login returned HTTP ${LOGIN_CODE}"
info "HTTPS smoke test passed (home and login page)"

# --- toolbox catalogue (visible only now) ----------------------------------
cp -a "$SERVICES_JSON" "${SERVICES_JSON}.bak-${STAMP}"
"$SHINY_PYTHON" - "$SERVICES_JSON" "${DEPLOY_DIR}/services-entry-ui.json" <<'PY'
import json, sys
services_path, entry_path = sys.argv[1], sys.argv[2]
data = json.load(open(services_path))
entry = json.load(open(entry_path)); entry["visible"] = True
target = next(c for c in data["categories"] if c["id"] == "modelling")
existing = next((s for s in target["services"] if s["id"] == entry["id"]), None)
if existing: existing.update(entry)
else: target["services"].append(entry)
target["services"].sort(key=lambda s: s.get("order", 999))
json.dump(data, open(services_path, "w"), indent=2, ensure_ascii=False)
json.load(open(services_path))
PY
info "toolbox catalogue updated (backup ${SERVICES_JSON}.bak-${STAMP})"

if [[ -f "$SERVICES_MD" ]] && ! grep -q '`/sfincs-ui/`' "$SERVICES_MD"; then
    "$SHINY_PYTHON" - "$SERVICES_MD" "$PORT" <<'PY' && info "SERVICES.md row added" || warn "SERVICES.md not updated"
import sys
p, port = sys.argv[1], sys.argv[2]
text = open(p).read()
row = f"| `/sfincs-ui/` | SFINCS UI -- build and run flood models | Python Shiny | uvicorn :{port} | `sfincs-ui` | OK |\n"
anchor = "| `/qgisserver`"
if anchor not in text: raise SystemExit(1)
open(p, "w").write(text.replace(anchor, row + anchor, 1))
PY
fi

echo
info "Deployed:   ${PUBLIC_URL}  (${DEPLOYED_SHA})"
info "Service:    systemctl status ${SERVICE_NAME}    journalctl -u ${SERVICE_NAME} -f"
info "Workspace:  ${WORKSPACE}"
info "Admin:      '${ADMIN_USERNAME}' (created only if no admin existed)"
```

- [ ] **Step 6: Static checks the executor can run**

Run: `bash -n /home/razinka/sfincs/deploy/deploy_ui.sh && echo syntax-ok`
Expected: `syntax-ok`

Run: `cd /home/razinka/sfincs && bash deploy/deploy_ui.sh --check`
Expected: a state table with `prod clone: ABSENT`, `unit: absent / inactive`, `port 8840: free`, `nginx: NOT registered`, `catalogue: ABSENT`, `live URL: 404`. Exit 0, nothing changed.

Run the nginx insertion snippet against a copy to prove the anchor logic:

```bash
S=/tmp/claude-1000/-home-razinka-sfincs/946ef2e3-64b8-42c9-b324-8e8da9f13c98/scratchpad
cp /etc/nginx/sites-available/nid4ocean $S/nid4ocean.copy
sed -e 's|@PORT@|8840|g' -e 's|@UPLOAD_MAX_MB@|500|g' /home/razinka/sfincs/deploy/sfincs-ui.nginx > $S/block
/opt/micromamba/envs/shiny/bin/python - $S/nid4ocean.copy $S/block <<'PY'
import sys
conf_path, block_path = sys.argv[1], sys.argv[2]
text = open(conf_path).read(); block = open(block_path).read()
block = block[block.index("    # ="):].rstrip() + "\n\n"
anchor = "    # =========================================================================\n    # Database Admin Tools"
assert anchor in text
open(conf_path, "w").write(text.replace(anchor, block + anchor, 1))
PY
grep -n 'location /sfincs-ui/\|client_max_body_size 500m\|Database Admin Tools' $S/nid4ocean.copy
```

Expected: the three lines, in that order, with the new block directly above the anchor.

Render the unit template and check it: `sed -e 's|@PORT@|8840|g' -e 's|@PROD_SRC@|/srv/shiny-server/sfincs-ui-src|g' -e 's|@URL_PREFIX@|/sfincs-ui|g' deploy/sfincs-ui.service.in | systemd-analyze verify /dev/stdin 2>&1 | grep -v 'Command .* is not executable' || true` is unreliable for a stdin unit; instead `grep -c 'KillMode=process' deploy/sfincs-ui.service.in` must print 1 and the rendered `ExecStart` line must read `... --port 8840 --root-path /sfincs-ui`.

- [ ] **Step 7: Append the deploy section to `deploy/README.md`**

Append:

````markdown

## SFINCS UI (`/sfincs-ui/`)

The build-and-run app (`sfincs_ui/`) is a separate deployment from the
viewer: a standalone uvicorn systemd unit `sfincs-ui` on port 8840 behind
nginx, in the osmose pattern, because hour-long model runs must survive
deploys and idle browsers (spec section 5).

```bash
sudo bash deploy/deploy_ui.sh              # install or update
bash deploy/deploy_ui.sh --check           # state only, no root
sudo bash deploy/deploy_ui.sh --restart
sudo bash deploy/deploy_ui.sh --uninstall  # keeps /srv/sfincs-ui/workspace
```

| Target | Change | Backup |
|---|---|---|
| `/srv/shiny-server/sfincs-ui-src` | prod clone of this repo at `origin/main`, pip-installed editable into the shiny env | replaced by fetch |
| `/srv/sfincs-ui/workspace` | database and run directories, owned by `shiny` | kept on uninstall |
| `/etc/sfincs-ui.env` | SFINCS_UI_* ceilings, MAMBA_ROOT_PREFIX, SFINCS_CURONIAN_DB | `.bak.<stamp>` |
| `/etc/systemd/system/sfincs-ui.service` | unit with `KillMode=process` | replaced |
| `/etc/nginx/sites-available/nid4ocean` | `location /sfincs-ui/` before "Database Admin Tools" | `.bak.<stamp>` |
| `/var/www/html/services.json` | catalogue entry `sfincs-ui`, visible after the smoke test | `.bak-<stamp>` |

Order: deployer preflight and port refusals, clone, pip install, workspace
and env file, preflight as `shiny`, migrate and `create-admin` as `shiny`
(password prompted, or `SFINCS_UI_ADMIN_PASSWORD` in the environment of the
sudo call), unit restart and local HTTP 200, nginx insert and reload, HTTPS
smoke test of `/` and `/login`, catalogue made visible.

Re-running is idempotent; `create-admin` does nothing when an admin exists.
````

- [ ] **Step 8: Commit**

```bash
cd /home/razinka/sfincs
git add deploy/deploy_ui.sh deploy/sfincs-ui.service.in deploy/sfincs-ui.env.in deploy/sfincs-ui.nginx deploy/services-entry-ui.json deploy/README.md
git commit -m "deploy: deploy_ui.sh with the sfincs-ui unit (KillMode=process), nginx block and catalogue entry

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

- [ ] **Step 9: User-run acceptance (not the executor's)**

The user runs, in this session: `! sudo bash deploy/deploy_ui.sh` (the script prompts for the admin password unless `SFINCS_UI_ADMIN_PASSWORD` is set in the sudo environment). Then opens https://laguna.ku.lt/sfincs-ui/, logs in as the admin, sees the Admin tab with Users, Queue policy and Audit log, and the audit log shows the `login_success` row. Verify afterwards with `bash deploy/deploy_ui.sh --check` and `systemctl show sfincs-ui -p KillMode` printing `KillMode=process`. The push to `origin/main` must happen before the deploy, since the prod clone fetches from GitHub.

---

### Task 11: Package README and final verification

**Files:**
- Create: `sfincs_ui/README.md`
- Modify: `README.md` (repo root; one paragraph in the layout table pointing at `sfincs_ui/`)

**Interfaces:** none new.

- [ ] **Step 1: Write the package README**

`sfincs_ui/README.md`:

```markdown
# sfincs_ui

Web app for laguna.ku.lt through which a logged-in user creates a SFINCS
project from a template, launches a simulation on the server and inspects the
results. Design: `docs/superpowers/specs/2026-09-30-sfincs-ui-design.md`.
Milestone 1 (this state): configuration, database, auth, Admin page, CLI,
service unit and deploy script. Projects, runs and the queue arrive in
milestone 2.

## Layout

`sfincs_ui/` is the project directory (this file, `pyproject.toml`,
`alembic.ini`, `tests/`); `sfincs_ui/sfincs_ui/` is the package. Migrations
live inside the package so `init_db()` finds them from an editable install and
from the source tree alike.

## Run the tests

    cd sfincs_ui && /opt/micromamba/envs/shiny/bin/python -m pytest -q

Do not `pip install` the dev tree into the shared env: production installs the
prod clone editable into the same env (`deploy/deploy_ui.sh`).

## Run locally

    export SFINCS_UI_WORKSPACE=$HOME/sfincs-ui-workspace SFINCS_UI_SECURE_COOKIES=false SFINCS_UI_PORT=8899
    cd sfincs_ui
    /opt/micromamba/envs/shiny/bin/python -m sfincs_ui migrate
    /opt/micromamba/envs/shiny/bin/python -m sfincs_ui create-admin --username admin
    /opt/micromamba/envs/shiny/bin/python -m sfincs_ui serve

Then open http://127.0.0.1:8899/ and log in. `SECURE_COOKIES=false` is only
for plain-http development; production keeps the default.

## Configuration

Every setting is an `SFINCS_UI_*` environment variable (`sfincs_ui/config.py`).
`WORKSPACE` is required. Env values are ceilings and defaults; an admin lowers
`max_simulations`, `max_threads`, `retention_days` and `quota_gb` on the Admin
page's Queue policy tab. `MIN_FREE_GB` and `UPLOAD_MAX_MB` are env-only.

## Schema changes

    cd sfincs_ui && SFINCS_UI_WORKSPACE=/tmp/x /opt/micromamba/envs/shiny/bin/python -m alembic -c alembic.ini revision --autogenerate -m "describe"

Review the generated file under `sfincs_ui/migrations/versions/`; `env.py`
must import every model module or autogenerate proposes dropping its tables
(`tests/test_db_init.py` guards this).

## Deployment

`sudo bash deploy/deploy_ui.sh` from the repo root; see `deploy/README.md`.
```

Add to the repository `README.md` layout table a row after the `app/` row:

```markdown
| `sfincs_ui/` | Build-and-run web app (login, projects, runs); milestone 1 shipped, see `sfincs_ui/README.md` |
```

(Find the table with `grep -n '| \`app/\`' README.md`; if the row format differs, match it.)

- [ ] **Step 2: Full verification**

Run, from the repo root:

```bash
cd /home/razinka/sfincs/sfincs_ui && /opt/micromamba/envs/shiny/bin/python -m pytest -q
cd /home/razinka/sfincs && grep -rniE 'shyfem|tutorial|feedback' sfincs_ui/sfincs_ui/ ; echo "grep exit $? (1 means clean)"
git diff --stat main -- app/ deploy/deploy.sh
bash -n deploy/deploy_ui.sh && echo syntax-ok
```

Expected: all tests pass; the grep prints nothing and exits 1; the diff is empty; `syntax-ok`.

- [ ] **Step 3: Commit**

```bash
cd /home/razinka/sfincs
git add sfincs_ui/README.md README.md
git commit -m "sfincs_ui: README for running, testing and deploying milestone 1

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

## Deferred from this milestone (recorded so later plans pick them up)

- `projects`, `runs`, `jobs` tables, the queue, the plane-beach template: milestone 2. Its first migration follows `0001_initial`.
- The active-simulate check before restart and the explicit kill of detached stages in `--uninstall` (two `MILESTONE 2` comments in `deploy_ui.sh`).
- Login rate limiting. SHYFEM UI has a `RateLimitMiddleware`; the spec does not ask for one and the copied `authenticate` already equalises timing for unknown users. Revisit when the app is public.
- Preflight item "`from sfincs_viewer import map_core` imports in the model env": milestone 4, when the package exists.
- Preflight item "the gauge database opens read-only through `common.read_table`": milestone 3, together with the `SFINCS_CURONIAN_DB` rewrite of `curonian/common.py`. Milestone 1 opens the file with `sqlite3` from the UI process instead.
- Seeding `settings.max_threads` to 8 under a 16 ceiling (see the note in Task 10 Step 2).
- `access_control.can_view_run` / `can_modify_run` and the typed exceptions (`NotAllowed`, `QueueFull`, `QuotaExceeded`, `TemplateError`, `BuildError`): they need runs, so milestone 2 (modify, queue, quota) and milestone 4 (view, baselines).
- Admin page "storage by user": milestone 6 with retention and quotas.
