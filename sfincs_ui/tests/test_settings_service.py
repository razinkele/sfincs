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
