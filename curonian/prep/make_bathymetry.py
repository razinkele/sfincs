"""Interpolate the in-lagoon isobaths to a 50 m bathymetry grid (elevation, m).

Output covers the lagoon polygon only; everything else is nodata so that the
subgrid merge falls back to the DEM and EMODnet there.
"""
from __future__ import annotations

from pathlib import Path

import geopandas as gpd
import hydromt  # noqa: F401  (registers the `.raster` DataArray accessor)
import numpy as np
import xarray as xr
from scipy.interpolate import LinearNDInterpolator, NearestNDInterpolator
from shapely.geometry import Polygon, box
from shapely.ops import unary_union

import common

NODATA = -9999.0

# North of this northing the lagoon polygon narrows into the Klaipeda strait, measured
# by width bank to bank:
#   6170000-6173500   1330-1754 m   lagoon proper
#   6174000             996 m
#   6174500             771 m       <- clip here
#   6175000-6181000    570-725 m    a narrow channel: the strait
# isobath_points() anchors depth 0 at every shoreline vertex (see its comment below), on
# purpose: without it the interpolator carries an isobath's depth right up to a bank. At
# 600-770 m wide, both banks of the strait fall inside each other's anchor radius, so
# LinearNDInterpolator sees nothing but zeros on either side and returns ~0 m across the
# whole throat -- an exact-zero bar over the dredged strait channel, at the one place the
# lagoon can drain. Clipping the polygon used for anchoring here makes this raster
# nodata north of the cut, so the elevation stack (build_model.DATASETS_DEP) falls back
# to dem_5m / emodnet_2022 in the strait, exactly as this module's docstring intends.
STRAIT_CLIP_NORTHING = 6_174_500.0


def lagoon_polygon() -> Polygon:
    gdf = gpd.read_file(common.DB, layer="lagoon_boundary").to_crs(common.CRS)
    geom = unary_union(gdf.geometry.values)
    parts = list(geom.geoms) if geom.geom_type == "MultiPolygon" else [geom]
    poly = max(parts, key=lambda p: p.area)
    return poly.buffer(0)


def bathymetry_polygon() -> Polygon:
    """lagoon_polygon() clipped south of STRAIT_CLIP_NORTHING (see its comment above).

    A clip local to make_bathymetry, not folded into lagoon_polygon() itself:
    make_geometries.active_region() also calls lagoon_polygon() and needs the lagoon
    unclipped there, with the strait supplied separately from channels.geojson.
    """
    lagoon = lagoon_polygon()
    minx, miny, maxx, _ = lagoon.bounds
    south = lagoon.intersection(box(minx - 1.0, miny - 1.0, maxx + 1.0, STRAIT_CLIP_NORTHING))
    if south.geom_type == "MultiPolygon":
        south = max(south.geoms, key=lambda p: p.area)
    return south


def isobath_points(iso: gpd.GeoDataFrame, lagoon: Polygon, spacing: float = 50.0):
    """Vertices of the isobaths inside the lagoon plus shoreline vertices at depth 0."""
    # Upper bound 10 m (not 20): inside the lagoon polygon the only isobaths deeper
    # than 10 m are 5 isolated fragments (<800 m total) at exactly 20 m with no
    # supporting 15 m contour anywhere nearby -- a source-data artifact, not the real
    # deep channel (that lies outside the lagoon polygon and is clipped away below).
    iso = iso[(iso["depth"] >= 0) & (iso["depth"] <= 10)].to_crs(common.CRS)
    clipped = gpd.clip(iso, lagoon.buffer(100.0))
    xs, ys, ds = [], [], []
    for depth, geom in zip(clipped["depth"], clipped.geometry):
        if geom is None or geom.is_empty:
            continue
        for line in getattr(geom, "geoms", [geom]):
            coords = np.asarray(line.segmentize(spacing).coords)
            xs.append(coords[:, 0]); ys.append(coords[:, 1]); ds.append(np.full(len(coords), float(depth)))
    # Depth-0 anchors on every shoreline the lagoon has -- the outer shore AND each
    # island. Without the interiors the interpolator sees no shallow constraint against
    # an island and carries the surrounding isobath depth right up to its bank, which is
    # wrong wherever an island sits in deeper water. The lagoon has 13 of them (~55 km2),
    # Rusne (~45 km2) being the one that matters, in the delta the flood metrics score.
    for ring in (lagoon.exterior, *lagoon.interiors):
        shore = np.asarray(ring.segmentize(spacing).coords)
        xs.append(shore[:, 0]); ys.append(shore[:, 1]); ds.append(np.zeros(len(shore)))
    xy = np.column_stack([np.concatenate(xs), np.concatenate(ys)])
    depth = np.concatenate(ds)
    xy, idx = np.unique(np.round(xy, 1), axis=0, return_index=True)
    return xy, depth[idx]


