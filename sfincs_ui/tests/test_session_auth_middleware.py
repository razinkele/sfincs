from unittest.mock import AsyncMock, MagicMock

import pytest

from sfincs_ui.middleware.client_ip import get_client_ip
from sfincs_ui.middleware.session_auth import (
    CSRF_COOKIE,
    SESSION_COOKIE,
    SessionAuthMiddleware,
    get_current_user,
)

USER = {"id": 1, "username": "alice", "display_name": None, "email": None, "role": "user", "is_active": True}


def _scope(method="GET", path="/", cookies="", root_path="", type_="http", client=("203.0.113.5", 1234), headers=None):
    hdrs = list(headers or [])
    if cookies:
        hdrs.append((b"cookie", cookies.encode()))
    scope = {"type": type_, "path": path, "headers": hdrs, "client": client}
    if type_ == "http":
        scope["method"] = method
    if root_path:
        scope["root_path"] = root_path
    return scope


def _capture():
    seen = {}

    async def app(scope, receive, send):
        seen["user"] = get_current_user()
        seen["called"] = True

    return app, seen


def _responses(send):
    return [c[0][0] for c in send.call_args_list]


class TestPassThrough:
    async def test_no_cookie_is_anonymous_not_redirect(self):
        app, seen = _capture()
        mw = SessionAuthMiddleware(app, MagicMock())
        await mw(_scope(path="/"), AsyncMock(), AsyncMock())
        assert seen["called"] and seen["user"] is None

    async def test_valid_cookie_sets_user(self):
        auth = MagicMock(); auth.validate_session.return_value = USER
        app, seen = _capture()
        await SessionAuthMiddleware(app, auth)(_scope(cookies=f"{SESSION_COOKIE}=tok"), AsyncMock(), AsyncMock())
        auth.validate_session.assert_called_once_with("tok")
        assert seen["user"] == USER

    async def test_invalid_cookie_is_anonymous(self):
        """Review Focus 3: a forged or expired cookie renders the page as anonymous."""
        auth = MagicMock(); auth.validate_session.return_value = None
        app, seen = _capture()
        await SessionAuthMiddleware(app, auth)(_scope(cookies=f"{SESSION_COOKIE}=stale"), AsyncMock(), AsyncMock())
        assert seen["called"] and seen["user"] is None

    async def test_websocket_anonymous_passes_through(self):
        """Review Focus 3: the websocket is accepted with user=None, never closed with 4001."""
        auth = MagicMock(); auth.validate_session.return_value = None
        app, seen = _capture()
        send = AsyncMock()
        await SessionAuthMiddleware(app, auth)(_scope(type_="websocket"), AsyncMock(), send)
        assert seen["called"] and seen["user"] is None
        assert not any(m.get("type") == "websocket.close" for m in _responses(send))

    async def test_websocket_with_cookie_sets_user(self):
        auth = MagicMock(); auth.validate_session.return_value = USER
        app, seen = _capture()
        await SessionAuthMiddleware(app, auth)(_scope(type_="websocket", cookies=f"{SESSION_COOKIE}=tok"), AsyncMock(), AsyncMock())
        assert seen["user"] == USER

    async def test_lifespan_passes_through(self):
        app, seen = _capture()
        await SessionAuthMiddleware(app, MagicMock())({"type": "lifespan"}, AsyncMock(), AsyncMock())
        assert seen["called"]

    async def test_contextvar_is_reset_after_request(self):
        auth = MagicMock(); auth.validate_session.return_value = USER
        app, _ = _capture()
        await SessionAuthMiddleware(app, auth)(_scope(cookies=f"{SESSION_COOKIE}=tok"), AsyncMock(), AsyncMock())
        assert get_current_user() is None


