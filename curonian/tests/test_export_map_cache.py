"""The Map tab's offline export: event resolution, gauge readings, end to end."""
import sys

import pandas as pd
import pytest

import common

sys.path.insert(0, str(common.REPO / "app"))
import map_core as mc  # noqa: E402
import map_fixture as fx  # noqa: E402

from prep import export_map_cache as emc  # noqa: E402


@pytest.mark.parametrize("run, event", [
    ("april_2013", "april_2013"),
    ("april_2013_gridwind_pressure", "april_2013"),
    ("xaver_2013_gridwind", "xaver_2013"),
])
def test_event_is_the_longest_matching_prefix(run, event):
    assert emc.event_for_run(run).name == event


@pytest.mark.parametrize("run", ["april", "april_2013x", "baseline"])
def test_unknown_run_names_fail_instead_of_defaulting(run):
    with pytest.raises(SystemExit, match="no event matches"):
        emc.event_for_run(run)


def test_main_writes_the_cache_and_the_gauge_csv(tmp_path, monkeypatch):
    runs, results = tmp_path / "runs", tmp_path / "results"
    fx.make_run(runs / "april_2013_synthetic")
    fake = pd.DataFrame({"site": ["Klaipeda"], "time": [pd.Timestamp("2013-04-05 06:00")], "level_m": [0.12]})
    monkeypatch.setattr(emc, "gauge_obs", lambda event: fake)
    meta = emc.main("april_2013_synthetic", runs_dir=runs, results_root=results)
    assert mc.cache_valid(runs / "april_2013_synthetic")
    assert meta["n_active"] == fx.N * fx.M - 15
    csv = pd.read_csv(results / "april_2013_synthetic" / "gauge_obs.csv", parse_dates=["time"])
    assert csv.to_dict("records") == [{"site": "Klaipeda", "time": pd.Timestamp("2013-04-05 06:00"), "level_m": 0.12}]


@pytest.mark.integration
def test_gauge_obs_equals_what_validate_scores():
    import validate
    from prep.make_forcing import load_gauge_levels
    event = common.event("april_2013")
    frame = emc.gauge_obs(event)
    assert set(frame["site"]) == set(validate.GAUGES)
    for site in validate.GAUGES:
        ours = frame[frame["site"] == site].set_index("time")["level_m"]
        theirs = load_gauge_levels(site, event)
        pd.testing.assert_series_equal(ours, theirs, check_names=False, check_index_type=False)
