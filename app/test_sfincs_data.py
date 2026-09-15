"""Parser contract between validate.py's report format and the viewer.

These run against the committed report in curonian/results/xaver_2013/, so a
change to validate.py's output format fails here instead of silently emptying
a panel on laguna.ku.lt.

    micromamba run -n hydromt-sfincs python -m pytest app/ -q
"""

import pytest

import app as viewer
import sfincs_data as sd

VARIANT = "xaver_2013"

pytestmark = pytest.mark.skipif(
    not sd.results_path(VARIANT, "validation.md").is_file(),
    reason=f"no committed validation report for {VARIANT}",
)


def test_lists_the_committed_run_variants():
    assert VARIANT in sd.list_variants()


def test_criteria_are_parsed_with_verdicts():
    items = sd.criteria(VARIANT)
    assert [c["label"] for c in items][:4] == [
        "C1 Uostadvaris peak",
        "C2 Nida 8 Dec rise",
        "C3 Klaipeda RMSE",
        "C4 Silute uplands",
    ]
    assert all(c["verdict"] and c["detail"] for c in items)


def test_info_lines_are_kept_but_not_scored():
    verdicts = [c["verdict"] for c in sd.criteria(VARIANT)]
    assert "info" in verdicts
    _, sentence = viewer.headline(VARIANT)
    # the two info lines must not inflate the denominator
    assert sentence.startswith("4 of 4")


def test_marginal_pass_is_reported_but_flagged():
    colour, sentence = viewer.headline(VARIANT)
    assert colour == "warning"
    assert "marginal" in sentence


def test_a_failed_criterion_turns_the_headline_red(monkeypatch):
    monkeypatch.setattr(
        sd, "criteria",
        lambda _v: [{"verdict": "met"}, {"verdict": "not met"}],
    )
    colour, sentence = viewer.headline(VARIANT)
    assert colour == "danger"
    assert sentence.startswith("1 of 2")


def test_unscored_verdicts_leave_the_denominator(monkeypatch):
    # validate.py emits "n/a" when a criterion cannot be evaluated.
    monkeypatch.setattr(
        sd, "criteria",
        lambda _v: [{"verdict": "met"}, {"verdict": "n/a"}],
    )
    _, sentence = viewer.headline(VARIANT)
    assert sentence.startswith("1 of 1")


def test_flooded_area_is_read_from_the_report():
    assert sd.flooded_area_km2(VARIANT) == pytest.approx(165.6)


def test_both_metric_tables_are_parsed():
    tables = sd.metric_tables(VARIANT)
    assert len(tables) == 2
    whole = next(f for k, f in tables.items() if k.startswith("Whole period"))
    assert list(whole["station"]) == ["Klaipeda", "Nida", "Vente", "Uostadvaris"]
    assert "RMSE m" in whole.columns


def test_periods_cover_whole_and_storm_windows():
    assert set(sd.periods(VARIANT)) == {"Whole period", "Storm window"}


def test_missing_variant_degrades_quietly():
    assert sd.criteria("no_such_run") == []
    assert sd.flooded_area_km2("no_such_run") is None
    assert sd.metric_tables("no_such_run") == {}
    assert sd.station_levels("no_such_run").empty


@pytest.mark.skipif(
    not sd.run_path(VARIANT, "sfincs.inp").is_file(),
    reason="run outputs are gitignored; present only on the modelling machine",
)
def test_run_summary_reads_the_model_setup():
    summary = dict(sd.run_summary(VARIANT))
    assert summary["Projection"] == "EPSG:3346"
    assert "1000 x 1100 cells" in summary["Grid"]
