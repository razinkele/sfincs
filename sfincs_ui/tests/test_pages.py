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

    def test_identity_script_always_pushes_wsauth(self):
        # ui.head_content is hoisted out of str(Tag), so assert on the script source.
        from sfincs_ui.app import _WS_IDENTITY_JS

        assert "data.ws_token || ''" in _WS_IDENTITY_JS
        assert "if (data.ws_token &&" not in _WS_IDENTITY_JS

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


class TestAdminHelpers:
    def test_collect_policy_changes_validates_everything_first(self):
        before = {"a": 1, "b": 2}
        with pytest.raises(ValueError):
            admin._collect_policy_changes({"a": 5, "b": None}, before)
        with pytest.raises((ValueError, TypeError)):
            admin._collect_policy_changes({"a": 5, "b": "x"}, before)

    def test_collect_policy_changes_uses_validator_on_every_key_before_saving(self):
        def validate(key, value):
            if int(value) > 10:
                raise ValueError(f"{key} above ceiling")
            return int(value)

        with pytest.raises(ValueError, match="b above ceiling"):
            admin._collect_policy_changes({"a": 5, "b": 99}, {"a": 1, "b": 2}, validate=validate)

    def test_collect_policy_changes_returns_only_changes(self):
        assert admin._collect_policy_changes({"a": 1, "b": 3.0}, {"a": 1, "b": 2}) == {"b": {"old": 2, "new": 3}}

    def test_audit_as_refuses_without_actor(self):
        from unittest.mock import MagicMock

        audit = MagicMock()
        assert admin._audit_as(None, audit, "create_user", target="user:x") is False
        audit.log.assert_not_called()

    def test_audit_as_writes_with_actor(self):
        from unittest.mock import MagicMock

        audit = MagicMock()
        assert admin._audit_as({"id": 7, "username": "root"}, audit, "create_user", target="user:x", detail={"role": "user"}) is True
        audit.log.assert_called_once_with("root", "create_user", target="user:x", detail={"role": "user"}, user_id=7)
