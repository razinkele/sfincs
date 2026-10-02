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
