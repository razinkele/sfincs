"""Setup: the template's settings form for the active project, and the Launch dialog."""

from __future__ import annotations

import logging

from shiny import module, reactive, render, ui
from shiny_deckgl import MapWidget, geojson_layer, scatterplot_layer

from sfincs_ui.exceptions import SfincsUiError
from sfincs_ui.templates import get_template
from sfincs_ui.templates.base import SettingField

logger = logging.getLogger(__name__)

NO_GEOREF = "No georeferenced geometry for this template."
_POINT_STYLE = {  # radius in metres, RGBA
    "stations": (300, [220, 40, 40, 220]),
    "inflows": (500, [40, 160, 60, 220]),
    "boundary": (400, [40, 40, 220, 220]),
}
LAGOON_VIEW = {"longitude": 21.2, "latitude": 55.3, "zoom": 8, "pitch": 0, "bearing": 0}
_TOOLTIP = {"html": "{name}"}


def render_field(field: SettingField, value) -> ui.Tag:
    changed = "changed" if value != field.default else ""
    if field.group == "Solver overrides":
        hint = " (empty: model default)" if field.optional else f" (default {field.default})"
    else:
        hint = ""
    label = ui.span(field.label, ui.span(hint, class_="text-muted small") if hint else "")
    if field.kind == "bool":
        widget = ui.input_checkbox(field.key, label, bool(value))
    elif field.kind == "choice":
        widget = ui.input_select(field.key, label, {str(c): str(c) for c in field.choices}, selected=str(value))
    elif field.kind == "datetime":
        widget = ui.input_text(field.key, label, value or "", placeholder="YYYY-MM-DD HH:MM")
    else:
        step = 1 if field.kind == "int" else None
        widget = ui.input_numeric(field.key, label, value, min=field.minimum, max=field.maximum, step=step)
    return ui.div(widget, ui.p(field.explanation, class_="text-muted small mb-2"), class_=f"setting {changed}".strip())


def _points(layer: dict) -> list[dict]:
    geom = layer["geometry"]
    coords = [geom["coordinates"]] if geom["type"] == "Point" else geom["coordinates"]
    labels = layer.get("labels") or [""] * len(coords)
    return [{"position": [float(x), float(y)], "name": n} for (x, y), n in zip(coords, labels)]


def map_layers(layers: list[dict]) -> list:
    """deck.gl layers for the template geometry; only WGS84 layers are drawn (Review Focus 5).

    The shiny_deckgl helpers pass keyword arguments through verbatim, so the props
    are camelCase deck.gl names and accessors use the "@@=" expression form.
    """
    out = []
    for layer in layers:
        if layer.get("crs") != "EPSG:4326":
            continue
        name, geom = layer["name"], layer["geometry"]
        feature = {"type": "Feature", "properties": {"name": name}, "geometry": geom}
        if name == "domain":
            out.append(geojson_layer(id=name, data=feature, filled=True, stroked=True, getFillColor=[30, 120, 200, 40],
                                     getLineColor=[30, 120, 200, 200], lineWidthMinPixels=2))
        elif name == "channels":
            out.append(geojson_layer(id=name, data=feature, stroked=True, filled=False, getLineColor=[200, 80, 30, 220], lineWidthMinPixels=2))
        elif geom["type"] in ("MultiPoint", "Point"):
            radius, colour = _POINT_STYLE.get(name, (300, [120, 120, 120, 220]))
            out.append(scatterplot_layer(id=name, data=_points(layer), getPosition="@@=d.position", getRadius=radius,
                                         getFillColor=colour, pickable=True, radiusMinPixels=4))
        else:
            out.append(geojson_layer(id=name, data=feature, stroked=True, getLineColor=[120, 120, 120, 220], lineWidthMinPixels=1))
    return out


def map_message(layers: list[dict]) -> str | None:
    return None if map_layers(layers) else NO_GEOREF


map_message_for = map_message  # the server's map_message output would shadow the function


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
            ui.column(6, ui.output_ui("form")),
            ui.column(6, ui.div(ui.input_action_button("save_btn", "Save settings", class_="btn-outline-primary w-100 mb-2"),
                                ui.input_action_button("launch_btn", "Launch run", class_="btn-primary w-100 mb-3"),
                                ui.output_ui("map_message"),
                                MapWidget(module.resolve_id("map"), view_state=LAGOON_VIEW, tooltip=_TOOLTIP).ui(height="420px"),
                                class_="card p-3 setup-side")),
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

    _widget = MapWidget(session.ns("map"), view_state=LAGOON_VIEW, tooltip=_TOOLTIP)

    @reactive.calc
    def _geometry() -> list[dict]:
        p = _project()
        if p is None:
            return []
        try:
            return get_template(p["template"]).geometry_layers(project_service.project_dir(p["id"]), p["settings"])
        except Exception:
            logger.exception("geometry_layers failed")
            return []

    @render.ui
    def map_message():
        if _project() is None:
            return None  # the message describes a template, so it needs an open project
        msg = map_message_for(_geometry())
        return ui.p(msg, class_="text-muted small") if msg else None

    @reactive.effect
    async def _push_map():
        await _widget.update(session, map_layers(_geometry()))

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
        except Exception:
            logger.exception("_save failed")
            ui.notification_show("Something went wrong; the error has been logged", type="error", duration=8)

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
            ui.input_numeric("run_threads", f"Threads (1-{cap})", min(tpl.default_threads(p["settings"]), cap), min=1, max=cap, step=1),
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
        except Exception:
            logger.exception("_do_launch failed")
            ui.notification_show("Something went wrong; the error has been logged", type="error", duration=8)
