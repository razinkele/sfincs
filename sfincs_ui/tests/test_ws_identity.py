"""The per-call authorization check: identity is re-read from the database every time."""

import pytest

from sfincs_ui.services.auth_service import AuthService
from sfincs_ui.services.ws_identity import resolve_identity


@pytest.fixture
def auth(db):
    return AuthService(session_factory=db)


@pytest.fixture
def admin_login(auth):
    """Two admins (so the first may be demoted or deleted), the first logged in."""
    a = auth.create_user("root", "pw12345678", role="admin")
    auth.create_user("backup", "pw12345678", role="admin")
    sess = auth.create_session(a["id"])
    ws = auth.create_ws_token(a["id"], sess)
    return a, sess, ws


def test_no_tokens_is_anonymous(auth):
    assert resolve_identity(None, None, auth) is None
    assert resolve_identity("", "", auth) is None


def test_admin_resolves_via_ws_token_and_via_cookie(auth, admin_login):
    a, sess, ws = admin_login
    assert resolve_identity(ws, None, auth)["role"] == "admin"
    assert resolve_identity(None, sess, auth)["id"] == a["id"]


def test_forged_ws_token_falls_back_to_cookie(auth, admin_login):
    a, sess, _ = admin_login
    assert resolve_identity("forged", sess, auth)["id"] == a["id"]
    assert resolve_identity("forged", None, auth) is None


def test_logout_revokes_both_paths(auth, admin_login):
    _, sess, ws = admin_login
    auth.delete_session(sess)
    assert resolve_identity(ws, None, auth) is None
    assert resolve_identity(None, sess, auth) is None
    assert resolve_identity(ws, sess, auth) is None


def test_deactivation_revokes(auth, admin_login):
    a, sess, ws = admin_login
    auth.update_user(a["id"], is_active=False)
    assert resolve_identity(ws, sess, auth) is None
    # Reactivation does not resurrect the old login: the rows were purged.
    auth.update_user(a["id"], is_active=True)
    assert resolve_identity(ws, sess, auth) is None


def test_demotion_takes_effect_on_next_call(auth, admin_login):
    a, sess, ws = admin_login
    auth.update_user(a["id"], role="user")
    # Demotion purges the admin-era login outright ...
    assert resolve_identity(ws, sess, auth) is None
    # ... and a fresh login resolves with the new role.
    fresh = auth.create_session(a["id"])
    assert resolve_identity(None, fresh, auth)["role"] == "user"


def test_promotion_keeps_the_session(auth, admin_login):
    other = auth.create_user("dave", "pw12345678")
    sess = auth.create_session(other["id"])
    auth.update_user(other["id"], role="admin")
    assert resolve_identity(None, sess, auth)["role"] == "admin"


def test_deletion_revokes(auth, admin_login):
    a, sess, ws = admin_login
    auth.delete_user(a["id"])
    assert resolve_identity(ws, sess, auth) is None


def test_password_reset_ends_existing_logins(auth, admin_login):
    a, sess, ws = admin_login
    auth.reset_password(a["id"], "another-password")
    assert resolve_identity(ws, None, auth) is None
    assert resolve_identity(None, sess, auth) is None


def test_harmless_update_keeps_the_session(auth, admin_login):
    a, sess, ws = admin_login
    auth.update_user(a["id"], display_name="Root")
    assert resolve_identity(ws, sess, auth)["display_name"] == "Root"


def test_revocation_only_touches_that_user(auth, admin_login):
    other = auth.create_user("carol", "pw12345678")
    other_sess = auth.create_session(other["id"])
    a, _, _ = admin_login
    auth.update_user(a["id"], is_active=False)
    assert resolve_identity(None, other_sess, auth)["username"] == "carol"
