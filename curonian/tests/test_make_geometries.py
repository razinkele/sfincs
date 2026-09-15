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
