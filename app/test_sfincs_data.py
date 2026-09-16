"""Parser contract between validate.py's report format and the viewer.

These run against the committed reports under curonian/results/ (one parametrized
test sweeps every published variant), so a change to validate.py's output format
fails here instead of silently emptying a panel on laguna.ku.lt.

    micromamba run -n shiny python -m pytest app/ -q
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


def test_marginal_pass_is_reported_but_flagged(monkeypatch):
    """A 'met (marginal)' verdict must read as a warning, not a clean pass.

    This used to lean on Xaver's C2, which was marginal at the time. The
    2026-09-17 re-run on corrected strait geometry turned C2 into a clean
    'met', so there is no longer a marginal verdict anywhere in the committed
    reports. The behaviour still needs a test, so the verdict is injected
    rather than borrowed from whichever run happens to be marginal today.
    """
    real = sd.criteria(VARIANT)
    marginal = [dict(c, verdict="met (marginal)") if i == 0 else c
                for i, c in enumerate(real)]
    monkeypatch.setattr(sd, "criteria", lambda v: marginal)
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
    assert sd.flooded_area_km2(VARIANT) == pytest.approx(157.3)


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


@pytest.mark.parametrize("variant", sd.list_variants())
def test_every_variant_exposes_a_whole_period_and_a_scored_window(variant):
    """Both headings must parse, whatever the event calls its scored window.

    Xaver's report says "Storm window"; April's says "Scoring window". The regex
    is the only thing that finds either, and a miss empties the metrics panel
    silently rather than failing.
    """
    found = sd.periods(variant)
    assert "Whole period" in found
    scored = [k for k in found if k != "Whole period"]
    assert len(scored) == 1, f"{variant}: expected one scored window, got {scored}"
    # metric_tables() keys its tables by the full heading line ("name: range"),
    # periods() by the bare name -- same regex, same input, so the two must
    # describe the same headings once reassembled the same way.
    assert set(sd.metric_tables(variant)) == {f"{k}: {v}" for k, v in found.items()}
