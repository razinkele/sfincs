"""The Nemunas discharge forcing against LHMT's own published record.

tests/test_make_forcing.py checks the *shape* of the forcing — that it covers
the period, interpolates, carries the Minija constant. It cannot tell whether
the numbers are the right numbers: its assertion is `350 < mean < 600`, which an
inverted lag, a different Smalininkai series, or a units slip would all survive.

These tests close that gap by comparing against the authority the data actually
comes from. The local path is curonian_db.gpkg -> make_forcing -> inputs/<event>/dis.csv;
the fixture is the same series taken straight from api.meteo.lt.
"""
from pathlib import Path

import pandas as pd
import pytest

import common

FIXTURES = {
    "xaver_2013": Path(__file__).parent / "data" / "lhmt_smalininkai_2013.csv",
    "april_2013": Path(__file__).parent / "data" / "lhmt_smalininkai_2013_04.csv",
}
PROV_EVENTS = [common.event("xaver_2013"), common.event("april_2013")]
STATION = "smalininku-vms"
API = "https://api.meteo.lt/v1"

# curonian_db.gpkg's Smalininkai record for late March/early April 2013 (a single
# source, source_id 167 throughout -- not a file-boundary artifact) predates LHMT's
# current published series: checked 2026-09-16 against a fresh api.meteo.lt fetch,
# it disagrees for every day from 2013-03-26 through 2013-04-10 (up to 53 m3/s, one
# sign flip in the run), then converges and agrees exactly for 2013-04-11 onward --
# through the rise, the 19 April crest (2150), the recession and the whole scoring
# window. Those ten-to-sixteen days are model spin-up, before the flood and outside
# score_window; from 2 April the gap is at most 17 m3/s on a ~480 m3/s baseline
# (~3%). Refreshing the shared database is a decision for its owner, not this test
# suite, so the exact-match check below starts where the two sources actually agree,
# and test_db_smalininkai_disagrees_with_lhmt_before_11_april_2013 pins the gap
# itself -- so a database refresh, or a further LHMT revision, is caught rather than
# silently absorbed by either test.
# Source days before this date are skipped for the named event, because the database
# disagreed with LHMT there. Empty since 2026-09-17: curonian_db.gpkg's source_id 167
# (Smalininkai, Jan-Jun 2013) was re-ingested from LHMT's current published series --
# 124 of its 181 days had come from an older .xls extraction and differed by up to
# 142 m3/s. April therefore compares its full window again. The mechanism is kept
# because the next stale block will want it: blocks 166 (Nov-Dec 2012) and 169
# (Jan-Apr 2014) still carry their original .xls values and still differ from the API.
KNOWN_STALE_BEFORE: dict = {}


def lhmt(event) -> pd.Series:
    """LHMT daily Nemunas discharge at Smalininkai, m3/s, indexed by date."""
    df = pd.read_csv(FIXTURES[event.name], comment="#", parse_dates=["observationDateUtc"])
    return df.set_index("observationDateUtc")["waterDischarge"].astype(float)


def model(event) -> pd.DataFrame:
    path = event.inputs_dir / "dis.csv"
    if not path.exists():
        pytest.skip(f"{path} not built yet")
    df = pd.read_csv(path, index_col=0, parse_dates=True)
    df.columns = [int(c) for c in df.columns]
    return df


def _midnights(event):
    return pd.date_range(event.tref, event.tstop, freq="D")


@pytest.mark.integration
@pytest.mark.parametrize("event", PROV_EVENTS, ids=lambda e: e.name)
def test_discharge_forcing_reproduces_lhmt_with_the_documented_lag(event):
    """dis.csv at time T must carry LHMT's reading from T - NEMUNAS_LAG_DAYS.

    Source days before KNOWN_STALE_BEFORE[event.name] are skipped, for events that
    have an entry. That dict is empty as of 2026-09-17 -- the one block it covered
    was re-ingested from LHMT -- so every day of every event is checked at the full
    0.5 m3/s tolerance. The skip stays for the next stale block.
    """
    obs, nem = lhmt(event), model(event)[1]
    stale_before = KNOWN_STALE_BEFORE.get(event.name)
    compared = 0
    for t in _midnights(event):
        src = t - pd.Timedelta(days=event.nemunas_lag_days)
        if src not in obs.index:
            continue
        if stale_before is not None and src < stale_before:
            continue
        assert nem.loc[t] == pytest.approx(obs.loc[src], abs=0.5), (
            f"{t:%Y-%m-%d}: model {nem.loc[t]} vs LHMT {obs.loc[src]} at {src:%Y-%m-%d}")
        compared += 1
    assert compared >= 14, f"only {compared} days compared; fixture may not cover the run"


