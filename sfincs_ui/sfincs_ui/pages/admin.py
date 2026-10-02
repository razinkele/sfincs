"""Admin: users and roles, queue policy, audit log.

Authorization comes from ``current_user()``, the server-validated identity,
on every render and every mutation. Nothing here trusts a client-side signal.
"""

from __future__ import annotations

import logging
import re

from shiny import module, reactive, render, ui

from sfincs_ui.models.user import ROLE_ADMIN, ROLE_USER, ROLES, validate_username
from sfincs_ui.services.audit_service import AuditService
from sfincs_ui.services.auth_service import AuthService
from sfincs_ui.services.settings_service import POLICY_KEYS, SettingsService

logger = logging.getLogger(__name__)

_LOG_PAGE = 50


# -- pure helpers (tested without Shiny) -------------------------------------

def _validate_create_user_form(username: str, password: str, role: str, email: str | None = None) -> list[str]:
    errors: list[str] = []
    try:
        validate_username((username or "").strip())
    except ValueError as exc:
        errors.append(f"Username: {exc}")
    if not password:
        errors.append("Password is required")
    elif len(password) < 8:
        errors.append("Password must be at least 8 characters")
    if role not in ROLES:
        errors.append(f"Role must be one of: {', '.join(ROLES)}")
    if email and not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email.strip()):
        errors.append("Email address is not valid")
    return errors


def _build_user_table_data(users: list[dict]) -> list[dict]:
    return [
        {
            "id": u["id"],
            "username": u["username"],
            "display_name": u.get("display_name") or u["username"],
            "email": u.get("email") or "-",
            "role": u["role"],
            "is_active": u.get("is_active", True),
        }
        for u in users
    ]


def _check_admin_access(user: dict | None) -> bool:
    return bool(user) and user.get("role") == ROLE_ADMIN


def _collect_policy_changes(values: dict, before: dict, validate=None) -> dict:
    """Validate and convert every submitted policy value, then diff against ``before``.

    ``validate(key, value) -> int`` defaults to ``int``; the page passes
    ``SettingsService.validate`` so the ceiling checks run here too. Raises
    ValueError/TypeError on the first bad value before anything is saved, so
    a later bad key can never leave earlier keys saved without an audit row.
    """
    validate = validate or (lambda _key, value: int(value))
    converted = {}
    for key, value in values.items():
        if value is None:
            raise ValueError(f"{key} is empty")
        converted[key] = validate(key, value)
    return {k: {"old": before[k], "new": v} for k, v in converted.items() if v != before[k]}


def _audit_as(actor: dict | None, audit_service, action: str, target: str | None = None, detail=None) -> bool:
    """Write one audit row as ``actor``; refuse (and log) when there is no validated actor."""
    if not actor:
        logger.warning("admin action %s on %s refused for audit: no validated actor", action, target)
        return False
    audit_service.log(actor["username"], action, target=target, detail=detail, user_id=actor.get("id"))
    return True


def _role_badge(role: str) -> str:
    cls = "bg-danger" if role == ROLE_ADMIN else "bg-primary"
    return f'<span class="badge {cls}">{role}</span>'


def _active_badge(is_active: bool) -> str:
    return '<span class="badge bg-success">Active</span>' if is_active else '<span class="badge bg-secondary">Inactive</span>'


# -- UI ----------------------------------------------------------------------

@module.ui
def admin_ui() -> ui.Tag:
    users_tab = ui.row(
        ui.column(3, ui.div(ui.output_ui("user_summary"), ui.hr(),
                            ui.input_action_button("create_user_btn", "Create user", class_="btn-primary w-100"),
                            class_="card p-3")),
        ui.column(9, ui.div(ui.output_ui("user_table"), class_="card p-3")),
        class_="mt-3",
    )
    policy_tab = ui.div(
        ui.p("Values an administrator may set, each bounded by the server's SFINCS_UI_* ceiling.", class_="text-muted"),
        ui.output_ui("policy_form"),
        ui.input_action_button("policy_save", "Save policy", class_="btn-primary mt-2"),
        class_="card p-3 mt-3",
    )
    log_tab = ui.row(
        ui.column(3, ui.div(ui.h6("Filters"),
                            ui.input_select("log_user_filter", "User", choices={"": "All users"}),
                            ui.input_select("log_action_filter", "Action", choices={"": "All actions"}),
                            ui.input_action_button("log_refresh_btn", "Refresh", class_="btn-outline-secondary w-100 mt-2"),
                            ui.hr(), ui.output_ui("log_summary"), class_="card p-3")),
        ui.column(9, ui.div(ui.output_ui("log_table"),
                            ui.div(ui.input_action_button("log_prev_btn", "Previous", class_="btn-sm btn-outline-secondary me-2"),
                                   ui.output_ui("log_page_info"),
                                   ui.input_action_button("log_next_btn", "Next", class_="btn-sm btn-outline-secondary ms-2"),
                                   class_="d-flex align-items-center justify-content-center mt-3"),
                            class_="card p-3")),
        class_="mt-3",
    )
    return ui.div(
        ui.output_ui("gate"),
        ui.navset_tab(
            ui.nav_panel("Users", users_tab),
            ui.nav_panel("Queue policy", policy_tab),
            ui.nav_panel("Audit log", log_tab),
            id="admin_tabs",
        ),
        class_="container py-3",
    )


