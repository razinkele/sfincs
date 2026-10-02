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
    assert {"users", "sessions", "ws_tokens", "audit_log", "settings", "projects", "runs", "jobs", "alembic_version"} <= tables
    with engine.connect() as conn:
        version = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
    assert version == _head_revision() == "0002_projects_runs_jobs"


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
