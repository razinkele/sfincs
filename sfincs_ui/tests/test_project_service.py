import pytest

from sfincs_ui.config import Config
from sfincs_ui.exceptions import NotAllowed, NotFound, TemplateError
from sfincs_ui.services.auth_service import AuthService
from sfincs_ui.services.project_service import ProjectService
from tests.fake_template import FakeTemplate


@pytest.fixture
def users(db):
    auth = AuthService(session_factory=db)
    admin, _ = auth.ensure_admin("root", "pw12345678")
    alice = auth.create_user("alice", "pw12345678")
    bob = auth.create_user("bob", "pw12345678")
    return admin, alice, bob


@pytest.fixture
def svc(db, tmp_path):
    return ProjectService(Config(workspace=tmp_path), session_factory=db, templates={"fake": FakeTemplate()})


def test_examples_are_seeded_once(svc):
    assert svc.ensure_examples() == 1 and svc.ensure_examples() == 0
    ex = svc.examples()
    assert len(ex) == 1 and ex[0]["owner_id"] is None and ex[0]["name"] == "Fake example" and ex[0]["template"] == "fake"


def test_create_list_get_rename_update(svc, users):
    _, alice, bob = users
    p = svc.create(alice, "fake", "My project")
    assert p["owner_id"] == alice["id"] and p["settings"] == {"alpha": 0.5} and p["template_title"] == "Fake"
    assert svc.project_dir(p["id"]).is_dir()
    assert [x["id"] for x in svc.list_for(alice)] == [p["id"]] and svc.list_for(bob) == []
    assert svc.get(alice, p["id"])["name"] == "My project"
    with pytest.raises(NotAllowed):
        svc.get(bob, p["id"])
    with pytest.raises(NotFound):
        svc.get(alice, "nope")
    svc.rename(alice, p["id"], "Renamed")
    updated = svc.update_settings(alice, p["id"], {"alpha": "0.8", "evil": 1})
    assert updated["settings"] == {"alpha": 0.8} and updated["name"] == "Renamed"
    with pytest.raises(TemplateError):
        svc.update_settings(alice, p["id"], {"alpha": 5})
    with pytest.raises(NotAllowed):
        svc.update_settings(bob, p["id"], {"alpha": 0.2})


def test_clone_copies_settings_only_and_examples_are_usable_by_all(svc, users):
    _, alice, bob = users
    svc.ensure_examples()
    ex = svc.examples()[0]
    c = svc.clone(bob, ex["id"], "Bob's copy")
    assert c["owner_id"] == bob["id"] and c["settings"] == ex["settings"] and c["id"] != ex["id"]
    with pytest.raises(NotAllowed):
        svc.rename(bob, ex["id"], "hijack")  # system project: admin only
    with pytest.raises(NotAllowed):
        svc.create(None, "fake", "anon")
    with pytest.raises(TemplateError):
        svc.create(alice, "unknown", "x")


def test_delete_removes_directory_and_refuses_while_active(svc, users, db, tmp_path):
    from tests.runner_helpers import make_run
    from sfincs_ui.models import Run

    _, alice, bob = users
    p = svc.create(alice, "fake", "P")
    with pytest.raises(NotAllowed):
        svc.delete(bob, p["id"])
    svc.delete(alice, p["id"])
    assert not svc.project_dir(p["id"]).exists() and svc.list_for(alice) == []
    run_id = make_run(db, tmp_path, "fake", {"alpha": 0.5}, owner_id=alice["id"])
    s = db(); project_id = s.get(Run, run_id).project_id; s.get(Run, run_id).status = "running"; s.commit(); s.close()
    with pytest.raises(NotAllowed, match="active"):
        svc.delete(alice, project_id)