def make_bathymetry(res: float = 50.0, out: Path = common.INPUTS / "lagoon_bathy_50m.tif") -> Path:
    lagoon = bathymetry_polygon()
    iso = gpd.read_file(common.ISOBATHS, layer=common.ISOBATH_LAYER)
    xy, depth = isobath_points(iso, lagoon)
    assert len(xy) > 1000, f"too few isobath points: {len(xy)}"

    minx, miny, maxx, maxy = lagoon.buffer(res).bounds
    minx, miny = np.floor(minx / res) * res, np.floor(miny / res) * res
    ncol, nrow = int(np.ceil((maxx - minx) / res)), int(np.ceil((maxy - miny) / res))
    xc = minx + res * (np.arange(ncol) + 0.5)
    yc = miny + nrow * res - res * (np.arange(nrow) + 0.5)      # north to south
    gx, gy = np.meshgrid(xc, yc)

    # Build the lagoon mask BEFORE interpolating and evaluate the interpolators only on
    # the cells that survive it. The result is identical -- outside cells were computed
    # and then thrown away by .where(inside) -- but the full 50 m bbox is ~2.8M cells
    # against ~640k inside the lagoon, so this skips roughly three quarters of the work.
    frame = xr.DataArray(np.full((nrow, ncol), np.nan, dtype="float32"), dims=("y", "x"),
                         coords={"y": yc, "x": xc}, name="elevtn")
    frame.raster.set_crs(common.CRS)
    frame.raster.set_nodata(np.nan)
    inside = frame.raster.geometry_mask(gpd.GeoDataFrame(geometry=[lagoon], crs=common.CRS))
    inside_np = np.asarray(inside)

    lin = LinearNDInterpolator(xy, depth)
    z = np.full(inside_np.shape, np.nan)
    zi = lin(gx[inside_np], gy[inside_np])
    holes = np.isnan(zi)
    if holes.any():
        zi[holes] = NearestNDInterpolator(xy, depth)(gx[inside_np][holes], gy[inside_np][holes])
    z[inside_np] = zi
    # isobath_points() already dropped depths > 10 m (see its comment); clip here to the
    # same 10 m so the interpolator's overshoot at the edge of that filtered set can't
    # push a cell past what the retained isobaths actually support. The tif's minimum
    # elevation is therefore -10.0 m.
    elev = -np.clip(z, 0.0, 10.0)

    da = xr.DataArray(elev.astype("float32"), dims=("y", "x"), coords={"y": yc, "x": xc}, name="elevtn")
    da.raster.set_crs(common.CRS)
    da.raster.set_nodata(np.nan)
    da = da.where(inside)
    assert float(da.count()) > 0.9 * lagoon.area / res**2, "lagoon coverage below 90 %"
    assert float(da.min()) >= -10.0 and float(da.max()) <= 0.0

    out.parent.mkdir(parents=True, exist_ok=True)
    da.raster.to_raster(out, driver="GTiff", nodata=NODATA, compress="lzw")
    print(f"wrote {out}  {ncol}x{nrow} @ {res} m, valid cells {int(da.count())}, "
          f"elev {float(da.min()):.1f}..{float(da.max()):.1f} m")
    return out


if __name__ == "__main__":
    make_bathymetry()
