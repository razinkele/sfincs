"""Setup map and Runs skip reason (milestone 3)."""

from sfincs_ui.pages import runs, setup
from sfincs_ui.templates import get_template


def test_setup_ui_has_the_map_slot():
    html = str(setup.setup_ui("setup"))
    assert 'id="setup-map"' in html and "setup-map_message" in html


def test_setup_map_ignores_local_crs_layers():
    """Review Focus 5: metre coordinates never reach deck.gl as degrees."""
    pb = get_template("plane_beach").geometry_layers(None, get_template("plane_beach").defaults())
    assert pb and all("crs" not in l for l in pb)
    assert setup.map_layers(pb) == []
    assert setup.map_message(pb) == "No georeferenced geometry for this template."
    mixed = pb + [{"name": "stations", "crs": "EPSG:4326", "geometry": {"type": "MultiPoint", "coordinates": [[21.1, 55.3]]}, "labels": ["Nida"]}]
    layers = setup.map_layers(mixed)
    assert len(layers) == 1 and setup.map_message(mixed) is None
    assert setup.map_layers([{"name": "domain", "crs": "EPSG:3346", "geometry": {"type": "Polygon", "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 0]]]}}]) == []


def test_map_layers_shapes():
    layers = setup.map_layers([
        {"name": "domain", "crs": "EPSG:4326", "geometry": {"type": "Polygon", "coordinates": [[[21.0, 55.0], [21.5, 55.0], [21.5, 55.5], [21.0, 55.0]]]}},
        {"name": "channels", "crs": "EPSG:4326", "geometry": {"type": "MultiLineString", "coordinates": [[[21.0, 55.0], [21.1, 55.1]]]}, "labels": ["strait"]},
        {"name": "stations", "crs": "EPSG:4326", "geometry": {"type": "MultiPoint", "coordinates": [[21.1, 55.3], [21.2, 55.4]]}, "labels": ["Nida", "Vente"]},
    ])
    # shiny_deckgl 1.9.2 helpers return plain dicts keyed "type" with camelCase deck.gl props.
    assert [(l["id"], l["type"]) for l in layers] == [("domain", "GeoJsonLayer"), ("channels", "GeoJsonLayer"), ("stations", "ScatterplotLayer")]
    stations = layers[2]
    assert stations["data"] == [{"position": [21.1, 55.3], "name": "Nida"}, {"position": [21.2, 55.4], "name": "Vente"}]
    assert stations["pickable"] is True
    # snake_case kwargs would be passed through unconverted and ignored by deck.gl
    assert stations["getPosition"] == "@@=d.position" and stations["getRadius"] == 300 and stations["getFillColor"] == [220, 40, 40, 220]
    assert not any("_" in k for l in layers for k in l)
    assert layers[0]["getFillColor"] == [30, 120, 200, 40] and layers[1]["getLineColor"] == [200, 80, 30, 220]


def test_runs_detail_lists_skipped_stages():
    html = str(runs.skipped_alert({"skipped": {"validate": "run ends before the scoring window"}}))
    assert "Skipped" in html and "validate (run ends before the scoring window)" in html
    assert runs.skipped_alert({}) is None and runs.skipped_alert(None) is None
    assert runs.skipped_alert({"stage": "build", "reason": "x", "log_tail": ""}) is None  # a failure summary, not a skip summary
