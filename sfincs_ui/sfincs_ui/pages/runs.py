"""Runs: my runs, the selected run's stages, progress and log tail, and run controls."""

from __future__ import annotations


from shiny import module, reactive, render, ui

from sfincs_ui.exceptions import SfincsUiError
from sfincs_ui.services import access_control as ac

_ACTIVE = ("queued", "building", "running", "validating", "exporting")
_BADGE = {"finished": "bg-success", "failed": "bg-danger", "cancelled": "bg-dark", "orphaned": "bg-dark",
          "queued": "bg-secondary", "building": "bg-info", "running": "bg-warning text-dark", "validating": "bg-info", "exporting": "bg-info"}


def status_badge(status: str) -> str:
    return f'<span class="badge {_BADGE.get(status, "bg-secondary")}">{status}</span>'


def format_stages(stages: list[dict]) -> list[str]:
    out = []
    for s in stages:
        line = f"{s['stage']}: {s['status']}"
        if s.get("exit_code") is not None:
            line += f" (exit {s['exit_code']})"
        out.append(line)
    return out


def progress_bar(progress: dict | None):
    if not progress:
        return ui.TagList()
    pct = progress["percent"]
    remaining = progress.get("remaining_s")
    label = f"{pct}%" + (f", about {remaining / 60:.1f} min remaining" if remaining is not None else "")
    return ui.div(ui.div(label, class_="progress-bar", role="progressbar", style=f"width: {pct}%"), class_="progress mb-2")


@module.ui
def runs_ui() -> ui.Tag:
    return ui.div(
        ui.h3("Runs"),
        ui.output_ui("running_now"),
        ui.output_ui("run_table"),
        ui.hr(),
        ui.output_ui("detail"),
        ui.output_ui("progress"),
        ui.div(ui.output_ui("controls"), class_="mb-2"),
        ui.output_ui("download_box"),
        ui.pre(ui.output_text("log_tail"), class_="small bg-body-tertiary p-2", style="max-height: 24rem; overflow: auto"),
        class_="container py-3",
    )


