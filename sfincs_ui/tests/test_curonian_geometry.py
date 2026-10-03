import json
from pathlib import Path

import pytest

from sfincs_ui.config import REPO_ROOT
from sfincs_ui.templates.curonian import load_geometry

INPUTS = REPO_ROOT / "curonian" / "inputs"


def test_layers_from_the_real_inputs_are_wgs84():
    if not (INPUTS / "active_region.geojson").is_file():
        pytest.skip("curonian inputs not in this checkout")
    load_geometry.cache_clear()
    layers = {l["name"]: l for l in load_geometry(INPUTS)}
    assert set(layers) == {"domain", "channels", "boundary", "inflows", "stations"}
    assert all(l["crs"] == "EPSG:4326" for l in layers.values())
    lon, lat = layers["stations"]["geometry"]["coordinates"][0]
    assert 20.5 < lon < 22.5 and 55.0 < lat < 56.0, (lon, lat)  # the lagoon, not the Atlantic
    assert len(layers["stations"]["labels"]) == len(layers["stations"]["geometry"]["coordinates"]) == 9
    assert layers["domain"]["geometry"]["type"] == "Polygon" and layers["channels"]["geometry"]["type"] == "MultiLineString"
    assert layers["channels"]["labels"] == ["strait", "atmata", "skirvyte"]
    assert layers["inflows"]["labels"] == ["Nemunas_Rusne", "Minija_mouth"] and "labels" not in layers["boundary"]
    assert len(layers["boundary"]["geometry"]["coordinates"]) == 7


def test_missing_files_are_skipped_not_fatal(tmp_path):
    (tmp_path / "stations.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": [
        {"type": "Feature", "properties": {"name": "A"}, "geometry": {"type": "Point", "coordinates": [320000.0, 6150000.0]}}]}))
    load_geometry.cache_clear()
    layers = load_geometry(tmp_path)
    assert [l["name"] for l in layers] == ["stations"] and layers[0]["labels"] == ["A"]
    (tmp_path / "channels.geojson").write_text("{not json")
    load_geometry.cache_clear()
    assert [l["name"] for l in load_geometry(tmp_path)] == ["stations"]
