import pytest
import requests
from shapely.geometry import LineString

import common
from prep import make_channels as mc
import geopandas as gpd


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
@pytest.mark.network
def test_fetch_osm_rivers_returns_both_distributaries():
    try:
        osm = mc.fetch_osm_rivers()
    except requests.HTTPError as exc:
        if exc.response is not None and exc.response.status_code >= 500:
            pytest.skip(f"Overpass unavailable: {exc}")
        raise
    except (requests.Timeout, requests.ConnectionError) as exc:
        pytest.skip(f"Overpass unavailable: {exc}")
    assert set(osm) == {"atmata", "skirvyte"}
    for line in osm.values():
        assert line.geom_type == "LineString" and len(line.coords) > 5


def test_main_keeps_existing_osm_file_when_fetch_fails(tmp_path, monkeypatch):
    """When Overpass fails but an existing OSM-derived file exists, keep it unchanged."""
    # Create initial OSM-derived channels file
    osm_dict = {"atmata": LineString([(21.37, 55.30), (21.25, 55.335)]),
                "skirvyte": LineString([(21.37, 55.30), (21.28, 55.27)])}
    gdf = mc.build_channels(osm_dict)
    gdf["source"] = ["fixed", "osm", "osm"]
    out_path = tmp_path / "channels.geojson"
    gdf.to_file(out_path, driver="GeoJSON")
    original_mtime = out_path.stat().st_mtime

    # Mock fetch_osm_rivers to raise
    monkeypatch.setattr(mc, "fetch_osm_rivers", lambda: (_ for _ in ()).throw(RuntimeError("down")))

    # Call main() - should keep existing file
    result = mc.main(out=out_path)
    assert out_path.stat().st_mtime == original_mtime  # file not rewritten
    assert result["source"].tolist() == ["fixed", "osm", "osm"]


def test_main_exits_2_without_allow_fallback_when_no_file(tmp_path, monkeypatch):
    """When Overpass fails, no existing file, and allow_fallback=False, exit(2)."""
    # Mock fetch_osm_rivers to raise
    monkeypatch.setattr(mc, "fetch_osm_rivers", lambda: (_ for _ in ()).throw(RuntimeError("down")))

    out_path = tmp_path / "channels.geojson"
    with pytest.raises(SystemExit) as exc_info:
        mc.main(out=out_path, allow_fallback=False)
    assert exc_info.value.code == 2
    assert not out_path.exists()


def test_main_writes_fallback_when_allow_fallback_true(tmp_path, monkeypatch):
    """When allow_fallback=True, write fallback coordinates."""
    # Mock fetch_osm_rivers to raise
    monkeypatch.setattr(mc, "fetch_osm_rivers", lambda: (_ for _ in ()).throw(RuntimeError("down")))

    out_path = tmp_path / "channels.geojson"
    result = mc.main(out=out_path, allow_fallback=True)
    assert out_path.exists()
    assert result["source"].tolist() == ["fixed", "fallback", "fallback"]


def test_merge_reports_discarded_segments(capsys):
    """_merge silently drops all but the longest segment of a disjoint way; say so."""
    far_apart = [LineString([(21.0, 55.0), (21.1, 55.0)]),      # the long one, kept
                 LineString([(21.5, 55.5), (21.52, 55.5)])]     # disjoint, discarded
    merged = mc._merge(far_apart)
    assert merged.geom_type == "LineString"
    assert "discard" in capsys.readouterr().out.lower()


def test_merge_stays_quiet_when_ways_join_up(capsys):
    joined = [LineString([(21.0, 55.0), (21.1, 55.0)]), LineString([(21.1, 55.0), (21.2, 55.0)])]
    merged = mc._merge(joined)
    assert merged.geom_type == "LineString" and capsys.readouterr().out == ""


def test_build_channels_raises_valueerror_on_implausible_strait(monkeypatch):
    """Runtime validation must survive `python -O`, which strips bare asserts."""
    monkeypatch.setattr(mc, "STRAIT_LONLAT", [(21.15, 55.62), (21.1501, 55.6201)])   # ~13 m long
    with pytest.raises(ValueError, match="strait"):
        mc.build_channels(None)


def test_main_lets_a_client_bug_propagate(tmp_path, monkeypatch):
    """A TypeError in our own fetch code is a bug, not an Overpass outage: it must
    not be swallowed into the fallback path, which would silently degrade the input."""
    monkeypatch.setattr(mc, "fetch_osm_rivers", lambda: (_ for _ in ()).throw(TypeError("client bug")))
    with pytest.raises(TypeError):
        mc.main(out=tmp_path / "channels.geojson", allow_fallback=True)
