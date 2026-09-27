# SFINCS viewer: animated map of model runs — design

Date: 2026-09-27
Status: approved in conversation, awaiting written-spec review

## Purpose

Add a **Map** tab to the SFINCS results viewer (`app/`, published at
https://laguna.ku.lt/sfincs/) that shows a completed run as an animated,
interactive WebGL map. The audience is colleagues **checking model behaviour**,
not the public: the map must make defects visible — the kind this project has
already hit (a 4 km gap in the burned strait, a station on the wrong side of
the spit, distributaries burned to a flat constant) — and let a user compare the
model to the gauges in place.

Success: for any of the six published runs, a colleague can play the event hour
by hour, switch between water level and change-from-start, see the maximum,
hover a station to compare model and gauge at that hour, click any cell to get
its full time series, and see the structural inputs (active area, sea boundary,
river inflows, channel centrelines) drawn on top.

## Decisions taken

| question | decision |
|---|---|
| animation, footprint, or both | both: hourly playback plus a "max" frame |
| quantity | a switch: **water level** (m, model datum) and **change from start** |
| extras | station markers with model vs gauge (A), click-a-cell time series (B), structural overlays (C) |
| rendering | frames rendered **on demand on the server** and swapped into a deck.gl `BitmapLayer` |
| cell time series | read from a per-run **cache written offline** |
| out of scope | variant comparison, water depth and velocity, video export, subgrid-resolution extent |

## Facts the design rests on (measured 2026-09-27)

- `sfincs_map.nc` holds `zs(time, n, m)` hourly (`dtout = 3600`) on the
  1100 × 1000, 100 m grid in LKS94 (EPSG:3346); April has 649 frames, Xaver
  313. Also `zb`, `msk`, `zsmax(timemax, n, m)`, `x`, `y`.
- `zs` is chunked one frame per chunk (zlib 2): one frame reads in 0.014 s, but
  one cell's full series takes 4.1 s.
- Colour-mapping one frame and PNG-encoding it takes ~0.08 s and yields ~58 KB.
- **SFINCS already masks dry cells**: in April hour 300, 116 835 of the 331 933
  active cells have no `zs` (fill value), and only 3 021 wet cells are
  shallower than 5 cm. The map uses SFINCS's own wet/dry, not a depth cut.
- `shiny_deckgl` 1.9.2 (in the `shiny` env) provides `bitmap_layer`,
  `geojson_layer`, `scatterplot_layer`, `path_layer`, `MapWidget.patch_layer`,
  map-click input and `timeline_control`/`timeline_server`. `pyproj` 3.7.1,
  Pillow 12.2.0 and rasterio 1.4.3 are also in the env.
- The app reads `runs/` and `results/` from `SFINCS_DATA_DIR`
  (`/home/razinka/sfincs/curonian`) as the `shiny` user; it has no access to
  gauge observations today (those live in `~/curonian/curonian_db.gpkg`,
  read through the `hydromt-sfincs` env).

## Architecture

```
hydromt-sfincs env (offline, after each run)       shiny env (the app)
-------------------------------------------        -------------------------------
curonian/prep/export_map_cache.py --run <name>      app/map_data.py   (no Shiny code)
  reads runs/<run>/sfincs_map.nc                      grid + warp index (shared)
  writes runs/<run>/zs_series.npy   (git-ignored)     frame(), render_png(), cell_series()
         runs/<run>/map_meta.json   (git-ignored)     overlays(), stations_at()
         results/<run>/gauge_obs.csv (committed)    app/app.py  -> new "Map" nav_panel
```

### Offline export — `curonian/prep/export_map_cache.py`

Run as `python -m prep.export_map_cache --run <name>` (event taken from the
run name's prefix, as `validate.py --run` does). Per run it writes:

- **`runs/<run>/zs_series.npy`** — `float16`, shape `(n_active, n_time)`,
  row-major, so one cell's series is one contiguous row (read by `np.load(...,
  mmap_mode="r")`). Rows are the active cells in `np.flatnonzero(msk > 0)`
  order; dry values are stored as NaN. About 430 MB for April, 210 MB for Xaver.
- **`runs/<run>/map_meta.json`** — hour labels (UTC ISO strings), the active
  cell count, the colour ranges (below), and the `sfincs_map.nc` mtime the cache
  was built from, so the app can detect a stale cache and fall back.
- **`results/<run>/gauge_obs.csv`** — `site,time,level_m` for the four scored
  gauges (`validate.GAUGES`) over the run's `data_window`, from
  `prep.make_forcing.load_gauge_levels` — the same values `validate.py` scores.
  Committed next to `validation.md`, so the app never touches the database.

Written world-readable. The README's run sequence gains the export after
`validate.py`, and it is run once for all six existing runs.

### App module — `app/map_data.py`

Pure functions with `functools.lru_cache`; no Shiny imports, so it is testable
alone.

- **Grid and warp.** Reads `x`, `y`, `msk`, `zb` from `sfincs_map.nc`. Builds,
  once, a north-up raster in Web Mercator (EPSG:3857) covering the grid, and for
  each output pixel the index of the nearest model cell (or −1 outside the
  active area), using `pyproj` to invert pixel centres to LKS94 and the grid's
  regular spacing to find the cell. Output resolution ≈ the model's 100 m.
  Returns the lon/lat bounds the `BitmapLayer` needs. All six runs share one
  grid, so the index is cached on the grid's shape and corner coordinates.
- **`frame(run, hour, quantity) -> np.ndarray`** on the model grid:
  - `level`: `zs[hour]`, NaN where SFINCS wrote no value.
  - `change`: `zs[hour] − baseline`, where **baseline** is `zs[0]` for cells wet
    in the first frame and `zb` for cells dry then — so newly flooded land shows
    its depth, not a meaningless difference.
  - `hour = "max"` uses `zsmax` in place of `zs[hour]`.
- **`render_png(values, quantity, vmin, vmax) -> bytes`** — warp, colour, encode
  RGBA PNG; NaN → fully transparent. `level` uses a sequential colormap
  (viridis); `change` a diverging one centred on 0 (RdBu_r). Returned as a
  `data:image/png;base64,…` URI for the layer. Rendered frames are memoised
  process-wide in an LRU of 512 entries (~30 MB) keyed on
  `(run, quantity, hour, map mtime)`.
- **Colour ranges** come from `map_meta.json`: `level` = 2nd–98th percentile of
  wet-cell `zs` over the whole run; `change` = ±(98th percentile of |change|).
  If the meta file is missing, the app computes them (~9 s, once per process).
- **`cell_series(run, lon, lat) -> (row, col, x, y, zb, pd.Series) | None`** —
  maps a click to the model cell; `None` outside the grid or on an inactive
  cell. Reads the row from `zs_series.npy`; if the cache is absent or stale,
  reads `sfincs_map.nc` directly (~4 s) and flags the result as slow.
- **`overlays() -> dict`** — `inputs/active_region.geojson`,
  `boundary_points.geojson`, `dis_points.geojson`, `channels.geojson` (and
  `stations.geojson` positions), reprojected to EPSG:4326.
- **`stations_at(run, hour) -> list[dict]`** — for each of the 9 stations in
  `sfincs_his.nc`: modelled level at the frame time; for the four scored gauges,
  the nearest observed reading within ±6 h from `gauge_obs.csv` with its time and
  the model − gauge error; `None` observation otherwise. Rusnė is flagged
  "modelled only — gauge zero unknown".

### App UI — new "Map" tab in `app/app.py`

- A `MapWidget` (basemap: Carto Positron, as in the TELEMAC viewer) with layers,
  bottom to top: water `bitmap_layer`; `geojson_layer` for the active-area
  outline and channel centrelines; `scatterplot_layer` for boundary points and
  river inflow points; `scatterplot_layer` for stations, coloured by
  model − gauge error (diverging green→red by |error|, grey when no reading
  within ±6 h), with a hover tooltip. Overlay layers toggle individually.
- Controls: quantity switch (level / change from start); `timeline_control`
  over the hourly labels plus a "max" toggle; Play/Pause at 250 ms per step; a
  legend with range and units.
- Frame updates use `patch_layer` to swap only the bitmap's `image`. If a
  render is still in flight when the next step fires, that step is skipped, not
  queued, so a slow link drops frames rather than lagging.
- Clicking the map plots the clicked cell's series below the map (matplotlib,
  like the existing station plot): level through the run, a vertical line at the
  current hour, the cell's ground level dashed, titled with row/col and
  coordinates. A click outside the model, or on a cell dry for the whole run,
  shows a one-line message instead.

## Error handling

| missing | behaviour |
|---|---|
| `sfincs_map.nc` | Map tab shows a message; all other tabs unaffected |
| `map_meta.json` | colour ranges computed on first use (~9 s, once) |
| `zs_series.npy`, or stale vs `sfincs_map.nc` mtime | click falls back to the direct read (~4 s) and says so |
| `gauge_obs.csv` | station markers show modelled levels only |
| overlay GeoJSON | that overlay is omitted with a note; the map still renders |

## Testing (TDD)

- **`app/test_map_data.py`** on a synthetic `sfincs_map.nc` fixture (a 20 × 30
  grid in EPSG:3346 with known cell values and a known wet/dry pattern):
  warp places a known LKS94 point on the right pixel and north is up; `frame`
  for both quantities, including the `zb` baseline for initially dry cells and
  the `max` frame; NaN → transparent; colour ranges and zero-centring;
  `cell_series` from cache and from the slow path agree to float16 precision;
  clicks outside the grid and on inactive cells return `None`.
- **One integration test** on the real April run (skipped if absent): a rendered
  frame decodes as a PNG of the expected size with transparent dry pixels; a cell
  series from the cache matches `sfincs_map.nc` directly.
- **`curonian/tests/test_export_map_cache.py`**: the cache round-trips on the
  synthetic file; `gauge_obs.csv` equals `load_gauge_levels` for each gauge;
  `map_meta.json` ranges equal a direct percentile computation.
- **App smoke test** alongside `app/test_sfincs_data.py`: the Map tab's UI and
  layer specs build for every variant without error.
- **Real use, before calling it done:** run the app locally and drive it with
  Playwright — play, scrub, switch quantity, toggle max, click a cell, hover a
  station — and measure per-frame latency on the April run.

## Deployment

- App code ships through the existing `deploy.sh` (it rsyncs `app/`); no new
  dependencies (`pyproj`, Pillow, rasterio already in the `shiny` env).
- Data: run `prep.export_map_cache` for all six runs (~1.9 GB added under the
  git-ignored `runs/`); commit the six `gauge_obs.csv` files.
- README: add the export step to the run sequence and a short "Map tab"
  paragraph to the viewer notes.
