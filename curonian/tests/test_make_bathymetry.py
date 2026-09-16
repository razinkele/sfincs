import numpy as np
import pytest
import rasterio
from shapely.geometry import LineString, Polygon
import geopandas as gpd

import common
from prep import make_bathymetry as mb


@pytest.mark.integration
def test_lagoon_polygon_is_the_big_one():
    poly = mb.lagoon_polygon()
    assert 1500e6 < poly.area < 1700e6  # 1601 km2 in the database
    assert poly.is_valid


def test_isobath_points_adds_shoreline_zeros():
    lagoon = Polygon([(0, 0), (1000, 0), (1000, 1000), (0, 1000)])
    iso = gpd.GeoDataFrame(
        {"depth": [2.0, 4.0]},
        geometry=[LineString([(100, 500), (900, 500)]), LineString([(500, 100), (500, 900)])],
        crs=common.CRS,
    )
    xy, depth = mb.isobath_points(iso, lagoon, spacing=100.0)
    assert xy.shape[1] == 2 and len(xy) == len(depth)
    assert (depth == 0.0).sum() >= 40           # 4000 m of shoreline at 100 m spacing
    assert set(np.unique(depth)) == {0.0, 2.0, 4.0}
    assert xy[:, 0].min() >= 0 and xy[:, 0].max() <= 1000


@pytest.mark.integration
def test_make_bathymetry_writes_lagoon_grid(tmp_path):
    out = mb.make_bathymetry(res=200.0, out=tmp_path / "bathy_200m.tif")  # coarse for speed
    with rasterio.open(out) as src:
        assert src.crs.to_epsg() == common.CRS
        assert src.nodata == -9999
        z = src.read(1, masked=True)
        assert z.count() > 30_000                # ~1600 km2 / 0.04 km2
        assert -10.0 <= z.min() and z.max() <= 0.5
        assert -6.5 < np.ma.median(z) < -1.0    # lagoon mean depth ~3.8 m
        centre_x, centre_y = 318_000, 6_130_000   # open lagoon west of Ventė
        row, col = src.index(centre_x, centre_y)
        assert z[row, col] < -1.5


@pytest.mark.integration
def test_lagoon_polygon_returns_a_single_polygon_not_a_multipolygon():
    """Everything downstream (.exterior, .interiors, .buffer) assumes a single Polygon.

    The database layer is a MultiPolygon; lagoon_polygon() picks its largest part.
    Only ever checked indirectly, via .area -- which a MultiPolygon also answers.
    """
    poly = mb.lagoon_polygon()
    assert isinstance(poly, Polygon)
    assert poly.geom_type == "Polygon"
    assert poly.exterior is not None


def test_isobath_points_anchors_island_shorelines_at_zero():
    """Islands need a 0 m depth anchor on their own shoreline, like the outer shore.

    Only the exterior ring was anchored, so water right against an island was
    interpolated from the surrounding isobaths alone and came out too deep. The real
    lagoon has 13 island holes totalling ~55 km2, the largest being Rusne (~45 km2)
    in the delta, so this is not a corner case.
    """
    lagoon = Polygon(
        shell=[(0, 0), (1000, 0), (1000, 1000), (0, 1000)],
        holes=[[(400, 400), (600, 400), (600, 600), (400, 600)]],
    )
    iso = gpd.GeoDataFrame(
        {"depth": [2.0]}, geometry=[LineString([(100, 200), (900, 200)])], crs=common.CRS)

    xy, depth = mb.isobath_points(iso, lagoon, spacing=50.0)
    zeros = xy[depth == 0.0]

    on_island_edge = np.abs(zeros - np.array([500.0, 400.0])).sum(axis=1).min()
    assert on_island_edge < 1.0, "no zero-depth anchor on the island shoreline"
    corner = np.abs(zeros - np.array([600.0, 600.0])).sum(axis=1).min()
    assert corner < 1.0, "island ring not segmentized all the way round"


@pytest.mark.integration
def test_strait_north_of_the_cut_is_nodata_not_a_zero_bar():
    """North of the strait's throat this raster must be nodata, not an interpolated 0 m.

    isobath_points() anchors depth 0 on every lagoon shoreline vertex, including both
    banks (see its comment) -- deliberate everywhere the lagoon is wide, but where the
    polygon narrows into the Klaipeda strait (down to ~600-770 m bank to bank a little
    north of northing 6_174_500, see mb.STRAIT_CLIP_NORTHING) both banks fall inside
    each other's anchor radius, and LinearNDInterpolator, seeing nothing but zeros on
    either side, returns ~0 m across the whole throat. That false 0 m bar (measured
    exactly 0.00 at e.g. x=318150..318550, y=6179500) then outranks dem_5m and
    emodnet_2022 in build_model.DATASETS_DEP -- the one place the lagoon can drain gets
    a datum-level dam. Before the fix this raster carries valid (and exactly-zero) data
    all the way to its bounding box's northern edge (measured up to 6_181_075); after
    it, the polygon used for anchoring is clipped south of the strait and this raster
    has no valid data north of the cut, so the elevation stack falls back to the DEM.
    """
    with rasterio.open(common.INPUTS / "lagoon_bathy_50m.tif") as src:
        arr = src.read(1, masked=True)
        valid_rows = np.where(~arr.mask.all(axis=1))[0]
        max_northing = max(src.xy(r, 0)[1] for r in valid_rows)
    cut = 6_174_500.0  # mb.STRAIT_CLIP_NORTHING
    assert max_northing <= cut + 50.0, (
        f"raster carries valid data up to northing {max_northing:.0f}, "
        f"{max_northing - cut:.0f} m north of the strait cut at {cut:.0f} -- expected "
        "nodata there so the elevation stack falls back to dem_5m/emodnet_2022"
    )
