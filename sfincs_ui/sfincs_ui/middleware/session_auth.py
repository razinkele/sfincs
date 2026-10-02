"""Cookie-session middleware for the SFINCS UI ASGI app.

Reads the ``sfincs_ui_session`` cookie, resolves it through AuthService and
publishes the user (or None) to the request through a contextvar. Unlike the
SHYFEM UI original this never redirects: anonymous visitors reach every page
with ``user=None`` and the pages decide what they may see (spec section 5).
The middleware owns /login, /logout and /api/whoami; the last one also mints
the websocket token that bridges the HTTP identity into the Shiny session.
"""

from __future__ import annotations

import contextvars
import json
import logging
import secrets
import urllib.parse
from html import escape

from sfincs_ui.middleware.client_ip import get_client_ip

logger = logging.getLogger(__name__)

SESSION_COOKIE = "sfincs_ui_session"
CSRF_COOKIE = "sfincs_ui_csrf"
_MAX_FORM_BODY = 16 * 1024

_user_var: contextvars.ContextVar[dict | None] = contextvars.ContextVar("sfincs_ui_user", default=None)


def get_current_user() -> dict | None:
    """The user resolved for the current ASGI scope, or None."""
    return _user_var.get()


def _parse_cookie(raw: bytes) -> dict[str, str]:
    out: dict[str, str] = {}
    for part in raw.decode("latin-1").split(";"):
        part = part.strip()
        if not part:
            continue
        name, _, value = part.partition("=")
        out[name.strip()] = value.strip()
    return out


def _cookie_header(scope) -> dict[str, str]:
    for name, value in scope.get("headers", []):
        if name == b"cookie":
            return _parse_cookie(value)
    return {}


def _strip_root(path: str, root_path: str) -> str:
    """Path relative to the mount.

    uvicorn 0.49 (this host) puts ``--root-path`` in front of ``scope["path"]``
    (measured 2026-10-01: a request for /login with --root-path /sfincs-ui
    arrives as path=/sfincs-ui/login, root_path=/sfincs-ui). Older servers and
    test transports deliver /login. Accept both.
    """
    if root_path and (path == root_path or path.startswith(root_path + "/")):
        return path[len(root_path):] or "/"
    return path


_LOGIN_HTML = """<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Sign in - SFINCS UI</title>
<style>
 body{{font-family:system-ui,sans-serif;background:#0b3d5b;color:#fff;display:flex;min-height:100vh;align-items:center;justify-content:center;margin:0}}
 .card{{background:rgba(255,255,255,.1);border:1px solid rgba(255,255,255,.25);border-radius:12px;padding:32px;width:min(380px,92vw)}}
 h1{{font-size:1.4rem;margin:0 0 4px}} p{{margin:0 0 20px;opacity:.8;font-size:.9rem}}
 label{{display:block;font-size:.85rem;margin:12px 0 4px}} input{{width:100%;padding:9px;border-radius:6px;border:1px solid rgba(255,255,255,.3);background:rgba(255,255,255,.12);color:#fff;box-sizing:border-box}}
 button{{margin-top:18px;width:100%;padding:10px;border:0;border-radius:6px;background:#2d9cba;color:#fff;font-weight:600;cursor:pointer}}
 .err{{background:rgba(220,53,69,.25);border:1px solid rgba(220,53,69,.6);padding:8px 10px;border-radius:6px;font-size:.85rem;margin-bottom:8px}}
 a{{color:#cfe9f3}}
</style></head><body><div class="card">
<h1>SFINCS UI</h1><p>Build, run and inspect Curonian Lagoon flood models.</p>
{error}
<form method="post" action="{login_action}">
<input type="hidden" name="csrf_token" value="{csrf_token}">
<label for="username">Username</label><input id="username" name="username" type="text" required autofocus autocomplete="username">
<label for="password">Password</label><input id="password" name="password" type="password" required autocomplete="current-password">
<button type="submit">Sign in</button>
</form>
<p style="margin-top:16px"><a href="{home}">Back to the public pages</a></p>
</div></body></html>
"""

_LOGOUT_HTML = """<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"><title>Log out - SFINCS UI</title></head>
<body style="font-family:system-ui,sans-serif;padding:2rem">
<p>Log out of SFINCS UI?</p>
<form method="post" action="{logout_action}"><button type="submit">Log out</button></form>
<p><a href="{home}">Cancel</a></p>
</body></html>
"""


