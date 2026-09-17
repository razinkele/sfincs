"""Break an event's along-lagoon head error down by station and by link.

The README's April findings quote these numbers; this is where they come from, so
they can be re-derived rather than trusted.

Two views of the same run, both sampled on the gauge readings the four stations
*share* inside a window -- nothing is interpolated, and every station is read on the
same stamps, so the per-link errors sum to the sea-to-delta error exactly:

- by station: model minus gauge, which is what a criterion like A3 differences
- by link: the head between adjacent stations, model against observed

Run it as `python -m diag.head_decomposition [event] [run]` from `curonian/`.
"""
from __future__ import annotations

import sys

import pandas as pd

import common
import validate as va
from prep import make_forcing as mf

# A3's window (validate.APRIL_CREST), with the closing day included: the 26th's 06:00
# reading is one of the five A3 averages, and a bare Timestamp("2013-04-26") is
# midnight, which would drop it.
CREST = (pd.Timestamp("2013-04-22"), pd.Timestamp("2013-04-26 23:59"))
# Sea to delta, in order, so the links chain.
CHAIN = ("Klaipeda", "Nida", "Vente", "Uostadvaris")


def shared_stamps(obs: dict[str, pd.Series], window: tuple[pd.Timestamp, pd.Timestamp]) -> pd.DatetimeIndex:
    """The reading times every station has inside `window`.

    Klaipeda and Uostadvaris are read once a day, Nida and Vente twice, so the
    intersection is the daily 06:00 set. Taking it once and using it for every
    station is what makes the links add up.
    """
    stamps = None
    for g in CHAIN:
        idx = obs[g].loc[window[0]:window[1]].index
        stamps = idx if stamps is None else stamps.intersection(idx)
    return stamps


def decompose(his: pd.DataFrame, obs: dict[str, pd.Series], stamps: pd.DatetimeIndex) -> dict:
    """Per-station bias and per-link head error on one set of stamps.

    Because every station is read on the same stamps, the link excesses sum to the
    sea-to-delta excess exactly -- each interior station's bias cancels between the
    two links that meet at it. `tests/test_diag.py` pins that.
    """
    at = {g: his[g].reindex(stamps, method="nearest") for g in CHAIN}
    station = {g: (at[g] - obs[g].loc[stamps]) for g in CHAIN}
    links = []
    for a, b in zip(CHAIN[-1:0:-1], CHAIN[-2::-1]):              # delta -> sea
        dm = (at[a] - at[b]).mean()
        do = (obs[a].loc[stamps] - obs[b].loc[stamps]).mean()
        links.append((f"{a} - {b}", dm, do))
    dm = (at[CHAIN[-1]] - at[CHAIN[0]]).mean()
    do = (obs[CHAIN[-1]].loc[stamps] - obs[CHAIN[0]].loc[stamps]).mean()
    return {
        "station": {g: (r.mean(), r.std(ddof=0)) for g, r in station.items()},
        "links": links,
        "total": (f"{CHAIN[-1]} - {CHAIN[0]}", dm, do),
    }


def report(event: common.Event, run: str) -> None:
    his = va.load_his(common.RUNS / run)
    obs = {g: mf.load_gauge_levels(g, event) for g in CHAIN}

    for label, window in (("A3 crest", CREST), (event.score_label, event.score_window)):
        stamps = shared_stamps(obs, window)
        d = decompose(his, obs, stamps)
        print(f"\n{label}: {len(stamps)} shared readings, "
              f"{stamps[0]:%Y-%m-%d %H:%M} .. {stamps[-1]:%Y-%m-%d %H:%M}")

        print(f"  {'station':14s} {'model-gauge':>12s} {'sd':>7s}")
        for g, (bias, sd) in d["station"].items():
            print(f"  {g:14s} {bias:+12.3f} {sd:7.3f}")

        print(f"  {'link':26s} {'model':>8s} {'observed':>9s} {'excess':>8s}")
        for name, dm, do in d["links"]:
            print(f"  {name:26s} {dm:+8.3f} {do:+9.3f} {dm - do:+8.3f}")
        name, dm, do = d["total"]
        print(f"  {name:26s} {dm:+8.3f} {do:+9.3f} {dm - do:+8.3f}   <- sea to delta")


if __name__ == "__main__":
    name = sys.argv[1] if len(sys.argv) > 1 else "april_2013"
    report(common.event(name), sys.argv[2] if len(sys.argv) > 2 else name)
