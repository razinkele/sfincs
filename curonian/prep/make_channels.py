"""Channel centrelines burned into the subgrid: Klaipėda strait, Atmata, Skirvytė.

Distributaries come from OSM Overpass (waterway=river); the strait has no OSM
fairway so it is a fixed coordinate list. Fallback coordinates cover an offline
Overpass. Output: inputs/channels.geojson with rivwth [m] and rivbed [m datum].
"""
from __future__ import annotations

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
    merged = linemerge(unary_union(lines))
    if merged.geom_type == "MultiLineString":
        merged = max(merged.geoms, key=lambda g: g.length)
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
    assert len(gdf) == 3 and gdf.geometry.is_valid.all()
    assert 10_000 < gdf.set_index("name").loc["strait", "geometry"].length < 20_000
    return gdf


def main(out=common.INPUTS / "channels.geojson") -> gpd.GeoDataFrame:
    try:
        osm = fetch_osm_rivers()
        source = "osm"
    except Exception as exc:  # network down or Overpass busy: use fixed coordinates
        print(f"Overpass unavailable ({exc}); using fallback coordinates")
        osm, source = None, "fallback"
    gdf = build_channels(osm)
    gdf["source"] = ["fixed", source, source]
    out.parent.mkdir(parents=True, exist_ok=True)
    gdf.to_file(out, driver="GeoJSON")
    print(f"wrote {out}\n{gdf[['name', 'rivwth', 'rivbed', 'source']]}\nlengths m: {gdf.geometry.length.round().tolist()}")
    return gdf


if __name__ == "__main__":
    main()
