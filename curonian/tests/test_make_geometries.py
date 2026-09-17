import geopandas as gpd
from shapely.geometry import LineString, Polygon

import common
from prep import make_geometries as mg


def test_domain_box_matches_grid():
    b = mg.domain_box().bounds
    assert b == (270_000.0, 6_080_000.0, 370_000.0, 6_190_000.0)


def test_boundary_ring_is_annulus_at_the_mouth():
    ring = mg.boundary_ring()
    mx, my = mg.mouth_xy()
    assert ring.contains(mg.Point(mx + 2300, my)) and not ring.contains(mg.Point(mx + 1000, my))
    assert mg.domain_box().contains(ring)


def test_boundary_points_lie_on_the_seaward_arc():
    pts = mg.boundary_points()
    assert list(pts["index"]) == list(range(1, 8)) and pts.crs.to_epsg() == common.CRS
    mx, my = mg.mouth_xy()
    assert all(abs(p.distance(mg.Point(mx, my)) - 2300) < 1 for p in pts.geometry)
    assert (pts.geometry.x < mx + 200).all()          # seaward = west of the mouth


def test_active_region_contains_lagoon_delta_and_mouth_but_not_open_sea():
    lagoon = Polygon([(280_000, 6_090_000), (350_000, 6_090_000), (350_000, 6_170_000), (280_000, 6_170_000)])
    strait = LineString([(320_000, 6_168_000), (318_000, 6_180_000)])
    reg = mg.active_region(lagoon, strait)
    mx, my = mg.mouth_xy()
    assert reg.contains(mg.Point(300_000, 6_120_000))     # lagoon
    assert reg.contains(mg.Point(345_000, 6_118_000))     # Šilutė lowland
    assert reg.contains(mg.Point(mx - 1500, my))          # harbour mouth disc
    assert not reg.contains(mg.Point(mx - 8000, my))      # open Baltic
    assert mg.domain_box().contains(reg)


def test_stations_have_nine_named_points_inside_domain():
    st = mg.stations()
    assert len(st) == 9 and st["name"].is_unique
    assert st.geometry.within(mg.domain_box()).all()


def test_mouth_disc_and_ring_outer_edge_follow_one_constant(monkeypatch):
    """active_region's mouth disc and boundary_ring's outer edge must stay the same size.

    They were two independent 2600.0 literals. If one is edited and the other is not,
    the ring stops coinciding with the active region's seaward edge and boundary cells
    can land outside the active mask -- a failure main()'s own assert would not catch,
    because the ring would still *intersect* the region.
    """
    monkeypatch.setattr(mg, "MOUTH_R_OUT", 3000.0)
    mx, my = mg.mouth_xy()
    mouth = mg.Point(mx, my)

    ring_outer = max(mouth.distance(mg.Point(c)) for c in mg.boundary_ring().exterior.coords)
    lagoon = Polygon([(280_000, 6_090_000), (350_000, 6_090_000), (350_000, 6_170_000), (280_000, 6_170_000)])
    strait = LineString([(320_000, 6_168_000), (318_000, 6_180_000)])
    reg = mg.active_region(lagoon, strait)

    assert abs(ring_outer - 3000.0) < 1.0
    assert reg.contains(mg.Point(mx - 2900, my)), "mouth disc did not grow with the constant"


# LHMT's own published coordinates for the gauges this model names, from
# api.meteo.lt /v1/hydro-stations, retrieved 2026-09-17. Nida and Vente have no
# entry in that register and so cannot be checked here.
#
# Every position in STATIONS_LONLAT came from a place name (spec section 8's
# fallback: station_pts holds water-quality stations, not gauges) and was then
# nudged onto a wet cell. This test does not forbid an offset -- it bounds each
# one and forces it to be declared, because Juodkrante was once nudged 1.3 km
# WEST, across the Curonian Spit into the Baltic, and reported sea level for
# entire runs with nothing complaining.
LHMT_GAUGES = {
    # station:      (lon, lat, max offset m, why the offset is what it is)
    "Klaipeda":     (21.11915,  55.713148, 2000, "model point is the harbour mouth, not the seaport gauge"),
    "Juodkrante":   (21.121437, 55.533293,  200, "LHMT coordinate used directly; lands on a wet lagoon cell"),
    "Uostadvaris":  (21.290822, 55.344016, 4000, "KNOWN ISSUE: 3.6 km from the gauge A1 is scored against, "
                                                 "inherited from a place-name position; see README"),
    "Rusne":        (21.3803,   55.30066,  1000, "nudged onto a wet cell in the Atmata"),
    "Silute":       (21.475836, 55.337168,  600, "nudged onto a wet cell"),
}


def test_stations_stay_near_their_lhmt_gauges():
    from shapely.geometry import Point

    for name, (lon, lat, limit, why) in LHMT_GAUGES.items():
        mlon, mlat = mg.STATIONS_LONLAT[name]
        offset = Point(*common.lonlat_to_xy(mlon, mlat)).distance(Point(*common.lonlat_to_xy(lon, lat)))
        assert offset <= limit, f"{name} sits {offset:.0f} m from its LHMT gauge (limit {limit} m): {why}"


def test_juodkrante_is_in_the_lagoon_not_the_baltic():
    """The regression this file exists to prevent.

    The Curonian Spit separates two water bodies that are ~1.5 km apart here. A
    station on the wrong side reads Baltic sea level all run and never errors.
    """
    from shapely.geometry import Point

    from prep.make_bathymetry import lagoon_polygon

    p = Point(*common.lonlat_to_xy(*mg.STATIONS_LONLAT["Juodkrante"]))
    assert lagoon_polygon().contains(p), "Juodkrante is outside the lagoon polygon -- check which side of the spit"
