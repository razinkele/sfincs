from sfincs_ui.services.model_service import OVERRIDES_DIFF, apply_overrides, read_settings, write_overrides, write_settings

INP = """\
x0              = 0.0
mmax            = 50

advection       = 1
alpha           = 0.5
huthresh        = 0.05
manning         = 0.04
"""


def test_settings_round_trip(tmp_path):
    p = write_settings(tmp_path, {"b": 1, "a": [1, 2]})
    assert p.name == "settings.json" and p.read_text() == '{\n  "a": [\n    1,\n    2\n  ],\n  "b": 1\n}'
    assert read_settings(tmp_path) == {"b": 1, "a": [1, 2]}


def test_apply_overrides_rewrites_in_place_and_appends_missing(tmp_path):
    inp = tmp_path / "sfincs.inp"
    inp.write_text(INP)
    diff = apply_overrides(inp, {"alpha": "0.7", "advection": "0", "tstop": "20240101 030000"})
    text = inp.read_text()
    assert "alpha           = 0.7\n" in text and "advection       = 0\n" in text
    assert "huthresh        = 0.05\n" in text and text.endswith("tstop           = 20240101 030000\n")
    assert text.index("advection") < text.index("alpha")  # order preserved
    assert "-alpha           = 0.5" in diff and "+alpha           = 0.7" in diff and "+tstop" in diff


def test_apply_overrides_no_change_gives_empty_diff(tmp_path):
    inp = tmp_path / "sfincs.inp"
    inp.write_text(INP)
    assert apply_overrides(inp, {"alpha": "0.5"}) == ""
    assert inp.read_text() == INP


def test_write_overrides_is_idempotent_and_writes_diff_last(tmp_path):
    (tmp_path / "sfincs.inp").write_text(INP)
    first = write_overrides(tmp_path, {"alpha": "0.7"})
    assert first.name == OVERRIDES_DIFF and "+alpha           = 0.7" in first.read_text()
    assert (tmp_path / "sfincs.inp.orig").read_text() == INP
    text_after_first = (tmp_path / "sfincs.inp").read_text()
    second = write_overrides(tmp_path, {"alpha": "0.7"})
    assert (tmp_path / "sfincs.inp").read_text() == text_after_first
    assert second.read_text() == first.read_text()


def test_write_overrides_records_empty_diff_when_nothing_changes(tmp_path):
    (tmp_path / "sfincs.inp").write_text(INP)
    p = write_overrides(tmp_path, {"alpha": "0.5"})
    assert p.exists() and p.read_text() == ""
