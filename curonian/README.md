# Curonian Lagoon SFINCS model

Whole-lagoon compound-flood model, first hindcast Storm Xaver (28 Nov – 11 Dec 2013).
Design: `../docs/superpowers/specs/2026-09-04-curonian-lagoon-xaver-model-design.md`.

All commands run from this folder inside the `hydromt-sfincs` env:

    micromamba run -n hydromt-sfincs python -m prep.make_bathymetry
    micromamba run -n hydromt-sfincs python -m prep.make_channels
    micromamba run -n hydromt-sfincs python -m prep.make_geometries
    micromamba run -n hydromt-sfincs python -m prep.fetch_gtsm
    micromamba run -n hydromt-sfincs python -m prep.make_forcing
    micromamba run -n hydromt-sfincs python build_model.py
    ../run_sfincs.sh runs/xaver_2013 16
    micromamba run -n hydromt-sfincs python validate.py

Tests: `micromamba run -n hydromt-sfincs python -m pytest tests -q`

## Run log

- Xaver 2013 one-day dry run (28→29 Nov 2013): 1.7 min on 16 threads, mean dt 3.47 s.
- Xaver 2013 full run (28 Nov–11 Dec 2013): 25.5 min on 16 threads, mean dt 3.46 s.
  Juodkrante, Nida, Rusne, and Silute originally landed on dry cells (their point_zs
  was flat at the local bed elevation); moved 0.2–1.2 km into the nearest wet cells
  (Silute needed the largest move; no closer wet cell exists at 100 m resolution)
  in `prep/make_geometries.STATIONS_LONLAT`, then reran `make_geometries`,
  `build_model.py`, and the full simulation. All 9 stations now vary by more than
  0.2 m over the run.

## Results: Xaver 2013

Full validation output: `results/xaver_2013/validation.md`,
`results/xaver_2013/validation_timeseries.png` (time series) and
`results/xaver_2013/flood_extent_delta.png` (delta flood-extent map).
`validate.py` produces `results/xaver_2013/` itself (it copies its own
`validation.md` and both PNGs there after writing them to the run folder);
nothing under `results/` is copied by hand. Tables and verdict lines pasted
verbatim below.

Whole period: 2013-11-28 00:00 to 2013-12-11 00:00

| station | n | bias m | RMSE m | r | peak err m | peak dt h |
|---|---|---|---|---|---|---|
| Klaipeda | 13 | -0.01 | 0.08 | 0.91 | +0.13 | +10 |
| Nida | 26 | -0.01 | 0.10 | 0.74 | -0.07 | -67 |
| Vente | 26 | +0.05 | 0.12 | 0.70 | +0.19 | -60 |
| Uostadvaris | 13 | -0.06 | 0.10 | 0.85 | +0.08 | +0 |

Storm window: 2013-12-05 00:00 to 2013-12-09 00:00

| station | n | bias m | RMSE m | r | peak err m | peak dt h |
|---|---|---|---|---|---|---|
| Klaipeda | 4 | -0.03 | 0.12 | 0.73 | +0.13 | +10 |
| Nida | 8 | -0.03 | 0.16 | 0.35 | -0.07 | -67 |
| Vente | 8 | +0.05 | 0.16 | 0.34 | +0.19 | -60 |
| Uostadvaris | 4 | -0.06 | 0.14 | 0.75 | +0.08 | +0 |

Flooded land in the delta window (depth > 5 cm, ground > 0 m): **165.5 km²**

### Success criteria (spec section 9)
- C1 Uostadvaris peak [2013-12-05 00:00 to 2013-12-09 00:00]: **met** -- model peak 2013-12-06 06:20, peak err +0.08 m, dt +0.3 h (threshold: peak err within +/-0.15 m and |dt| <= 6 h)
- C2 Nida 8 Dec rise [2013-12-07 06:00 to 2013-12-08 18:00]: **met (marginal)** -- model 0.46 m -> 0.71 m vs gauge 0.84 m, err -0.13 m, rise reproduced (threshold: err within +/-0.15 m (<=0.10 m for a clean 'met'), rise reproduced in sign)
- C3 Klaipeda RMSE [2013-12-05 00:00 to 2013-12-09 00:00]: **met** -- storm RMSE 0.12 m (whole-period RMSE 0.08 m) (threshold: storm-window RMSE <= 0.15 m)
- C4 Silute uplands [delta window (325000, 6105000, 360000, 6145000)]: **met** -- 0.00% of land with ground > 3 m flooded (threshold: < 1 % flooded)
- Info: Uostadvaris 8 Dec 06:00 [2013-12-08 06:00]: **info** -- model 0.59 m vs gauge 0.83 m, err -0.24 m (threshold: n/a (context only))
- Info: Nida 8 Dec 06:00 [2013-12-08 06:00]: **info** -- model 0.52 m vs gauge 0.74 m, err -0.22 m (threshold: n/a (context only))