@pytest.mark.integration
@pytest.mark.parametrize("event", PROV_EVENTS, ids=lambda e: e.name)
def test_the_lag_is_applied_in_the_right_direction(event):
    """A lag of the wrong sign, or none, must fail rather than look plausible.

    This is the regression the value check alone cannot catch: Nemunas discharge
    changes slowly, so shifting it a day still gives numbers of the right size.

    Scoped exactly like test_discharge_forcing_reproduces_lhmt_with_the_documented_lag,
    and for a reason worth keeping even now that KNOWN_STALE_BEFORE is empty: days the
    database disagrees on can never match the fixture under ANY lag, so if they were
    counted, same_day/wrong_way could never reach n and both assertions below would be
    unfalsifiable -- passing even with no lag applied at all.
    """
    obs, nem = lhmt(event), model(event)[1]
    stale_before = KNOWN_STALE_BEFORE.get(event.name)
    midnights = [t for t in _midnights(event)
                 if stale_before is None or t - pd.Timedelta(days=event.nemunas_lag_days) >= stale_before]
    same_day = wrong_way = 0
    for t in midnights:
        for offset, name in ((0, "same_day"), (-event.nemunas_lag_days, "wrong_way")):
            src = t - pd.Timedelta(days=offset)
            if src in obs.index and nem.loc[t] == pytest.approx(obs.loc[src], abs=0.5):
                if name == "same_day":
                    same_day += 1
                else:
                    wrong_way += 1
    n = len(midnights)
    assert same_day < n, "dis.csv matches LHMT with NO lag — NEMUNAS_LAG_DAYS is not being applied"
    assert wrong_way < n, "dis.csv matches LHMT with the lag INVERTED"


@pytest.mark.integration
@pytest.mark.parametrize("event", PROV_EVENTS, ids=lambda e: e.name)
def test_minija_column_is_the_documented_constant(event):
    """Column 2 is Minija, held constant; a units slip would show here."""
    minija = model(event)[2]
    assert (minija == event.minija_q).all()
    assert 10.0 < event.minija_q < 200.0, "implausible as m3/s for the Minija"


@pytest.mark.integration
def test_db_smalininkai_agrees_with_lhmt_after_the_2026_09_17_reingest():
    """The database's Smalininkai block must match LHMT's published series.

    Succeeds test_db_smalininkai_disagrees_with_lhmt_before_11_april_2013, which
    pinned the gap while it existed. On 2026-09-17 source_id 167 (Jan-Jun 2013) was
    re-ingested from api.meteo.lt: 124 of its 181 days had come from an older
    extraction, `smalininkai 2013 01-06.xls`, and differed by up to 142 m3/s. The
    block mean moved 701.7 -> 683.4 m3/s.

    This asserts the refresh holds. It fails if the block is restored from the .xls,
    if LHMT revises again, or if a partial re-ingest leaves some days behind -- each
    of which a human should see rather than have silently absorbed into the forcing.

    Scope note: only block 167 was refreshed. Blocks 166 (Nov-Dec 2012) and 169
    (Jan-Apr 2014) still carry their original .xls values and still differ from the
    API, so a step may exist at the block boundaries. Block 168 (Jul-Dec 2013), which
    is where the Xaver event lives, already agreed exactly and was not touched.
    """
    event = common.event("april_2013")
    obs = lhmt(event)
    df = common.read_table(
        "SELECT date, discharge_m3s FROM river_discharge WHERE river='Nemunas' AND gauge='Smalininkai' "
        "AND date BETWEEN ? AND ?", event.data_window)
    db = pd.Series(df["discharge_m3s"].values, index=pd.to_datetime(df["date"]))

    compared = 0
    for day, q in db.items():
        if day not in obs.index:
            continue
        assert q == pytest.approx(obs.loc[day], abs=0.5), (
            f"{day:%Y-%m-%d}: db {q} vs LHMT {obs.loc[day]} -- the Jan-Jun 2013 re-ingest has "
            "regressed, or LHMT has revised again; look before changing this tolerance")
        compared += 1
    assert compared >= 40, f"only {compared} days compared; expected the full April data window"


@pytest.mark.integration
@pytest.mark.network
@pytest.mark.parametrize("event", PROV_EVENTS, ids=lambda e: e.name)
def test_fixture_still_matches_the_live_lhmt_record(event):
    """Guards the other direction: that the committed fixture has not gone stale.

    LHMT can revise a historical series. Skips rather than fails when the API is
    unreachable — someone else's outage is not this repo's regression.
    """
    import requests

    obs = lhmt(event)
    months = pd.period_range(event.tref, event.tstop, freq="M").strftime("%Y-%m")
    live = {}
    for month in months:
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
                f"refresh {FIXTURES[event.name].name}")
            checked += 1
    assert checked >= 14, f"live API returned only {checked} comparable days"
