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
