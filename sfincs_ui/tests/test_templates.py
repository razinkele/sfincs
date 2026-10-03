import sys
from pathlib import Path

import pytest

from sfincs_ui.config import Config
from sfincs_ui.exceptions import TemplateError
from sfincs_ui.templates import TEMPLATES, get_template
from sfincs_ui.templates.base import SettingField, Template
from sfincs_ui.templates.plane_beach import PlaneBeachTemplate


@pytest.fixture
def tpl():
    return get_template("plane_beach")


def test_registry():
    assert isinstance(TEMPLATES["plane_beach"], PlaneBeachTemplate)
    assert isinstance(get_template("plane_beach"), Template)
    with pytest.raises(TemplateError):
        get_template("nope")


def test_fields_and_defaults(tpl):
    keys = [f.key for f in tpl.fields()]
    assert keys == ["resolution_m", "duration_hours", "boundary_level_m", "manning", "alpha", "huthresh", "advection"]
    assert all(isinstance(f, SettingField) and f.explanation for f in tpl.fields())
    assert tpl.defaults() == {"resolution_m": 100, "duration_hours": 6, "boundary_level_m": 2.0, "manning": 0.04,
                              "alpha": 0.5, "huthresh": 0.05, "advection": True}
    assert {f.key for f in tpl.fields() if f.group == "Solver overrides"} == {"alpha", "huthresh", "advection"}


def test_validate_coerces_bounds_and_drops_unknown(tpl):
    s = tpl.validate({"resolution_m": "50", "duration_hours": "3", "boundary_level_m": "1.5", "manning": 0.02,
                      "alpha": "0.7", "huthresh": 0.1, "advection": "0", "evil": 1})
    assert s == {"resolution_m": 50, "duration_hours": 3, "boundary_level_m": 1.5, "manning": 0.02,
                 "alpha": 0.7, "huthresh": 0.1, "advection": False}
    with pytest.raises(TemplateError, match="duration_hours"):
        tpl.validate({**tpl.defaults(), "duration_hours": 0})
    with pytest.raises(TemplateError, match="resolution_m"):
        tpl.validate({**tpl.defaults(), "resolution_m": 33})
    with pytest.raises(TemplateError, match="alpha"):
        tpl.validate({**tpl.defaults(), "alpha": "abc"})
    assert tpl.validate({}) == tpl.defaults()  # missing keys take defaults


def test_build_command_is_the_standalone_script(tpl, tmp_path):
    cfg = Config(workspace=tmp_path)
    argv = tpl.build_command(tmp_path / "run", tpl.defaults(), cfg)
    assert argv[0] == sys.executable and argv[1] == "-P"
    assert Path(argv[2]).name == "plane_beach_build.py" and Path(argv[2]).is_absolute()
    assert argv[3:] == ["--run-dir", str(tmp_path / "run"), "--settings", str(tmp_path / "run" / "settings.json")]
    assert tpl.stage_cwd("build", tmp_path / "run", cfg) == tmp_path / "run"
    assert tpl.stage_cwd("simulate", tmp_path / "run", cfg) == tmp_path / "run"


def test_overrides_validation_export_and_evidence(tpl, tmp_path):
    cfg = Config(workspace=tmp_path)
    assert tpl.inp_overrides({**tpl.defaults(), "alpha": 0.7, "advection": False}) == {"alpha": "0.7", "huthresh": "0.05", "advection": "0"}
    assert tpl.validate_command(tmp_path, tpl.defaults(), cfg) is None and tpl.has_validation is False
    assert tpl.export_command(tmp_path, tpl.defaults(), cfg) is None and tpl.has_export is False
    assert set(tpl.model_files()) == {"sfincs.dep", "sfincs.msk", "sfincs.bnd", "sfincs.bzs", "sfincs.obs"}
    assert tpl.default_threads(tpl.defaults()) == 1
    assert tpl.example_projects()[0][0] == "Plane beach example"
    layers = tpl.geometry_layers(tmp_path, tpl.defaults())
    assert {l["name"] for l in layers} == {"domain", "boundary", "stations"}


def test_coerce_edge_cases(tpl):
    with pytest.raises(TemplateError, match="advection"):
        tpl.validate({**tpl.defaults(), "advection": "maybe"})
    assert tpl.validate({**tpl.defaults(), "advection": "False"})["advection"] is False
    assert tpl.validate({**tpl.defaults(), "advection": 1})["advection"] is True
    with pytest.raises(TemplateError, match="whole number"):
        tpl.validate({**tpl.defaults(), "duration_hours": "3.7"})
    assert tpl.validate({**tpl.defaults(), "duration_hours": "3.0"})["duration_hours"] == 3
    with pytest.raises(TemplateError, match="finite"):
        tpl.validate({**tpl.defaults(), "alpha": float("nan")})
    with pytest.raises(TemplateError, match="duration_hours"):
        tpl.validate({**tpl.defaults(), "duration_hours": float("inf")})


def test_optional_field_round_trip():
    """Review Focus 3: an empty box means 'use the model's value' and survives coercion as None."""
    f = SettingField("dtmax", "dtmax", "float", None, minimum=1, maximum=600, optional=True)
    assert f.coerce(None) is None and f.coerce("") is None and f.coerce("  ") is None
    assert f.coerce("30") == 30.0
    with pytest.raises(TemplateError, match="dtmax"):
        f.coerce("0.5")
    required = SettingField("alpha", "alpha", "float", 0.5, minimum=0.1, maximum=0.9)
    with pytest.raises(TemplateError, match="required"):
        required.coerce(None)


def test_datetime_field_canonical_form():
    f = SettingField("tstop", "tstop", "datetime", None, optional=True)
    assert f.coerce("2013-12-09 06:00") == "2013-12-09 06:00"
    assert f.coerce("2013-12-09T06:00") == "2013-12-09 06:00"
    assert f.coerce("2013-12-09 06:00:00") == "2013-12-09 06:00"
    assert f.coerce(None) is None
    with pytest.raises(TemplateError, match="tstop"):
        f.coerce("9 Dec 2013")


def test_skip_reasons_default_empty(tpl):
    assert tpl.skip_reasons(tpl.defaults()) == {}