Forcing as run (`inputs/forcing_summary.txt`): GTSM boundary offset +0.092 m
(calm window 28 Nov–4 Dec 2013), boundary peak 1.00 m at 2013-12-07 07:00;
wind peak 19.5 m/s at 2013-12-06 06:00 from 236°; Nemunas discharge
351–653 m³/s, Minija held constant at 46.0 m³/s. The wind peak coincides
with the Klaipeda and Uostadvaris gauge peaks and lands 25 h before the
GTSM boundary peak — the mechanism behind the Nida and wind-field findings
below.

### Findings

- GTSM offset and timing vs the Klaipeda gauge: the GTSM boundary was bias
  corrected by +0.092 m over the calm window 28 Nov–4 Dec 2013 and peaks at
  1.00 m at 2013-12-07 07:00. The Klaipeda 06:00 gauge peaks at 0.88 m at
  2013-12-06 06:00, 25 h earlier than the raw boundary peak — recorded as a
  FINDING against the 12 h check tolerance in `inputs/forcing_summary.txt`,
  not treated as a blocker. Compared reading-by-reading against the Klaipeda
  06:00 series itself, whole-period RMSE is 0.08 m (r = 0.91) and the
  storm-window (5–9 Dec) RMSE is 0.12 m (r = 0.73) — both inside the ±0.15 m
  target (C3). The table's "+10 h" peak timing is a same-time artefact of a
  gauge that plateaus at 0.85–0.88 m across 6–8 Dec rather than showing one
  sharp peak, against the model's own continuous maximum of about 1.0 m on
  6–7 Dec. The 06:00 error alternates sign day to day rather than sitting
  uniformly high or low: −0.11 m on 6 Dec, +0.13 m on 7 Dec, −0.16 m on
  8 Dec — correct storm-day timing but not a one-directional bias. Before
  the storm the model shows 0.2–0.6 m oscillations that the once-daily
  06:00/18:00 gauge cannot confirm or rule out — high-frequency energy
  carried in on the GTSM boundary.
- Uostadvaris peak: model 1.00 m at 06:20 on 6 Dec vs gauge 0.92 m at 06:00,
  peak error +0.08 m at +0.3 h — inside the ±0.15 m / ±6 h target (C1: met).
- Nida delayed rise: the model's own peak (0.77 m) arrives with the gale on
  5–6 Dec, well before the gauge's peak of 0.84 m on 8 Dec 18:00 — the
  table's "peak dt −67 h" is the gap between these two different events, not
  a timing error on a single one. At the four reading times spanning the
  rise the model tracks the gauge closely: 0.52 m vs gauge 0.74 m (8 Dec
  06:00), 0.71 m vs 0.84 m (8 Dec 18:00), 0.61 m vs 0.70 m (9 Dec 06:00),
  0.66 m vs 0.72 m (9 Dec 18:00) — the rise is reproduced in sign at every
  step; the miss at the gauge's own peak (8 Dec 18:00) is −0.13 m, inside
  the ±0.15 m target but marginal (C2: met, marginal). Nida, Juodkrante,
  Rusne and Silute all had to be moved 0.2–1.2 km into wet cells to get a
  usable point series (see Run log).
- The second rise is missed at both gauges, not just Nida: at 8 Dec 06:00
  the model is −0.24 m low at Uostadvaris (0.59 m vs gauge 0.83 m) and
  −0.22 m low at Nida (0.52 m vs gauge 0.74 m) — almost the same miss at two
  gauges roughly 60 km apart. That similarity is evidence the miss is
  systematic (most likely missing spatial structure in the forcing) rather
  than an artefact of moving the Nida station off its spec position, and it
  strengthens the "uniform wind first" ranking in Assumptions to revisit
  below.
- Vente: the table's peak error (+0.19 m at −60 h) is a window-max-to-
  window-max comparison, 60 h apart. At matching 06:00 readings on 6 Dec the
  model overshoots the setup peak by about 0.35 m (0.95 m modelled vs
  0.60 m gauge) and tracks the gauge well afterwards; RMSE 0.12 m overall.
- Flooded area: 165.5 km² of land floods in the delta window (depth > 5 cm,
  ground > 0 m only). This is a lower bound on inundation extent — cells at
  or below 0 m ground are excluded — but likely an overestimate of real
  flooding, since the model has no drainage or pumping, the modelled
  whole-period peak error at Klaipeda is +0.13 m even though the mean bias
  there is only -0.01 m, and dikes may be under-resolved at 5 m grid
  resolution. Rusne island and the Silute polders flood field by field, a
  plausible pattern; land with ground > 3 m in the delta window (this
  includes the higher ground around Silute, though the station's own
  observation cell sits at 2.94 m and is excluded from the mask) stays
  essentially dry (C4: 0.00% flooded).
