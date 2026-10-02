"""Assemble the SFINCS UI: Shiny app inside the session middleware."""

from __future__ import annotations

import logging
from pathlib import Path

from shiny import App, reactive, render, ui

from sfincs_ui.config import Config, get_config, set_config
from sfincs_ui.db.base import init_db
from sfincs_ui.middleware.session_auth import SessionAuthMiddleware, get_current_user
from sfincs_ui.pages import admin, home
from sfincs_ui.services.audit_service import AuditService
from sfincs_ui.services.auth_service import AuthService
from sfincs_ui.services.environment import EnvironmentReport, check_environment
from sfincs_ui.services.settings_service import SettingsService
from sfincs_ui.services.ws_identity import resolve_ws_user

logger = logging.getLogger(__name__)

_WS_IDENTITY_JS = """
document.addEventListener('DOMContentLoaded', function () {
  fetch('api/whoami').then(function (r) { return r.json(); }).then(function (data) {
    if (window.Shiny && window.Shiny.setInputValue) {
      window.Shiny.setInputValue('_wsauth', data.ws_token || '', {priority: 'event'});
    }
  }).catch(function () {});
});
"""


def _banner(report: EnvironmentReport):
    if report.ok:
        return None
    return ui.div(
        ui.tags.strong("This server cannot run models right now: "),
        ui.tags.ul(*[ui.tags.li(p) for p in report.problems], class_="mb-0"),
        class_="alert alert-danger env-banner",
        role="alert",
    )


def build_ui(config: Config, report: EnvironmentReport) -> ui.Tag:
    return ui.page_navbar(
        ui.nav_panel("Home", home.home_ui("home")),
        ui.nav_panel("Admin", admin.admin_ui("admin")),
        ui.nav_spacer(),
        ui.nav_control(ui.input_dark_mode(id="dark_mode")),
        ui.nav_control(ui.output_ui("user_menu")),
        title="SFINCS UI",
        id="main_nav",
        header=ui.TagList(
            ui.head_content(
                ui.tags.link(rel="stylesheet", href="sfincs_ui.css"),
                ui.tags.script(_WS_IDENTITY_JS),
            ),
            _banner(report),
        ),
    )


def build_server(config: Config, auth_service: AuthService, audit_service: AuditService,
                 settings_service: SettingsService):
    def server(input, output, session):
        ws_user: reactive.Value[dict | None] = reactive.value(None)

        @reactive.effect
        def _resolve_identity():
            token = input._wsauth() if "_wsauth" in input else None
            try:
                ws_user.set(resolve_ws_user(token, auth_service))
            except Exception:
                logger.warning("ws identity resolution failed; treating as anonymous", exc_info=True)
                ws_user.set(None)

        def current_user() -> dict | None:
            # The ws-token bridge first; under direct uvicorn the cookie also
            # reaches the websocket scope, so fall back to it.
            return ws_user.get() or get_current_user()

        hidden = {"admin": False}

        @reactive.effect
        def _hide_admin_for_non_admins():
            # Wait for the browser's whoami round trip (it always pushes
            # `_wsauth`, empty for anonymous) so a real admin whose cookie
            # has not been resolved yet never loses the tab. The Admin body
            # gates itself too; this is presentation, not security.
            if "_wsauth" not in input:
                return
            if not admin._check_admin_access(current_user()) and not hidden["admin"]:
                hidden["admin"] = True
                ui.remove_nav_panel("main_nav", "Admin")

        @render.ui
        def user_menu():
            user = current_user()
            prefix = config.url_prefix
            if user is None:
                return ui.tags.a("Log in", href=f"{prefix}/login", class_="btn btn-sm btn-outline-light")
            return ui.span(
                ui.span(user["username"], class_="me-2 text-light"),
                ui.tags.a("Log out", href=f"{prefix}/logout", class_="btn btn-sm btn-outline-light"),
            )

        home.home_server("home", current_user=current_user)
        admin.admin_server("admin", auth_service=auth_service, audit_service=audit_service,
                           settings_service=settings_service, current_user=current_user)

    return server


def create_app(config: Config | None = None, *, environment: EnvironmentReport | None = None):
    if config is None:
        config = get_config()
    else:
        set_config(config)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    init_db()
    report = environment if environment is not None else check_environment(config)
    for problem in report.problems:
        logger.warning("environment: %s", problem)

    auth_service = AuthService()
    audit_service = AuditService()
    settings_service = SettingsService(config)

    app = App(build_ui(config, report), build_server(config, auth_service, audit_service, settings_service),
              static_assets=Path(__file__).parent / "www")
    return SessionAuthMiddleware(
        app,
        auth_service=auth_service,
        audit_service=audit_service,
        root_path=config.url_prefix,
        session_ttl_hours=config.session_ttl_hours,
        use_secure_cookies=config.secure_cookies,
        trusted_proxies=config.trusted_proxies,
    )