class SessionAuthMiddleware:
    def __init__(
        self,
        app,
        auth_service,
        audit_service=None,
        root_path: str = "",
        session_ttl_hours: int = 24,
        use_secure_cookies: bool = True,
        trusted_proxies: list[str] | None = None,
    ):
        self.app = app
        self.auth_service = auth_service
        self.audit_service = audit_service
        self.root_path = root_path.rstrip("/")
        self.session_ttl_hours = session_ttl_hours
        self.use_secure_cookies = use_secure_cookies
        self.trusted_proxies = trusted_proxies or []

    async def __call__(self, scope, receive, send):
        if scope["type"] not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return

        root_path = scope.get("root_path", "") or self.root_path
        session_token = _cookie_header(scope).get(SESSION_COOKIE)

        if scope["type"] == "http":
            path, method = _strip_root(scope.get("path", "/"), root_path), scope.get("method", "GET")
            if path == "/login" and method == "GET":
                await self._serve_login(send, root_path)
                return
            if path == "/login" and method == "POST":
                await self._handle_login(scope, receive, send, root_path)
                return
            if path == "/logout" and method == "GET":
                await self._serve_html(send, _LOGOUT_HTML.format(logout_action=f"{root_path}/logout", home=f"{root_path}/"))
                return
            if path == "/logout" and method == "POST":
                await self._handle_logout(scope, session_token, send, root_path)
                return
            if path == "/api/whoami" and method == "GET":
                await self._handle_whoami(session_token, send)
                return

        user = self.auth_service.validate_session(session_token) if session_token else None
        token = _user_var.set(user)
        try:
            await self.app(scope, receive, send)
        finally:
            _user_var.reset(token)

    # -- helpers ---------------------------------------------------------

    def _audit(self, username, action, ip_address=None, user_id=None):
        if self.audit_service is None:
            return
        try:
            self.audit_service.log(username=username, action=action, ip_address=ip_address, user_id=user_id)
        except Exception:
            logger.exception("audit write failed")

    def _cookie(self, name: str, value: str, root_path: str, max_age: int) -> bytes:
        parts = [f"{name}={value}", f"Path={root_path or '/'}", "HttpOnly", "SameSite=Lax", f"Max-Age={max_age}"]
        if self.use_secure_cookies:
            parts.append("Secure")
        return "; ".join(parts).encode()

    @staticmethod
    async def _serve_html(send, html: str, status: int = 200, extra_headers=()):
        body = html.encode()
        await send({
            "type": "http.response.start",
            "status": status,
            "headers": [(b"content-type", b"text/html; charset=utf-8"), (b"content-length", str(len(body)).encode()), *extra_headers],
        })
        await send({"type": "http.response.body", "body": body})

    @staticmethod
    async def _redirect(send, location: str, extra_headers=()):
        await send({"type": "http.response.start", "status": 302, "headers": [(b"location", location.encode()), *extra_headers]})
        await send({"type": "http.response.body", "body": b""})

    @staticmethod
    async def _json(send, obj: dict):
        body = json.dumps(obj).encode()
        await send({
            "type": "http.response.start",
            "status": 200,
            "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode())],
        })
        await send({"type": "http.response.body", "body": body})

    async def _serve_login(self, send, root_path: str, error: str = ""):
        csrf = secrets.token_urlsafe(32)
        html = _LOGIN_HTML.format(
            error=f'<div class="err" role="alert">{escape(error)}</div>' if error else "",
            login_action=f"{root_path}/login",
            csrf_token=csrf,
            home=f"{root_path}/",
        )
        await self._serve_html(send, html, extra_headers=[(b"set-cookie", self._cookie(CSRF_COOKIE, csrf, root_path, 600))])

    async def _read_form(self, receive) -> dict[str, str]:
        body = b""
        while True:
            message = await receive()
            body += message.get("body", b"")
            if len(body) > _MAX_FORM_BODY:
                return {}
            if not message.get("more_body", False):
                break
        parsed = urllib.parse.parse_qs(body.decode("utf-8", errors="replace"))
        return {k: v[0] for k, v in parsed.items()}

    async def _handle_login(self, scope, receive, send, root_path: str):
        form = await self._read_form(receive)
        ip = get_client_ip(scope, self.trusted_proxies)
        form_csrf = form.get("csrf_token", "")
        cookie_csrf = _cookie_header(scope).get(CSRF_COOKIE, "")
        if not form_csrf or not cookie_csrf or not secrets.compare_digest(form_csrf, cookie_csrf):
            await self._serve_login(send, root_path, error="Invalid request. Please try again.")
            return
        username, password = form.get("username", ""), form.get("password", "")
        user = self.auth_service.authenticate(username, password)
        if user is None:
            self._audit(username or "<empty>", "login_failed", ip_address=ip)
            await self._serve_login(send, root_path, error="Invalid username or password.")
            return
        self._audit(user["username"], "login_success", ip_address=ip, user_id=user["id"])
        token = self.auth_service.create_session(user["id"], ttl_hours=self.session_ttl_hours, ip_address=ip)
        try:
            self.auth_service.cleanup_expired_sessions()
        except Exception:
            logger.exception("expired-session cleanup failed")
        cookie = self._cookie(SESSION_COOKIE, token, root_path, self.session_ttl_hours * 3600)
        await self._redirect(send, f"{root_path}/", extra_headers=[(b"set-cookie", cookie)])

    async def _handle_logout(self, scope, session_token, send, root_path: str):
        user = self.auth_service.validate_session(session_token) if session_token else None
        if session_token:
            self.auth_service.delete_session(session_token)
        self._audit(
            (user or {}).get("username", "unknown"), "logout",
            ip_address=get_client_ip(scope, self.trusted_proxies), user_id=(user or {}).get("id"),
        )
        cookie = self._cookie(SESSION_COOKIE, "", root_path, 0)
        await self._redirect(send, f"{root_path}/", extra_headers=[(b"set-cookie", cookie)])

    async def _handle_whoami(self, session_token, send):
        user = self.auth_service.validate_session(session_token) if session_token else None
        if user is None:
            await self._json(send, {"username": None, "display_name": None, "role": None, "ws_token": None})
            return
        ws_token = self.auth_service.create_ws_token(user["id"], session_token)
        await self._json(send, {
            "username": user["username"], "display_name": user.get("display_name"),
            "role": user["role"], "ws_token": ws_token,
        })
