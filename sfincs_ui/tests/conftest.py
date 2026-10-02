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


@pytest.fixture(autouse=True, scope="session")
def _fast_argon2():
    """Cheap argon2 parameters for the suite; production keeps the library defaults."""
    from argon2 import PasswordHasher

    from sfincs_ui.services import auth_service

    cheap = PasswordHasher(time_cost=1, memory_cost=8 * 1024, parallelism=1)
    auth_service._ph = cheap
    auth_service._DUMMY_HASH = cheap.hash("x")
    yield


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
                        max_simulations=1, max_threads=4, min_free_gb=10)
    config.set_config(cfg)
    r = JobRunner(cfg, SettingsService(cfg, session_factory=db), session_factory=db,
                  templates={"fake": FakeTemplate(), "fake_v": FakeTemplate(with_validation=True)}, poll_interval=0.05, grace_s=2.0)
    yield r
    for pid in list(r.spawned_pids):
        try:
            os.killpg(pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
