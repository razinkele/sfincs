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
