"""Home: what the tool does, how to get an account, where the public runs will appear."""

from __future__ import annotations

from shiny import module, render, ui

_ABOUT = ui.markdown(
    """
**SFINCS UI** lets a logged-in user create a SFINCS project from a template,
edit its settings, launch a simulation on this server, watch it run, and
inspect and compare the results. The first template is the Curonian Lagoon
model whose published hindcasts are in the read-only viewer at
[/sfincs/](/sfincs/).

Accounts are created by an administrator; there is no self-registration.
Visitors without an account can open runs their owners marked public and the
published baselines once the Results page ships (milestone 4).
"""
)


@module.ui
def home_ui() -> ui.Tag:
    return ui.div(
        ui.h2("SFINCS UI"),
        _ABOUT,
        ui.hr(),
        ui.h5("Public runs and baselines"),
        ui.p("Public runs appear here once the Results page ships (milestone 4).", class_="text-muted"),
        ui.h5("Example projects"),
        ui.output_ui("examples"),
        ui.output_ui("greeting"),
        class_="container py-3",
    )


@module.server
def home_server(input, output, session, current_user, project_service=None):
    @render.ui
    def greeting():
        user = current_user()
        if user is None:
            return ui.p("Log in to create projects and launch runs.", class_="text-muted")
        return ui.p(f"Signed in as {user['username']} ({user['role']}).", class_="text-muted")

    @render.ui
    def examples():
        rows = project_service.examples() if project_service is not None else []
        if not rows:
            return ui.p("No example projects.", class_="text-muted")
        return ui.tags.ul(*[ui.tags.li(f"{p['name']} ({p['template_title']})") for p in rows])
