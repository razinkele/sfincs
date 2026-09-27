# SFINCS viewer: animated map of model runs — design

Date: 2026-09-27
Status: revision 2, after a five-lens review (28 findings confirmed first-hand,
merged to 15; all addressed below). Awaiting written-spec review.

## Purpose

Add a **Map** tab to the SFINCS results viewer (`app/`, published at
https://laguna.ku.lt/sfincs/) that shows a completed run as an animated,
interactive WebGL map. The audience is colleagues **checking model behaviour**,
not the public: the map must make defects visible — the kind this project has
already hit (a 4 km gap in the burned strait, a station on the wrong side of
the spit, distributaries burned to a flat constant) — without inventing any of
its own, and let a user compare the model to the gauges in place.

Success: for any of the six published runs, a colleague can play the event hour
by hour, switch between water level and change from start, see the maximum,
compare model and gauge at the stations, click any cell to get its full time
series, and see the geometry the run was built with drawn on top.

## Decisions taken

| question | decision |
|---|---|
| animation, footprint, or both | both: hourly playback plus a "max" view |
| quantity | a switch: **water level** (m, model datum) and **change from start** |
| extras | station markers vs gauges (A), click-a-cell time series (B), structural overlays (C) |
| rendering | frames rendered **on demand on the server**, swapped into a deck.gl `BitmapLayer` |
| cell time series | read from a per-run **cache written offline** |
| playback | the app's own server-side loop with a **client frame acknowledgement**, not `shiny_deckgl`'s timeline helpers |
| change baseline | **nearest wet-at-start water level, clipped to the cell's bed** (continuous across the starting shoreline) |
| gauge comparison | coloured **only on frames within 30 min of a gauge reading** (validate.py's pairing) |
| out of scope | variant comparison, water depth and velocity, video export, subgrid-resolution extent |

## Facts the design rests on (measured 2026-09-27)

- `sfincs_map.nc` holds `zs(time, n, m)` hourly (`dtout = 3600`) on a 1100 ×
  1000, 100 m grid in LKS94 (EPSG:3346), x 270 050–369 950, y 6 080 050–
  6 189 950, unrotated; April runs have 649 frames, Xaver runs 313. Also `zb`,
  `msk`, `zsmax(timemax, n, m)`, `x`, `y`. All six runs share the grid.
- `zs` is chunked one frame per chunk (zlib 2): one frame reads in 0.014 s; one
  cell's full series takes 4.1 s.
- Colour-mapping and PNG-encoding a 1100 × 1000 frame takes ~0.08 s, ~58 KB
  (~77 KB as a base64 data URI).
- **SFINCS masks dry cells itself**: `zs` is a fill value where a cell is dry
  (April hour 300: 116 835 of 331 933 active cells). The map uses that wet/dry.
- **All runs use subgrid** (`sbgfile = sfincs_subgrid.nc`), and the map's `zb`
  equals the subgrid table's `z_zmin` exactly — the **lowest** point in each
  100 m cell, not a representative ground level. 79 % of April's newly flooded
  cells are only partly wet at peak.
- Wet water levels span −0.35 to 2.27 m across the six runs (`zsmax` maxima
  1.49–2.27 m), so float16 storage resolves every stored value to ≤ 2 mm.
- Gauge readings exist only at 06:00 and 18:00 UTC
  (`prep.make_forcing.load_gauge_levels`); `validate.skill` pairs model and
  gauge within 30 min.
- `validate.py --run` does **not** derive the event from the run name:
  `--event` is separate and defaults to `xaver_2013`.
- Each run directory records the geometry it was built with, in LKS94 text
  files: `sfincs.obs` (9 stations, `x y "name"`), `sfincs.bnd` (7 boundary
  points), `sfincs.src` (2 inflow points). `inputs/*.geojson` is shared and has
  been edited between runs.
- `shiny_deckgl` 1.9.2 (in the `shiny` env): `bitmap_layer(id, image, bounds)`
  passes `bounds` through to deck.gl; `MapWidget.patch_layer` / `partial_update`
  are fire-and-forget (no client reply); the map-level click input is
  `{id}_map_click` with `longitude`/`latitude` (a `BitmapLayer` is not
  pickable, so the layer click never fires on it); the tooltip is one
  widget-wide template, and every non-raster layer is made pickable unless it
  sets `pickable=False`. `timeline_control`/`timeline_server` fix their label
  list and slider length when built. scipy 1.17, pyproj 3.7, Pillow 12.2 and
  rasterio 1.4 are in both envs.
- The app runs under Shiny Server OSS as **one Python process for all
  sessions**, with the default idle timeout, so it exits soon after the last
  session closes.

## Architecture

```
hydromt-sfincs env (offline, after each run)        shiny env (the app)
-------------------------------------------         ------------------------------
curonian/prep/export_map_cache.py --run <name>       app/map_data.py   (no Shiny code)
  reads runs/<run>/sfincs_map.nc, sfincs.obs/bnd/src   load cache, frame(), render_png()
  writes (git-ignored, runs/<run>/):                   cell_series(), stations_at(), overlays()
    zs_series.npy   map_baseline.npy                 app/map_ui.py     (Map tab UI + server)
    map_warp.npz    map_meta.json                    app/www/map_ack.js (frame acknowledgement)
  writes (committed, results/<run>/): gauge_obs.csv  app/app.py        (adds the nav_panel)
```

### Offline export — `curonian/prep/export_map_cache.py`

`python -m prep.export_map_cache --run <name>`. The **event is the longest key
of `common.EVENTS` that prefixes the run name**; no match is an error (no
default). Per run it writes, each to a temporary name in the same directory and
then `os.replace`d into place, so a live reader never sees a half-written or
truncated file:

- **`zs_series.npy`** — `float16`, shape `(n_active, n_time)`, row-major (one
  cell's series is one contiguous row); rows are the active cells in
  `np.flatnonzero(msk > 0)` order (the same C order as `zs[t][msk > 0]`); dry
  values NaN. ~430 MB for an April run, ~210 MB for a Xaver run.
- **`map_baseline.npy`** — `float32` `(n, m)`, the change-from-start baseline
  (below).
- **`map_warp.npz`** — the pixel→cell index for the web-map image and its
  lon/lat bounds (below). Identical across runs today; stored per run so a
  future grid change needs no special case.
- **`map_meta.json`** — hour labels (UTC, ISO 8601), `n_active`, grid shape,
  colour ranges, and the `sfincs_map.nc` size and mtime the files were built
  from.
- **`results/<run>/gauge_obs.csv`** — `site,time,level_m` for the four scored
  gauges (`validate.GAUGES`) over the event's `data_window`, from
  `load_gauge_levels` — the values `validate.py` scores. Committed next to
  `validation.md`, so the app never touches the database.

Colour ranges are computed while streaming the frames, from fixed 1 mm bins
over −2…10 m (values outside clamped to the end bins), so the export never holds
more than one frame plus the histogram: `level` = 2nd–98th percentile of wet
`zs`; `change` = ±(98th percentile of |zs − baseline|).

The README's run sequence gains the export after `validate.py`; it is run once
for all six existing runs (~1.9 GB under the git-ignored `runs/`).

### Change-from-start baseline

`change = zs − baseline`, with one baseline per cell, continuous across the
starting shoreline:

- cells **wet in the first frame**: `baseline = zs[0]`;
- cells **dry in the first frame**: `baseline = max(zs[0] of the nearest
  wet-at-start cell, zb)`, the nearest cell found with
  `scipy.ndimage.distance_transform_edt(..., return_indices=True)` over the
  active grid.

So a low-lying cell that floods shows how far the water rose relative to the
water that reached it, not its depth. The step at the shoreline that a mixed
"level rise / depth" baseline produced (median 0.16 m between neighbours with
equal water level, April hour 400) disappears. A cell whose bed is above the
nearby starting water shows its depth above its bed minimum, since `zb` is the
subgrid minimum. The legend says "change from start (m) — relative to the
starting water level nearby".

### App modules

**`app/map_data.py`** — pure functions, no Shiny imports.

- **Loading** — `load_run(run)` returns the memmapped `zs_series.npy`, the
  baseline, warp and meta, cached on `(path, st_mtime_ns, st_ino, st_size)` of
  each file so a re-export is picked up and a replaced file is reopened rather
  than read through a stale map. A cache is **valid** only if `map_meta.json`
  exists and its recorded `sfincs_map.nc` size and mtime match the file; a
  missing or stale meta makes every derived file (series, baseline, warp,
  ranges) invalid.
- **Warp** — the web-map image is **north-up in EPSG:3857 with square pixels of
  176 m** (≈ 100 m on the ground at the grid's 55.3 °N; Mercator scale ≈ 1.76),
  ~1040 × 1140 px. For each pixel centre the export inverts to LKS94 with pyproj
  and stores the index of the nearest active cell, or −1. `bounds` is the
  image's outer pixel edges converted to lon/lat. Rows are evenly spaced in
  Mercator y, which is how deck.gl reads a `BitmapLayer` in LNGLAT.
- **`frame(run, hour, quantity)`** on the model grid — `level`: `zs[hour]`;
  `change`: `zs[hour] − baseline`; NaN where SFINCS wrote no value.
- **`render_png(values, quantity, vmin, vmax) -> str`** — warp, colour
  (`level`: viridis; `change`: RdBu_r centred on 0), NaN → transparent, RGBA
  PNG, returned as a `data:` URI. Memoised in an LRU of 512 entries (~40 MB of
  base64) keyed on `(run, quantity, hour, vmin, vmax, map mtime)`. The LRU lives
  as long as the process, which in practice is one visit (see Deployment).
- **`cell_series(run, lon, lat)`** → `(row, col, x, y, zb, zsmax, pd.Series)`
  or `None` outside the grid or on an inactive cell; reads its row from the
  cache; if the cache is invalid, reads `sfincs_map.nc` directly (~4 s) and
  flags the result as slow.
- **`stations_at(run, hour)`** — one record per station in the run's
  `sfincs.obs` (positions and names, reprojected to lon/lat), with the modelled
  level from `sfincs_his.nc` at the frame time. For the four scored gauges, if a
  reading in `gauge_obs.csv` lies **within 30 min of the frame time**, the
  record carries the reading, `model − gauge`, and a preformatted tooltip string;
  otherwise it is marked "no reading this hour". Stations without a scored gauge
  (Juodkrantė, Rusnė, Šilutė, Atmata_mouth, Zalivino_RU) are marked "modelled
  only"; Rusnė's tooltip adds "gauge zero unknown".
- **`overlays(run)`** — stations, boundary points and inflow points from the
  run's own `sfincs.obs`, `sfincs.bnd`, `sfincs.src`; the active-area outline and
  channel centrelines from `inputs/active_region.geojson` and
  `inputs/channels.geojson` (the run directory has no copy), labelled in the UI
  as "current inputs". All reprojected to EPSG:4326.

**`app/map_ui.py`** — the Map tab's UI function and server function, so
`app.py` only adds a `nav_panel` and one call. Keeps the playback logic out of
the 330-line `app.py`.

### Map

- `MapWidget` (Carto Positron basemap). Layers, bottom to top: water
  `bitmap_layer`; active-area outline and channel centrelines (`geojson_layer` /
  `path_layer`); boundary and inflow points (`scatterplot_layer`); stations
  (`scatterplot_layer`). **Every overlay sets `pickable=False`** except the
  stations, so the single tooltip template only ever appears over a station.
  Overlays toggle individually.
- **Station marker style**: scored gauge with a reading this hour — filled,
  coloured on a signed diverging scale of `model − gauge` (blue = model low,
  red = model high), clipped at ±0.20 m, bound shown in the legend; scored gauge
  with no reading this hour — filled grey; modelled-only station — hollow ring.
- **Each playback step patches both the water image and the station layer's
  data** (9 points) in one `partial_update`.

### Playback

The app owns playback; `shiny_deckgl`'s `timeline_control`/`timeline_server`
are not used.

- The current hour lives in a server-side `reactive.Value`. Play/Pause toggles
  a `playing` flag; while playing, an effect with `invalidate_later(0.25)`
  advances the hour and sends the frame. The `ui.input_slider` only **displays**
  the position (`update_slider`) and is read only for scrubbing while paused, so
  the loop never waits on Shiny's slider round trip. A text output shows the UTC
  label.
- **Frame acknowledgement**: each update carries a sequence number. A small
  script, `app/www/map_ack.js`, registers a custom message handler; the server
  sends a second message with the same number right after the patch, and the
  handler answers with `Shiny.setInputValue("map_frame_ack", seq)`. Messages are
  handled in order, so the answer means the frame has reached the browser. A
  tick is **skipped** while the last sent number is unacknowledged, so a slow
  link drops frames rather than lagging.
- **At the last frame** playback stops (no looping).
- **Variant switch**: playback stops, the hour resets to 0, the slider's
  maximum and labels are updated, and any acknowledgement or patch for the old
  run is ignored (the sequence number carries the run name).
- **Max view**: a toggle. Turning it on pauses playback and shows `zsmax`
  (level) or `zsmax − baseline` (change) on the run's usual colour range,
  clipped, with "max, clipped to the playback range" in the legend (`zsmax` is
  tracked every model step, so it can exceed every hourly frame). Stations show
  their maximum from `sfincs_his.nc` against the highest gauge reading in the
  event's score window, and the tooltip names both times. Turning max off
  returns to the hour it left.

### Click a cell

The click handler reads `input[<widget>.map_click_input_id]()` (`longitude`,
`latitude`); a click on a station marker also fires it, which is harmless. The
plot below the map (matplotlib, like the existing station plot) shows the
cell's level through the run, a vertical line at the current hour (a horizontal
line at `zsmax` in max view), and the cell's **bed minimum** dashed, labelled
"bed minimum (subgrid)"; title with row/col and coordinates. Outside the model,
or on a cell dry for the whole run, a one-line message instead. A slow
(uncached) read runs as a Shiny `ExtendedTask` so other sessions are not
blocked, with "reading from the map file (~4 s)" shown meanwhile.

## Error handling

| state | behaviour |
|---|---|
| no `sfincs_map.nc` | Map tab shows a message; other tabs unaffected |
| cache invalid (meta missing or stale) | the Map tab says "run the export for this run" and still plays: hour labels from `sfincs_map.nc`, baseline and warp computed on first use (seconds, off the event loop), colour ranges from the first, middle and last frames only, and cell clicks take the slow path |
| no `gauge_obs.csv` | station markers show modelled levels only, all hollow |
| an overlay file missing | that overlay omitted with a note; the map still renders |

## Testing (TDD)

- **`app/test_map_data.py`** on a synthetic `sfincs_map.nc` fixture (a 20 × 30
  EPSG:3346 grid, known values, known wet/dry pattern, with matching
  `sfincs.obs/bnd/src`, a small `sfincs_his.nc` and `gauge_obs.csv`):
  - warp: a known LKS94 point lands on the right pixel; north is up; the image
    shape follows from the 176 m pixel rule;
  - `frame` for both quantities, and the baseline: two adjacent cells with equal
    `zs`, one wet at start and one not, get equal `change`; a cell above the
    starting water gets `zs − zb`;
  - NaN → transparent; ranges from the streamed histogram equal `np.percentile`
    within one bin;
  - `cell_series` from cache and from the slow path agree within 2 mm; clicks
    outside the grid and on inactive cells return `None`;
  - `stations_at`: an error at a frame 20 min from a reading, "no reading" at
    one 2 h away, hollow for modelled-only stations, Rusnė's note, the max view,
    and a missing `gauge_obs.csv`;
  - `overlays` read the run's own files; a missing overlay file is omitted;
  - cache validity: meta missing with the series present → invalid; a replaced
    file is reopened.
- **One integration test** on the real April run, skipped if its files are
  absent: a rendered frame decodes as a PNG of the specified shape with
  transparent dry pixels; a cached cell series matches `sfincs_map.nc` within
  2 mm.
- **`curonian/tests/test_export_map_cache.py`**: round-trip on the synthetic
  file; `april_2013_gridwind_pressure` resolves to `april_2013`, an unknown
  prefix fails; `gauge_obs.csv` equals `load_gauge_levels`; files appear only
  through `os.replace` (no partial file on a simulated failure).
- **App smoke test**: the Map tab's UI and first layer specs build for every
  variant, skipped for a variant whose `sfincs_map.nc` is absent.
- **Playback, driven with Playwright on the real April run** — the acceptance
  test:
  - median step (tick to image acknowledged) ≤ 250 ms over 100 steps, and no
    step over 1 s;
  - with the network throttled to 1 Mbit/s, playback drops frames and the hour
    shown still tracks wall-clock time rather than falling behind;
  - switching April → Xaver mid-playback stops at hour 0 with 313 labels and no
    April frame drawn afterwards;
  - clicking water draws a series; hovering a gauge at 06:00 shows an error,
    at 09:00 shows "no reading this hour".

## Deployment

- App code ships through the existing `deploy.sh` (it rsyncs `app/`, including
  `app/www/`, served by adding `"/www": app/www` to the `static_assets`
  dictionary `App(...)` already passes for `/figures`); no new dependencies.
- Shiny Server's default idle timeout ends the process soon after the last tab
  closes, so the frame LRU is effectively per visit. That is accepted: the
  export persists the warp, baseline and ranges, so a cold start only memmaps
  files. No change to `sfincs.shiny-server.conf`.
- Data: run `prep.export_map_cache` for all six runs; commit the six
  `gauge_obs.csv` files. `.gitignore` already covers `curonian/runs/`.
- README: the export step in the run sequence, and a short "Map tab" paragraph
  in the viewer notes.
