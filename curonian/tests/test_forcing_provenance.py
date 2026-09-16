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
KNOWN_STALE_BEFORE = {"april_2013": pd.Timestamp("2013-04-11")}


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

    Scoped to skip source days before KNOWN_STALE_BEFORE[event.name] (April only):
    the database's own record disagrees with LHMT there for reasons that are
    pinned, not fixed, by test_db_smalininkai_disagrees_with_lhmt_before_11_april_2013
    below. Every other event, and every day this event's database agrees on, is
    still checked at the full 0.5 m3/s tolerance.
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

    Scoped exactly like test_discharge_forcing_reproduces_lhmt_with_the_documented_lag:
    restricted to midnights whose *correctly-lagged* source day is at or after
    KNOWN_STALE_BEFORE[event.name] (April only; a no-op for Xaver). Without this,
    the six stale April spin-up days can never match the fixture under any lag, so
    same_day/wrong_way could never reach the un-scoped n and both assertions below
    would be unfalsifiable for April -- passing even with no lag applied at all.
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
def test_db_smalininkai_disagrees_with_lhmt_before_11_april_2013():
    """Pins the known database/LHMT gap so it stays visible rather than swept under
    the scoping in test_discharge_forcing_reproduces_lhmt_with_the_documented_lag.

    curonian_db.gpkg's Smalininkai discharge for 2013-03-26..2013-04-10 (all one
    source, source_id 167 -- confirmed not a file-boundary artifact) disagrees with
    the LHMT fixture fetched 2026-09-16 by up to 53 m3/s. Bounding it here means a
    database refresh, or a further LHMT revision either direction, breaks this
    assertion and gets a human's attention instead of silently changing what the
    other tests skip over.
    """
    event = common.event("april_2013")
    obs = lhmt(event)
    range_start = event.data_window[0]
    range_end = (KNOWN_STALE_BEFORE["april_2013"] - pd.Timedelta(days=1)).strftime("%Y-%m-%d")
    df = common.read_table(
        "SELECT date, discharge_m3s FROM river_discharge WHERE river='Nemunas' AND gauge='Smalininkai' "
        "AND date BETWEEN ? AND ?", (range_start, range_end))
    db = pd.Series(df["discharge_m3s"].values, index=pd.to_datetime(df["date"]))

    compared, max_diff = 0, 0.0
    for day, q in db.items():
        if day not in obs.index:
            continue
        diff = abs(q - obs.loc[day])
        max_diff = max(max_diff, diff)
        assert diff <= 55.0, (
            f"{day:%Y-%m-%d}: db {q} vs LHMT {obs.loc[day]}, diff {diff} exceeds the known ~53 m3/s gap")
        compared += 1
    assert compared >= 14, f"only {compared} days compared; expected the full 26 Mar-10 Apr stretch"
    # Pins the *magnitude*, not just the existence, of the gap: an upper bound alone
    # (diff <= 55.0 above) would stay green if a partial refresh fixed fifteen of the
    # sixteen days and left one off by a few m3/s -- exactly the silent drift this
    # test exists to catch. 53.0 is the maximum observed on 2026-09-16 (2013-04-01,
    # DB 473 vs LHMT 526); +-2.0 is headroom for float/round-trip noise, not for a
    # real revision. If this fails because the gap shrank or moved, that is the
    # database being refreshed or LHMT revising again -- update the pin and
    # KNOWN_STALE_BEFORE deliberately, do not just widen the tolerance.
    assert max_diff == pytest.approx(53.0, abs=2.0), (
        f"known database/LHMT gap changed shape: max diff is now {max_diff}, was 53.0 on 2026-09-16 -- "
        "a human should look before this pin is updated")


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
