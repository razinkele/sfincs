"""SFINCS Curonian Lagoon — read-only results viewer.

Published in the laguna.ku.lt toolbox at https://laguna.ku.lt/sfincs/.

The app presents completed SFINCS runs: model set-up, the spec section 9
success criteria, per-station validation metrics, published figures, station
water levels and the solver log.  It does not build models or launch
simulations — those stay in the command-line workflow (``build_model.py`` /
``run_sfincs.sh``) where long jobs belong.
"""

from __future__ import annotations

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
from shiny import App, reactive, render, ui

import sfincs_data as sd

# --------------------------------------------------------------------------
# Verdict presentation
# --------------------------------------------------------------------------
# validation.md reports each criterion as "met", "met (marginal)", "not met",
# "info" or "n/a".  How strictly a marginal result should read is a modelling
# judgement, not a display detail, so the policy is isolated here: change this
# one mapping to change how every badge and the run headline are coloured.
VERDICT_STYLES = {
    "met": ("success", "met"),
    "met (marginal)": ("warning", "met, marginal"),
    "not met": ("danger", "not met"),
    "info": ("secondary", "context"),
    "n/a": ("secondary", "n/a"),
}

# Verdicts that count towards the headline "N of M criteria met".  A marginal
# pass counts as a pass; info lines are context and are excluded from the total.
PASSING = {"met", "met (marginal)"}
SCORED = PASSING | {"not met"}


def verdict_style(verdict: str) -> tuple[str, str]:
    return VERDICT_STYLES.get(verdict.strip().lower(), ("secondary", verdict))


def headline(variant: str) -> tuple[str, str]:
    """Overall run status as (bootstrap colour, sentence)."""
    scored = [c for c in sd.criteria(variant) if c["verdict"].strip().lower() in SCORED]
    if not scored:
        return "secondary", "No scored success criteria in this report."
    passed = [c for c in scored if c["verdict"].strip().lower() in PASSING]
    marginal = [c for c in passed if c["verdict"].strip().lower() == "met (marginal)"]
    sentence = f"{len(passed)} of {len(scored)} success criteria met"
    if len(passed) < len(scored):
        return "danger", sentence
    if marginal:
        return "warning", f"{sentence} ({len(marginal)} marginal)"
    return "success", sentence


# --------------------------------------------------------------------------
# UI
# --------------------------------------------------------------------------

VARIANTS = sd.list_variants()
VARIANT_CHOICES = {v: sd.variant_label(v) for v in VARIANTS}

ABOUT = ui.markdown(
    """
**SFINCS** (Super-Fast INundation of CoastS) is a reduced-physics compound
flood model from Deltares.  This viewer publishes completed runs of the
Curonian Lagoon / Nemunas delta set-up for the December 2013 storm *Xaver*.

Runs are produced offline with HydroMT-SFINCS; this page is read-only.
"""
)

app_ui = ui.page_sidebar(
    ui.sidebar(
        ui.input_select("variant", "Model run", VARIANT_CHOICES),
        ui.output_ui("headline_box"),
        ui.output_ui("flooded_box"),
        ui.hr(),
        ui.tags.small(ABOUT),
        width=330,
    ),
    ui.navset_card_tab(
        ui.nav_panel(
            "Overview",
            ui.output_ui("setup_table"),
            ui.h5("Success criteria", class_="mt-4"),
            ui.output_ui("criteria_list"),
        ),
        ui.nav_panel("Validation metrics", ui.output_ui("metric_tables")),
        ui.nav_panel(
            "Figures",
            ui.output_ui("figure_gallery"),
        ),
        ui.nav_panel(
            "Station levels",
            ui.row(
                ui.column(
                    8,
                    ui.input_selectize(
                        "stations",
                        "Observation points",
                        choices=[],
                        multiple=True,
                        width="100%",
                    ),
                ),
                ui.column(
                    4,
                    ui.input_switch("storm_only", "Storm window only", value=False),
                ),
            ),
            ui.output_plot("station_plot", height="520px"),
            ui.output_ui("station_note"),
        ),
        ui.nav_panel("Solver log", ui.output_ui("run_log")),
        id="tabs",
    ),
    title="SFINCS — Curonian Lagoon flood model",
    fillable=False,
)


# --------------------------------------------------------------------------
# Server
# --------------------------------------------------------------------------

