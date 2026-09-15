# Curonian Lagoon Xaver model — follow-ups and rulings (from the SDD run of 2026-09-04)

Collected from the execution ledger before the workspace was removed. The final whole-branch review triaged the deferred minors: none affect the results; all are cheap in a later sweep.


- Task 0: minor (deferred): common.read_table uses `with sqlite3.connect(...)` which does not close the connection; prefer contextlib.closing.
- Task 0: minor (deferred): sqlite URI path not percent-encoded (fine for current fixed paths).
- Task 1: minor (deferred): make_bathymetry.py report rationale says deep points are excluded by clip, yet min elev is exactly -10.0 → the ≤10 m filter is load-bearing; correct the comment/rationale.
- Task 1: minor (deferred): make_bathymetry.py clamp np.clip(z,0,20) and assert min ≥ -20 left at old bound; tighten to 10 to match the filter.
- Task 1: minor (deferred): shoreline depth-0 anchors only from lagoon exterior; 13 island interiors get no zero anchor (interpolation quality near islands only).
- Task 1: minor (deferred): lagoon_polygon() Polygon return type only indirectly tested; interpolator evaluated over full bbox (2.8M cells) before masking — performance only.
- Task 2: minor (deferred): `except Exception` in main() conflates client bugs with outages.
- Task 2: minor (deferred): bare asserts in build_channels for runtime validation (brief-mandated).
- Task 2: minor (deferred): _merge keeps only the longest segment of disjoint OSM ways without a log line.
- Task 2: minor (deferred): report self-checks in task-2-report.md mis-graded fallback lengths (report only).
- Task 3: minor (deferred): mouth_radius 2600 in active_region duplicates boundary_ring r_out as an independent magic number.
- Task 3: minor (deferred): most functions in make_geometries.py lack docstrings (brief-mandated code).
- Task 3: minor (deferred): committed GeoJSON at full float64 precision; active region 4300 km2 is 200 km2 under the 4500 ceiling (DELTA_BOX dominates).
- Task 5: minor (deferred): dedup and (stations,time) dim-order branches in series_from_files untested (brief-verbatim tests); sort_index not stable.
- Task 5: minor (deferred): CSV float repr noise (17 digits) — round to 3 decimals before writing.
- Task 5: minor (deferred): assert-based validation in prep script (brief-verbatim).
- Task 6: minor (deferred): bias_correct/peak gap use the full Klaipėda series (06:00 and 18:00) without an explicit 06:00 filter; harmless now (no 18:00 readings) but not enforced.
- Task 6: minor (deferred): test_bias_correct builds obs entirely inside the calm window, so window clipping is untested.
- Housekeeping (deferred to final fix wave): curonian/inputs/gtsm_2013_11_12.zip is untracked and not git-ignored — add `curonian/inputs/*.zip` and `curonian/inputs/gtsm_2013_11_12/` to .gitignore.
- Task 7: controller observation — runs/xaver_2013/sfincs.inp shows manning_land = 0.04 (SFINCS default) although setup_subgrid was called with manning_land=0.06; in subgrid mode roughness comes from the tables, so this is presumably inert, but the 0.06 must be verified in sfincs_subgrid.nc (Task 9/10 or the final review) and the inp keyword aligned for clarity.
- Task 7: minor (deferred): hardcoded probe coordinates (318000, 6130000) and 150 m ring tolerance in check_model without named constants (brief-verbatim).
- Housekeeping (deferred to final fix wave): .gitignore does not cover curonian/runs/ as a whole — small SFINCS binaries (sfincs.inp/.msk/.ind/.bnd/.bzs/.src/.dis/.wnd/.obs) are untracked-but-not-ignored; add `curonian/runs/` to .gitignore (keep runs/.gitkeep via `!curonian/runs/.gitkeep`).
- Task 8: minor (deferred): README "a few hundred metres" understates Silute's 1.2 km move.
- Task 8: minor (deferred): relocated coordinates in make_geometries.STATIONS_LONLAT lack a comment explaining the deviation from the spec points.
- Task 9: minor (deferred): south-up regression test varies ground by column only — would not catch a row-flip regression; the else-branch flip has no test.