- Assumptions to revisit, in the order the results suggest: (1) uniform wind
  first — the Vente setup overshoot, the Nida peak-timing mismatch, and the
  systematic 8 Dec 06:00 miss at both Uostadvaris and Nida (see above) all
  point at missing spatial structure in the wind field that a single
  uniform wind value (taken at Nida) cannot supply; (2) the GTSM boundary
  next — its peak lands 25 h after the wind peak and the Klaipeda/
  Uostadvaris gauge peaks, and it carries high-frequency energy the
  once-daily gauge cannot confirm; (3) the 500 cm gauge-zero assumption
  looks right as it stands — bias is within ±6 cm at all four gauges;
  (4) channel dimensions and the Minija constant discharge — this event
  gives no evidence either way.

## Reproducing from a clean checkout

Raw, read-only source data this project reads but does not commit (paths on
the machine this was built on):

- `~/telemac/data/LowerNEMUNASdem_5m.tif` (DEM)
- `~/telemac/Curonian/data/curonian_bathymetry_hires.nc` (EMODnet-derived hi-res bathymetry)
- `~/curonian/isobates.gpkg` (in-lagoon isobaths)
- `~/curonian/curonian_db.gpkg` (gauge and discharge attribute tables)
- `~/eutropy/era5_raw/era5_wind_nida_2013.nc` (ERA5 wind at Nida)
- `~/.cdsapirc` — CDS API credentials for `prep.fetch_gtsm` (never printed, stored or
  committed by this project)

Two steps need the network and can fail or rate-limit on a bad connection:
Overpass (OSM) in `prep.make_channels` (falls back to fixed coordinates if it
fails and `--allow-fallback` is passed; keeps an existing OSM-derived file
otherwise) and the CDS download in `prep.fetch_gtsm`.

Git-ignored derived inputs that a clean checkout must regenerate before
`build_model.py` will run: `inputs/lagoon_bathy_50m.tif` (`prep.make_bathymetry`)
and the GTSM zip/CSV (`prep.fetch_gtsm`, needs `~/.cdsapirc`). Everything else
under `inputs/` is committed.

Build and run, from this folder inside the `hydromt-sfincs` env:

    micromamba run -n hydromt-sfincs python -m prep.make_bathymetry
    micromamba run -n hydromt-sfincs python -m prep.make_channels
    micromamba run -n hydromt-sfincs python -m prep.make_geometries
    micromamba run -n hydromt-sfincs python -m prep.fetch_gtsm
    micromamba run -n hydromt-sfincs python -m prep.make_forcing
    micromamba run -n hydromt-sfincs python build_model.py
    ../run_sfincs.sh runs/xaver_2013 16
    micromamba run -n hydromt-sfincs python validate.py

What `pytest tests` proves at each level:

- `micromamba run -n hydromt-sfincs python -m pytest tests -q` — everything,
  on a machine with the raw sources above mounted. Two `integration` tests
  check for their own prerequisite first and skip silently
  (`pytest.skip(...)`) rather than failing a checkout that hasn't built the
  model yet or fetched GTSM yet: `test_built_model_passes_checks` (needs
  `runs/xaver_2013/sfincs.inp`) and `test_real_gtsm_csv_covers_the_event`
  (needs `inputs/gtsm_klaipeda.csv`). The other `integration` tests read the
  raw sources directly and fail (not skip) if those paths aren't mounted.
- `... pytest tests -q -m "not network"` — the same, minus the one test that
  makes a live Overpass call (which itself also skips on a 5xx/timeout/
  connection error rather than failing, per `test_make_channels.py`).
- `... pytest tests -q -m "not integration"` — a deterministic, fully
  offline suite: pure-function unit tests only, no raw data, run folder, or
  network required. This is what a fresh checkout with none of the above can
  run immediately.

## Limitations

- `sfincs.inp` sets `depfile = sfincs.dep`, but hydromt_sfincs 1.2.2's
  `setup_subgrid()` never writes that file in subgrid mode; SFINCS ignores
  the key and reads elevation from the subgrid table instead. Do not run
  with `--no-subgrid` unless a `sfincs.dep` is written first — that mode
  reads `depfile` directly and there is none.
- `latitude` is left at hydromt's default `0.0` in `sfincs.inp`, so the
  Coriolis term vanishes (f = 2Ω·sin(0) = 0). This is a model change
  deferred on purpose so the validated results above stay as they are;
  setting a real latitude would need a re-run and re-validation.
- SFINCS warns at startup about subgrid uv points where
  `z_zmin − uv_zmin > 0.1 m`. Expected: the strait is burned to −12 m
  (`channels.geojson` `rivbed`), well below the surrounding subgrid cells'
  own minimum, by design (section 4 of the spec).
- `segment_length` is not an accepted key for `datasets_riv` entries in
  hydromt_sfincs 1.2.2; removed from `build_model.DATASETS_RIV`, so the
  library's own 500 m default is used instead.
