import pytest
from hydromt import DataCatalog
import geopandas as gpd
from shapely.geometry import box

import common


def _geom(minx, miny, maxx, maxy):
    """Create a GeoDataFrame geometry for clipping in the project CRS (EPSG:3346)."""
    return gpd.GeoDataFrame(geometry=[box(minx, miny, maxx, maxy)], crs=common.CRS)


@pytest.mark.integration
def test_catalog_sources_load():
    dc = DataCatalog(data_libs=[str(common.ROOT / "data_catalog.yml")])
    for name in ("dem_5m", "lagoon_bathy_50m", "emodnet_2022", "lagoon_boundary", "channels", "active_region", "boundary_ring"):
        assert name in dc.sources, name
    dem = dc.get_rasterdataset("dem_5m", geom=_geom(330_000, 6_115_000, 332_000, 6_117_000), buffer=0)
    # DEM's WKT is non-canonical LKS-94; to_epsg(min_confidence=20) identifies EPSG:3346
    assert dem.raster.crs.to_epsg(min_confidence=20) == common.CRS and dem.name == "elevtn"
    assert abs(dem.raster.res[0]) == 5.0 and float(dem.max()) < 20
    bathy = dc.get_rasterdataset("lagoon_bathy_50m", geom=_geom(315_000, 6_125_000, 320_000, 6_130_000), buffer=0)
    assert float(bathy.min()) < -1.0
    emod = dc.get_rasterdataset("emodnet_2022", bbox=(20.85, 55.65, 20.95, 55.75), buffer=0)
    assert emod.raster.crs.is_geographic and emod.name == "elevtn" and float(emod.min()) < -10
    ch = dc.get_geodataframe("channels")
    assert set(ch["name"]) == {"strait", "atmata", "skirvyte"}
