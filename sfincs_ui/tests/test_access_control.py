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
    """Only the owner or an admin may act on a run; baselines never."""
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


@pytest.mark.parametrize("flag,expected", [(True, True), (1, True), (None, False), (0, False), (False, False)])
def test_is_active_values_fail_closed(flag, expected):
    user = {**OWNER, "is_active": flag}
    assert ac.can_modify_run(user, _run()) is expected
    assert ac.can_view_run(user, _run()) is expected


def test_absent_is_active_means_active():
    user = {k: v for k, v in OWNER.items() if k != "is_active"}
    assert ac.can_modify_run(user, _run()) is True


@pytest.mark.parametrize("user", [{"role": "user", "is_active": True}, {"id": None, "role": "user", "is_active": True}])
def test_nameless_user_never_matches_an_unowned_resource(user):
    assert not ac.can_view_run(user, _run(owner_id=None))
    assert not ac.can_modify_run(user, _run(owner_id=None))
    assert not ac.can_modify_project(user, {"id": "e", "owner_id": None})


def test_inactive_admin_has_no_rights():
    inactive_admin = {**ADMIN, "is_active": False}
    assert not ac.is_admin(inactive_admin)
    assert not ac.can_modify_run(inactive_admin, _run())
    assert not ac.can_modify_project(inactive_admin, {"id": "e", "owner_id": None})
    assert not ac.can_use_project(inactive_admin, {"id": "e", "owner_id": None})
    assert ac.can_view_run(inactive_admin, _run(baseline=True))  # baselines are public to everyone


@pytest.mark.parametrize("user,project,expected", [
    (OWNER, {"id": "p", "owner_id": 2}, True), (OTHER, {"id": "p", "owner_id": 2}, False),
    (ADMIN, {"id": "e", "owner_id": None}, True), (OWNER, {"id": "e", "owner_id": None}, False), (None, {"id": "e", "owner_id": None}, False),
])
def test_can_modify_project_matrix(user, project, expected):
    assert ac.can_modify_project(user, project) is expected


def test_require_project_helpers():
    system = {"id": "e", "owner_id": None}
    with pytest.raises(NotAllowed):
        ac.require_modify_project(OWNER, system)
    ac.require_modify_project(ADMIN, system)
    with pytest.raises(NotAllowed):
        ac.require_use_project(None, system)
    ac.require_use_project(OTHER, system)
