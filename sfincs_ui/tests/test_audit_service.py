import json

from sfincs_ui.services.audit_service import AuditService


def test_log_and_query(db):
    svc = AuditService(session_factory=db)
    svc.log("alice", "login_success", ip_address="10.0.0.1")
    svc.log("alice", "settings_update", target="max_threads", detail={"old": 8, "new": 12})
    svc.log("bob", "login_failed")
    rows = svc.query()
    assert [r["action"] for r in rows] == ["login_failed", "settings_update", "login_success"]
    assert svc.count() == 3
    assert svc.count(username="alice") == 2
    assert svc.query(action="settings_update")[0]["target"] == "max_threads"
    assert json.loads(svc.query(action="settings_update")[0]["detail"]) == {"old": 8, "new": 12}
    assert svc.distinct_actions() == ["login_failed", "login_success", "settings_update"]


def test_string_detail_is_kept_verbatim(db):
    svc = AuditService(session_factory=db)
    svc.log("alice", "note", detail="plain text")
    assert svc.query()[0]["detail"] == "plain text"


def test_user_id_survives_user_deletion(db):
    from sfincs_ui.services.auth_service import AuthService

    auth = AuthService(session_factory=db)
    u = auth.create_user("ivy", "pw12345678")
    svc = AuditService(session_factory=db)
    svc.log("ivy", "login_success", user_id=u["id"])
    auth.delete_user(u["id"])
    row = svc.query()[0]
    assert row["username"] == "ivy" and row["user_id"] is None
