"""The two invariants the README's April numbers rest on."""
import numpy as np
import pandas as pd
import geopandas as gpd
import pytest
from shapely.geometry import Polygon

import common
from diag import head_decomposition as hd
from diag import mass_balance as mb


def _series(values, times):
    return pd.Series(values, index=pd.DatetimeIndex(times))


def test_shared_stamps_keeps_only_readings_every_station_has():
    """Klaipeda and Uostadvaris are read daily, Nida and Vente twice daily.

    Averaging each station over its own stamps would compare a daily mean against a
    twice-daily one, and the links would then not add up. This is the guard.
    """
    daily = pd.date_range("2013-04-22 06:00", "2013-04-26 06:00", freq="D")
    twice = pd.date_range("2013-04-22 06:00", "2013-04-26 18:00", freq="12h")
    obs = {g: _series(np.zeros(len(daily)), daily) for g in ("Klaipeda", "Uostadvaris")}
    obs |= {g: _series(np.zeros(len(twice)), twice) for g in ("Nida", "Vente")}

    stamps = hd.shared_stamps(obs, hd.CREST)
    assert list(stamps) == list(daily)


def test_link_excesses_sum_to_the_sea_to_delta_excess():
    """The README quotes both, and reads the links as a decomposition of the total.

    That only holds because every station is sampled on the same stamps: each
    interior station's bias then cancels between the two links meeting at it. A
    sabotage check follows -- offsetting one station's *model* series must move two
    links in opposite directions and leave the total alone.
    """
    stamps = pd.date_range("2013-04-22 06:00", "2013-04-26 06:00", freq="D")
    rng = np.random.default_rng(0)
    obs = {g: _series(rng.normal(size=len(stamps)), stamps) for g in hd.CHAIN}
    his = pd.DataFrame({g: obs[g] + 0.1 * i for i, g in enumerate(hd.CHAIN)}, index=stamps)

    d = hd.decompose(his, obs, stamps)
    total = d["total"][1] - d["total"][2]
    assert sum(dm - do for _, dm, do in d["links"]) == pytest.approx(total, abs=1e-12)

    bumped = his.copy(); bumped["Nida"] += 0.25
    d2 = hd.decompose(bumped, obs, stamps)
    assert d2["total"][1] - d2["total"][2] == pytest.approx(total, abs=1e-12)
    moved = [round((b[1] - b[2]) - (a[1] - a[2]), 6) for a, b in zip(d["links"], d2["links"])]
    assert sorted(moved) == [-0.25, 0.0, 0.25]


def test_lagoon_cells_needs_the_polygon_and_the_active_mask():
    """Either condition alone counts the wrong water.

    The polygon alone takes cells the model never solves; the mask alone takes the
    Baltic and the flooded delta. The area this divides by has to be neither.
    """
    n = 6
    msk = np.zeros((n, n), dtype=int)
    msk[:, :4] = 1                                   # active on the left
    x0, y0 = common.X0, common.Y0
    box = Polygon([(x0 + 200, y0 + 200), (x0 + 600, y0 + 200),
                   (x0 + 600, y0 + 400), (x0 + 200, y0 + 400)])
    lagoon = gpd.GeoDataFrame(geometry=[box], crs=common.CRS)

    cells = mb.lagoon_cells(lagoon, msk)
    assert cells.sum() == 4                          # the box spans 4x2 cells; only 2x2 are active
    assert not cells[:, 4:].any(), "cells outside the active mask were counted"
    assert not cells[0, :].any(), "cells outside the polygon were counted"
