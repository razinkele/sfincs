"""Geometries that shape the model: active region, boundary ring, boundary points, stations."""
from __future__ import annotations

import geopandas as gpd
import numpy as np
from shapely.geometry import LineString, Point, Polygon, box
from shapely.ops import unary_union

import common
from prep.make_bathymetry import lagoon_polygon

STATIONS_LONLAT = {
    "Klaipeda": (21.09, 55.715), "Juodkrante": (21.11, 55.55), "Nida": (21.005, 55.303),
    "Vente": (21.19, 55.34), "Uostadvaris": (21.24, 55.33), "Rusne": (21.37, 55.30),
    "Silute": (21.48, 55.35), "Atmata_mouth": (21.23, 55.335), "Zalivino_RU": (21.05, 54.98),
}
DELTA_BOX = (325_000, 6_100_000, 370_000, 6_150_000)   # Šilutė / Rusnė / Russian lowlands


def domain_box() -> Polygon:
    return box(common.X0, common.Y0, common.X0 + common.MMAX * common.DX, common.Y0 + common.NMAX * common.DY)


def mouth_xy() -> tuple[float, float]:
    return common.lonlat_to_xy(*common.KLAIPEDA_MOUTH_LONLAT)


def active_region(lagoon: Polygon, strait_line: LineString, mouth_radius: float = 2600.0) -> Polygon:
    mx, my = mouth_xy()
    parts = [lagoon.buffer(2000.0), box(*DELTA_BOX), strait_line.buffer(1500.0), Point(mx, my).buffer(mouth_radius)]
    reg = unary_union(parts).intersection(domain_box())
    if reg.geom_type == "MultiPolygon":
        reg = max(reg.geoms, key=lambda g: g.area)
    return reg.buffer(0)


def boundary_ring(r_in: float = 2000.0, r_out: float = 2600.0) -> Polygon:
    mx, my = mouth_xy()
    return Point(mx, my).buffer(r_out).difference(Point(mx, my).buffer(r_in))


def boundary_points(n: int = 7, r: float = 2300.0) -> gpd.GeoDataFrame:
    """Points on the seaward arc (bearings 195°..345°, i.e. SSW through W to NNW)."""
    mx, my = mouth_xy()
    bearings = np.linspace(195, 345, n)
    geoms = [Point(mx + r * np.sin(np.radians(b)), my + r * np.cos(np.radians(b))) for b in bearings]
    return gpd.GeoDataFrame({"index": np.arange(1, n + 1)}, geometry=geoms, crs=common.CRS)


def stations() -> gpd.GeoDataFrame:
    rows = [{"name": k, "geometry": Point(*common.lonlat_to_xy(lon, lat))} for k, (lon, lat) in STATIONS_LONLAT.items()]
    return gpd.GeoDataFrame(rows, crs=common.CRS)


def main(inputs=common.INPUTS) -> None:
    lagoon = lagoon_polygon()
    channels = gpd.read_file(inputs / "channels.geojson").set_index("name")
    reg = active_region(lagoon, channels.loc["strait", "geometry"])
    ring = boundary_ring()
    assert domain_box().contains(reg) and domain_box().contains(ring)
    assert reg.intersects(ring), "boundary ring must touch the active region"
    gpd.GeoDataFrame(geometry=[reg], crs=common.CRS).to_file(inputs / "active_region.geojson", driver="GeoJSON")
    gpd.GeoDataFrame(geometry=[ring], crs=common.CRS).to_file(inputs / "boundary_ring.geojson", driver="GeoJSON")
    boundary_points().to_file(inputs / "boundary_points.geojson", driver="GeoJSON")
    stations().to_file(inputs / "stations.geojson", driver="GeoJSON")
    print(f"active region {reg.area/1e6:.0f} km2; wrote 4 GeoJSON files to {inputs}")


if __name__ == "__main__":
    main()
