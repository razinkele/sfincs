import pytest

from sfincs_ui.services.auth_service import AuthService


@pytest.fixture
def auth(db):
    return AuthService(session_factory=db)


def test_create_and_authenticate(auth):
    u = auth.create_user("alice", "correct horse", role="user", email="a@example.org")
    assert u["username"] == "alice" and u["role"] == "user" and u["is_active"] is True
    assert auth.authenticate("alice", "correct horse")["id"] == u["id"]
    assert auth.authenticate("alice", "wrong") is None
    assert auth.authenticate("nobody", "x") is None


def test_email_is_optional(auth):
    u = auth.create_user("bob", "password123")
    assert u["email"] is None


def test_duplicate_username_rejected(auth):
    auth.create_user("alice", "pw12345678")
    with pytest.raises(ValueError):
        auth.create_user("alice", "pw12345678")


def test_unsafe_username_rejected(auth):
    for bad in ["", "..", "a/b", "-dash", "x" * 65]:
        with pytest.raises(ValueError):
            auth.create_user(bad, "pw12345678")


def test_inactive_user_cannot_log_in(auth):
    u = auth.create_user("carol", "pw12345678")
    auth.update_user(u["id"], is_active=False)
    assert auth.authenticate("carol", "pw12345678") is None


def test_session_round_trip_and_logout(auth):
    u = auth.create_user("dave", "pw12345678")
    tok = auth.create_session(u["id"], ttl_hours=1, ip_address="10.0.0.1")
    assert auth.validate_session(tok)["username"] == "dave"
    assert auth.delete_session(tok) is True
    assert auth.validate_session(tok) is None
    assert auth.validate_session("forged") is None


def test_expired_session_is_removed(auth):
    u = auth.create_user("erin", "pw12345678")
    tok = auth.create_session(u["id"], ttl_hours=0)
    assert auth.validate_session(tok) is None
    assert auth.cleanup_expired_sessions() == 0  # already purged by validate


def test_ws_token_inherits_session_validity(auth):
    u = auth.create_user("frank", "pw12345678")
    sess = auth.create_session(u["id"])
    ws = auth.create_ws_token(u["id"], sess)
    assert auth.validate_ws_token(ws)["username"] == "frank"
    auth.delete_session(sess)
    assert auth.validate_ws_token(ws) is None


def test_delete_last_admin_refused(auth):
    admin, _ = auth.ensure_admin("root", "pw12345678")
    with pytest.raises(ValueError):
        auth.delete_user(admin["id"])
    # an inactive second admin does not count as a usable replacement
    other = auth.create_user("other", "pw12345678", role="admin")
    auth.update_user(other["id"], is_active=False)
    with pytest.raises(ValueError):
        auth.delete_user(admin["id"])


def test_update_user_refuses_to_strip_last_admin(auth):
    """Review Focus 1: the only admin must not demote or deactivate themself."""
    admin, _ = auth.ensure_admin("root", "pw12345678")
    with pytest.raises(ValueError, match="last admin"):
        auth.update_user(admin["id"], role="user")
    with pytest.raises(ValueError, match="last admin"):
        auth.update_user(admin["id"], is_active=False)
    assert auth.list_users()[0]["role"] == "admin"
    second = auth.create_user("second", "pw12345678", role="admin")
    assert auth.update_user(admin["id"], role="user")["role"] == "user"
    assert auth.list_users()[1]["id"] == second["id"]


def test_ensure_admin_is_idempotent(auth):
    first, created = auth.ensure_admin("root", "pw12345678")
    assert created is True
    again, created_again = auth.ensure_admin("root", "another-password")
    assert created_again is False and again["id"] == first["id"]
    assert auth.authenticate("root", "pw12345678") is not None
    assert auth.authenticate("root", "another-password") is None


def test_reset_password(auth):
    u = auth.create_user("gina", "old-password")
    assert auth.reset_password(u["id"], "new-password") is True
    assert auth.authenticate("gina", "new-password") is not None
    assert auth.reset_password(999, "x") is False


def test_delete_user_removes_sessions_and_tokens(auth, db):
    from sfincs_ui.models import AuthSession, WSAuthToken

    u = auth.create_user("hank", "pw12345678")
    sess = auth.create_session(u["id"])
    auth.create_ws_token(u["id"], sess)
    assert auth.delete_user(u["id"]) is True
    s = db()
    try:
        assert s.query(AuthSession).count() == 0
        assert s.query(WSAuthToken).count() == 0
    finally:
        s.close()


def test_delete_user_refused_while_they_own_an_active_run(auth, db, tmp_path):
    """Deleting the owner would cascade away live run and job rows while the solver keeps running."""
    from sfincs_ui.models import Project, Run
    from tests.runner_helpers import make_run

    u = auth.create_user("ivy", "pw12345678")
    run_id = make_run(db, tmp_path, "fake", {"alpha": 0.7}, owner_id=u["id"])
    s = db()
    try:
        run = s.get(Run, run_id); run.status = "running"; project_id = run.project_id; s.commit()
    finally:
        s.close()
    with pytest.raises(ValueError, match="active run"):
        auth.delete_user(u["id"])
    s = db()
    try:
        assert s.get(Run, run_id) is not None
        s.get(Run, run_id).status = "finished"; s.commit()
    finally:
        s.close()
    assert auth.delete_user(u["id"]) is True
    s = db()
    try:
        assert s.get(Project, project_id) is None and s.get(Run, run_id) is None
    finally:
        s.close()
