import pytest

from sfincs_ui.exceptions import NotAllowed, SfincsUiError
from sfincs_ui.services import access_control as ac

ADMIN = {"id": 1, "username": "root", "role": "admin", "is_active": True}
OWNER = {"id": 2, "username": "alice", "role": "user", "is_active": True}
OTHER = {"id": 3, "username": "bob", "role": "user", "is_active": True}


def _run(owner_id=2, public=False, baseline=False):
    return {"id": "r", "owner_id": owner_id, "public": public, "baseline": baseline}


@pytest.mark.parametrize("user,run,expected", [
    (None, _run(), False), (None, _run(public=True), True), (None, _run(baseline=True), True),
    (OTHER, _run(), False), (OTHER, _run(public=True), True),
    (OWNER, _run(), True), (ADMIN, _run(), True), (ADMIN, _run(owner_id=None), True),
])
def test_can_view_run_matrix(user, run, expected):
    assert ac.can_view_run(user, run) is expected


@pytest.mark.parametrize("user,run,expected", [
    (None, _run(), False), (OTHER, _run(), False), (OTHER, _run(public=True), False),
    (OWNER, _run(), True), (ADMIN, _run(), True), (ADMIN, _run(baseline=True), False), (OWNER, _run(baseline=True), False),
])
def test_can_modify_run_matrix(user, run, expected):
    """Review Focus 5: only the owner or an admin may act on a run; baselines never."""
    assert ac.can_modify_run(user, run) is expected


def test_project_rules():
    own = {"id": "p", "owner_id": 2}
    system = {"id": "e", "owner_id": None}
    assert ac.can_modify_project(OWNER, own) and not ac.can_modify_project(OTHER, own)
    assert ac.can_modify_project(ADMIN, system) and not ac.can_modify_project(OWNER, system)
    assert ac.can_use_project(OWNER, own) and ac.can_use_project(OTHER, system) and not ac.can_use_project(None, system)
    assert not ac.can_use_project(OTHER, own)


def test_require_helpers_raise_not_allowed():
    with pytest.raises(NotAllowed):
        ac.require_modify_run(OTHER, _run())
    with pytest.raises(NotAllowed):
        ac.require_view_run(None, _run())
    with pytest.raises(NotAllowed):
        ac.require_user(None)
    assert ac.require_user(OWNER) == OWNER
    ac.require_view_run(None, _run(public=True))  # no raise
    assert issubclass(NotAllowed, SfincsUiError)


def test_inactive_user_has_no_rights():
    inactive = {**OWNER, "is_active": False}
    assert not ac.can_modify_run(inactive, _run()) and not ac.can_view_run(inactive, _run())
