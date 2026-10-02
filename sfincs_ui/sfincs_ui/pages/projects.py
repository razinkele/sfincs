"""Projects: my projects and the shipped examples (spec section 4)."""

from __future__ import annotations


from shiny import module, reactive, render, ui

from sfincs_ui.exceptions import SfincsUiError
from sfincs_ui.templates import TEMPLATES



@module.ui
def projects_ui() -> ui.Tag:
    return ui.div(
        ui.div(ui.h3("Projects", class_="me-auto"),
               ui.input_action_button("new_project_btn", "New project", class_="btn-primary"),
               class_="d-flex align-items-center mb-2"),
        ui.output_ui("project_table"),
        ui.hr(),
        ui.h5("Example projects"),
        ui.output_ui("examples"),
        class_="container py-3",
    )


@module.server
def projects_server(input, output, session, project_service, current_user, active_project, goto):
    tick = reactive.value(0)
    registered: set[str] = set()

    def _refresh():
        tick.set(tick.get() + 1)

    def _notify(exc: Exception):
        ui.notification_show(str(exc), type="error", duration=8)

    @render.ui
    def project_table():
        tick.get()
        user = current_user()
        if user is None:
            return ui.p("Log in to create projects.", class_="text-muted")
        rows = project_service.list_for(user)
        if not rows:
            return ui.p("No projects yet. Create one or clone an example.", class_="text-muted")
        body = []
        for p in rows:
            _register(p["id"])
            body.append(ui.tags.tr(
                ui.tags.td(p["name"]), ui.tags.td(p["template_title"]), ui.tags.td(str(p["run_count"])),
                ui.tags.td(str(p["updated_at"])[:16]),
                ui.tags.td(
                    ui.input_action_button(f"open_{_safe(p['id'])}", "Open", class_="btn-sm btn-primary me-1"),
                    ui.input_action_button(f"clone_{_safe(p['id'])}", "Clone", class_="btn-sm btn-outline-secondary me-1"),
                    ui.input_action_button(f"rename_{_safe(p['id'])}", "Rename", class_="btn-sm btn-outline-secondary me-1"),
                    ui.input_action_button(f"delete_{_safe(p['id'])}", "Delete", class_="btn-sm btn-outline-danger"),
                ),
            ))
        return ui.tags.table(ui.tags.thead(ui.tags.tr(*[ui.tags.th(h) for h in ("Name", "Template", "Runs", "Updated", "")])),
                             ui.tags.tbody(*body), class_="table table-sm align-middle")

    @render.ui
    def examples():
        tick.get()
        rows = project_service.examples()
        if not rows:
            return ui.p("No example projects.", class_="text-muted")
        cards = []
        for p in rows:
            _register(p["id"])
            cards.append(ui.div(ui.h6(p["name"]), ui.p(TEMPLATES[p["template"]].description, class_="small text-muted"),
                                ui.input_action_button(f"clone_{_safe(p['id'])}", "Clone into my projects", class_="btn-sm btn-outline-primary"),
                                class_="card p-3 me-2 mb-2", style="max-width: 24rem"))
        return ui.div(*cards, class_="d-flex flex-wrap")

    def _register(project_id: str):
        if project_id in registered:
            return
        registered.add(project_id)
        pid = _safe(project_id)

        @reactive.effect
        @reactive.event(input[f"open_{pid}"])
        def _open():
            if current_user() is None:
                return
            active_project.set(project_id)
            goto("Setup")

        @reactive.effect
        @reactive.event(input[f"clone_{pid}"])
        def _clone():
            user = current_user()
            if user is None:
                ui.notification_show("Log in to clone a project", type="warning"); return
            try:
                src = project_service.get(user, project_id)
                p = project_service.clone(user, project_id, f"{src['name']} (copy)")
                active_project.set(p["id"]); _refresh()
                ui.notification_show(f"Cloned as {p['name']}", type="message")
            except SfincsUiError as exc:
                _notify(exc)

        @reactive.effect
        @reactive.event(input[f"rename_{pid}"])
        def _rename():
            if current_user() is None:
                return
            ui.modal_show(ui.modal(ui.input_text(f"rename_name_{pid}", "New name"), title="Rename project",
                                   footer=ui.div(ui.modal_button("Cancel"), ui.input_action_button(f"confirm_rename_{pid}", "Rename", class_="btn-primary")),
                                   easy_close=True))

        @reactive.effect
        @reactive.event(input[f"confirm_rename_{pid}"])
        def _do_rename():
            try:
                project_service.rename(current_user(), project_id, input[f"rename_name_{pid}"]())
                ui.modal_remove(); _refresh()
            except SfincsUiError as exc:
                _notify(exc)

        @reactive.effect
        @reactive.event(input[f"delete_{pid}"])
        def _delete():
            if current_user() is None:
                return
            ui.modal_show(ui.modal(ui.p("Delete this project and all its runs?"), title="Delete project",
                                   footer=ui.div(ui.modal_button("Cancel"), ui.input_action_button(f"confirm_delete_{pid}", "Delete", class_="btn-danger")),
                                   easy_close=True))

        @reactive.effect
        @reactive.event(input[f"confirm_delete_{pid}"])
        def _do_delete():
            try:
                project_service.delete(current_user(), project_id)
                if active_project.get() == project_id:
                    active_project.set(None)
                ui.modal_remove(); _refresh()
            except SfincsUiError as exc:
                _notify(exc)

    @reactive.effect
    @reactive.event(input.new_project_btn)
    def _new():
        if current_user() is None:
            ui.notification_show("Log in to create a project", type="warning"); return
        ui.modal_show(ui.modal(
            ui.input_select("new_template", "Template", {k: t.title for k, t in TEMPLATES.items()}),
            ui.input_text("new_name", "Name"),
            title="New project",
            footer=ui.div(ui.modal_button("Cancel"), ui.input_action_button("confirm_new", "Create", class_="btn-primary")),
            easy_close=True))

    @reactive.effect
    @reactive.event(input.confirm_new)
    def _do_new():
        try:
            p = project_service.create(current_user(), input.new_template(), input.new_name())
            active_project.set(p["id"]); ui.modal_remove(); _refresh(); goto("Setup")
        except SfincsUiError as exc:
            _notify(exc)


def _safe(project_id: str) -> str:
    return project_id.replace("-", "_")
