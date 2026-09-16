"""The Nemunas discharge forcing against LHMT's own published record.

tests/test_make_forcing.py checks the *shape* of the forcing — that it covers
the period, interpolates, carries the Minija constant. It cannot tell whether
the numbers are the right numbers: its assertion is `350 < mean < 600`, which an
inverted lag, a different Smalininkai series, or a units slip would all survive.

These tests close that gap by comparing against the authority the data actually
comes from. The local path is curonian_db.gpkg -> make_forcing -> inputs/dis.csv;
the fixture is the same series taken straight from api.meteo.lt.
"""
from pathlib import Path

import pandas as pd
import pytest

import common

XAVER = common.EVENTS["xaver_2013"]

FIXTURE = Path(__file__).parent / "data" / "lhmt_smalininkai_2013.csv"
STATION = "smalininku-vms"
API = "https://api.meteo.lt/v1"


def lhmt() -> pd.Series:
    """LHMT daily Nemunas discharge at Smalininkai, m3/s, indexed by date."""
    df = pd.read_csv(FIXTURE, comment="#", parse_dates=["observationDateUtc"])
    return df.set_index("observationDateUtc")["waterDischarge"].astype(float)


def model() -> pd.DataFrame:
    df = pd.read_csv(XAVER.inputs_dir / "dis.csv", index_col=0, parse_dates=True)
    df.columns = [int(c) for c in df.columns]
    return df


def _midnights():
    return pd.date_range(common.TREF, common.TSTOP, freq="D")


@pytest.mark.integration
def test_discharge_forcing_reproduces_lhmt_with_the_documented_lag():
    """dis.csv at time T must carry LHMT's reading from T - NEMUNAS_LAG_DAYS."""
    obs, nem = lhmt(), model()[1]
    compared = 0
    for t in _midnights():
        src = t - pd.Timedelta(days=common.NEMUNAS_LAG_DAYS)
        if src not in obs.index:
            continue
        assert nem.loc[t] == pytest.approx(obs.loc[src], abs=0.5), (
            f"{t:%Y-%m-%d}: model {nem.loc[t]} vs LHMT {obs.loc[src]} at {src:%Y-%m-%d}")
        compared += 1
    assert compared >= 14, f"only {compared} days compared; fixture may not cover the run"


@pytest.mark.integration
def test_the_lag_is_applied_in_the_right_direction():
    """A lag of the wrong sign, or none, must fail rather than look plausible.

    This is the regression the value check alone cannot catch: Nemunas discharge
    changes slowly, so shifting it a day still gives numbers of the right size.
    """
    obs, nem = lhmt(), model()[1]
    same_day = wrong_way = 0
    for t in _midnights():
        for offset, name in ((0, "same_day"), (-common.NEMUNAS_LAG_DAYS, "wrong_way")):
            src = t - pd.Timedelta(days=offset)
            if src in obs.index and nem.loc[t] == pytest.approx(obs.loc[src], abs=0.5):
                if name == "same_day":
                    same_day += 1
                else:
                    wrong_way += 1
    n = len(_midnights())
    assert same_day < n, "dis.csv matches LHMT with NO lag — NEMUNAS_LAG_DAYS is not being applied"
    assert wrong_way < n, "dis.csv matches LHMT with the lag INVERTED"


@pytest.mark.integration
def test_minija_column_is_the_documented_constant():
    """Column 2 is Minija, held constant; a units slip would show here."""
    minija = model()[2]
    assert (minija == common.MINIJA_Q_DEC).all()
    assert 10.0 < common.MINIJA_Q_DEC < 200.0, "implausible as m3/s for the Minija"


@pytest.mark.integration
@pytest.mark.network
def test_fixture_still_matches_the_live_lhmt_record():
    """Guards the other direction: that the committed fixture has not gone stale.

    LHMT can revise a historical series. Skips rather than fails when the API is
    unreachable — someone else's outage is not this repo's regression.
    """
    import requests

    obs = lhmt()
    live = {}
    for month in ("2013-11", "2013-12"):
        try:
            r = requests.get(f"{API}/hydro-stations/{STATION}/observations/historical/{month}",
                             headers={"User-Agent": "curonian-sfincs-tests/0.1"}, timeout=30)
            r.raise_for_status()
        except requests.RequestException as exc:
            pytest.skip(f"api.meteo.lt unreachable: {exc}")
        for o in r.json().get("observations", []):
            if o.get("waterDischarge") is not None:
                live[pd.Timestamp(o["observationDateUtc"])] = float(o["waterDischarge"])

    checked = 0
    for day, q in obs.items():
        if day in live:
            assert live[day] == pytest.approx(q, abs=0.5), (
                f"{day:%Y-%m-%d}: fixture {q} but LHMT now reports {live[day]} — "
                f"refresh tests/data/lhmt_smalininkai_2013.csv")
            checked += 1
    assert checked >= 14, f"live API returned only {checked} comparable days"