# -- server ------------------------------------------------------------------

@module.server
def admin_server(input, output, session, auth_service: AuthService, audit_service: AuditService,
                 settings_service: SettingsService, current_user):
    users_data: reactive.Value[list[dict]] = reactive.value([])
    log_offset: reactive.Value[int] = reactive.value(0)
    log_tick: reactive.Value[int] = reactive.value(0)
    registered: set[int] = set()

    def _is_admin() -> bool:
        return _check_admin_access(current_user())

    def _admin_actor() -> dict | None:
        """The re-validated admin making this request, or None (mutation refused)."""
        user = current_user()
        return user if _check_admin_access(user) else None

    def _audit(actor: dict | None, action: str, target: str | None = None, detail=None) -> None:
        # The actor is captured before the mutation: resetting one's own
        # password or demoting oneself ends one's own session, and the row
        # must still be written. Never fabricates an actor.
        _audit_as(actor, audit_service, action, target=target, detail=detail)

    def _refresh_users() -> None:
        users_data.set(auth_service.list_users())

    def _notify_error(exc: Exception) -> None:
        ui.notification_show(str(exc), type="error", duration=8)

    @render.ui
    def gate():
        if _is_admin():
            return None
        return ui.div("Administrator access required.", class_="alert alert-warning")

    # Users ------------------------------------------------------------------

    @reactive.effect
    def _load_users():
        if _is_admin():
            _refresh_users()

    @render.ui
    def user_summary():
        if not _is_admin():
            return None
        users = users_data.get()
        admins = sum(1 for u in users if u["role"] == ROLE_ADMIN)
        return ui.div(ui.h6("Accounts"), ui.p(f"{len(users)} users, {admins} admins"))

    @render.ui
    def user_table():
        if not _is_admin():
            return None
        rows = _build_user_table_data(users_data.get())
        if not rows:
            return ui.p("No users yet.", class_="text-muted")
        body = []
        for r in rows:
            uid = r["id"]
            body.append(ui.tags.tr(
                ui.tags.td(r["username"]), ui.tags.td(r["display_name"]), ui.tags.td(r["email"]),
                ui.tags.td(ui.HTML(_role_badge(r["role"]))), ui.tags.td(ui.HTML(_active_badge(r["is_active"]))),
                ui.tags.td(
                    ui.input_action_button(f"reset_pw_{uid}", "Reset password", class_="btn-sm btn-outline-secondary me-1"),
                    ui.input_action_button(f"toggle_active_{uid}", "Deactivate" if r["is_active"] else "Activate", class_="btn-sm btn-outline-secondary me-1"),
                    ui.input_action_button(f"toggle_role_{uid}", "Make user" if r["role"] == ROLE_ADMIN else "Make admin", class_="btn-sm btn-outline-secondary me-1"),
                    ui.input_action_button(f"delete_user_{uid}", "Delete", class_="btn-sm btn-outline-danger"),
                ),
            ))
        return ui.tags.table(
            ui.tags.thead(ui.tags.tr(*[ui.tags.th(h) for h in ("Username", "Name", "Email", "Role", "Status", "Actions")])),
            ui.tags.tbody(*body), class_="table table-sm align-middle",
        )

    def _register_user_actions(uid: int) -> None:
        @reactive.effect
        @reactive.event(input[f"reset_pw_{uid}"])
        def _reset_pw():
            if not _is_admin():
                return
            ui.modal_show(ui.modal(
                ui.input_password(f"new_pw_{uid}", "New password (at least 8 characters)"),
                title="Reset password",
                footer=ui.div(ui.modal_button("Cancel"), ui.input_action_button(f"confirm_reset_pw_{uid}", "Reset", class_="btn-primary")),
                easy_close=True,
            ))

        @reactive.effect
        @reactive.event(input[f"confirm_reset_pw_{uid}"])
        def _do_reset_pw():
            actor = _admin_actor()
            if actor is None:
                return
            pw = input[f"new_pw_{uid}"]() or ""
            if len(pw) < 8:
                ui.notification_show("Password must be at least 8 characters", type="error")
                return
            try:
                ok = auth_service.reset_password(uid, pw)
            except ValueError as exc:
                _notify_error(exc)
                return
            except Exception:
                logger.exception("_do_reset_pw failed")
                ui.notification_show("Something went wrong; the error has been logged", type="error", duration=8)
                return
            if not ok:
                ui.notification_show("User not found", type="error")
                return
            _audit(actor, "reset_password", target=f"user:{uid}")
            ui.modal_remove()
            ui.notification_show("Password reset", type="message")

        @reactive.effect
        @reactive.event(input[f"toggle_active_{uid}"])
        def _toggle_active():
            actor = _admin_actor()
            if actor is None:
                return
            user = next((u for u in users_data.get() if u["id"] == uid), None)
            if user is None:
                return
            try:
                auth_service.update_user(uid, is_active=not user["is_active"])
                _audit(actor, "toggle_active", target=f"user:{uid}", detail={"is_active": not user["is_active"]})
                _refresh_users()
            except ValueError as exc:
                _notify_error(exc)
            except Exception:
                logger.exception("_toggle_active failed")
                ui.notification_show("Something went wrong; the error has been logged", type="error", duration=8)

        @reactive.effect
        @reactive.event(input[f"toggle_role_{uid}"])
        def _toggle_role():
            actor = _admin_actor()
            if actor is None:
                return
            user = next((u for u in users_data.get() if u["id"] == uid), None)
            if user is None:
                return
            new_role = ROLE_USER if user["role"] == ROLE_ADMIN else ROLE_ADMIN
            try:
                auth_service.update_user(uid, role=new_role)
                _audit(actor, "change_role", target=f"user:{uid}", detail={"role": new_role})
                _refresh_users()
            except ValueError as exc:
                _notify_error(exc)
            except Exception:
                logger.exception("_toggle_role failed")
                ui.notification_show("Something went wrong; the error has been logged", type="error", duration=8)

        @reactive.effect
        @reactive.event(input[f"delete_user_{uid}"])
        def _delete_user():
            if not _is_admin():
                return
            ui.modal_show(ui.modal(
                ui.p("Delete this account? Their sessions end immediately."),
                title="Delete user",
                footer=ui.div(ui.modal_button("Cancel"), ui.input_action_button(f"confirm_delete_{uid}", "Delete", class_="btn-danger")),
                easy_close=True,
            ))

        @reactive.effect
        @reactive.event(input[f"confirm_delete_{uid}"])
        def _do_delete_user():
            actor = _admin_actor()
            if actor is None:
                return
            try:
                auth_service.delete_user(uid)
                # Self-deletion: the actor's row is gone, so the audit row keeps the name only.
                _audit({**actor, "id": None} if actor["id"] == uid else actor, "delete_user", target=f"user:{uid}")
                _refresh_users()
                ui.modal_remove()
            except ValueError as exc:
                _notify_error(exc)
            except Exception:
                logger.exception("_do_delete_user failed")
                ui.notification_show("Something went wrong; the error has been logged", type="error", duration=8)

    @reactive.effect
    def _register_all_user_actions():
        for u in users_data.get():
            if u["id"] not in registered:
                registered.add(u["id"])
                _register_user_actions(u["id"])

    @reactive.effect
    @reactive.event(input.create_user_btn)
    def _show_create_modal():
        if not _is_admin():
            return
        ui.modal_show(ui.modal(
            ui.input_text("new_username", "Username"),
            ui.input_text("new_display_name", "Display name (optional)"),
            ui.input_text("new_email", "Email (optional)"),
            ui.input_password("new_password", "Password (at least 8 characters)"),
            ui.input_select("new_role", "Role", choices={ROLE_USER: "user", ROLE_ADMIN: "admin"}),
            ui.output_ui("create_user_errors"),
            title="Create user",
            footer=ui.div(ui.modal_button("Cancel"), ui.input_action_button("confirm_create_user", "Create", class_="btn-primary")),
            easy_close=True,
        ))

    create_errors: reactive.Value[list[str]] = reactive.value([])

    @render.ui
    def create_user_errors():
        errs = create_errors.get()
        return ui.div(*[ui.p(e, class_="text-danger small mb-1") for e in errs]) if errs else None

    @reactive.effect
    @reactive.event(input.confirm_create_user)
    def _do_create_user():
        actor = _admin_actor()
        if actor is None:
            return
        username, password = (input.new_username() or "").strip(), input.new_password() or ""
        role, email = input.new_role(), (input.new_email() or "").strip() or None
        errs = _validate_create_user_form(username, password, role, email)
        if errs:
            create_errors.set(errs)
            return
        try:
            auth_service.create_user(username, password, role=role, display_name=(input.new_display_name() or "").strip() or None, email=email)
        except ValueError as exc:
            create_errors.set([str(exc)])
            return
        except Exception:
            logger.exception("_do_create_user failed")
            ui.notification_show("Something went wrong; the error has been logged", type="error", duration=8)
            return
        create_errors.set([])
        _audit(actor, "create_user", target=f"user:{username}", detail={"role": role})
        _refresh_users()
        ui.modal_remove()
        ui.notification_show(f"Created {username}", type="message")

    # Queue policy -----------------------------------------------------------

    @render.ui
    def policy_form():
        if not _is_admin():
            return None
        fields = []
        for row in settings_service.rows():
            fields.append(ui.div(
                ui.input_numeric(f"policy_{row.key}", f"{row.label} (ceiling {row.ceiling})", row.value, min=1, max=row.ceiling, step=1),
                ui.p(row.explanation, class_="text-muted small"),
            ))
        return ui.div(*fields)

    @reactive.effect
    @reactive.event(input.policy_save)
    def _save_policy():
        actor = _admin_actor()
        if actor is None:
            return
        before = settings_service.effective()
        try:
            changed = _collect_policy_changes(
                {key: input[f"policy_{key}"]() for key in POLICY_KEYS}, before, validate=settings_service.validate,
            )
            for key, change in changed.items():
                settings_service.set(key, change["new"])
        except (ValueError, TypeError) as exc:
            _notify_error(exc)
            return
        except Exception:
            logger.exception("_save_policy failed")
            ui.notification_show("Something went wrong; the error has been logged", type="error", duration=8)
            return
        if changed:
            _audit(actor, "settings_update", target="queue_policy", detail=changed)
        ui.notification_show("Policy saved" if changed else "No changes", type="message")

    # Audit log --------------------------------------------------------------

    @reactive.effect
    def _populate_log_filters():
        if not _is_admin():
            return
        log_tick.get()
        users = {"": "All users", **{u["username"]: u["username"] for u in auth_service.list_users()}}
        actions = {"": "All actions", **{a: a for a in audit_service.distinct_actions()}}
        ui.update_select("log_user_filter", choices=users, selected=input.log_user_filter() or "")
        ui.update_select("log_action_filter", choices=actions, selected=input.log_action_filter() or "")

    @reactive.effect
    @reactive.event(input.log_refresh_btn)
    def _on_log_refresh():
        log_tick.set(log_tick.get() + 1)

    @reactive.effect
    @reactive.event(input.log_user_filter, input.log_action_filter)
    def _on_filter_change():
        log_offset.set(0)

    @reactive.effect
    @reactive.event(input.log_prev_btn)
    def _prev():
        log_offset.set(max(0, log_offset.get() - _LOG_PAGE))

    @reactive.effect
    @reactive.event(input.log_next_btn)
    def _next():
        log_offset.set(log_offset.get() + _LOG_PAGE)

    def _filters():
        return {"username": input.log_user_filter() or None, "action": input.log_action_filter() or None}

    @render.ui
    def log_summary():
        if not _is_admin():
            return None
        log_tick.get()
        return ui.p(f"{audit_service.count(**_filters())} entries")

    @render.ui
    def log_page_info():
        if not _is_admin():
            return None
        log_tick.get()
        total = audit_service.count(**_filters())
        start = log_offset.get()
        return ui.span(f"{min(start + 1, total)}-{min(start + _LOG_PAGE, total)} of {total}", class_="small text-muted")

    @render.ui
    def log_table():
        if not _is_admin():
            return None
        log_tick.get()
        rows = audit_service.query(limit=_LOG_PAGE, offset=log_offset.get(), **_filters())
        if not rows:
            return ui.p("No entries.", class_="text-muted")
        return ui.tags.table(
            ui.tags.thead(ui.tags.tr(*[ui.tags.th(h) for h in ("Time (UTC)", "User", "Action", "Target", "Detail", "IP")])),
            ui.tags.tbody(*[ui.tags.tr(*[ui.tags.td(r[k]) for k in ("timestamp", "username", "action", "target", "detail", "ip_address")]) for r in rows]),
            class_="table table-sm",
        )
