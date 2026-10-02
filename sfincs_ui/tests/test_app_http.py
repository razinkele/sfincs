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
