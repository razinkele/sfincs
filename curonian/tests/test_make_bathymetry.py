import numpy as np
import pytest
import rasterio
from shapely.geometry import LineString, Polygon
import geopandas as gpd

import common
from prep import make_bathymetry as mb


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
