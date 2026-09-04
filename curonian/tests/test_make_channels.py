import pytest
from shapely.geometry import LineString

import common
from prep import make_channels as mc


def test_build_channels_from_fallback_has_three_rows():
    gdf = mc.build_channels(None)
    assert list(gdf["name"]) == ["strait", "atmata", "skirvyte"]
    assert gdf.crs.to_epsg() == common.CRS
    assert dict(zip(gdf["name"], gdf["rivwth"])) == {"strait": 400, "atmata": 200, "skirvyte": 150}
    assert dict(zip(gdf["name"], gdf["rivbed"])) == {"strait": -12.0, "atmata": -4.0, "skirvyte": -3.0}
    lengths = dict(zip(gdf["name"], gdf.geometry.length))
    assert 10_000 < lengths["strait"] < 20_000
    assert 5_000 < lengths["atmata"] < 25_000 and 5_000 < lengths["skirvyte"] < 25_000


def test_build_channels_prefers_osm_geometry():
    osm = {"atmata": LineString([(21.37, 55.30), (21.25, 55.335)]),
           "skirvyte": LineString([(21.37, 55.30), (21.28, 55.27)])}
    gdf = mc.build_channels(osm).set_index("name")
    assert gdf.loc["atmata", "geometry"].length == pytest.approx(
        mc.to_3346(osm["atmata"]).length, rel=1e-6)


@pytest.mark.integration
def test_fetch_osm_rivers_returns_both_distributaries():
    osm = mc.fetch_osm_rivers()
    assert set(osm) == {"atmata", "skirvyte"}
    for line in osm.values():
        assert line.geom_type == "LineString" and len(line.coords) > 5
