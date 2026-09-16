"""Channel centrelines burned into the subgrid: Klaipėda strait, Atmata, Skirvytė.

Distributaries come from OSM Overpass (waterway=river); the strait has no OSM
fairway so it is a fixed coordinate list. Fallback coordinates cover an offline
Overpass. Output: inputs/channels.geojson with rivwth [m] and rivbed [m datum].

The fixed strait coordinate list is a poor centreline (see
prep/derive_strait.py's docstring): if the committed output already carries a
"thalweg"-sourced strait (produced by that module), main() preserves it across a
rerun instead of overwriting it with STRAIT_LONLAT, on both the OSM-success and
Overpass-failure paths.
"""
from __future__ import annotations

import sys

import geopandas as gpd
import requests
from pyproj import Transformer
from shapely.geometry import LineString
from shapely.ops import linemerge, transform, unary_union

import common

OVERPASS = "https://overpass-api.de/api/interpreter"
HEADERS = {"User-Agent": "curonian-sfincs/0.1 (SFINCS model prep; https://github.com/razinkele)"}
QUERY = ('[out:json][timeout:60];'
         '(way["waterway"="river"]["name"~"^Atmata$|Skirvyt"](55.20,21.05,55.80,21.50););'
         'out geom;')

CHANNELS = {  # name: (rivwth m, rivbed m in model datum)
    "strait": (400, -12.0),
    "atmata": (200, -4.0),
    "skirvyte": (150, -3.0),
}
STRAIT_LONLAT = [(21.15, 55.62), (21.13, 55.65), (21.12, 55.68), (21.10, 55.71), (21.09, 55.73)]
FALLBACK_LONLAT = {
    "atmata": [(21.37, 55.30), (21.33, 55.31), (21.29, 55.32), (21.25, 55.335)],
    "skirvyte": [(21.37, 55.30), (21.34, 55.285), (21.31, 55.275), (21.28, 55.27)],
}
_T = Transformer.from_crs(4326, common.CRS, always_xy=True)


def to_3346(line_lonlat: LineString) -> LineString:
    return transform(lambda x, y, z=None: _T.transform(x, y), line_lonlat)


def _merge(lines: list[LineString]) -> LineString:
    """Join OSM ways into one centreline, keeping the longest part if they are disjoint.

    Disjoint ways mean the name matched a river that OSM maps in several pieces (a
    side branch, or a gap at a bridge). Keeping only the longest is the right call
    for a centreline to burn in, but it is a real loss of geometry -- report it
    rather than dropping it silently.
    """
    merged = linemerge(unary_union(lines))
    if merged.geom_type == "MultiLineString":
        parts = sorted(merged.geoms, key=lambda g: g.length, reverse=True)
        merged = parts[0]
        dropped = [round(g.length, 6) for g in parts[1:]]
        print(f"_merge: ways are disjoint -- keeping the longest ({merged.length:.6f}) "
              f"and discarding {len(dropped)} segment(s) of length {dropped}")
    return merged


def fetch_osm_rivers(timeout: int = 90) -> dict[str, LineString]:
    r = requests.post(OVERPASS, data={"data": QUERY}, headers=HEADERS, timeout=timeout)
    r.raise_for_status()
    groups: dict[str, list[LineString]] = {"atmata": [], "skirvyte": []}
    for el in r.json().get("elements", []):
        name = el.get("tags", {}).get("name", "")
        key = "atmata" if name == "Atmata" else "skirvyte" if name.startswith("Skirvyt") else None
        if key and el.get("geometry"):
            groups[key].append(LineString([(p["lon"], p["lat"]) for p in el["geometry"]]))
    missing = [k for k, v in groups.items() if not v]
    if missing:
        raise RuntimeError(f"Overpass returned no ways for {missing}")
    return {k: _merge(v) for k, v in groups.items()}


