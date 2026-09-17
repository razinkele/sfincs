import geopandas as gpd
import numpy as np
import pytest
import rasterio
from shapely.geometry import LineString, Point

import common
from prep import derive_channel_bed as dcb
from prep.make_channels import CHANNELS


def _write_synthetic_dem(path, transform, values):
    with rasterio.open(path, "w", driver="GTiff", height=values.shape[0], width=values.shape[1],
                        count=1, dtype="float32", crs="EPSG:3346", transform=transform, nodata=-9999.0) as dst:
        dst.write(values, 1)


def test_sample_points_matches_segmentize_and_keeps_vertices():
    """Sampling is shapely segmentize(200), not length/200 -- it preserves the line's
    own vertices (real bends) and only adds points where a segment exceeds 200 m. This
    is what makes the committed atmata/skirvyte centrelines yield 98/106 points, not
    the ~67/48 a naive arc-length division would give."""
    line = LineString([(0, 0), (150, 0), (150, 500)])   # one short leg, one long leg
    pts = dcb.sample_points(line, spacing=200.0)
    assert (150.0, 0.0) in [tuple(round(c, 6) for c in p) for p in pts], "original vertex was dropped"
    assert pts[0] == (0.0, 0.0) and pts[-1] == (150.0, 500.0)


def test_dem_thalweg_takes_the_minimum_within_radius(tmp_path):
    """The thalweg is the deepest pixel nearby, not the value under the point itself --
    guards against sampling a bank when the centreline wobbles a few metres off the
    true deep line."""
    dem_path = tmp_path / "dem.tif"
    transform = rasterio.Affine(5.0, 0.0, 0.0, 0.0, -5.0, 100.0)  # north-up, origin (0,100)
    values = np.full((20, 20), -1.0, dtype="float32")   # shallow bank everywhere
    values[10, 10] = -7.0                                # a deep pixel near (50, 50)
    _write_synthetic_dem(dem_path, transform, values)

    thalweg = dcb.dem_thalweg([(52.0, 48.0)], dem_path=dem_path, radius=50.0)
    assert thalweg[0] == pytest.approx(-7.0)


def test_dem_thalweg_is_inf_where_dem_has_no_data(tmp_path):
    dem_path = tmp_path / "dem.tif"
    transform = rasterio.Affine(5.0, 0.0, 0.0, 0.0, -5.0, 100.0)
    values = np.full((20, 20), -9999.0, dtype="float32")   # all nodata
    _write_synthetic_dem(dem_path, transform, values)

    thalweg = dcb.dem_thalweg([(50.0, 50.0)], dem_path=dem_path, radius=50.0)
    assert not np.isfinite(thalweg[0])


def test_channel_bed_points_floors_a_shallow_dem_spike_at_the_old_constant(tmp_path):
    """Sabotage: plant a DEM spike shallower than skirvyte's -3.0 m constant (like the
    real -1.22 m spot the spec warns about) and confirm the derived bed does not follow
    it down -- it is floored at the old constant instead. Without the floor this
    assertion fails (the derived value would equal the spike)."""
    dem_path = tmp_path / "dem.tif"
    transform = rasterio.Affine(5.0, 0.0, 0.0, 0.0, -5.0, 1000.0)
    values = np.full((200, 200), -6.0, dtype="float32")   # deep background everywhere but...
    values[30:51, 30:51] = -1.0   # ...a whole shallow neighbourhood around (200, 800):
    # dem_thalweg takes the *minimum* within radius, so a single shallow pixel next to
    # deep water would never surface -- it takes the whole 50 m neighbourhood reading
    # shallow to reproduce "the DEM misses the channel here", like the real Skirvyte
    # spot the spec measured at -1.22 m.
    _write_synthetic_dem(dem_path, transform, values)

    line = LineString([(0, 800), (200, 800), (400, 800)])
    rows = dcb.channel_bed_points("skirvyte", line, dem_path=dem_path)
    rivbed = {round(r["geometry"].x): r["rivbed"] for r in rows}
    assert rivbed[200] == CHANNELS["skirvyte"][1] == -3.0, "shallow DEM spike leaked through the floor"
    assert rivbed[0] < -3.0, "the deep DEM value elsewhere should not also be floored away"


def test_channel_bed_points_keeps_a_deep_dem_value_below_the_constant(tmp_path):
    """The flip side of the floor test: where the DEM is genuinely deeper than the old
    constant, that deeper value must be used, not silently discarded."""
    dem_path = tmp_path / "dem.tif"
    transform = rasterio.Affine(5.0, 0.0, 0.0, 0.0, -5.0, 1000.0)
    values = np.full((200, 200), -8.0, dtype="float32")
    _write_synthetic_dem(dem_path, transform, values)

    line = LineString([(0, 800), (200, 800)])
    rows = dcb.channel_bed_points("atmata", line, dem_path=dem_path)
    assert all(r["rivbed"] < CHANNELS["atmata"][1] for r in rows)


def test_channel_bed_points_strait_ignores_the_dem_even_when_it_is_deeper(tmp_path):
    """Sabotage: put a -20 m pit directly under the strait's line. The strait must
    still come out at exactly its design -12.0 m everywhere -- it has no survey there
    (common.DEM_5M's bounds end well south of it) and must not pick up spurious depth
    from whatever happens to be in `dem_path`."""
    dem_path = tmp_path / "dem.tif"
    transform = rasterio.Affine(5.0, 0.0, 0.0, 0.0, -5.0, 1000.0)
    values = np.full((200, 200), -20.0, dtype="float32")   # a deep pit under the whole line
    _write_synthetic_dem(dem_path, transform, values)

    line = LineString([(0, 800), (200, 800), (400, 800)])
    rows = dcb.channel_bed_points("strait", line, dem_path=dem_path)
    assert rows, "no points produced"
    assert all(r["rivbed"] == CHANNELS["strait"][1] == -12.0 for r in rows)


