import asyncio

import pytest

from sfincs_ui.exceptions import LaunchRefused, NotAllowed, NotFound
from sfincs_ui.services import run_service as rs
from sfincs_ui.services.auth_service import AuthService
from sfincs_ui.services.project_service import ProjectService
from sfincs_ui.services.run_service import RunService
from sfincs_ui.services.settings_service import SettingsService
from tests.fake_template import FakeTemplate


@pytest.fixture
def world(db, tmp_path, runner, monkeypatch):
    from sfincs_ui.config import get_config
    cfg = get_config()  # set by the runner fixture: max_simulations=1, max_threads=4, min_free_gb=10, fake binary
    auth = AuthService(session_factory=db)
    admin, _ = auth.ensure_admin("root", "pw12345678")
    alice = auth.create_user("alice", "pw12345678")
    bob = auth.create_user("bob", "pw12345678")
    monkeypatch.setattr(rs, "free_space_gb", lambda path: 500.0)
    templates = {"fake": FakeTemplate()}
    projects = ProjectService(cfg, session_factory=db, templates=templates)
    settings = SettingsService(cfg, session_factory=db)
    runs = RunService(cfg, settings, projects, runner, session_factory=db, templates=templates)
    project = projects.create(alice, "fake", "P", {"alpha": 0.7})
    return {"admin": admin, "alice": alice, "bob": bob, "projects": projects, "runs": runs, "project": project, "cfg": cfg}


async def test_launch_runs_to_completion_and_exposes_downloads(world, runner):
    await runner.start()
    r = world["runs"].launch(world["alice"], world["project"]["id"], "first", 2)
    assert r["status"] == "queued" and r["threads"] == 2 and r["owner_id"] == world["alice"]["id"]
    await runner.wait(r["id"], timeout=20)
    got = world["runs"].get(world["alice"], r["id"])
    assert got["status"] == "finished" and [s["stage"] for s in got["stages"]] == ["build", "simulate"]
    assert world["runs"].download_path(world["alice"], r["id"], "sfincs_his.nc").is_file()
    assert "+alpha           = 0.7" in world["runs"].download_path(world["alice"], r["id"], "overrides.diff").read_text()
    with pytest.raises(NotFound):
        world["runs"].download_path(world["alice"], r["id"], "sfincs_map.nc")
    stage, text = world["runs"].log_tail(world["alice"], r["id"])
    assert stage == "simulate" and "Simulation finished" in text
    assert world["runs"].progress(world["alice"], r["id"])["percent"] == 100


def test_launch_refusals(world, monkeypatch):
    runs, alice, pid = world["runs"], world["alice"], world["project"]["id"]
    with pytest.raises(LaunchRefused, match="4"):
        runs.launch(alice, pid, "x", 9)
    with pytest.raises(LaunchRefused):
        runs.launch(alice, pid, "x", 0)
    with pytest.raises(LaunchRefused, match="name"):
        runs.launch(alice, pid, "  ", 1)
    with pytest.raises(NotAllowed):
        runs.launch(world["bob"], pid, "x", 1)
    with pytest.raises(NotAllowed):
        runs.launch(None, pid, "x", 1)
    monkeypatch.setattr(rs, "free_space_gb", lambda path: 2.5)
    with pytest.raises(LaunchRefused, match="2.5 GB free.*10 GB"):
        runs.launch(alice, pid, "x", 1)


async def test_cancel_other_users_run_refused(world, runner, monkeypatch):
    """Review Focus 5."""
    monkeypatch.setenv("FAKE_STEPS", "100"); monkeypatch.setenv("FAKE_SLEEP", "0.1")
    await runner.start()
    r = world["runs"].launch(world["alice"], world["project"]["id"], "slow", 1)
    deadline = asyncio.get_running_loop().time() + 30
    while world["runs"].get(world["alice"], r["id"])["status"] != "running":
        assert asyncio.get_running_loop().time() < deadline
        await asyncio.sleep(0.02)
    with pytest.raises(NotAllowed):
        await world["runs"].cancel(world["bob"], r["id"])
    with pytest.raises(NotAllowed):
        world["runs"].set_pinned(world["bob"], r["id"], True)
    with pytest.raises(NotAllowed):
        world["runs"].set_public(world["bob"], r["id"], True)
    with pytest.raises(NotAllowed):
        world["runs"].log_tail(world["bob"], r["id"])
    assert world["runs"].get(world["alice"], r["id"])["status"] == "running"
    await world["runs"].cancel(world["admin"], r["id"])  # an admin may
    assert world["runs"].get(world["alice"], r["id"])["status"] == "cancelled"


async def test_download_path_other_users_private_run_refused_until_public(world, runner):
    """Review Focus 5."""
    await runner.start()
    r = world["runs"].launch(world["alice"], world["project"]["id"], "p", 1)
    await runner.wait(r["id"], timeout=20)
    with pytest.raises(NotAllowed):
        world["runs"].download_path(world["bob"], r["id"], "sfincs_his.nc")
    with pytest.raises(NotAllowed):
        world["runs"].get(None, r["id"])
    world["runs"].set_public(world["alice"], r["id"], True)
    assert world["runs"].download_path(world["bob"], r["id"], "sfincs_his.nc").is_file()
    assert world["runs"].get(None, r["id"])["public"] is True
    world["runs"].set_pinned(world["alice"], r["id"], True)
    assert world["runs"].get(world["alice"], r["id"])["pinned"] is True


async def test_list_for_scopes_and_running_jobs(world, runner, monkeypatch):
    monkeypatch.setenv("FAKE_STEPS", "100"); monkeypatch.setenv("FAKE_SLEEP", "0.1")
    await runner.start()
    r = world["runs"].launch(world["alice"], world["project"]["id"], "mine", 1)
    assert [x["id"] for x in world["runs"].list_for(world["alice"])] == [r["id"]]
    assert world["runs"].list_for(world["bob"]) == []
    assert [x["id"] for x in world["runs"].list_for(world["admin"])] == [r["id"]]
    deadline = asyncio.get_running_loop().time() + 30
    while not world["runs"].running_jobs(world["admin"]):
        assert asyncio.get_running_loop().time() < deadline
        await asyncio.sleep(0.02)
    assert world["runs"].running_jobs(world["admin"])[0]["run_id"] == r["id"]
    with pytest.raises(NotAllowed):
        world["runs"].running_jobs(world["alice"])
    await world["runs"].cancel(world["alice"], r["id"])


def test_free_space_gb(tmp_path):
    assert rs.free_space_gb(tmp_path) > 0


def test_launch_failure_before_submit_leaves_no_row(world, monkeypatch):
    from sfincs_ui.services import run_service as rs_mod

    def boom(run_dir, settings):
        raise OSError("disk full")

    monkeypatch.setattr(rs_mod, "write_settings", boom)
    with pytest.raises(OSError):
        world["runs"].launch(world["alice"], world["project"]["id"], "x", 1)
    assert world["runs"].list_for(world["alice"]) == []
    world["projects"].delete(world["alice"], world["project"]["id"])  # must not be blocked by a phantom active run