def build_channels(osm: dict[str, LineString] | None) -> gpd.GeoDataFrame:
    geoms = {"strait": to_3346(LineString(STRAIT_LONLAT))}
    for key in ("atmata", "skirvyte"):
        src = osm[key] if osm and key in osm else LineString(FALLBACK_LONLAT[key])
        geoms[key] = to_3346(src)
    rows = [{"name": k, "rivwth": CHANNELS[k][0], "rivbed": CHANNELS[k][1], "geometry": geoms[k]}
            for k in ("strait", "atmata", "skirvyte")]
    gdf = gpd.GeoDataFrame(rows, crs=common.CRS)
    # Real exceptions, not bare asserts: these guard committed input geometry and
    # must still fire under `python -O`, which strips assert statements entirely.
    if len(gdf) != 3 or not gdf.geometry.is_valid.all():
        raise ValueError(f"expected 3 valid channel geometries, got {len(gdf)}: "
                         f"{dict(zip(gdf['name'], gdf.geometry.is_valid))}")
    strait_len = gdf.set_index("name").loc["strait", "geometry"].length
    if not 10_000 < strait_len < 20_000:
        raise ValueError(f"strait centreline is {strait_len:.0f} m, outside the plausible "
                         f"10-20 km range for the Klaipeda strait")
    return gdf


def _existing_thalweg_strait(out):
    """The current file's "strait" row, if prep/derive_strait.py produced it.

    Read before anything else touches `out`, so that re-running this script (e.g.
    once Overpass is reachable again) cannot silently overwrite a strait centreline
    derived from the model's own active-cell mask with the hardcoded STRAIT_LONLAT
    fallback -- the very defect prep/derive_strait.py and its guard test
    (tests/test_make_channels.py) exist to catch. Returns None if there is no
    existing file, it does not parse, or its strait source is not "thalweg".
    """
    if not out.exists():
        return None
    try:
        row = gpd.read_file(out).set_index("name").loc["strait"]
        return row if row["source"] == "thalweg" else None
    except Exception:
        return None


def main(out=common.INPUTS / "channels.geojson", allow_fallback: bool = False) -> gpd.GeoDataFrame:
    prior_strait = _existing_thalweg_strait(out)

    try:
        osm = fetch_osm_rivers()
        source = "osm"
    except (requests.RequestException, RuntimeError) as exc:
        # Deliberately narrow: RequestException covers every network/HTTP/JSON-decode
        # failure and RuntimeError is fetch_osm_rivers' own "no ways returned". A bug
        # in our client code (TypeError, KeyError, ...) must propagate instead of
        # silently downgrading a committed input to fallback coordinates.
        # Check if existing file has OSM data (strait may be "fixed" or, if
        # prep/derive_strait.py produced it, "thalweg" -- either is fine to keep).
        if out.exists():
            try:
                existing = gpd.read_file(out)
                kept = existing["source"].tolist()
                if kept[:1] and kept[0] in ("fixed", "thalweg") and kept[1:] == ["osm", "osm"]:
                    print(f"Overpass failed ({exc}); keeping existing OSM-derived {out}")
                    return existing
            except Exception:
                pass  # Fall through to handle failure

        # No existing OSM file: handle based on allow_fallback flag
        if not allow_fallback:
            msg = f"Overpass failed ({exc}); no fallback without --allow-fallback flag"
            print(msg, file=sys.stderr)
            raise SystemExit(2)

        # Write fallback
        print(f"Overpass failed ({exc}); writing fallback coordinates to {out}")
        osm, source = None, "fallback"

    gdf = build_channels(osm)
    gdf["source"] = ["fixed", source, source]
    if prior_strait is not None:
        is_strait = gdf["name"] == "strait"
        gdf.loc[is_strait, "geometry"] = [prior_strait["geometry"]]
        gdf.loc[is_strait, "rivwth"] = prior_strait["rivwth"]
        gdf.loc[is_strait, "rivbed"] = prior_strait["rivbed"]
        gdf.loc[is_strait, "source"] = "thalweg"
        print(f"keeping mask-derived strait centreline from {out} (source=thalweg)")
    out.parent.mkdir(parents=True, exist_ok=True)
    common.write_geojson(gdf, out)
    print(f"wrote {out}\n{gdf[['name', 'rivwth', 'rivbed', 'source']]}\nlengths m: {gdf.geometry.length.round().tolist()}")
    return gdf


if __name__ == "__main__":
    allow_fallback = "--allow-fallback" in sys.argv
    main(allow_fallback=allow_fallback)