class TestRootPath:
    async def test_login_route_matches_with_root_path_in_scope_path(self):
        """uvicorn --root-path /sfincs-ui delivers path=/sfincs-ui/login."""
        send = AsyncMock()
        inner = AsyncMock()
        await SessionAuthMiddleware(inner, MagicMock())(_scope(path="/sfincs-ui/login", root_path="/sfincs-ui"), AsyncMock(), send)
        inner.assert_not_called()
        assert _responses(send)[0]["status"] == 200 and b"csrf_token" in _responses(send)[1]["body"]

    async def test_login_route_matches_without_root_path_in_scope_path(self):
        send = AsyncMock()
        inner = AsyncMock()
        await SessionAuthMiddleware(inner, MagicMock())(_scope(path="/login", root_path="/sfincs-ui"), AsyncMock(), send)
        inner.assert_not_called()
        assert _responses(send)[0]["status"] == 200

    async def test_whoami_under_root_path(self):
        auth = MagicMock(); auth.validate_session.return_value = None
        send = AsyncMock()
        await SessionAuthMiddleware(AsyncMock(), auth, root_path="/sfincs-ui")(_scope(path="/sfincs-ui/api/whoami", root_path="/sfincs-ui"), AsyncMock(), send)
        assert dict(_responses(send)[0]["headers"])[b"content-type"] == b"application/json"


class TestLogin:
    async def test_get_login_serves_form_with_csrf_cookie(self):
        send = AsyncMock()
        await SessionAuthMiddleware(AsyncMock(), MagicMock(), root_path="/sfincs-ui")(_scope(path="/login"), AsyncMock(), send)
        start, body = _responses(send)
        assert start["status"] == 200
        headers = dict(start["headers"])
        assert headers[b"content-type"].startswith(b"text/html")
        cookie = headers[b"set-cookie"].decode()
        assert cookie.startswith(f"{CSRF_COOKIE}=") and "Path=/sfincs-ui" in cookie and "Secure" in cookie
        assert b'action="/sfincs-ui/login"' in body["body"] and b"SFINCS" in body["body"]

    async def test_post_login_success_sets_cookie_and_redirects(self):
        auth = MagicMock()
        auth.authenticate.return_value = USER
        auth.create_session.return_value = "newtok"
        audit = MagicMock()
        mw = SessionAuthMiddleware(AsyncMock(), auth, audit_service=audit, root_path="/sfincs-ui", session_ttl_hours=2)
        receive = AsyncMock(return_value={"type": "http.request", "body": b"username=alice&password=pw&csrf_token=abc", "more_body": False})
        send = AsyncMock()
        await mw(_scope(method="POST", path="/login", cookies=f"{CSRF_COOKIE}=abc"), receive, send)
        start = _responses(send)[0]
        assert start["status"] == 302
        headers = dict(start["headers"])
        assert headers[b"location"] == b"/sfincs-ui/"
        cookie = headers[b"set-cookie"].decode()
        assert cookie.startswith(f"{SESSION_COOKIE}=newtok") and "HttpOnly" in cookie and "SameSite=Lax" in cookie
        assert "Max-Age=7200" in cookie and "Secure" in cookie
        auth.create_session.assert_called_once_with(1, ttl_hours=2, ip_address="203.0.113.5")
        auth.cleanup_expired_sessions.assert_called_once()
        assert audit.log.call_args.kwargs["action"] == "login_success"

    async def test_post_login_bad_password_rerenders_with_error_and_audits(self):
        auth = MagicMock(); auth.authenticate.return_value = None
        audit = MagicMock()
        mw = SessionAuthMiddleware(AsyncMock(), auth, audit_service=audit)
        receive = AsyncMock(return_value={"type": "http.request", "body": b"username=alice&password=bad&csrf_token=abc", "more_body": False})
        send = AsyncMock()
        await mw(_scope(method="POST", path="/login", cookies=f"{CSRF_COOKIE}=abc"), receive, send)
        start, body = _responses(send)
        assert start["status"] == 200 and b"Invalid username or password" in body["body"]
        assert audit.log.call_args.kwargs["action"] == "login_failed"
        auth.create_session.assert_not_called()

    async def test_post_login_csrf_mismatch_rejected(self):
        auth = MagicMock()
        mw = SessionAuthMiddleware(AsyncMock(), auth)
        receive = AsyncMock(return_value={"type": "http.request", "body": b"username=alice&password=pw&csrf_token=zzz", "more_body": False})
        send = AsyncMock()
        await mw(_scope(method="POST", path="/login", cookies=f"{CSRF_COOKIE}=abc"), receive, send)
        start, body = _responses(send)
        assert start["status"] == 200 and b"Invalid request" in body["body"]
        auth.authenticate.assert_not_called()

    async def test_post_login_body_in_chunks(self):
        auth = MagicMock(); auth.authenticate.return_value = USER; auth.create_session.return_value = "t"
        mw = SessionAuthMiddleware(AsyncMock(), auth)
        chunks = [
            {"type": "http.request", "body": b"username=alice&pass", "more_body": True},
            {"type": "http.request", "body": b"word=pw&csrf_token=abc", "more_body": False},
        ]
        receive = AsyncMock(side_effect=chunks)
        await mw(_scope(method="POST", path="/login", cookies=f"{CSRF_COOKIE}=abc"), receive, AsyncMock())
        auth.authenticate.assert_called_once_with("alice", "pw")


