"""The viewer's Map tab: UI, deck.gl layers and the playback loop.

Playback is the app's own (shiny_deckgl's timeline helpers fix their labels at
build time and cannot follow the run selector). The hour lives on the server and
advances every STEP_S; a frame is sent only once the browser has acknowledged
the previous one (app/www/map_ack.js), and the latest hour is sent as soon as
that acknowledgement arrives -- so a slow link drops frames, not time.
Spec: docs/superpowers/specs/2026-09-27-sfincs-map-viewer-design.md
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass

import matplotlib.pyplot as plt
from shiny import reactive, render, ui
from shiny_deckgl import (CARTO_POSITRON, MapWidget, bitmap_layer, geojson_layer,
                          scatterplot_layer)

import map_data as md

STEP_S = 0.25
MAP = MapWidget(
    "map",
    view_state={"longitude": 21.25, "latitude": 55.40, "zoom": 8.4},
    style=CARTO_POSITRON,
    tooltip={"html": "<b>{name}</b><br/>{text}"},
)
OVERLAYS = {
    "outline": "Active area (current inputs)",
    "channels": "Channels (current inputs)",
    "boundary": "Sea boundary",
    "inflows": "River inflows",
    "stations": "Stations",
}


@dataclass
class Playback:
    run: str = ""
    hour: int = 0
    playing: bool = False
    sent: int = 0
    acked: int = 0
    pending: bool = False

    def switch(self, run: str) -> None:
        self.run, self.hour, self.playing = run, 0, False
        self.acked, self.pending = self.sent, False     # nothing of the old run can gate the new one

    def play(self, n_frames: int) -> None:
        if self.hour >= n_frames - 1:
            self.hour = 0
        self.playing = True

    def pause(self) -> None:
        self.playing = False

    def tick(self, n_frames: int) -> bool:
        if not self.playing:
            return False
        if self.hour + 1 >= n_frames:
            self.playing = False
            return False
        self.hour += 1
        return True

    def claim_send(self) -> int | None:
        if self.sent > self.acked:
            self.pending = True
            return None
        self.sent += 1
        self.pending = False
        return self.sent

    def ack(self, run: str, seq: int) -> bool:
        """Record an acknowledgement; True if a held frame should now be sent."""
        if run != self.run:
            return False
        self.acked = max(self.acked, seq)
        return self.pending and self.acked >= self.sent


def map_layers(rm: md.RunMaps, ov: dict, image: str) -> list[dict]:
    """Bottom to top. Only the stations are pickable: the tooltip is one
    widget-wide template and would pop up blank over any other pickable layer."""
    return [
        bitmap_layer("water", image, list(rm.warp.bounds), opacity=0.85, pickable=False),
        geojson_layer("outline", ov["outline"], stroked=True, filled=False,
                      getLineColor=[60, 60, 60, 200], lineWidthMinPixels=1, pickable=False),
        geojson_layer("channels", ov["channels"], stroked=True, filled=False,
                      getLineColor=[230, 120, 0, 230], lineWidthMinPixels=2, pickable=False),
        scatterplot_layer("boundary", ov["boundary"], getPosition="@@=d.position",
                          getFillColor=[0, 90, 200, 220], radiusMinPixels=4, pickable=False),
        scatterplot_layer("inflows", ov["inflows"], getPosition="@@=d.position",
                          getFillColor=[0, 160, 80, 220], radiusMinPixels=5, pickable=False),
        scatterplot_layer("stations", [], getPosition="@@=d.position", getFillColor="@@=d.fill",
                          getLineColor="@@=d.line", stroked=True, lineWidthMinPixels=2,
                          radiusMinPixels=7, pickable=True),
    ]


def map_panel():
    return ui.nav_panel(
        "Map",
        ui.layout_columns(
            ui.input_radio_buttons("map_quantity", None,
                                   {"level": "Water level", "change": "Change from start"}, inline=True),
            ui.input_switch("map_max", "Maximum over the run", value=False),
            col_widths=(8, 4),
        ),
        ui.input_checkbox_group("map_overlays", None, OVERLAYS, selected=list(OVERLAYS), inline=True),
        ui.layout_columns(
            ui.input_action_button("map_play", "Play", class_="btn-sm"),
            ui.input_slider("map_hour", None, min=0, max=1, value=0, step=1, ticks=False, width="100%"),
            ui.output_text("map_time"),
            col_widths=(1, 8, 3),
        ),
        MAP.ui(height="600px"),
        ui.output_ui("map_legend"),
        ui.output_ui("map_status"),
        ui.output_plot("map_cell_plot", height="300px"),
        ui.output_text("map_cell_caption"),
        ui.tags.script(src="www/map_ack.js"),
    )


def map_server(input, output, session, variant) -> None:
    pb = Playback()
    hour = reactive.value(0)
    playing = reactive.value(False)
    resend = reactive.value(0)

    @reactive.calc
    def run_maps():
        v = variant()
        return md.load_run(v) if md.map_available(v) else None

    def _n_frames() -> int:
        rm = run_maps()
        return len(rm.labels) if rm is not None else 1

    def _set_playing(on: bool) -> None:
        playing.set(on)
        ui.update_action_button("map_play", label="Pause" if on else "Play")

    @reactive.effect(priority=20)
    async def _on_run():
        rm = run_maps()
        pb.switch(variant())
        hour.set(0)
        _set_playing(False)
        ui.update_slider("map_hour", min=0, max=max(_n_frames() - 1, 1), value=0)
        if rm is None:
            return
        with reactive.isolate():
            q = input.map_quantity()
        await MAP.update(session, map_layers(rm, md.overlays(rm.run), md.frame_image(rm, 0, q)))

    @reactive.effect(priority=10)
    async def _visibility():
        run_maps()
        chosen = set(input.map_overlays() or [])
        await MAP.set_layer_visibility(session, {k: k in chosen for k in OVERLAYS})

    @reactive.effect
    @reactive.event(input.map_play)
    def _play():
        if input.map_max():
            return
        if pb.playing:
            pb.pause()
        else:
            pb.play(_n_frames())
            hour.set(pb.hour)
        _set_playing(pb.playing)

    @reactive.effect
    def _tick():
        if not playing():
            return
        reactive.invalidate_later(STEP_S)
        with reactive.isolate():
            if pb.tick(_n_frames()):
                hour.set(pb.hour)
                ui.update_slider("map_hour", value=pb.hour)
            if not pb.playing:
                _set_playing(False)

    @reactive.effect
    @reactive.event(input.map_hour)
    def _scrub():
        if pb.playing:
            return                     # while playing the slider only displays
        pb.hour = min(int(input.map_hour()), _n_frames() - 1)
        hour.set(pb.hour)

    @reactive.effect
    @reactive.event(input.map_max)
    def _max():
        if input.map_max() and pb.playing:
            pb.pause()
            _set_playing(False)

    @reactive.effect
    async def _send_frame():
        rm = run_maps()
        resend()
        if rm is None:
            return
        is_max = input.map_max()
        when = "max" if is_max else min(hour(), len(rm.labels) - 1)
        q = input.map_quantity()
        seq = pb.claim_send()
        if seq is None:
            return                     # previous frame unacknowledged: _ack re-triggers us
        image = md.frame_image(rm, when, q)
        stations = md.stations_at(rm.run, "max" if is_max else rm.times[when])
        await MAP.partial_update(session, [{"id": "water", "image": image},
                                           {"id": "stations", "data": stations}])
        await session.send_custom_message("map_frame_seq", {"run": rm.run, "seq": seq})

    @reactive.effect
    @reactive.event(input.map_frame_ack)
    def _ack():
        msg = input.map_frame_ack()
        if msg and pb.ack(str(msg.get("run")), int(msg.get("seq", 0))):
            with reactive.isolate():
                resend.set(resend() + 1)

    @render.text
    def map_time():
        rm = run_maps()
        if rm is None:
            return ""
        if input.map_max():
            return "maximum over the run"
        h = min(hour(), len(rm.labels) - 1)
        return f"{rm.labels[h]} UTC  ({h + 1}/{len(rm.labels)})"

    @render.ui
    def map_legend():
        rm = run_maps()
        if rm is None:
            return None
        lg = md.legend(rm, input.map_quantity(), input.map_max())
        gradient = ", ".join(lg["colors"])
        return ui.div(
            ui.tags.small(ui.tags.b(lg["title"])),
            ui.div(style=f"height:12px;background:linear-gradient(to right, {gradient});"),
            ui.div(ui.tags.small(f"{lg['vmin']:.2f}"), ui.tags.small(f"{lg['vmax']:.2f}"),
                   style="display:flex;justify-content:space-between;"),
            ui.tags.small(" · ".join(lg["notes"]
                                     + ["stations: blue = model low, red = model high, clipped at "
                                        f"±{md.ERROR_CLIP_M:.2f} m; grey = no gauge reading this hour; "
                                        "hollow = modelled only"]),
                          class_="text-muted"),
            class_="mt-2",
        )

    @render.ui
    def map_status():
        v = variant()
        if not md.map_available(v):
            return ui.markdown("_This run has no `sfincs_map.nc`; the map is unavailable._")
        notes = []
        rm = run_maps()
        if not rm.cached:
            notes.append("No valid map cache for this run: run "
                         f"`python -m prep.export_map_cache --run {v}` — clicks read the map file (~4 s).")
        if md.gauge_obs(v).empty:
            notes.append("No `gauge_obs.csv` for this run: stations show modelled levels only.")
        missing = md.overlays(v)["missing"]
        if missing:
            notes.append("Missing overlay files: " + ", ".join(missing) + ".")
        return ui.tags.small(ui.markdown("  \n".join(notes)), class_="text-warning") if notes else None

    @reactive.extended_task
    async def _series_task(rm, lon, lat):
        return await asyncio.to_thread(md.cell_series, rm, lon, lat)

    @reactive.effect
    @reactive.event(input[MAP.map_click_input_id])
    def _click():
        rm = run_maps()
        c = input[MAP.map_click_input_id]()
        if rm is None or not c:
            return
        _series_task(rm, float(c["longitude"]), float(c["latitude"]))

    @render.text
    def map_cell_caption():
        """Names the plotted cell once a series is drawn; empty for messages
        (lets the acceptance test tell a real plot from the placeholder)."""
        if _series_task.status() != "success":
            return ""
        cs = _series_task.result()
        if cs is None or cs.series.isna().all():
            return ""
        return f"cell row {cs.row}, col {cs.col}"

    @render.plot
    def map_cell_plot():
        fig, ax = plt.subplots(figsize=(10, 3))
        status = _series_task.status()
        rm = run_maps()

        def message(text):
            ax.text(0.5, 0.5, text, ha="center", va="center", transform=ax.transAxes, color="#666")
            ax.set_axis_off()
            return fig

        if status == "initial":
            return message("Click the map to plot a cell's water level through the run.")
        if status == "running":
            return message("Reading from the map file (~4 s)…" if rm is not None and not rm.cached
                           else "Reading…")
        if status == "error":
            return message("Could not read this cell.")
        cs = _series_task.result()
        if cs is None:
            return message("That point is outside the model's active area.")
        if cs.series.isna().all():
            return message(f"Cell {cs.row},{cs.col} is dry for the whole run.")
        ax.plot(cs.series.index, cs.series.values, linewidth=1.2, label="water level")
        ax.axhline(cs.zb, linestyle="--", color="#8a6d3b", linewidth=1, label="bed minimum (subgrid)")
        if input.map_max():
            ax.axhline(cs.zsmax, color="#c0392b", linewidth=1, label="max")
        elif rm is not None:
            ax.axvline(rm.times[min(hour(), len(rm.times) - 1)], color="#c0392b", linewidth=1)
        ax.set_title(f"cell row {cs.row}, col {cs.col}  (x {cs.x:.0f}, y {cs.y:.0f}, EPSG:3346)"
                     + ("  — read from the map file" if cs.slow else ""), fontsize="small")
        ax.set_ylabel("m")
        ax.grid(alpha=0.3)
        ax.legend(loc="upper left", frameon=False, fontsize="small")
        fig.autofmt_xdate()
        fig.tight_layout()
        return fig
