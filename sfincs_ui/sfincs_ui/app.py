"""Assemble the SFINCS UI: Shiny app inside the session middleware."""

from __future__ import annotations

import logging
from pathlib import Path

from shiny import App, reactive, render, ui
from shiny_deckgl import head_includes

from sfincs_ui.config import Config, get_config, set_config
from sfincs_ui.db.base import init_db
from sfincs_ui.middleware.lifespan import LifespanMiddleware
from sfincs_ui.middleware.session_auth import SessionAuthMiddleware, get_current_session_token
from sfincs_ui.pages import admin, home, projects, runs, setup
from sfincs_ui.services.audit_service import AuditService
from sfincs_ui.services.auth_service import AuthService
from sfincs_ui.services.environment import EnvironmentReport, check_environment
from sfincs_ui.services.job_runner import JobRunner
from sfincs_ui.services.project_service import ProjectService
from sfincs_ui.services.reconcile import reconcile
from sfincs_ui.services.run_service import RunService
from sfincs_ui.services.settings_service import SettingsService
from sfincs_ui.services.ws_identity import resolve_identity

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
        ui.nav_panel("Projects", projects.projects_ui("projects")),
        ui.nav_panel("Setup", setup.setup_ui("setup")),
        ui.nav_panel("Runs", runs.runs_ui("runs")),
        ui.nav_panel("Admin", admin.admin_ui("admin")),
        ui.nav_spacer(),
        ui.nav_control(ui.input_dark_mode(id="dark_mode")),
        ui.nav_control(ui.output_ui("user_menu")),
        title="SFINCS UI",
        id="main_nav",
        header=ui.TagList(
            head_includes(),
            ui.head_content(ui.tags.link(rel="stylesheet", href="sfincs_ui.css"), ui.tags.script(_WS_IDENTITY_JS)),
            _banner(report),
        ),
    )


def build_server(config: Config, services: dict):
    auth_service = services["auth"]

    def server(input, output, session):
        # The cookie seen when the websocket connected. Only the raw token is
        # kept: the user behind it is re-read from the database on every call.
        session_token = get_current_session_token()

        def current_user() -> dict | None:
            # Re-validated on every call (never cached) so logout, deactivation,
            # demotion, password reset and deletion take effect on the next
            # render or click of an already-open tab. The ws-token bridge comes
            # first; under direct uvicorn the cookie also reaches the websocket.
            ws_token = input._wsauth() if "_wsauth" in input else None
            try:
                return resolve_identity(ws_token, session_token, auth_service)
            except Exception:
                logger.warning("identity resolution failed; treating as anonymous", exc_info=True)
                return None

        def goto(panel: str) -> None:
            ui.update_navs("main_nav", selected=panel)

        active_project: reactive.Value[str | None] = reactive.value(None)
        active_run: reactive.Value[str | None] = reactive.value(None)
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
                return ui.tags.a("Log in", href=f"{prefix}/login", class_="btn btn-sm btn-outline-secondary")
            return ui.span(ui.span(user["username"], class_="me-2"),
                           ui.tags.a("Log out", href=f"{prefix}/logout", class_="btn btn-sm btn-outline-secondary"))

        home.home_server("home", current_user=current_user, project_service=services["projects"])
        projects.projects_server("projects", project_service=services["projects"], current_user=current_user,
                                 active_project=active_project, goto=goto)
        setup.setup_server("setup", project_service=services["projects"], run_service=services["runs"],
                           settings_service=services["settings"], current_user=current_user,
                           active_project=active_project, active_run=active_run, goto=goto)
        runs.runs_server("runs", run_service=services["runs"], current_user=current_user, active_run=active_run)
        admin.admin_server("admin", auth_service=auth_service, audit_service=services["audit"],
                           settings_service=services["settings"], current_user=current_user)

    return server


def create_app(config: Config | None = None, *, environment: EnvironmentReport | None = None,
               templates: dict | None = None, start_runner: bool = True):
    if config is None:
        config = get_config()
    else:
        set_config(config)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    init_db()
    report = environment if environment is not None else check_environment(config)
    for problem in report.problems:
        logger.warning("environment: %s", problem)
    if templates is None:
        from sfincs_ui.templates import TEMPLATES
        templates = TEMPLATES

    auth_service = AuthService()
    audit_service = AuditService()
    settings_service = SettingsService(config)
    project_service = ProjectService(config, templates=templates)
    project_service.ensure_examples()
    runner = JobRunner(config, settings_service, templates=templates, reconciler=reconcile)
    run_service = RunService(config, settings_service, project_service, runner, templates=templates)
    services = {"auth": auth_service, "audit": audit_service, "settings": settings_service,
                "projects": project_service, "runs": run_service}

    shiny_app = App(build_ui(config, report), build_server(config, services), static_assets=Path(__file__).parent / "www")
    authed = SessionAuthMiddleware(shiny_app, auth_service=auth_service, audit_service=audit_service,
                                   root_path=config.url_prefix, session_ttl_hours=config.session_ttl_hours,
                                   use_secure_cookies=config.secure_cookies, trusted_proxies=config.trusted_proxies)
    app = LifespanMiddleware(authed, on_startup=runner.start if start_runner else None,
                             on_shutdown=runner.stop if start_runner else None)
    app.runner = runner
    app.services = services
    return app
