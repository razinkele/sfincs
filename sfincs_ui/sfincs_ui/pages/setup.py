"""Setup: the template's settings form for the active project, and the Launch dialog."""

from __future__ import annotations


from shiny import module, reactive, render, ui

from sfincs_ui.exceptions import SfincsUiError
from sfincs_ui.templates import get_template
from sfincs_ui.templates.base import SettingField



def render_field(field: SettingField, value) -> ui.Tag:
    changed = "changed" if value != field.default else ""
    label = ui.span(field.label, ui.span(f" (default {field.default})", class_="text-muted small") if field.group == "Solver overrides" else "")
    if field.kind == "bool":
        widget = ui.input_checkbox(field.key, label, bool(value))
    elif field.kind == "choice":
        widget = ui.input_select(field.key, label, {str(c): str(c) for c in field.choices}, selected=str(value))
    else:
        step = 1 if field.kind == "int" else None
        widget = ui.input_numeric(field.key, label, value, min=field.minimum, max=field.maximum, step=step)
    return ui.div(widget, ui.p(field.explanation, class_="text-muted small mb-2"), class_=f"setting {changed}".strip())


def collect_settings(input, fields: list[SettingField]) -> dict:
    out = {}
    for f in fields:
        raw = input[f.key]()
        out[f.key] = raw
    return out


@module.ui
def setup_ui() -> ui.Tag:
    return ui.div(
        ui.output_ui("header"),
        ui.row(
            ui.column(7, ui.output_ui("form")),
            ui.column(5, ui.div(ui.input_action_button("save_btn", "Save settings", class_="btn-outline-primary w-100 mb-2"),
                                ui.input_action_button("launch_btn", "Launch run", class_="btn-primary w-100"),
                                ui.p("The map preview arrives with the Curonian template.", class_="text-muted small mt-3"),
                                class_="card p-3")),
        ),
        class_="container py-3",
    )


@module.server
def setup_server(input, output, session, project_service, run_service, settings_service, current_user, active_project, active_run, goto):
    def _project():
        pid = active_project.get()
        user = current_user()
        if pid is None or user is None:
            return None
        try:
            return project_service.get(user, pid)
        except SfincsUiError:
            return None

    def _notify(exc):
        ui.notification_show(str(exc), type="error", duration=8)

    @render.ui
    def header():
        if current_user() is None:
            return ui.p("Log in and open a project to edit its settings.", class_="text-muted")
        p = _project()
        if p is None:
            return ui.p("Open a project on the Projects page.", class_="text-muted")
        return ui.div(ui.h3(p["name"]), ui.p(p["template_title"], class_="text-muted"))

    @render.ui
    def form():
        p = _project()
        if p is None:
            return None
        tpl = get_template(p["template"])
        groups: dict[str, list] = {}
        for f in tpl.fields():
            groups.setdefault(f.group, []).append(render_field(f, p["settings"].get(f.key, f.default)))
        return ui.div(*[ui.div(ui.h5(g), *items, class_="mb-3") for g, items in groups.items()])

    def _current_settings(p) -> dict:
        return collect_settings(input, get_template(p["template"]).fields())

    @reactive.effect
    @reactive.event(input.save_btn)
    def _save():
        p = _project()
        if p is None:
            return
        try:
            project_service.update_settings(current_user(), p["id"], _current_settings(p))
            ui.notification_show("Settings saved", type="message")
        except SfincsUiError as exc:
            _notify(exc)

    @reactive.effect
    @reactive.event(input.launch_btn)
    def _launch_dialog():
        p = _project()
        if p is None:
            return
        tpl = get_template(p["template"])
        cap = settings_service.get("max_threads")
        ui.modal_show(ui.modal(
            ui.input_text("run_name", "Run name", value=f"{p['name']} {p['run_count'] + 1}"),
            ui.input_numeric("run_threads", f"Threads (1-{cap})", tpl.default_threads(p["settings"]), min=1, max=cap, step=1),
            ui.p("Unsaved settings are saved first.", class_="text-muted small"),
            title="Launch run",
            footer=ui.div(ui.modal_button("Cancel"), ui.input_action_button("confirm_launch", "Launch", class_="btn-primary")),
            easy_close=True))

    @reactive.effect
    @reactive.event(input.confirm_launch)
    def _do_launch():
        p = _project()
        if p is None:
            return
        try:
            user = current_user()
            project_service.update_settings(user, p["id"], _current_settings(p))
            run = run_service.launch(user, p["id"], input.run_name(), input.run_threads())
            active_run.set(run["id"]); ui.modal_remove(); goto("Runs")
            ui.notification_show(f"Launched {run['name']}", type="message")
        except SfincsUiError as exc:
            _notify(exc)
