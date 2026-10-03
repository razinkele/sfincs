from shiny import ui

from sfincs_ui.pages import projects, runs, setup
from sfincs_ui.templates import get_template


def test_pages_render_with_expected_ids():
    html = str(projects.projects_ui("projects"))
    for i in ("projects-new_project_btn", "projects-project_table", "projects-examples"):
        assert i in html
    html = str(setup.setup_ui("setup"))
    for i in ("setup-form", "setup-save_btn", "setup-launch_btn", "setup-header"):
        assert i in html
    html = str(runs.runs_ui("runs"))
    for i in ("runs-run_table", "runs-detail", "runs-log_tail", "runs-download_box"):
        assert i in html


def test_render_field_per_kind():
    tpl = get_template("plane_beach")
    fields = {f.key: f for f in tpl.fields()}
    assert 'type="number"' in str(setup.render_field(fields["duration_hours"], 6))
    assert "<select" in str(setup.render_field(fields["resolution_m"], 100)) and 'value="100"' in str(setup.render_field(fields["resolution_m"], 100))
    assert 'type="checkbox"' in str(setup.render_field(fields["advection"], True))
    assert "changed" in str(setup.render_field(fields["alpha"], 0.7)) and "changed" not in str(setup.render_field(fields["alpha"], 0.5))
    assert "default 0.5" in str(setup.render_field(fields["alpha"], 0.7))


def test_collect_settings_reads_each_field():
    tpl = get_template("plane_beach")

    class FakeInput:
        def __init__(self, values):
            self._v = values

        def __getitem__(self, key):
            return lambda: self._v[key]

    values = {"resolution_m": "50", "duration_hours": 3, "boundary_level_m": 1.5, "manning": 0.03, "alpha": 0.6, "huthresh": 0.1, "advection": False}
    assert setup.collect_settings(FakeInput(values), tpl.fields()) == values


def test_runs_helpers():
    assert "bg-success" in runs.status_badge("finished") and "bg-danger" in runs.status_badge("failed")
    assert "bg-warning" in runs.status_badge("running") and "bg-secondary" in runs.status_badge("queued")
    stages = [{"stage": "build", "status": "completed", "started_at": None, "finished_at": None, "exit_code": 0},
              {"stage": "simulate", "status": "running", "started_at": None, "finished_at": None, "exit_code": None}]
    assert runs.format_stages(stages) == ["build: completed (exit 0)", "simulate: running"]
    assert "45%" in str(runs.progress_bar({"percent": 45, "remaining_s": 120.0})) and "2.0 min" in str(runs.progress_bar({"percent": 45, "remaining_s": 120.0}))
    assert str(runs.progress_bar(None)) == ""


def test_render_optional_and_datetime_fields():
    tpl = get_template("curonian")
    fields = {f.key: f for f in tpl.fields()}
    html = str(setup.render_field(fields["dtmax"], None))
    assert 'type="number"' in html and "empty: model default" in html and "changed" not in html
    assert "changed" in str(setup.render_field(fields["dtmax"], 30.0))
    html = str(setup.render_field(fields["tstop"], None))
    assert 'type="text"' in html and 'placeholder="YYYY-MM-DD HH:MM"' in html
    assert 'value="2013-12-09 06:00"' in str(setup.render_field(fields["tstop"], "2013-12-09 06:00"))