def server(input, output, session):

    @reactive.calc
    def variant() -> str:
        return input.variant()

    @reactive.calc
    def levels():
        return sd.station_levels(variant())

    @reactive.effect
    def _sync_station_choices():
        """Keep the station picker in step with the selected run."""
        columns = list(levels().columns)
        ui.update_selectize(
            "stations",
            choices=columns,
            selected=[c for c in ("Klaipeda", "Nida", "Vente", "Uostadvaris") if c in columns]
            or columns[:4],
        )

    # ---- sidebar -------------------------------------------------------

    @render.ui
    def headline_box():
        colour, text = headline(variant())
        return ui.div(text, class_=f"alert alert-{colour} py-2 px-3 mb-2 small")

    @render.ui
    def flooded_box():
        area = sd.flooded_area_km2(variant())
        if area is None:
            return ui.div()
        return ui.div(
            ui.tags.strong(f"{area:g} km²"),
            ui.tags.br(),
            ui.tags.small("flooded land in the delta window (depth > 5 cm)"),
            class_="border rounded py-2 px-3 mb-2",
        )

    # ---- overview ------------------------------------------------------

    @render.ui
    def setup_table():
        rows = sd.run_summary(variant())
        if not rows:
            return ui.markdown(
                "_No `sfincs.inp` found for this run — model outputs are kept "
                "outside the repository, so this page needs `SFINCS_DATA_DIR` "
                "to point at the model working tree._"
            )
        body = [
            ui.tags.tr(ui.tags.th(label, scope="row", class_="fw-normal text-muted"),
                       ui.tags.td(value))
            for label, value in rows
        ]
        return ui.tags.table(ui.tags.tbody(*body), class_="table table-sm w-auto")

    @render.ui
    def criteria_list():
        items = sd.criteria(variant())
        if not items:
            return ui.markdown("_No success criteria reported._")
        cards = []
        for c in items:
            colour, label = verdict_style(c["verdict"])
            cards.append(
                ui.div(
                    ui.div(
                        ui.span(label, class_=f"badge bg-{colour} me-2"),
                        ui.tags.strong(c["label"]),
                        class_="mb-1",
                    ),
                    ui.div(c["detail"], class_="small text-muted"),
                    ui.div(c["window"], class_="small text-muted fst-italic"),
                    class_="border-start border-3 ps-3 py-2 mb-2",
                )
            )
        return ui.div(*cards)

    # ---- metrics -------------------------------------------------------

    @render.ui
    def metric_tables():
        tables = sd.metric_tables(variant())
        if not tables:
            return ui.markdown("_No metric tables in this report._")
        blocks = []
        for heading, frame in tables.items():
            header = ui.tags.tr(*[ui.tags.th(c) for c in frame.columns])
            rows = [
                ui.tags.tr(*[ui.tags.td(str(v)) for v in record])
                for record in frame.itertuples(index=False)
            ]
            blocks.append(
                ui.div(
                    ui.h6(heading),
                    ui.tags.table(
                        ui.tags.thead(header),
                        ui.tags.tbody(*rows),
                        class_="table table-sm table-striped w-auto",
                    ),
                    class_="mb-4",
                )
            )
        blocks.append(
            ui.tags.small(
                "bias, RMSE and peak error in metres; peak dt in hours "
                "(positive = model later than gauge).",
                class_="text-muted",
            )
        )
        return ui.div(*blocks)

    # ---- figures -------------------------------------------------------

    @render.ui
    def figure_gallery():
        blocks = []
        for name, caption in sd.FIGURES:
            path = sd.results_path(variant(), name)
            if not path.is_file():
                continue
            # Served through the app's own static route (see app static_assets).
            blocks.append(
                ui.div(
                    ui.h6(caption),
                    ui.tags.img(
                        src=f"figures/{variant()}/{name}",
                        class_="img-fluid border rounded",
                    ),
                    class_="mb-4",
                )
            )
        if not blocks:
            return ui.markdown("_No published figures for this run._")
        return ui.div(*blocks)

    # ---- station levels ------------------------------------------------

    @render.plot
    def station_plot():
        frame = levels()
        chosen = [c for c in input.stations() or [] if c in frame.columns]
        fig, ax = plt.subplots()
        if frame.empty or not chosen:
            ax.text(0.5, 0.5, "No station data for this run",
                    ha="center", va="center", transform=ax.transAxes, color="#666")
            ax.set_axis_off()
            return fig

        window = frame
        if input.storm_only():
            span = sd.periods(variant()).get("Storm window", "")
            start, _, stop = span.partition(" to ")
            if start and stop:
                window = frame.loc[start.strip():stop.strip()]

        for name in chosen:
            ax.plot(window.index, window[name], linewidth=1.2, label=name)
        ax.set_ylabel("water level (m)")
        ax.set_xlabel("")
        ax.grid(alpha=0.3)
        ax.legend(loc="upper left", frameon=False, ncol=2, fontsize="small")
        fig.autofmt_xdate()
        fig.tight_layout()
        return fig

    @render.ui
    def station_note():
        frame = levels()
        if frame.empty:
            return ui.markdown(
                "_Station output (`sfincs_his.nc`) is not available for this run._"
            )
        return ui.tags.small(
            f"{len(frame.columns)} observation points, "
            f"{len(frame):,} time steps from {frame.index[0]:%Y-%m-%d %H:%M} "
            f"to {frame.index[-1]:%Y-%m-%d %H:%M}.",
            class_="text-muted",
        )

    # ---- log -----------------------------------------------------------

    @render.ui
    def run_log():
        return ui.tags.pre(
            sd.run_log_tail(variant()),
            class_="small border rounded p-3 bg-light",
            style="max-height: 60vh; overflow: auto;",
        )


app = App(app_ui, server, static_assets={"/figures": sd.RESULTS_DIR})
