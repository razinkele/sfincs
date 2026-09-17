"""Geometries that shape the model: active region, boundary ring, boundary points, stations."""
from __future__ import annotations

import geopandas as gpd
import numpy as np
from shapely.geometry import LineString, Point, Polygon, box
from shapely.ops import unary_union

import common
from prep.make_bathymetry import lagoon_polygon

# Spec section 8 takes gauge coordinates "from `station_pts` in curonian_db.gpkg where
# present, otherwise from the place names". station_pts turns out to hold water-quality
# stations (LTK1, LTK2, ...), not hydrological gauges, so every position here came from a
# place name and was then nudged to sit on a wet model cell (see README Run log).
#
# Juodkrante was nudged the WRONG WAY: 1.3 km west put it across the Curonian Spit, in the
# Baltic, where it reported sea level for entire runs. It now uses LHMT's own published
# coordinate for juodkrantes-vms (21.121437, 55.533293; water body "Kursiu marios"),
# retrieved from api.meteo.lt on 2026-09-17, which lands on a wet lagoon cell unaided and
# needs no offset at all. tests/test_make_geometries.py bounds every station against its
# LHMT coordinate so this cannot recur silently.
#
# Uostadvaris moved for the same reason on 2026-09-17, and it matters more: it is a
# SCORED gauge. Its place-name position sat 3583 m from uostadvario-vms, and sampling
# the model field at both showed the difference is worth +0.40 m at the April peak --
# nearly three times A1's entire +/-0.15 m tolerance. It now uses LHMT's coordinate.
STATIONS_LONLAT = {
    "Klaipeda": (21.09, 55.715), "Juodkrante": (21.121437, 55.533293), "Nida": (21.0066, 55.3015),
    "Vente": (21.19, 55.34), "Uostadvaris": (21.290822, 55.344016), "Rusne": (21.3710, 55.2955),
    "Silute": (21.4816, 55.3392), "Atmata_mouth": (21.23, 55.335), "Zalivino_RU": (21.05, 54.98),
}
DELTA_BOX = (325_000, 6_100_000, 370_000, 6_150_000)   # Šilutė / Rusnė / Russian lowlands

# One radius, two users: the seaward disc active_region() adds at the harbour mouth and
# the outer edge of boundary_ring(). They must coincide -- the waterlevel boundary cells
# live in the ring and have to fall inside the active mask. Read at call time (not bound
# as a default argument) so that changing it here really does move both.
MOUTH_R_OUT = 2600.0
MOUTH_R_IN = 2000.0     # inner edge of the ring; the annulus is MOUTH_R_IN..MOUTH_R_OUT


def domain_box() -> Polygon:
    """The full model grid footprint, from the origin and cell counts in common."""
    return box(common.X0, common.Y0, common.X0 + common.MMAX * common.DX, common.Y0 + common.NMAX * common.DY)


def mouth_xy() -> tuple[float, float]:
    """Projected coordinates of the Klaipėda harbour mouth, the model's sea entrance."""
    return common.lonlat_to_xy(*common.KLAIPEDA_MOUTH_LONLAT)


def active_region(lagoon: Polygon, strait_line: LineString, mouth_radius: float | None = None) -> Polygon:
    """Cells SFINCS may wet: the lagoon, the delta box, the strait and the mouth disc.

    Returns the largest connected part, so an isolated sliver cannot become a second
    basin. `mouth_radius` defaults to MOUTH_R_OUT, matching boundary_ring()'s outer edge.
    """
    mx, my = mouth_xy()
    r_mouth = MOUTH_R_OUT if mouth_radius is None else mouth_radius
    parts = [lagoon.buffer(2000.0), box(*DELTA_BOX), strait_line.buffer(1500.0), Point(mx, my).buffer(r_mouth)]
    reg = unary_union(parts).intersection(domain_box())
    if reg.geom_type == "MultiPolygon":
        reg = max(reg.geoms, key=lambda g: g.area)
    return reg.buffer(0)


def boundary_ring(r_in: float | None = None, r_out: float | None = None) -> Polygon:
    """Annulus at the mouth holding the waterlevel boundary cells (msk == 2).

    Its outer edge is MOUTH_R_OUT, the same radius active_region() uses for its mouth
    disc, so every boundary cell falls inside the active mask.
    """
    mx, my = mouth_xy()
    r_in = MOUTH_R_IN if r_in is None else r_in
    r_out = MOUTH_R_OUT if r_out is None else r_out
    return Point(mx, my).buffer(r_out).difference(Point(mx, my).buffer(r_in))


def boundary_points(n: int = 7, r: float = 2300.0) -> gpd.GeoDataFrame:
    """Points on the seaward arc (bearings 195°..345°, i.e. SSW through W to NNW)."""
    mx, my = mouth_xy()
    bearings = np.linspace(195, 345, n)
    geoms = [Point(mx + r * np.sin(np.radians(b)), my + r * np.cos(np.radians(b))) for b in bearings]
    return gpd.GeoDataFrame({"index": np.arange(1, n + 1)}, geometry=geoms, crs=common.CRS)


def stations() -> gpd.GeoDataFrame:
    """The nine observation points SFINCS writes to sfincs_his.nc, in STATIONS_LONLAT order."""
    rows = [{"name": k, "geometry": Point(*common.lonlat_to_xy(lon, lat))} for k, (lon, lat) in STATIONS_LONLAT.items()]
    return gpd.GeoDataFrame(rows, crs=common.CRS)


def main(inputs=common.INPUTS) -> None:
    """Write active_region, boundary_ring, boundary_points and stations to `inputs`."""
    lagoon = lagoon_polygon()
    channels = gpd.read_file(inputs / "channels.geojson").set_index("name")
    reg = active_region(lagoon, channels.loc["strait", "geometry"])
    ring = boundary_ring()
    assert domain_box().contains(reg) and domain_box().contains(ring)
    assert reg.intersects(ring), "boundary ring must touch the active region"
    common.write_geojson(gpd.GeoDataFrame(geometry=[reg], crs=common.CRS), inputs / "active_region.geojson")
    common.write_geojson(gpd.GeoDataFrame(geometry=[ring], crs=common.CRS), inputs / "boundary_ring.geojson")
    common.write_geojson(boundary_points(), inputs / "boundary_points.geojson")
    common.write_geojson(stations(), inputs / "stations.geojson")
    print(f"active region {reg.area/1e6:.0f} km2; wrote 4 GeoJSON files to {inputs}")


if __name__ == "__main__":
    main()
