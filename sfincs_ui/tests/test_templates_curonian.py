import sys

import pytest

from sfincs_ui.config import Config
from sfincs_ui.exceptions import TemplateError
from sfincs_ui.templates import TEMPLATES, get_template
from sfincs_ui.templates.curonian import CURONIAN_EVENTS, CuronianTemplate


@pytest.fixture
def tpl():
    return get_template("curonian")


@pytest.fixture
def cfg(tmp_path):
    return Config(workspace=tmp_path, curonian_dir=tmp_path / "curonian", model_python="micromamba run -n hydromt-sfincs python")


def test_registered_and_events_mirror():
    assert isinstance(TEMPLATES["curonian"], CuronianTemplate)
    assert set(CURONIAN_EVENTS) == {"xaver_2013", "april_2013"}
    x = CURONIAN_EVENTS["xaver_2013"]
    assert (x.tref, x.tstop, x.score_window_end, x.data_window_end, x.zsini) == ("2013-11-28 00:00", "2013-12-11 00:00", "2013-12-09 00:00", "2013-12-20 00:00", None)
    assert CURONIAN_EVENTS["april_2013"].zsini == -0.17


def test_fields_groups_and_defaults(tpl):
    groups = {f.key: f.group for f in tpl.fields()}
    assert groups["manning_land"] == "Build parameters (rebuilds the subgrid table)"
    assert {k for k, g in groups.items() if g == "Solver overrides"} == {"alpha", "huthresh", "zsini", "dtmax", "nuvisc", "viscosity", "advection", "tstop"}
    d = tpl.defaults()
    assert d["event"] == "xaver_2013" and d["wind"] == "uniform" and d["subgrid"] is True and d["manning_land"] == 0.06
    assert d["zsini"] is None and d["dtmax"] is None and d["nuvisc"] is None and d["tstop"] is None
    assert all(f.optional for f in tpl.fields() if f.key in ("zsini", "dtmax", "nuvisc", "tstop"))


def test_build_command_flags(tpl, cfg):
    s = {**tpl.defaults(), "wind": "grid", "pressure": True, "subgrid": False, "manning_land": 0.08}
    argv = tpl.build_command(cfg.workspace / "run", s, cfg)
    assert argv[:5] == ["micromamba", "run", "-n", "hydromt-sfincs", "python"]
    assert argv[5] == str(cfg.curonian_dir / "build_model.py")
    rest = argv[6:]
    assert rest[:4] == ["--event", "xaver_2013", "--run-dir", str(cfg.workspace / "run")]
    assert "--wind" in rest and rest[rest.index("--wind") + 1] == "grid" and "--pressure" in rest and "--no-subgrid" in rest
    assert rest[rest.index("--manning-land") + 1] == "0.08" and "--manning-sea" in rest and "--rgh-lev-land" in rest
    plain = tpl.build_command(cfg.workspace / "run", tpl.defaults(), cfg)
    assert "--wind" not in plain and "--pressure" not in plain and "--no-subgrid" not in plain
    assert tpl.stage_cwd("build", cfg.workspace / "run", cfg) == cfg.curonian_dir
    assert tpl.stage_cwd("simulate", cfg.workspace / "run", cfg) == cfg.workspace / "run"


def test_unset_overrides_are_omitted(tpl):
    """Review Focus 3 and the manning rule."""
    o = tpl.inp_overrides(tpl.defaults())
    assert o == {"alpha": "0.5", "huthresh": "0.05", "viscosity": "1", "advection": "1"}
    assert not any("manning" in k for k in o)
    s = {**tpl.defaults(), "zsini": 0.4, "dtmax": 30, "nuvisc": 0.02, "viscosity": False, "tstop": "2013-12-09 06:00"}
    o = tpl.inp_overrides(s)
    assert o["zsini"] == "0.4" and o["dtmax"] == "30.0" and o["nuvisc"] == "0.02" and o["viscosity"] == "0"
    assert o["tstop"] == "20131209 060000"


def test_validate_and_export_commands(tpl, cfg):
    run = cfg.workspace / "run"
    v = tpl.validate_command(run, tpl.defaults(), cfg)
    assert v[5] == str(cfg.curonian_dir / "validate.py") and v[6:] == ["--event", "xaver_2013", "--run-dir", str(run), "--out-dir", str(run / "validation")]
    e = tpl.export_command(run, tpl.defaults(), cfg)
    assert e[5:7] == ["-m", "prep.export_map_cache"] and e[7:] == ["--event", "xaver_2013", "--run-dir", str(run), "--out-dir", str(run / "validation")]
    assert tpl.stage_cwd("validate", run, cfg) == cfg.curonian_dir and tpl.stage_cwd("export", run, cfg) == cfg.curonian_dir
    assert tpl.default_threads(tpl.defaults()) == 8
    assert tpl.model_files() == ("sfincs.msk", "sfincs.ind", "sfincs.bzs", "sfincs.dis", "sfincs.obs")


def test_tstop_before_score_window_skips_validation(tpl, cfg):
    """Review Focus 1."""
    s = tpl.validate({**tpl.defaults(), "tstop": "2013-12-07 00:00"})
    assert tpl.validate_command(cfg.workspace / "r", s, cfg) is None
    assert tpl.skip_reasons(s) == {"validate": "run ends before the scoring window"}
    s2 = tpl.validate({**tpl.defaults(), "tstop": "2013-12-09 00:00"})
    assert tpl.validate_command(cfg.workspace / "r", s2, cfg) is not None and tpl.skip_reasons(s2) == {}


def test_tstop_bounds_per_event(tpl):
    """Review Focus 2."""
    with pytest.raises(TemplateError, match="tstop"):
        tpl.validate({**tpl.defaults(), "tstop": "2013-12-25 00:00"})  # after the data window
    with pytest.raises(TemplateError, match="tstop"):
        tpl.validate({**tpl.defaults(), "tstop": "2013-11-28 00:00"})  # not after tref
    ok = tpl.validate({**tpl.defaults(), "event": "april_2013", "tstop": "2013-05-10 12:00"})
    assert ok["tstop"] == "2013-05-10 12:00"
    with pytest.raises(TemplateError, match="tstop"):
        tpl.validate({**tpl.defaults(), "event": "april_2013", "tstop": "2013-12-09 00:00"})


def test_pressure_requires_grid_wind(tpl):
    with pytest.raises(TemplateError, match="pressure"):
        tpl.validate({**tpl.defaults(), "pressure": True})
    assert tpl.validate({**tpl.defaults(), "wind": "grid", "pressure": True})["pressure"] is True


def test_examples(tpl):
    names = [n for n, _ in tpl.example_projects()]
    assert names == ["Xaver 2013 (uniform wind)", "April 2013 (uniform wind)"]
    assert tpl.example_projects()[1][1]["event"] == "april_2013"