def test_derive_channel_bed_all_rivbed_values_are_finite(tmp_path):
    """burn_river_rect silently drops any gdf_zb row whose rivbed is non-finite
    (`gdf_zb[np.isfinite(gdf_zb[name])]`), so a DEM miss must be floored to a real
    number before it ever reaches the output file, not passed through as inf/NaN."""
    dem_path = tmp_path / "dem.tif"
    transform = rasterio.Affine(5.0, 0.0, 0.0, 0.0, -5.0, 100.0)
    values = np.full((20, 20), -9999.0, dtype="float32")   # DEM entirely missing
    _write_synthetic_dem(dem_path, transform, values)

    gdf = gpd.GeoDataFrame(
        {"name": ["strait", "atmata", "skirvyte"],
         "rivwth": [400, 200, 150],
         "rivbed": [-12.0, -4.0, -3.0]},
        geometry=[LineString([(0, 0), (300, 0)]), LineString([(0, 50), (300, 50)]),
                  LineString([(0, 90), (300, 90)])],
        crs=common.CRS,
    )
    channels_path = tmp_path / "channels.geojson"
    common.write_geojson(gdf, channels_path)

    out = dcb.derive_channel_bed(channels_path=channels_path, dem_path=dem_path)
    assert np.isfinite(out["rivbed"]).all()
    # With no DEM data at all, atmata/skirvyte must fall all the way back to their
    # old constants -- exactly the floor's fallback behaviour.
    by_channel = out.set_index("channel")["rivbed"]
    assert set(by_channel.loc["atmata"].unique()) == {-4.0}
    assert set(by_channel.loc["skirvyte"].unique()) == {-3.0}
    assert set(by_channel.loc["strait"].unique()) == {-12.0}


def test_derive_channel_bed_points_lie_on_their_own_centreline(tmp_path):
    """Every emitted point must sit on the centreline it was sampled from -- not on
    some other channel's line, and not off the line entirely."""
    dem_path = tmp_path / "dem.tif"
    transform = rasterio.Affine(5.0, 0.0, 0.0, 0.0, -5.0, 100.0)
    values = np.full((20, 20), -6.0, dtype="float32")
    _write_synthetic_dem(dem_path, transform, values)

    gdf = gpd.GeoDataFrame(
        {"name": ["strait", "atmata", "skirvyte"],
         "rivwth": [400, 200, 150],
         "rivbed": [-12.0, -4.0, -3.0]},
        geometry=[LineString([(0, 0), (300, 20)]), LineString([(0, 50), (300, 90)]),
                  LineString([(0, 90), (300, 10)])],
        crs=common.CRS,
    )
    channels_path = tmp_path / "channels.geojson"
    common.write_geojson(gdf, channels_path)

    out = dcb.derive_channel_bed(channels_path=channels_path, dem_path=dem_path)
    lines = gpd.read_file(channels_path).set_index("name")["geometry"]
    for _, row in out.iterrows():
        # write_geojson rounds coordinates to millimetres (common.GEOJSON_PRECISION);
        # allow a matching tolerance rather than requiring exact containment.
        assert lines[row["channel"]].distance(row["geometry"]) < 0.01, \
            f"{row['channel']} point {row['geometry']} is off its own centreline"


@pytest.mark.integration
def test_derive_channel_bed_reproduces_the_measured_profile():
    """End-to-end against the real committed channels.geojson and the real 5 m DEM.

    Reference numbers (see the fix-distributary-bed report): atmata 98 points,
    thalweg roughly -6.5..-2.8 m; skirvyte 106 points, roughly -9.0..-1.2 m; both
    with a majority of points deeper than their old constant. Checked as ranges/counts,
    not exact floats -- the DEM sampling window is an implementation detail.
    """
    if not common.DEM_5M.exists():
        pytest.skip("real 5 m DEM not available on this machine")
    gdf = dcb.derive_channel_bed()
    by_channel = gdf.set_index("channel")

    atmata = by_channel.loc["atmata"]
    skirvyte = by_channel.loc["skirvyte"]
    strait = by_channel.loc["strait"]

    assert len(atmata) == 98
    assert len(skirvyte) == 106

    assert -7.0 < atmata["rivbed"].min() < -6.0
    assert -4.5 < atmata["rivbed"].max() <= -4.0          # floored at the -4.0 constant
    assert (atmata["rivbed"] < -4.0).sum() > 0.5 * len(atmata)

    assert -9.5 < skirvyte["rivbed"].min() < -8.5
    assert -3.5 < skirvyte["rivbed"].max() <= -3.0        # floored at the -3.0 constant
    assert (skirvyte["rivbed"] < -3.0).sum() > 0.5 * len(skirvyte)

    assert (strait["rivbed"] == -12.0).all()

    # Both distributaries must never read shallower than their old per-channel
    # constant -- the invariant the floor exists to guarantee.
    assert (atmata["rivbed"] <= -4.0).all()
    assert (skirvyte["rivbed"] <= -3.0).all()

    # A real distributary's bed varies along its length (pools and bars), not a flat
    # line at the old constant -- this is the whole point of sampling the DEM instead
    # of keeping one number per channel.
    assert atmata["rivbed"].std() > 0.3
    assert skirvyte["rivbed"].std() > 0.3
