"""Derive a per-segment river-bed profile for the Nemunas distributaries from the 5 m DEM.

`prep/make_channels.py`'s Atmata and Skirvyte features carry one `rivbed` constant
each (-4.0 m, -3.0 m -- "first estimates" per the design spec). `burn_river_rect`
does "deeper of (elevation, rivbed) wins", so where the real channel is deeper than
that constant the burn throttles it back up to the constant, cutting conveyance and
forcing the model to build a steeper lagoon-to-delta slope than observed to pass the
same flood (see .superpowers/sdd/2026-09-16-april-2013-nemunas-flood/
fix-distributary-bed-report.md for the full diagnosis; April's Uostadvaris-Vente
head excess of +0.235 m over observed is measured there).

This module replaces the single constant with a profile sampled every 200 m along
each centreline in `inputs/channels.geojson`:

- atmata, skirvyte: the DEM thalweg -- the minimum of `common.DEM_5M` within
  `THALWEG_RADIUS_M` of each sample point (the deepest nearby pixel, not whatever the
  centreline happens to sit over, since a wobble of a few metres can land on a bank).
  That value is then floored at the channel's existing `rivbed` constant, i.e. the
  derived bed is `min(dem_thalweg, old_constant)` -- deeper of the two wins, exactly
  as `burn_river_rect` itself resolves elevation vs. rivbed. The floor matters because
  the DEM misses the channel at a few points (Skirvyte's thalweg reaches -1.22 m at
  its shallowest); without it a shallow DEM spike would throttle the channel worse
  than the constant did.
- strait: `common.DEM_5M`'s bounds end at y=6,160,704, well south of the strait, so
  there is no survey there. Its rivbed constant (-12.0 m) is emitted unchanged at
  every sample point. It still has to be *sampled and included* in the output,
  though: `burn_river_rect` assigns bed levels to grid cells from whichever `gdf_zb`
  point is nearest along the (per-tile) merged centreline, so a strait with no zb
  points of its own could inherit a distributary's -3/-4 m and lose its dredged
  channel.

Sampling method: shapely's `segmentize(SAMPLE_SPACING_M)`, not `length / spacing` --
it inserts vertices so no segment exceeds the spacing while leaving the line's own
vertices (real bends) alone. This is the same convention
`tests/test_make_channels.py::test_burned_channels_lie_on_active_cells` and
`prep/derive_strait.py` use for "sample a centreline at roughly the grid
resolution", and it is why the committed atmata/skirvyte centrelines yield 98/106
points rather than the ~67/48 a naive arc-length division would give.

Deliberately separate from `prep/make_channels.py` (OSM Overpass) and
`prep/make_bathymetry.py` (the lagoon interpolation): this module only reads the
already-committed `inputs/channels.geojson` and the local 5 m DEM, so it is safe to
run offline, repeatedly, without touching either of those.
"""
from __future__ import annotations

from pathlib import Path

import geopandas as gpd
import numpy as np
import rasterio
from rasterio.mask import mask as rio_mask
from shapely.geometry import Point, mapping

import common
from prep.make_channels import CHANNELS

SAMPLE_SPACING_M = 200.0
THALWEG_RADIUS_M = 50.0

# Only atmata and skirvyte have 5 m survey coverage; see the module docstring for why
# the strait is excluded from DEM sampling but still emitted.
DEM_CHANNELS = ("atmata", "skirvyte")

# Match common.write_geojson's coordinate precision (millimetres in this projected
# CRS): the raw DEM is float32, so leaving rivbed at full precision would make every
# regenerated file a diff of binary noise.
ROUND_M = 3


def sample_points(line, spacing: float = SAMPLE_SPACING_M) -> list[tuple[float, float]]:
    """Points every `spacing` m along `line`, keeping its own vertices (bends) intact."""
    return list(line.segmentize(spacing).coords)


def dem_thalweg(points, dem_path: Path = common.DEM_5M, radius: float = THALWEG_RADIUS_M) -> np.ndarray:
    """Minimum DEM elevation within `radius` m of each point -- the channel bed, not
    whatever the centreline happens to sit over.

    Returns +inf where the DEM has no valid pixel within `radius` (outside its
    extent, or nodata there), so a caller flooring against a known rivbed constant
    falls back to that constant cleanly instead of propagating a NaN into the burn
    (`burn_river_rect` silently drops any non-finite `rivbed` row).
    """
    out = np.full(len(points), np.inf, dtype=float)
    with rasterio.open(dem_path) as src:
        nodata = src.nodata
        for i, (x, y) in enumerate(points):
            circle = Point(x, y).buffer(radius)
            try:
                arr, _ = rio_mask(src, [mapping(circle)], crop=True, nodata=nodata, all_touched=True)
            except ValueError:
                continue  # the circle does not overlap the raster at all
            arr = arr[0]
            valid = arr[np.isfinite(arr) & (arr != nodata)]
            if valid.size:
                out[i] = float(valid.min())
    return out


def channel_bed_points(name: str, line, dem_path: Path = common.DEM_5M) -> list[dict]:
    """One channel's sampled bed-level points.

    atmata/skirvyte: DEM thalweg floored at the channel's existing rivbed constant.
    strait (or any other name not in DEM_CHANNELS): the constant, unchanged, at
    every sample point -- see the module docstring for why it still needs points.
    """
    _, old_rivbed = CHANNELS[name]
    pts = sample_points(line)
    if name in DEM_CHANNELS:
        thalweg = dem_thalweg(pts, dem_path=dem_path)
        rivbed = np.minimum(thalweg, old_rivbed)  # deeper of the two wins
    else:
        rivbed = np.full(len(pts), old_rivbed, dtype=float)
    return [
        {
            "channel": name,
            "chainage_m": round(float(line.project(Point(xy))), 1),
            "rivbed": round(float(zb), ROUND_M),
            "geometry": Point(xy),
        }
        for xy, zb in zip(pts, rivbed)
    ]


def derive_channel_bed(channels_path: Path = common.INPUTS / "channels.geojson",
                        dem_path: Path = common.DEM_5M) -> gpd.GeoDataFrame:
    """Sampled bed-level points for every channel in `channels_path` (strait included)."""
    gdf = gpd.read_file(channels_path).set_index("name")
    rows: list[dict] = []
    for name in ("strait", "atmata", "skirvyte"):
        rows += channel_bed_points(name, gdf.loc[name, "geometry"], dem_path=dem_path)
    out = gpd.GeoDataFrame(rows, columns=["channel", "chainage_m", "rivbed", "geometry"], crs=gdf.crs)
    assert np.isfinite(out["rivbed"]).all(), \
        "non-finite rivbed would be silently dropped by burn_river_rect's gdf_zb filter"
    return out


def write_channel_bed(out: Path = common.INPUTS / "channel_bed.geojson",
                       channels_path: Path = common.INPUTS / "channels.geojson",
                       dem_path: Path = common.DEM_5M) -> gpd.GeoDataFrame:
    gdf = derive_channel_bed(channels_path, dem_path)
    common.write_geojson(gdf, out)
    counts = gdf["channel"].value_counts().to_dict()
    by_channel = gdf.groupby("channel")["rivbed"]
    print(f"wrote {out}: counts {counts}")
    for name, s in by_channel:
        print(f"  {name}: n={len(s)} rivbed {s.min():.2f}..{s.max():.2f} m, median {s.median():.2f} m")
    return gdf


if __name__ == "__main__":
    write_channel_bed()
