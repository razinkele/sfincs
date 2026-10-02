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
            assert panel in r.text  # nav titles are static; the examples list is a server render, asserted above


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
