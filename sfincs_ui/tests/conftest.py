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