## Rulings
- Branch: curonian-xaver (from main b2925a1). Ruling: feature branch in place instead of a git worktree — the plan's commands use absolute ~/SFINCS/curonian paths and the run folder holds gigabytes of git-ignored model data; a worktree would break both. Costs if wrong: none beyond needing a manual `git checkout main` to compare.
- Task 0: review approved (reviewer sonnet). Ruling: `.gitignore` `.superpowers/` line flagged as extra was controller-requested — intended, the SDD workspace stays untracked. Costs if wrong: nothing (one ignore line).
- Task 1: implementer DONE_WITH_CONCERNS. Ruling: isobath depth filter tightened from ≤20 m to ≤10 m — five isolated 20 m fragments inside the lagoon polygon are source artifacts (lagoon natural depth < 6 m; the 12–14 m strait channel is burned in by Task 2/7, not interpolated). Costs if wrong: a few deep pockets near the strait entrance would be shallower than reality until the channel burn covers them. Also: brief lacked `import hydromt` (accessor registration) — plan defect fixed in code.
- Task 2: implementer DONE_WITH_CONCERNS — Overpass 406 on both tries, fallback lines used. Controller diagnostic: overpass-api.de returns 406 for the default python-requests User-Agent and 200 (4 ways) with a descriptive User-Agent. Ruling: correctness concern, not an outage → resume implementer to add a User-Agent header and regenerate channels.geojson from OSM before review. Costs if wrong: none (fallback path stays).
- Task 3: dispatched (implementer sonnet, BASE f7814f3) while Task 2 review runs. Ruling: overlap allowed — Task 3 creates new files only and reads Task 2's committed inputs/channels.geojson; any Task 2 fix round runs before Task 4. Costs if wrong: a Task 2 geometry fix could require re-running Task 3's script (seconds).
- Task 2: review (sonnet) — quality approved, 1 Important open: main() silently overwrites OSM-sourced channels.geojson with fallback geometry and exits 0 on any fetch failure. Ruling: finding accepted over the brief's literal main() — the spec allows the fallback only when Overpass is unreachable, and a silent downgrade of a committed input is worse than a loud failure. Fix: keep an existing OSM-sourced file on fetch failure; otherwise write the fallback and exit 2 unless --allow-fallback. Costs if wrong: one extra flag on an offline machine. Trailers verified on both commits.
- Task 4: dispatched (implementer haiku, BASE 70de77f) while Task 3 review and Task 2 re-review run. Ruling: same overlap rule — Task 4 adds data_catalog.yml + one test, reads committed inputs only.
- Task 4: implementer BLOCKED — plan defect: hydromt 0.10 interprets get_rasterdataset(bbox=...) as EPSG:4326 degrees; the test passed metres for EPSG:3346 rasters. Ruling: change tests/test_catalog.py to clip with geom=GeoDataFrame(box(...), crs=3346) for dem_5m and lagoon_bathy_50m, keep the degree bbox for emodnet_2022 (4326). Catalogue YAML unchanged. Costs if wrong: none (test-only change). Catalogue commit f10e9e5 landed before the test passed — accepted; the fix commit must show GREEN.
- Task 6: implementer DONE_WITH_CONCERNS (commit 288edd9). Ruling: (1) Nemunas 351–653 m3/s over the full period vs brief's 350–560 — data fact (post-storm runoff 8–11 Dec), accepted. (2) FINDING block added to main(): GTSM peak (7 Dec 07:00) is 25 h after the first Klaipėda 06:00 maximum (6 Dec); the gauge sits on a 587–588 cm plateau 6–8 Dec at 06:00, so the hourly peak is unresolved by the daily readings — carry to validation, not a blocker. Costs if wrong: boundary peak timing error of up to a day would show up as a Klaipėda RMSE failure in Task 9.
- Task 7: dispatched (implementer sonnet, BASE 966c79c) while Task 6 review and Task 4 re-review run. Ruling: overlap allowed — Task 7 creates build_model.py + its test only and reads committed inputs; the subgrid build is the wall-clock bottleneck. Costs if wrong: a Task 6 forcing fix would force a rebuild (~30 min).
- Task 7: implementer DONE_WITH_CONCERNS (commit 1b5c72c). Ruling: plan defect — hydromt_sfincs 1.2.2 writes the NetCDF subgrid (sfincs_subgrid.nc, `sbgfile = sfincs_subgrid.nc`), not the legacy sfincs.sbg; SFINCS v2.4 reads the NetCDF format. Accepted; test literal updated. Costs if wrong: SFINCS would refuse the subgrid file at run time (Task 8 would show it immediately). Check dict {'n_active': 331933, 'n_bnd': 70, 'connected': True, 'bnd_in_ring': True}; subgrid build 5.5 min.
- Task 8: implementer DONE_WITH_CONCERNS (commit 98b3b0b: README run log + prep/make_geometries.py + inputs/stations.geojson). Full run 25.5 min on 16 threads, mean dt 3.46 s; 3 full runs in total because 4 stations (incl. Nida, Silute) sat on dry cells and were relocated (Silute by ~1.2 km — no closer wet cell). Ruling: relocations accepted (the brief's own remedy); committing the geometry files with the README is the brief's Step 3 clause. Open scientific item: Nida's modelled peak (0.77 m, 5 Dec 22:50) follows the central-lagoon signal rather than the observed 8 Dec rise — carry to Task 9 validation and Task 10 findings; a further relocation is a Task 10 recommendation, not a fix now. Costs if wrong: the Nida success criterion may fail for siting rather than physics reasons.
- Task 9: review (sonnet) — code approved, Important findings: (1) report claim "tie-break inert" false for Uostadvaris (4-point tie, 06:30 vs 06:10); (2) tie-break `min(tied, key=|t - obs.idxmax()|)` depends on the observations and can only shrink |peak_dt_h|; (3) no regression tests for the tie-break or the south-up flood_map branch. Ruling: make the tie-break observation-independent — the median (centre) time of the tied plateau within 1 mm — fix the brief's synthetic test to a single-peak signal (its two-period sine was the plan defect), add regression tests for both deviations, fix the dead else-branch orientation, correct the report prose, regenerate validation.md/PNGs. Costs if wrong: peak_dt_h values may shift by minutes; the printed table is expected unchanged at 1-hour rounding.

## Parked at the end
- Final: parked — validate.criteria C4 divides by the count of >3 m land pixels; NaN → "not met" if a window had no uplands — Ruling: real but unreachable for the delta window; guard in a follow-up. Costs if wrong: a misleading verdict on a different window.
- Final: parked — criteria tests cover one met/one not-met per criterion but not the |dt|>6 h branch of C1 — Ruling: meets the brief; broaden in a follow-up.

---

# Resolution sweep — 2026-09-15

Every item above is dispositioned below. Statuses: **done** (fixed in this sweep),
**already done** (closed by commits 6cb61f3 / f843bd3, after this doc was written),
**moot** (the artefact no longer exists), **n/a** (an observation, not an action).

## Found during the sweep, not in the list above

- **BLOCKER — the checkout was renamed `~/SFINCS` → `~/sfincs` and three paths did not
  follow.** `data_catalog.yml`'s `root: /home/razinka/SFINCS/curonian` made every
  relative catalogue path (`inputs/lagoon_bathy_50m.tif`, `channels.geojson`,
  `active_region.geojson`, `boundary_ring.geojson`) resolve under a directory that does
  not exist, so `build_model.py` could not run at all; `common.SFINCS_BIN` and
  `common.RUN_SFINCS_SH` were dead; the top-level README taught six wrong paths. This is
  what the two failing tests at the start of the sweep were reporting — the handoff's
  "51 tests green" was stale (actual: 49 passed, 2 failed). Fixed by deriving from
  `common.ROOT` (`REPO = ROOT.parent`) and setting the catalogue to `root: .`, which
  resolves against the yml's own directory. `tests/test_common.py::
  test_repo_paths_are_derived_from_this_file_not_hardcoded` guards it; verified RED
  against the old hardcoded constant before fixing. `run_sfincs.sh` was already correct
  (it derives its own path from `BASH_SOURCE`).
- **README claimed `inputs/gtsm_klaipeda.csv` is git-ignored; it is tracked.** The
  reproduction section told a clean checkout to regenerate the "GTSM zip/CSV" and so to
  obtain `~/.cdsapirc`. Only the zip and its extracted directory are ignored — the
  derived CSV is committed. Rewritten, and the ERA5 grid NetCDFs (genuinely ignored, and
  needed for `--wind grid`) added to the list.

## Task 0

- **done** — sqlite URI not percent-encoded → `common._db_uri()`, `urllib.parse.quote`.
  Unescaped `?`/`#` would silently open the wrong file.
- **already done** — `read_table` connection closing via `contextlib.closing`.

## Task 1

- **done** — island interiors got no depth-0 anchor. `isobath_points()` now loops
  `(lagoon.exterior, *lagoon.interiors)`. The lagoon has 13 island holes totalling
  ~55 km², the largest being Rusnė at ~45 km² with 35.7 km of shoreline, in the delta
  the flood metrics score — so this is a real bathymetry correction, not a nicety.
  **Effect measured at 50 m: 520 of 640 408 cells move by >1 cm (0.08 %), 341 by >10 cm,
  mean change +0.0001 m, extremes +1.92 / −1.31 m.** Local, as the geometry implies.
- **done** — interpolator evaluated over the full bbox before masking. The lagoon mask is
  now built first and the interpolators are evaluated only on cells inside it.
  **Proved a no-op**: bit-identical values and NaN pattern against the pre-change output
  at 200 m, checked *before* the island anchors were added so the two changes could not
  mask each other. Runtime for the 50 m grid is now ~13 s (2.78M candidate cells →
  640 408 evaluated).
- **done** — `lagoon_polygon()` return type now tested explicitly; everything downstream
  assumes a single `Polygon` and `.area` (the only previous check) answers for a
  `MultiPolygon` too.
- **already done** — report rationale about the ≤10 m filter being load-bearing.
- **already done** — clamp and assert tightened from 20 m to 10 m.

## Task 2

- **done** — `except Exception` in `main()` narrowed to
  `(requests.RequestException, RuntimeError)`. A `TypeError`/`KeyError` in our own client
  code now propagates instead of silently downgrading a committed input to fallback
  coordinates. `RuntimeError` stays in the tuple: it is `fetch_osm_rivers`' own
  "Overpass returned no ways".
- **done** — bare asserts in `build_channels` → `ValueError` with the measured length in
  the message. `python -O` strips asserts; these guard committed geometry.
- **done** — `_merge` now prints which segments it discarded and how long they were.
- **moot** — `task-2-report.md` self-checks: the SDD workspace was removed, no such file.

## Task 3

- **done** — `mouth_radius` 2600 duplicated `boundary_ring`'s `r_out` → `MOUTH_R_OUT`
  and `MOUTH_R_IN`, read at call time (not bound as default arguments, which would
  defeat the point). A test monkeypatches the constant and asserts both the ring's outer
  edge and the active region's mouth disc follow it.
- **done** — docstrings added to `make_geometries`' functions.
- **done** — committed GeoJSON at full float64 precision → `common.write_geojson()`
  (GDAL `COORDINATE_PRECISION=3`, i.e. millimetres in a projected CRS). Verified
  precision-only: max Hausdorff shift across all six files is 0.68 mm.
- **n/a** — "active region 4300 km² is 200 km² under the 4500 ceiling": an observation
  about headroom, not a defect. Unchanged at 4300 km² after regeneration.

## Task 5

- **done** — `series_from_files` dedup and `(stations, time)` dim-order branches now
  tested; `sort_index(kind="stable")` so the month-file overlap resolves the same way
  every run (verified RED: the second file's value won before the fix).
- **done** — CSV float repr noise → `common.CSV_FLOAT_FMT = "%.3f"` on every forcing
  write. Millimetre water level, mm/s wind, thousandth of a m³/s.
- **done** — assert-based validation in `fetch_gtsm` (gappy series, station distance)
  and `make_forcing` (boundary, wind, discharge, CMEMS) → `ValueError` with diagnostics.

## Task 6

- **done** — `test_bias_correct` window clipping now tested: observations far outside
  the calm window would move the offset by ~5 m if they leaked in.
- **already done** — explicit 06:00 filter on the Klaipėda series.

## Task 7

- **done** — `manning_land` **verified, then aligned**. `sfincs_subgrid.nc`'s `uv_navg`
  spans 0.0200–0.0600, so `setup_subgrid`'s 0.06 did reach the subgrid tables and the
  `manning_land = 0.04` in `sfincs.inp` was genuinely inert. The inp keyword is now
  written to match (`MANNING_LAND`/`MANNING_SEA` in `build_model.py`), with a test
  asserting inp and tables agree.
- **done** — hardcoded probe coordinates and ring tolerance → `OPEN_LAGOON_PROBE` and
  `BND_RING_TOL_M`, plus a test that the probe lies inside the active region (a probe
  outside it would make `check_model`'s `connected` result meaningless).

## Task 8

- **already done** — README states the 0.2–1.2 km station moves.
- **already done** — `STATIONS_LONLAT` carries the relocation comment.

## Task 9

- **done** — south-up regression. The old test varied ground by *column*, so a row flip
  left the area identical and it passed either way; and `flood_map()` returns an area,
  which is orientation-invariant, so the regression is invisible at that level. New
  tests assert orientation on `_flood_arrays` directly (gy descending, row 0 = north)
  for **both** the `dep_subgrid.tif` branch and the `zb` fallback. Proved by sabotage:
  removing each flip fails the new tests while the old one still passes.

## Parked items

- **done** — C4 divided by the count of >3 m land pixels, so a window with no uplands
  gave 0/0 = NaN and `NaN < 1.0` = False, i.e. **"not met"** — a model failure for a
  criterion that measured nothing. Now `c4_verdict()`; ruling: report **"n/a"**, since a
  criterion with no data is neither passed nor failed and `criteria()` already carries a
  non-pass/fail verdict ("info").
- **done** — the `|dt| > 6 h` branch of C1 now has a test (right peak height, 60 h late
  → "not met"), proved by sabotage.

## Verification

Suite went from **52 tests with 2 failing** to **76 tests, all green** (24 added).
A run shows either "76 passed" or "75 passed, 1 skipped" depending on whether
Overpass answers: `test_fetch_osm_rivers_returns_both_distributaries` skips on a
5xx rather than failing the suite for someone else's outage. Every fix
that could be driven RED-first was; the three pure coverage-gap items (row flip, C1
timing, dim-order branch) were proved by sabotaging the production code and watching the
new tests fail while the old ones passed.

All three runs were rebuilt and rerun after the input changes so `results/` still matches
the code that produced it. `prep.make_channels` was deliberately **not** re-run — Overpass
is live data and could return different centrelines, which would be an uncontrolled second
change; `inputs/channels.geojson` was rewritten from the committed file at mm precision
instead, preserving its `['fixed', 'osm', 'osm']` provenance.
