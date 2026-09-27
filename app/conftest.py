"""Shared fixtures for the viewer's tests. `synthetic` builds the 20 x 30 run
from map_fixture.py in a temp data dir and points sfincs_data at it."""
import pytest

import map_fixture
import sfincs_data as sd

SYNTHETIC_RUN = "synthetic_2013"


@pytest.fixture
def synthetic(tmp_path, monkeypatch):
    runs, results = tmp_path / "runs", tmp_path / "results"
    map_fixture.make_run(runs / SYNTHETIC_RUN)
    map_fixture.write_validation(results / SYNTHETIC_RUN)
    map_fixture.write_inputs(tmp_path / "inputs")
    monkeypatch.setattr(sd, "DATA_DIR", tmp_path)
    monkeypatch.setattr(sd, "RUNS_DIR", runs)
    monkeypatch.setattr(sd, "RESULTS_DIR", results)
    return SYNTHETIC_RUN