class TestLogout:
    async def test_get_logout_is_a_confirm_page(self):
        auth = MagicMock()
        send = AsyncMock()
        await SessionAuthMiddleware(AsyncMock(), auth)(_scope(path="/logout", cookies=f"{SESSION_COOKIE}=tok"), AsyncMock(), send)
        start, body = _responses(send)
        assert start["status"] == 200 and b'method="post"' in body["body"]
        auth.delete_session.assert_not_called()

    async def test_post_logout_deletes_session_and_clears_cookie(self):
        auth = MagicMock(); auth.validate_session.return_value = USER
        audit = MagicMock()
        send = AsyncMock()
        await SessionAuthMiddleware(AsyncMock(), auth, audit_service=audit, root_path="/p")(
            _scope(method="POST", path="/logout", cookies=f"{SESSION_COOKIE}=tok"), AsyncMock(), send
        )
        auth.delete_session.assert_called_once_with("tok")
        start = _responses(send)[0]
        headers = dict(start["headers"])
        assert start["status"] == 302 and headers[b"location"] == b"/p/"
        assert "Max-Age=0" in headers[b"set-cookie"].decode()
        assert audit.log.call_args.kwargs["action"] == "logout"


class TestWhoami:
    async def test_anonymous_gets_nulls_not_401(self):
        auth = MagicMock(); auth.validate_session.return_value = None
        send = AsyncMock()
        await SessionAuthMiddleware(AsyncMock(), auth)(_scope(path="/api/whoami"), AsyncMock(), send)
        start, body = _responses(send)
        assert start["status"] == 200
        import json
        assert json.loads(body["body"]) == {"username": None, "display_name": None, "role": None, "ws_token": None}

    async def test_logged_in_gets_ws_token(self):
        auth = MagicMock(); auth.validate_session.return_value = USER; auth.create_ws_token.return_value = "wst"
        send = AsyncMock()
        await SessionAuthMiddleware(AsyncMock(), auth)(_scope(path="/api/whoami", cookies=f"{SESSION_COOKIE}=tok"), AsyncMock(), send)
        import json
        data = json.loads(_responses(send)[1]["body"])
        assert data["username"] == "alice" and data["role"] == "user" and data["ws_token"] == "wst"
        auth.create_ws_token.assert_called_once_with(1, "tok")


class TestClientIp:
    def test_untrusted_peer_ignores_forwarded_for(self):
        scope = _scope(headers=[(b"x-forwarded-for", b"1.2.3.4")], client=("203.0.113.5", 1))
        assert get_client_ip(scope, ["127.0.0.0/8"]) == "203.0.113.5"

    def test_trusted_proxy_yields_rightmost_untrusted(self):
        scope = _scope(headers=[(b"x-forwarded-for", b"9.9.9.9, 1.2.3.4, 127.0.0.2")], client=("127.0.0.1", 1))
        assert get_client_ip(scope, ["127.0.0.0/8"]) == "1.2.3.4"

    def test_no_client_is_unknown(self):
        assert get_client_ip({"headers": []}, []) == "unknown"


class TestSessionTokenContextvar:
    async def test_session_token_published_and_reset(self):
        from sfincs_ui.middleware.session_auth import get_current_session_token

        auth = MagicMock(); auth.validate_session.return_value = USER
        seen = {}

        async def app(scope, receive, send):
            seen["token"] = get_current_session_token()

        await SessionAuthMiddleware(app, auth)(_scope(type_="websocket", cookies=f"{SESSION_COOKIE}=tok"), AsyncMock(), AsyncMock())
        assert seen["token"] == "tok"
        assert get_current_session_token() is None

    async def test_no_cookie_publishes_no_token(self):
        from sfincs_ui.middleware.session_auth import get_current_session_token

        seen = {}

        async def app(scope, receive, send):
            seen["token"] = get_current_session_token()

        await SessionAuthMiddleware(app, MagicMock())(_scope(), AsyncMock(), AsyncMock())
        assert seen["token"] is None