@module.server
def runs_server(input, output, session, run_service, current_user, active_run):
    tick = reactive.value(0)
    registered: set[str] = set()

    def _refresh():
        tick.set(tick.get() + 1)

    def _notify(exc):
        ui.notification_show(str(exc), type="error", duration=8)

    def _selected() -> dict | None:
        rid = active_run.get()
        user = current_user()
        if rid is None:
            return None
        try:
            return run_service.get(user, rid)
        except SfincsUiError:
            return None

    @render.ui
    def running_now():
        tick.get()
        user = current_user()
        if not ac.is_admin(user):
            return None
        jobs = run_service.running_jobs(user)
        if not jobs:
            return None
        reactive.invalidate_later(5)
        return ui.div(ui.h6("Running now (all users)"),
                      ui.tags.ul(*[ui.tags.li(f"{j['run_name']}: {j['stage']} ({j['status']}, pid {j['pid']})") for j in jobs]))

    @render.ui
    def run_table():
        tick.get()
        user = current_user()
        if user is None:
            return ui.p("Log in to see your runs.", class_="text-muted")
        rows = run_service.list_for(user)
        if any(r["status"] in _ACTIVE for r in rows):
            reactive.invalidate_later(3)
        if not rows:
            return ui.p("No runs yet. Launch one from Setup.", class_="text-muted")
        body = []
        for r in rows:
            _register(r["id"])
            body.append(ui.tags.tr(
                ui.tags.td(r["name"]), ui.tags.td(r["project_name"]), ui.tags.td(ui.HTML(status_badge(r["status"]))),
                ui.tags.td(str(r["threads"])), ui.tags.td(str(r["started_at"] or "")[:16]), ui.tags.td(str(r["finished_at"] or "")[:16]),
                ui.tags.td(ui.input_action_button(f"select_{_safe(r['id'])}", "Select", class_="btn-sm btn-outline-primary")),
            ))
        return ui.tags.table(ui.tags.thead(ui.tags.tr(*[ui.tags.th(h) for h in ("Run", "Project", "Status", "Threads", "Started", "Finished", "")])),
                             ui.tags.tbody(*body), class_="table table-sm align-middle")

    def _register(run_id: str):
        if run_id in registered:
            return
        registered.add(run_id)

        @reactive.effect
        @reactive.event(input[f"select_{_safe(run_id)}"])
        def _select():
            active_run.set(run_id)

    @render.ui
    def detail():
        tick.get()
        r = _selected()
        if r is None:
            return ui.p("Select a run.", class_="text-muted")
        if r["status"] in _ACTIVE:
            reactive.invalidate_later(2)
        parts = [ui.h5(f"{r['name']} ", ui.HTML(status_badge(r["status"]))),
                 ui.p(f"Project {r['project_name']}, {r['threads']} thread(s)", class_="text-muted small"),
                 ui.tags.ul(*[ui.tags.li(line) for line in format_stages(r["stages"])])]
        if r["status"] == "failed" and r["summary"]:
            parts.append(ui.div(ui.strong(f"Failed in {r['summary']['stage']}: {r['summary']['reason']}"),
                                ui.pre(r["summary"]["log_tail"], class_="small"), class_="alert alert-danger"))
        return ui.div(*parts)

    @render.ui
    def progress():
        r = _selected()
        if r is None or r["status"] != "running":
            return None
        reactive.invalidate_later(2)
        try:
            return progress_bar(run_service.progress(current_user(), r["id"]))
        except SfincsUiError:
            return None

    @render.text
    def log_tail():
        r = _selected()
        if r is None:
            return ""
        if r["status"] in _ACTIVE:
            reactive.invalidate_later(2)
        try:
            stage, text = run_service.log_tail(current_user(), r["id"])
        except SfincsUiError:
            return ""
        return f"[{stage}]\n{text}" if stage else ""

    @render.ui
    def controls():
        tick.get()
        r = _selected()
        user = current_user()
        if r is None or not ac.can_modify_run(user, {"owner_id": r["owner_id"], "public": r["public"]}):
            return None
        if r["status"] in _ACTIVE:
            reactive.invalidate_later(2)
        buttons = []
        if r["status"] in _ACTIVE:
            buttons.append(ui.input_action_button("cancel_btn", "Cancel", class_="btn-sm btn-outline-danger me-1"))
        buttons.append(ui.input_action_button("pin_btn", "Unpin" if r["pinned"] else "Pin", class_="btn-sm btn-outline-secondary me-1"))
        buttons.append(ui.input_action_button("public_btn", "Make private" if r["public"] else "Make public", class_="btn-sm btn-outline-secondary"))
        return ui.div(*buttons)

    @reactive.effect
    @reactive.event(input.cancel_btn)
    async def _cancel():
        r = _selected()
        if r is None:
            return
        try:
            await run_service.cancel(current_user(), r["id"]); _refresh()
            ui.notification_show("Run cancelled", type="message")
        except SfincsUiError as exc:
            _notify(exc)

    @reactive.effect
    @reactive.event(input.pin_btn)
    def _pin():
        r = _selected()
        if r is None:
            return
        try:
            run_service.set_pinned(current_user(), r["id"], not r["pinned"]); _refresh()
        except SfincsUiError as exc:
            _notify(exc)

    @reactive.effect
    @reactive.event(input.public_btn)
    def _public():
        r = _selected()
        if r is None:
            return
        try:
            run_service.set_public(current_user(), r["id"], not r["public"]); _refresh()
        except SfincsUiError as exc:
            _notify(exc)

    @render.ui
    def download_box():
        tick.get()
        r = _selected()
        if r is None:
            return None
        try:
            run_service.download_path(current_user(), r["id"], "sfincs_his.nc")
        except SfincsUiError:
            return None
        return ui.download_button("download_his", "Download sfincs_his.nc", class_="btn-sm btn-outline-secondary mb-2")

    @render.download(filename=lambda: "sfincs_his.nc")
    def download_his():
        r = _selected()
        if r is None:
            return
        try:
            path = run_service.download_path(current_user(), r["id"], "sfincs_his.nc")
        except SfincsUiError as exc:
            _notify(exc); return
        with open(path, "rb") as fh:
            while chunk := fh.read(1 << 20):
                yield chunk


def _safe(run_id: str) -> str:
    return run_id.replace("-", "_")
