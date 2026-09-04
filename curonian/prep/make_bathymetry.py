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
from shapely.geometry import Polygon
from shapely.ops import unary_union

import common

NODATA = -9999.0


def lagoon_polygon() -> Polygon:
    gdf = gpd.read_file(common.DB, layer="lagoon_boundary").to_crs(common.CRS)
    geom = unary_union(gdf.geometry.values)
    parts = list(geom.geoms) if geom.geom_type == "MultiPolygon" else [geom]
    poly = max(parts, key=lambda p: p.area)
    return poly.buffer(0)


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
    shore = np.asarray(lagoon.exterior.segmentize(spacing).coords)
    xs.append(shore[:, 0]); ys.append(shore[:, 1]); ds.append(np.zeros(len(shore)))
    xy = np.column_stack([np.concatenate(xs), np.concatenate(ys)])
    depth = np.concatenate(ds)
    xy, idx = np.unique(np.round(xy, 1), axis=0, return_index=True)
    return xy, depth[idx]


def make_bathymetry(res: float = 50.0, out: Path = common.INPUTS / "lagoon_bathy_50m.tif") -> Path:
    lagoon = lagoon_polygon()
    iso = gpd.read_file(common.ISOBATHS, layer=common.ISOBATH_LAYER)
    xy, depth = isobath_points(iso, lagoon)
    assert len(xy) > 1000, f"too few isobath points: {len(xy)}"

    minx, miny, maxx, maxy = lagoon.buffer(res).bounds
    minx, miny = np.floor(minx / res) * res, np.floor(miny / res) * res
    ncol, nrow = int(np.ceil((maxx - minx) / res)), int(np.ceil((maxy - miny) / res))
    xc = minx + res * (np.arange(ncol) + 0.5)
    yc = miny + nrow * res - res * (np.arange(nrow) + 0.5)      # north to south
    gx, gy = np.meshgrid(xc, yc)

    lin = LinearNDInterpolator(xy, depth)
    z = lin(gx, gy)
    holes = np.isnan(z)
    if holes.any():
        z[holes] = NearestNDInterpolator(xy, depth)(gx[holes], gy[holes])
    # isobath_points() already dropped depths > 10 m (see its comment); clip here to the
    # same 10 m so the interpolator's overshoot at the edge of that filtered set can't
    # push a cell past what the retained isobaths actually support. The tif's minimum
    # elevation is therefore -10.0 m.
    elev = -np.clip(z, 0.0, 10.0)

    da = xr.DataArray(elev.astype("float32"), dims=("y", "x"), coords={"y": yc, "x": xc}, name="elevtn")
    da.raster.set_crs(common.CRS)
    da.raster.set_nodata(np.nan)
    inside = da.raster.geometry_mask(gpd.GeoDataFrame(geometry=[lagoon], crs=common.CRS))
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
