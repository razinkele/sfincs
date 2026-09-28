# Curonian Lagoon SFINCS model

Whole-lagoon compound-flood model, hindcasting two 2013 events on the same grid,
bathymetry and channels. Storm Xaver (28 Nov – 11 Dec 2013) is a Baltic surge that
pushes water into the lagoon through the Klaipeda strait; all three of its forcing
variants pass their success criteria (see "Results: Xaver 2013" below). The April
2013 Nemunas freshet (5 Apr – 2 May 2013) is the opposite driver — a slow, large
river inflow that has to leave through the same strait — and **the hindcast is a
partial result**: four of its seven scored criteria are met. The three that are
not — the delta filling ~3.6 days early (A2a), cresting late (A2b), and Rusnė
rising 0.20 m too little (A6a) — have two causes. A2a and A6a are the signature
of an ice jam on the lower Atmata that the model does not contain (see "Why the
delta fills early: an unmodelled ice jam" below); A2b is not moved by the jam and
more likely follows the timing of the sea boundary's crest. The sea boundary is fitted to the daily Klaipėda
readings (see "Sea boundary: fitted to the daily Klaipeda readings") and the river
inputs are the corrected Nemunas share and the measured Minija (see "River inputs:
Nemunas share and measured Minija"); neither correction fixes the timing misses.
Design: `../docs/superpowers/specs/2026-09-04-curonian-lagoon-xaver-model-design.md`
(Xaver) and `../docs/superpowers/specs/2026-09-16-april-2013-nemunas-flood-design.md`
(April).

All commands run from this folder inside the `hydromt-sfincs` env:

    micromamba run -n hydromt-sfincs python -m prep.make_bathymetry
    micromamba run -n hydromt-sfincs python -m prep.make_channels
    micromamba run -n hydromt-sfincs python -m prep.make_geometries
    micromamba run -n hydromt-sfincs python -m prep.fetch_gtsm
    micromamba run -n hydromt-sfincs python -m prep.make_forcing --event xaver_2013
    micromamba run -n hydromt-sfincs python build_model.py
    ../run_sfincs.sh runs/xaver_2013 16
    micromamba run -n hydromt-sfincs python validate.py
    micromamba run -n hydromt-sfincs python -m prep.export_map_cache --run xaver_2013

    micromamba run -n hydromt-sfincs python -m prep.make_forcing --event april_2013
    micromamba run -n hydromt-sfincs python build_model.py --event april_2013
    ../run_sfincs.sh runs/april_2013 16
    micromamba run -n hydromt-sfincs python validate.py --event april_2013
    micromamba run -n hydromt-sfincs python -m prep.export_map_cache --run april_2013

Two channel inputs are derived from a *built* model rather than from raw data, so
they bootstrap — build once, derive, rebuild. `prep.derive_strait` reads the active
mask out of `runs/xaver_2013` and rewrites the strait centreline in
`inputs/channels.geojson`; `prep.derive_channel_bed` then samples the 5 m DEM along
all three centrelines into `inputs/channel_bed.geojson`. Both outputs are committed,
so a clean checkout never has to run them:

    micromamba run -n hydromt-sfincs python -m prep.derive_strait
    micromamba run -n hydromt-sfincs python -m prep.derive_channel_bed

`diag/` holds diagnostics that read a finished run and print; they write nothing and
are safe to re-run. They are where the README's head and mass-balance numbers come
from:

    micromamba run -n hydromt-sfincs python -m diag.head_decomposition april_2013
    micromamba run -n hydromt-sfincs python -m diag.mass_balance april_2013

Tests: `micromamba run -n hydromt-sfincs python -m pytest tests -q`

**Map tab.** A read-only Shiny app in `app/` at the repo root (published at
<https://laguna.ku.lt/sfincs/>, deployed with `sudo bash deploy/deploy.sh` — see
`deploy/README.md`) views these runs. The viewer's Map tab plays a run hour by hour on a WebGL map —
water level or change from start (relative to the starting water level nearby,
so the starting shoreline shows no false step), plus the run's maximum —
with the stations coloured by model − gauge wherever a gauge reading lies within
30 min of the frame, the sea boundary, river inflows, active area and channel
centrelines drawn on top, and a click on any cell plotting its series. It needs
`prep.export_map_cache --run <name>` after each run: that writes the cell-series
cache (~430 MB per April run, ~210 MB per Xaver run, git-ignored under `runs/`)
and `results/<name>/gauge_obs.csv` (committed). Without it the tab still plays,
but a click reads `sfincs_map.nc` directly (~4 s).

## Run log

- Xaver 2013 one-day dry run (28→29 Nov 2013): 1.7 min on 16 threads, mean dt 3.47 s.
- Xaver 2013 full run (28 Nov–11 Dec 2013): 25.5 min on 16 threads, mean dt 3.46 s.
  Juodkrante, Nida, Rusne, and Silute originally landed on dry cells (their point_zs
  was flat at the local bed elevation); moved 0.2–1.2 km into the nearest wet cells
  (Silute needed the largest move; no closer wet cell exists at 100 m resolution)
  in `prep/make_geometries.STATIONS_LONLAT`, then reran `make_geometries`,
  `build_model.py`, and the full simulation. All 9 stations now vary by more than
  0.2 m over the run.
- Xaver 2013 gridded wind run (28 Nov–11 Dec 2013, `runs/xaver_2013_gridwind`):
  24.2 min on 16 threads, mean dt 3.46 s.
- Xaver 2013 gridded wind + pressure run (28 Nov–11 Dec 2013,
  `runs/xaver_2013_gridwind_pressure`): 25.4 min on 16 threads, mean dt 3.46 s.
- 2026-09-15: all three runs rebuilt and rerun after the island-shoreline
  bathymetry correction and the millimetre-precision regeneration of the
  committed inputs (see the cleanup sweep in
  `../docs/superpowers/plans/2026-09-04-curonian-lagoon-xaver-model-followups.md`),
  so the numbers below match the code that produced them. Baseline 38.4 min,
  gridded wind 26.3 min, gridded wind + pressure 28.0 min on 16 threads; mean dt
  3.464 s in all three, unchanged. The baseline's longer wall time is machine
  load during that run (15-minute load average peaked near 79 on 28 cores), not
  a model change. Every number that moved is recorded below; all four success
  criteria stayed met in all three runs.
- 2026-09-17: all three Xaver runs rebuilt and rerun three times, after each of
  the geometry fixes the April hindcast turned up (see "Results: April 2013").
  Final round, on the per-segment distributary beds: baseline 78.1 min, gridded
  wind 83.7 min, gridded wind + pressure 83.0 min — all three running at once on
  9 threads each, which is why the wall times are three times the 16-thread
  figures above; mean dt 3.464 s in all three, unchanged. Each build's subgrid was
  checked against April's cell for cell along all three channels before its run
  started (strait flat at −12.00 m; Atmata median −4.40 m, Skirvytė −4.82 m).
- April 2013 freshet run (`runs/april_2013`, 5 Apr–2 May 2013): build
  (`build_model.py --event april_2013`) 4 m 41 s, same `check_model()` gate as
  Xaver (`{'n_active': 331933, 'n_bnd': 70, 'connected': True, 'bnd_in_ring':
  True}` — same grid, same subgrid, same channels, per the spec). Run 47 m
  55 s wall clock on 16 threads (SFINCS's own accounting: 2868.652 s total,
  83.6% in momentum, 14.6% in continuity), mean dt 3.517 s; load average
  stayed under 1.5 throughout on a 28-core machine. `sfincs.inp` carries
  `tstart = 20130405 000000`, `tstop = 20130502 000000`,
  `zsini = -0.17` — the prescribed initial lagoon level (mean of the three
  lagoon gauges at TREF, not the sea boundary's first value; spec section 7).
  No `error`/`nan` in the solver log; `sfincs_his.nc` is finite everywhere
  over the full 5 Apr–2 May time axis. See "Results: April 2013" below for
  what the run produced.
- 2026-09-27: April 2013 gridded wind and gridded wind + pressure runs
  (`runs/april_2013_gridwind`, `runs/april_2013_gridwind_pressure`), built with
  `build_model.py --event april_2013 --wind grid [--pressure]` on
  `inputs/april_2013/era5_grid.nc`. Same `check_model()` gate as the baseline;
  subgrid, mask, boundary, discharge and stations identical to `runs/april_2013`
  (checked before running), so only the wind/pressure forcing differs. Run 83.9
  and 85.6 min wall clock (5033 s and 5134 s SFINCS total) — both at once on 14
  threads each, not the 16-thread single-run figure; mean dt 3.517 s in both,
  unchanged from the baseline. No `error`/`nan` in either log; `sfincs_his.nc`
  finite throughout. See "Sensitivity: gridded ERA5 wind and pressure (April)".
- 2026-09-28 (morning): all six runs (three Xaver, three April) re-run on the fitted sea
  boundary (see "Sea boundary: fitted to the daily Klaipeda readings"), 01:12–05:54,
  one after another on 12 threads each (a TELEMAC job held 16 cores). SFINCS total
  time 3218–3350 s for the April runs, 1609–1747 s for Xaver; mean dt unchanged
  (~3.51 s April). All six map caches re-exported with `prep.export_map_cache`.
- 2026-09-28 (afternoon): all six runs re-run again on the corrected river inputs
  (see "River inputs: Nemunas share and measured Minija"; code commit 9ace515,
  results commit 99f446c), 12:50–17:17 on 16 threads. SFINCS total time
  2790–3026 s for the April runs, 1496–2460 s for Xaver (the last Xaver run
  overlapped other load). All six map caches re-exported. Three diagnostic April
  runs were made alongside and kept in `results/experiments/` (not listed by the
  viewer): see "Why the delta fills early: an unmodelled ice jam".

## Sea boundary: fitted to the daily Klaipeda readings

Until 2026-09-28 the sea boundary was the GTSM series at Klaipėda plus one static
offset per event, fitted over a calm window before the event. It is now GTSM plus a
correction fitted to every Klaipėda 06:00 reading in the run
(`prep/make_forcing.daily_fit_correction`, commit 162bf14):

- at each daily reading the residual (reading − GTSM) is computed;
- the residuals are interpolated linearly in time and held flat past the
  outermost reading;
- a gap of more than 3 days between readings, or a run end more than 3 days
  from a reading, raises an error rather than extrapolating.

As run (`inputs/<event>/forcing_summary.txt`): Xaver is corrected by 15 readings,
residual −0.034 to +0.247 m (mean +0.110); April by 29 readings, residual −0.280 to
+0.078 m (mean −0.100); the largest gap is 24 h in both.

**Why not an hourly gauge.** The hourly EPA tide gauge at Klaipėda (Copernicus
Marine in-situ `INSITU_BAL_PHYBGCWAV_DISCRETE_MYNRT_013_032`, file
`BO_TS_TG_Klaipeda.nc`, 55.733N 21.083E, hourly 2006-02 to 2014-08) has **no data in
April, November or December 2013** — monthly counts for 2013 are Mar 61 h, Apr 0,
May 185, Oct 388, Nov 0, Dec 0. The Baltic reanalysis
(`BALTICSEA_MULTIYEAR_PHY_003_011`) is daily at best, and the Liepāja gauge starts in
November 2020. The LHMT 06:00 readings in `curonian_db` are the only sea level
there is for both events.

**Evidence** (spike, 2026-09-28), from the months where the EPA gauge does have data:

- The LHMT 06:00 readings agree with the hourly gauge: 2 319 pairs, r 0.992, sd of
  the difference 2.6 cm, mean −1.5 cm, best at lag 0/−1 h. So a 06:00 reading is a
  good sample of the true level at that hour.
- Over 19 event-sized windows (7-day fit + 21-day score) in Oct 2012 – Aug 2013,
  with GTSM for those months, scored hourly against the gauge:

  | | static offset | fitted to daily readings |
  | --- | --- | --- |
  | median hourly RMSE | 0.052 m | **0.028 m** |
  | worst window RMSE | 0.112 m | 0.051 m |
  | error over the top-2 % hours | 0.065 m | 0.021 m |
  | whole winter Oct 2012 – Feb 2013, RMSE (r) | 0.129 m (0.73) | 0.036 m (0.98) |
  | summer Jun – Aug 2013, RMSE | 0.056 m | 0.027 m |

  The fitted boundary was better in 19 of 19 windows.

**What it cannot fix.** Split by time scale, the error in variations longer than
2 days falls from 0.123 m to 0.017 m; the error shorter than 2 days is unchanged at
~0.03 m. Between two readings the boundary's shape is GTSM's, and once-daily
sampling cannot correct it. Xaver shows the limit: Klaipėda's peak error is still
+0.15 m, because the storm peak falls between two 06:00 readings.

**Consequence for validation.** C3 (Xaver) and A4 (April) compared the model with
those same Klaipėda readings, so they no longer test anything: both are now info
lines, "Klaipeda boundary fit", and are not scored (C3 storm RMSE 0.01 m; A4 RMSE
0.001–0.002 m). A3 stays scored. Its sea end is now constrained, so it tests the
delta end of the head.

If hourly EPA data for 2013 is ever obtained, it should replace this fit, and C3
and A4 would become independent tests again.

## River inputs: Nemunas share and measured Minija

Two corrections to the river inflows, commit 9ace515; all six runs were re-run on
them on the afternoon of 2026-09-28.

**Nemunas: 0.896 × Smalininkai, not 1.00 ×.** The model injected the Smalininkai
discharge unchanged at the Rusnė apex. It now injects
`common.NEMUNAS_DELTA_FACTOR = 1.12 × 0.80 = 0.896` times it:

- × 1.12 for the tributaries that join below Smalininkai (Šešupė, Jūra, Šešuvis);
- × 0.80 because about 20 % of the Nemunas leaves through the Gilija/Matrosovka
  before Rusnė — Zemlys et al. 2013 (124 of 624 m³/s); Valiuškevičius et al. 2019,
  Baltica 31(2), doi 10.5200/baltica.2018.31.09: "About 80% of the annual runoff
  of the Nemunas River flows through the right distributaries".

It is the same transformation the sibling SHYFEM project documents
(`~/curonian/etl/03_river_forcing_export.py`). Before, the delta received about
12 % too much water.

**Minija: measured at Lankupiai, not a constant.** The Minija was an estimated
constant (46 m³/s for Xaver, 83 m³/s for April) because a comment said the
database record ended in 2011. That was stale once the LHMT API's Lankupiai
2012–2014 record was loaded. The model now uses the measured daily discharge
(`inputs/<event>/lhmt_lankupiai.csv`; © LHMT, CC BY-SA 4.0) with no lag or
scaling, since the gauge is ~10 km above the mouth. In April the measured flow was
14–20 m³/s on 5–11 April (the constant ran about 5× too high), 84 → 144 → 129 m³/s
on 13–15 April and 35–50 m³/s in late April; for Xaver it is 45–105 m³/s.

**Kept: the 1-day Nemunas lag.** It was checked against the sibling project's
fitted travel time, 24.822 + 4879.7/Q hours (27 h at 2000 m³/s, 35 h at 500 m³/s),
and left as it is.

As run (`inputs/<event>/forcing_summary.txt`): Nemunas at Rusnė 314–585 m³/s for
Xaver and 358–1926 m³/s for April; Minija 45–105 and 14–144 m³/s.

On its own (Run A, `results/experiments/april_2013_riverfix/`) the correction took
382 Mm³ out of the delta over the April run — 310 Mm³ from the Nemunas, 72 Mm³ from
the Minija. It lowered the April levels (A1 +0.13 → +0.07 m, A3 +0.09 → +0.02 m,
Uostadvaris scoring-window bias +0.16 → +0.09 m) but barely the timing (A2a −96 →
−87 h, still not met; A2b still not met), and
Rusnė now rises too little (A6a −0.20 m, not met); see "Why the delta fills early:
an unmodelled ice jam". Xaver moved by at most 0.01 m in any error.

## Results: Xaver 2013

> **Re-run on the afternoon of 2026-09-28 on the corrected river inputs** (see
> "River inputs: Nemunas share and measured Minija"). The figures below are from
> that run. C1, C2 and C4 stay met in all three variants and every error moved by
> at most 0.01 m: C1 +0.08 → +0.07 m, C2 −0.01 → −0.02 m, the 8 Dec 06:00 miss at
> Uostadvaris/Nida −0.09/−0.12 → −0.10/−0.13 m; flooded area 158.4 → 157.1 km².
>
> **Re-run on the morning of 2026-09-28 on the fitted sea boundary** (see "Sea
> boundary: fitted to the daily Klaipeda readings"). C3 became an info line, so C1,
> C2 and C4 are the scored criteria. Against the static-offset run the C2 error went
> from −0.04 to −0.01 m, the 8 Dec 06:00 miss at Uostadvaris/Nida from −0.11/−0.14
> to −0.09/−0.12 m, and flooded area from 155.6 to 158.4 km² (all before the
> river-input corrections).
>
> **Re-run three times on 2026-09-17**, each time after the April hindcast exposed
> a defect in the shared geometry: first a bathymetry bar at datum across the
> strait and a 4 km gap in the burned strait channel; then the Uostadvaris
> observation point, 3.6 km from its LHMT gauge; then the Nemunas distributaries
> burned to a first-estimate constant instead of their surveyed bed. All are
> described under **Results: April 2013**. Xaver's *forcing* is unchanged
> through those re-runs: its Jul–Dec 2013 Smalininkai block agrees with LHMT exactly, so no
> discharge fix touched it (the river-input corrections of 2026-09-28 came later).
> **C1–C4 remain met in all three variants**, so the published Xaver claim does
> not depend on any of the broken geometry; the surge pushes water *into* the
> lagoon, which is far less sensitive to outflow capacity than a freshet. The
> strait fixes improved the numbers sharply — Nida's and Ventė's whole-period
> peak timing moved from −67 h and −60 h to +2 h, C2 went from "met (marginal)"
> to a clean "met" in every variant, and at the corrected station Uostadvaris
> reaches RMSE 0.04–0.09 m with r up to 0.96 (before the fitted boundary). The distributary beds, the last
> change, moved only the delta and only slightly: C1's error went from +0.09 to
> +0.07 m in the baseline and from +0.01 to −0.01 m with gridded wind
> (and likewise +0.01 to −0.01 m with pressure), the 8 Dec 06:00 Uostadvaris miss widened by
> 0.02 m, and flooded area fell 1–2 km² (all before the fitted boundary). The
> figures below are from the afternoon 2026-09-28 re-run, not these.

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
| Klaipeda | 13 | +0.00 | 0.01 | 1.00 | +0.15 | +9 |
| Nida | 26 | -0.01 | 0.07 | 0.88 | +0.02 | +2 |
| Vente | 26 | +0.05 | 0.10 | 0.79 | +0.10 | +2 |
| Uostadvaris | 13 | -0.01 | 0.06 | 0.92 | +0.07 | +0 |

Storm window: 2013-12-05 00:00 to 2013-12-09 00:00

| station | n | bias m | RMSE m | r | peak err m | peak dt h |
|---|---|---|---|---|---|---|
| Klaipeda | 4 | +0.01 | 0.01 | 1.00 | +0.15 | +9 |
| Nida | 8 | -0.07 | 0.12 | 0.79 | -0.02 | +0 |
| Vente | 8 | +0.02 | 0.12 | 0.73 | +0.08 | -67 |
| Uostadvaris | 4 | -0.03 | 0.08 | 0.90 | +0.07 | +0 |

Flooded land in the delta window (depth > 5 cm, ground > 0 m): **157.1 km²**

### Success criteria (spec section 9)
- C1 Uostadvaris peak [2013-12-05 00:00 to 2013-12-09 00:00]: **met** -- model peak 2013-12-06 06:20, peak err +0.07 m, dt +0.3 h (threshold: peak err within +/-0.15 m and |dt| <= 6 h)
- C2 Nida 8 Dec rise [2013-12-07 06:00 to 2013-12-08 18:00]: **met** -- model 0.40 m -> 0.82 m vs gauge 0.84 m, err -0.02 m, rise reproduced (threshold: err within +/-0.15 m (<=0.10 m for a clean 'met'), rise reproduced in sign)
- C3 Klaipeda boundary fit [2013-12-05 00:00 to 2013-12-09 00:00]: **info** -- storm RMSE 0.01 m (whole-period RMSE 0.01 m) (threshold: n/a -- the sea boundary is fitted to these readings; not an independent test)
- C4 Silute uplands [delta window (325000, 6105000, 360000, 6145000)]: **met** -- 0.00% of land with ground > 3 m flooded (threshold: < 1 % flooded)
- Info: Uostadvaris 8 Dec 06:00 [2013-12-08 06:00]: **info** -- model 0.73 m vs gauge 0.83 m, err -0.10 m (threshold: n/a (context only))
- Info: Nida 8 Dec 06:00 [2013-12-08 06:00]: **info** -- model 0.61 m vs gauge 0.74 m, err -0.13 m (threshold: n/a (context only))

Forcing as run (`inputs/xaver_2013/forcing_summary.txt`): GTSM corrected by 15
Klaipeda 06:00 readings, residual −0.034 to +0.247 m (mean +0.110), largest gap
24 h; boundary level 0.40 m at the start, storm peak 1.02 m at 2013-12-06 16:00;
Klaipeda 06:00 gauge peak 0.88 m at 2013-12-06 06:00; wind peak 19.5 m/s at
2013-12-06 06:00 from 236°; Nemunas at Rusnė (0.896 × Smalininkai) 314–585 m³/s,
Minija (measured at Lankupiai) 45–105 m³/s. The fitted boundary, the gauge and the
wind all peak on 6 December.

### Findings

- Sea boundary vs the Klaipeda gauge: the GTSM boundary is corrected to each of the
  15 Klaipeda 06:00 readings in the run (residual −0.034 to +0.247 m, mean +0.110;
  see "Sea boundary: fitted to the daily Klaipeda readings") and peaks at 1.02 m at
  2013-12-06 16:00, the same day as the gauge's 0.88 m at 06:00 and the wind peak.
  C3 is therefore an info line, not a test: storm-window RMSE 0.01 m, whole-period
  0.01 m, r 1.00, by construction. The table's Klaipeda peak error of +0.15 m at
  +9 h is what the fit cannot reach: the model's continuous storm maximum falls
  between two 06:00 readings, and between readings the boundary's shape is GTSM's.
  (Before the fitted boundary the static offset left a 25 h gap between the
  boundary peak and the gauge peak, a storm-window RMSE of 0.12 m, and a 06:00
  error alternating −0.11 m, +0.13 m, −0.16 m on 6–8 Dec.) Before the storm the
  model shows 0.2–0.6 m oscillations that the once-daily 06:00/18:00 gauge cannot
  confirm or rule out — high-frequency energy carried in on the GTSM boundary,
  which the daily fit does not remove.
- Uostadvaris peak: model peak at 06:20 on 6 Dec against the gauge's 0.92 m at
  06:00 — peak error +0.07 m at +0.3 h, inside the ±0.15 m / ±6 h target
  (C1: met). Sampled at the gauge's own coordinate since 2026-09-17; the
  whole-period bias there is −0.01 m at RMSE 0.06 m, r 0.92.
- Nida delayed rise: the model rises from 0.40 m to 0.82 m across 7–8 December
  against the gauge's peak of 0.84 m, a miss of −0.02 m with the rise reproduced
  in sign — a clean C2 "met" (−0.04 m before the fitted boundary). Before the
  geometry fixes the same comparison read 0.46 m → 0.71 m for a −0.13 m miss,
  which passed only marginally. The whole-period peak error is +0.02 m at +2 h,
  where before the geometry fixes it was −0.07 m at −67 h: the old figure was the
  gap between two different events (the model's own gale-driven peak on 5–6
  December and the gauge's on the 8th), and that ambiguity is gone. Nida,
  Juodkrante, Rusne and Silute all had to be moved 0.2–1.2 km into wet cells to
  get a usable point series (see Run log).
- The second rise is missed at both gauges, not just Nida: at 8 Dec 06:00
  the model is −0.10 m low at Uostadvaris (0.73 m vs gauge 0.83 m) and
  −0.13 m low at Nida (0.61 m vs gauge 0.74 m) — almost the same miss at two
  gauges roughly 60 km apart, so it is systematic rather than an artefact of
  moving the Nida station off its spec position. Two candidates have now been
  tested and neither explains it. Wind: the gridded ERA5 runs (see "Sensitivity:
  gridded ERA5 wind and pressure" below) reduce it to −0.08/−0.09 m. The daily
  level of the sea boundary: fitting it to the Klaipeda readings moved the miss
  only from −0.11/−0.14 m to −0.09/−0.12 m (before the river-input corrections,
  which added 0.01 m to each). What is left untested is the sea
  boundary's shape *between* readings, which once-daily readings cannot
  constrain.
- Vente: the whole-period peak error is +0.10 m at +2 h, so the model and gauge
  maxima still fall within hours of each other. RMSE 0.10 m over the whole period,
  0.12 m in the storm window. (Before the fitted boundary, at matching 06:00
  readings on 6 Dec the model overshot the setup peak by about 0.21 m — 0.81 m
  modelled vs 0.60 m gauge — and tracked the gauge well afterwards.)
- Flooded area: 157.1 km² of land floods in the delta window (depth > 5 cm,
  ground > 0 m only; 158.4 km² before the river-input corrections, 155.6 km²
  before the fitted boundary). This is a lower bound
  on inundation extent — cells at or below 0 m ground are excluded — but likely
  an overestimate of real flooding, since the model has no drainage or pumping,
  the modelled whole-period peak error at Klaipeda is +0.15 m even though the mean
  bias there is +0.00 m, and dikes may be under-resolved at 5 m grid resolution.
  Rusne island and the Silute polders flood field by field, a plausible pattern;
  land with ground > 3 m in the delta window (this includes the higher ground
  around Silute, though the station's own observation cell sits at 2.94 m and is
  excluded from the mask) stays essentially dry (C4: 0.00% flooded).
- Assumptions to revisit, reordered after the fitted boundary and the
  gridded-wind sensitivity runs: (1) the sea boundary between the daily readings —
  its level on each reading is now fitted, but its sub-daily shape (the storm peak
  between two 06:00 readings, the pre-storm oscillations) is still GTSM's, and it
  is the one remaining candidate for the 8 Dec 06:00 miss; only an hourly sea-level
  series could test it (see "Sea boundary: fitted to the daily Klaipeda readings");
  (2) wind spatial structure — tested directly (see "Sensitivity: gridded ERA5 wind
  and pressure"): it cut flooded area by about 17 % but left the 8 Dec 06:00 miss
  nearly unchanged, so a uniform vs. gridded wind field is not the main driver of
  that miss; (3) the 500 cm gauge-zero assumption looks right as it stands —
  whole-period bias is within ±5 cm at the three gauges not fitted to (Klaipeda's
  +0.00 m is now by construction); (4) channel dimensions — this event gives no
  evidence either way. (The Minija is no longer an assumption: it is the measured
  Lankupiai discharge; see "River inputs: Nemunas share and measured Minija".)

## Sensitivity: gridded ERA5 wind and pressure

The baseline run above forces SFINCS with a spatially uniform wind: the ERA5
10 m wind at a single point (Nida) broadcast across the whole domain. Two
sensitivity runs replace that with the actual ERA5 field over the lagoon, to
test the wind-spatial-structure item in the baseline's Assumptions list
above (that list is reordered above to reflect what these runs found).

### What changed

`prep/fetch_era5_grid.py` fetches the hourly, 0.25° ERA5
reanalysis-era5-single-levels grid over a box around the lagoon (56.0–54.75°N,
20.25–22.0°E; 8×6 cells) for 27 Nov–11 Dec 2013 and reshapes it to
`inputs/xaver_2013/era5_grid.nc` (`wind10_u`, `wind10_v`, `press_msl` on
`time, y, x`). `build_model.py --wind grid --run-name xaver_2013_gridwind`
calls `setup_wind_forcing_from_grid` on that file instead of
`setup_wind_forcing`'s single-point `wind.csv` (`sfincs.inp` gets
`netamuamvfile` instead of `wndfile`). `build_model.py --wind grid --pressure
--run-name xaver_2013_gridwind_pressure` additionally calls
`setup_pressure_forcing_from_grid` on the same file (`netampfile`).
`pavbnd` stays 0 (hydromt_sfincs' own default, left untouched) and `baro`
stays 1 (also its default): the GTSM boundary series already has the inverse
barometer effect baked in from its own reanalysis, so a boundary pressure
correction here would double count it, while `baro = 1` still lets SFINCS
apply the pressure gradient force from `netampfile` inside the domain.
Bathymetry, subgrid, boundary, discharge and river forcing are unchanged from
`runs/xaver_2013`; both variants pass the same `check_model()` gate
(`{'n_active': 331933, 'n_bnd': 70, 'connected': True, 'bnd_in_ring': True}`,
identical to the baseline) and are scored by `validate.py --run <name>` the
same way as the baseline. `inputs/xaver_2013/era5_grid_summary.txt` records the fetch: a
315-step, 8×6-cell, 0.25° grid for 2013-11-27 23:00–2013-12-11 01:00; Nida-point
wind speed RMSE 0.000 m/s against the existing point series (well inside the
0.5 m/s check); peak wind speed 20.6 m/s at 2013-12-06 03:00 (55.50°N,
20.50°E); mean sea level pressure 100956 Pa; pressure minimum 96740 Pa at
2013-12-06 08:00.

### Run log

Wall time and mean dt for both runs are in the main "Run log" section above.

### Comparison

Numbers below are pasted verbatim from `results/xaver_2013/validation.md`,
`results/xaver_2013_gridwind/validation.md` and
`results/xaver_2013_gridwind_pressure/validation.md` (peak err/dt for
Uostadvaris and Vente are the storm-window figures; Uostadvaris peak err/dt
are the C1 line's, which carries one more decimal than the table).

| run | Vente storm peak err m | Uostadvaris peak err m | Uostadvaris peak dt h | Nida C2 err m (verdict) | Uostadvaris 8 Dec 06:00 err m | Nida 8 Dec 06:00 err m | C3 Klaipeda fit storm RMSE m (info) | flooded area km² | C1 | C2 | C3 | C4 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| baseline (uniform wind) | +0.08 | +0.07 | +0.3 | -0.02 (met) | -0.10 | -0.13 | 0.01 | 157.1 | met | met | info | met |
| gridded wind | +0.07 | -0.00 | +0.3 | -0.02 (met) | -0.08 | -0.09 | 0.01 | 130.7 | met | met | info | met |
| gridded wind + pressure | +0.06 | -0.00 | +0.3 | -0.03 (met) | -0.09 | -0.10 | 0.01 | 130.2 | met | met | info | met |

Full validation output: `results/xaver_2013_gridwind/validation.md`,
`results/xaver_2013_gridwind_pressure/validation.md`, and each run's own
`validation_timeseries.png`/`flood_extent_delta.png` in the same two
`results/` subfolders.

### Interpretation

All figures here are from the afternoon 2026-09-28 re-run, on the fitted sea
boundary and the corrected river inputs. The sensitivity conclusion is the same as
on the static-offset runs, with one exception: the Ventė overshoot.

The Ventė storm-window peak error barely narrows with gridded wind: +0.08 m in the
baseline, +0.07 m with gridded wind, +0.06 m with pressure added — steps of 0.01 m,
the same size as the river-input correction moved it (+0.08, +0.08, +0.07 m before
it). On the static-offset runs it read +0.07, +0.04 and +0.03 m. That narrowing did
not survive the boundary change, so it should not be read as a wind effect.

The systematic 8 December second-rise underestimate is still present and still
largely unexplained by wind: −0.10/−0.13 m (Uostadvaris/Nida) in the baseline,
−0.08/−0.09 m with gridded wind and −0.09/−0.10 m with pressure. The geometry fix
took the baseline from −0.23/−0.22 m to −0.11/−0.14 m, the fitted boundary a
further 0.02 m off each, and the river-input correction put 0.01 m back on each;
neither wind nor the daily boundary level accounts for the rest (see Findings
above).

C3 is now an info line: Klaipėda storm RMSE 0.01 m in all three runs, because the
boundary is fitted to those readings. The Nida C2 rise error is −0.02 to −0.03 m,
a clean "met" in every variant. Adding pressure on top of gridded wind still moves
every number by at most 0.02 m or 0.5 km², consistent with `pavbnd = 0` keeping
the pressure effect local.

The peak-dt tie-break caveat still applies, though it now bites in one place
rather than several: Ventė's storm-window peak dt reads −67 h in the baseline
while both gridded variants read +0 h, because the window holds two maxima of
comparable height (the model's gale-driven peak on 5–6 December and the gauge's
later peak on 8 December) and which one `skill()`'s tie-break lands on shifts
with small changes in the series. Nida reads +0 h in all three. Read Ventė's
figure as an artefact of the tie-break, not a timing error.

The flooded-area drop with gridded forcing persists (157.1 km² → 130.7 and
130.2 km², about 17 %; 158.4 → 131.7 and 131.3 km² before the river-input
corrections, 155.6 → 128.8 and 128.3 km² before the fitted boundary),
consistent with the ERA5 grid's wind over the delta being weaker or differently
oriented than the Nida point value the baseline applies everywhere. That
mechanism was not isolated further and should be read as plausible, not
confirmed.

## Results: April 2013

Full validation output: `results/april_2013/validation.md`,
`results/april_2013/validation_timeseries.png` (time series) and
`results/april_2013/flood_extent_delta.png` (delta flood-extent map).
`validate.py --event april_2013` produces `results/april_2013/` itself the same
way it does for Xaver (it copies its own `validation.md` and both PNGs there
after writing them to the run folder); nothing under `results/` is copied by
hand. Tables and verdict lines pasted verbatim below.

Whole period: 2013-04-05 00:00 to 2013-05-02 00:00

| station | n | bias m | RMSE m | r | peak err m | peak dt h |
|---|---|---|---|---|---|---|
| Klaipeda | 27 | +0.00 | 0.00 | 1.00 | +0.02 | +19 |
| Nida | 54 | -0.08 | 0.09 | 0.98 | -0.08 | -58 |
| Vente | 54 | +0.06 | 0.07 | 0.97 | +0.07 | -6 |
| Uostadvaris | 27 | +0.07 | 0.11 | 0.94 | +0.07 | +18 |

Scoring window: 2013-04-13 00:00 to 2013-05-02 00:00

| station | n | bias m | RMSE m | r | peak err m | peak dt h |
|---|---|---|---|---|---|---|
| Klaipeda | 19 | +0.00 | 0.00 | 1.00 | +0.02 | +19 |
| Nida | 38 | -0.06 | 0.07 | 0.98 | -0.08 | -58 |
| Vente | 38 | +0.07 | 0.08 | 0.97 | +0.07 | -6 |
| Uostadvaris | 19 | +0.09 | 0.13 | 0.90 | +0.07 | +18 |

Flooded land in the delta window (depth > 5 cm, ground > 0 m): **63.5 km²**

### Success criteria (spec section 9)
- A1 Uostadvaris peak [2013-04-13 00:00 to 2013-05-02 00:00]: **met** -- model peak 0.61 m vs gauge 0.54 m, err +0.07 m (threshold: peak err within +/-0.15 m)
- A2a filling rate [first crossing of +0.20 m]: **not met** -- model 2013-04-15 17:00 vs gauge (interpolated) 2013-04-19 08:00, dt -87 h (threshold: within +/-24 h of the observed crossing)
- A2b crest timing [2013-04-21 18:00 to 2013-04-24 18:00]: **not met** -- model peak 2013-04-25 00:10; observed plateau 22 Apr-24 Apr (threshold: model peak inside the observed plateau +/-12 h)
- A3 delta-to-sea head [2013-04-22 00:00 to 2013-04-26 00:00]: **met** -- model 0.50 m vs gauge 0.48 m over 5 readings, err +0.02 m (threshold: mean head within +/-0.15 m)
- A4 Klaipeda boundary fit [2013-04-13 00:00 to 2013-05-02 00:00]: **info** -- RMSE 0.002 m against an observed sd of 0.089 m (threshold: n/a -- the sea boundary is fitted to these readings; not an independent test)
- A5 Silute uplands [whole run, delta window (325000, 6105000, 360000, 6145000)]: **met** -- 0.00% of land with ground > 3 m flooded (threshold: < 1 % flooded)
- A6a Rusne rise [2013-04-13 00:00 to 2013-05-02 00:00]: **not met** -- model 1.33 m vs gauge 1.53 m above the 05-11 Apr mean, err -0.20 m (daily values; gauge zero unknown, rise only) (threshold: rise within +/-0.15 m)
- A6b Rusne crest date [19 Apr to 24 Apr]: **met** -- model crest 21 Apr; observed plateau 20 Apr-23 Apr (threshold: model crest inside the observed plateau +/-1 day)

Forcing as run (`inputs/april_2013/forcing_summary.txt`): GTSM corrected by 29
Klaipeda 06:00 readings, residual −0.280 to +0.078 m (mean −0.100), largest gap
24 h; boundary level −0.35 m at the start rising to a crest of 0.16 m at
2013-04-25 01:00; Klaipeda 06:00 gauge peak 0.15 m at 2013-04-24 06:00; wind peak
12.2 m/s at 2013-04-25 01:00 from 265°; Nemunas at Rusnė (0.896 × Smalininkai)
358–1926 m³/s, Minija (measured at Lankupiai) 14–144 m³/s. The GTSM crest lands
19 h from the Klaipeda 06:00 gauge peak — past the 12 h check tolerance, recorded
as a FINDING per spec and not treated as a blocker (with only daily gauge readings,
19 h is inside the observation's own resolution; the fit sets the level at each
reading, not the timing between them).

### Findings

- **Three of the seven scored criteria are not met** — A2a and A2b, both on
  timing, and A6a, Rusnė's rise. A1, A3, A5 and A6b are met. A4 is an info line
  (see "Sea boundary: fitted to the daily Klaipeda readings"). Before the
  river-input corrections five of seven were met (A6a passed at −0.11 m); before
  the fitted boundary four of eight, with A3 and A4 also failing. A2a and A6a point
  to one thing the model does not contain, an ice jam on the lower Atmata; A2b does
  not (see "Why the delta fills early: an unmodelled ice jam" below).
- **A6 checks the freshet at Rusnė, in the delta itself**, against LHMT's daily
  Atmata level (`inputs/april_2013/lhmt_rusne.csv`; © LHMT, CC BY-SA 4.0). That
  gauge's zero is not known in the model datum (it sits ~2 m from the 500 cm
  assumed for the lagoon gauges), so A6 scores only the rise above the 5–11 Apr
  calm-window mean and the crest date, never absolute level. The model's rise is
  1.33 m against 1.53 m observed (−0.20 m, not met; −0.11 m and met before the
  river-input corrections, when the delta received about 12 % too much Nemunas).
  Its crest falls on 21 Apr, inside the observed 20–23 Apr plateau. The model's
  Rusnė starts rising on time, so the inflow timing is right, but it levels off by
  17 Apr while the gauge keeps rising to its 21–22 Apr peak. The run itself is
  not in question: `sfincs.inp`'s `tstart`/`tstop` match the event, `sfincs_his.nc`
  is finite throughout, and the solver log is clean.
- **Levels are close; the timing is not.** Over the scoring window, station bias
  through the two 2026-09-28 corrections:

  | station | static offset | fitted boundary | + corrected river inputs | RMSE (now) |
  | --- | --- | --- | --- | --- |
  | Klaipėda (the sea) | −0.16 m | +0.00 m | +0.00 m | 0.00 m (fitted to it) |
  | Nida | −0.13 m | −0.02 m | −0.06 m | 0.07 m |
  | Ventė | −0.00 m | +0.10 m | +0.07 m | 0.08 m |
  | Uostadvaris (the delta) | +0.10 m | +0.16 m | +0.09 m | 0.13 m |

  With the sea end fitted, the eastern side — Ventė and Uostadvaris — stood
  0.10–0.15 m high; taking the excess Nemunas and Minija water out brought it to
  +0.07 and +0.09 m. Nida moved the other way, from −0.02 m to −0.06 m (r 0.98
  throughout). The old near-perfect Ventė (bias −0.00 m, RMSE 0.04 m) and A1
  (+0.05 m) on the static-offset run were partly compensating errors: a sea end
  held too low pulling down a delta end that was too high. With the sea end fixed
  A1 was met at +0.13 m, close to its ±0.15 m limit; with the river inputs
  corrected it is +0.07 m (peak 0.61 m vs gauge 0.54 m). Before the distributaries
  were given their surveyed bed (see *The second cause* below) Uostadvaris read
  +0.22 m, RMSE 0.25 m and peak error +0.16 m, and A1 failed.
- **A3 is met, and tests the delta end.** A3 scores the mean Uostadvaris −
  Klaipėda head, so its error is the difference of those two stations' biases.
  With Klaipėda fitted to its readings, A3's +0.02 m (model 0.50 m vs gauge 0.48 m)
  is the delta end's excess alone; it was +0.09 m before the river-input
  corrections and +0.23 m on the static-offset run. The decomposition then (before
  the fitted boundary), over A3's crest window on the five readings all four
  gauges share, was:

  | station | model − gauge | sd |
  | --- | --- | --- |
  | Klaipėda (the sea) | **−0.209 m** | 0.053 m |
  | Nida | −0.134 m | 0.008 m |
  | Ventė | −0.041 m | 0.077 m |
  | Uostadvaris (the delta) | **+0.024 m** | 0.016 m |

  That table's reading — a sea boundary held too low, pulling hardest at the
  strait and decaying inland — is what the fitted boundary confirmed: Klaipėda's
  bias went to +0.00 m and Nida's from −0.13 m to −0.02 m. Its other reading, that
  the delta stood within 2.4 cm of its gauge, did not survive: the delta was being
  held down by the low sea, and with the sea right it stood high. Averaged over
  the whole scoring window the decomposition then gave an Uostadvaris − Ventė
  excess head of +0.235 m before the bed fix and **+0.112 m** after it, and Ventė −
  Nida +0.124 m (all before the fitted boundary). Both tables come from
  `diag/head_decomposition.py`, which prints them for either event; they have not
  been recomputed for either 2026-09-28 re-run.
- **A2a and A2b are the timing misses.** The model reaches +0.20 m at Uostadvaris
  87 h early (96 h before the river-input corrections, 89 h before the fitted
  boundary, 103 h before the bed fix): the delta fills ~3.6 days too soon, then
  crests after the observed plateau (A2b, model peak 2013-04-25 00:10 against an
  observed 22–24 Apr plateau). Neither the sea boundary nor the river inputs move
  A2a by more than 9 h; the ice-jam experiments below do. None of them moves A2b,
  whose crest sits on the sea boundary's crest instead (see the Conclusion there).
- **A3 was met until 2026-09-17, and its passing was an artefact.** It read
  −0.13 m while Uostadvaris was sampled 3.6 km down-delta of its gauge, where the
  modelled level is about 0.40 m lower. Two errors were cancelling: an over-built
  gradient and a sampling point part-way down it. With the station on its gauge
  the cancellation was gone and A3 failed at +0.23 m (before the fitted boundary).
  Its pass since 2026-09-28 is a different case: both ends now sit on their own
  gauges, and the sea end is constrained by the readings.
- **A4 is now an info line**, "Klaipeda boundary fit": RMSE 0.002 m against an
  observed sd of 0.089 m, because the boundary is fitted to the same readings it
  compares with. Before the fitted boundary it failed at RMSE 0.176 m and never
  moved through any of the geometry or data work — the cause was the boundary's
  static calm-window offset (spec section 10, limitation 5), which the fit
  replaces.
- **Mass balance** (before the fitted boundary and before the river-input
  corrections; not recomputed since). Over the 27-day run the two discharge points
  delivered 3.17 × 10⁹ m³. Spread over the 1601 km² of lagoon the model actually
  resolves (`lagoon_boundary` intersected with the active mask) that is a 1.98 m
  rise if nothing drained. The area-weighted mean lagoon level went from −0.170 m
  at the start to a peak of +0.205 m on 28 April — a rise of 0.375 m, so the model
  passed **81 % of the freshet through the strait and held 19 %**. The observed
  lagoon peaked at 0.54 m at Uostadvaris and had receded to 0.10 m by the end, so
  it passed essentially all of it. The river-input corrections alone took 382 Mm³
  out of the delta over the run (see "River inputs: Nemunas share and measured
  Minija"). Modelled flooded extent is now 63.5 km² (73.3 km² before the
  river-input corrections, 66.5 km² before the fitted boundary, 81.0 km² before the
  bed fix). `diag/mass_balance.py` computes this, definition included.
- **Where to look next.** The river end is now accounted for: the inflow volume is
  corrected, the inflow timing checks out (the model's Rusnė starts rising on time,
  and the 1-day lag was checked against the sibling project's fitted travel time
  and kept), and the
  delta-timing misses and Rusnė's missing rise are the signature of an ice jam (see
  the next section). Two leads remain. (1) Hourly EPA sea level for 2013 at
  Klaipėda: the sea boundary's remaining weakness is sub-daily; for a slow freshet
  it matters less than for Xaver, and only hourly data could improve it (see "Sea
  boundary: fitted to the daily Klaipeda readings"). (2) An observation of the 2013
  jam itself — when it formed and when it went — if one exists; with it, the
  blockage in `results/experiments/` could be built in on evidence rather than
  fitted. The burned distributary widths (200 m Atmata, 150 m Skirvytė, spec
  section 4), Manning's n on the distributaries and grid storage are still
  untouched, but they are no longer the suspects: they act all the time, not only
  before 18 April.

### Why the delta fills early: an unmodelled ice jam

**What the gauges show** (daily readings). The Nemunas at Smalininkai rises from
699 m³/s on 12 Apr to 1660 m³/s on 15 Apr and 2150 m³/s on 19 Apr. Rusnė, on the
Atmata, rises from 13 Apr at a steady ~0.2 m/day to a peak on 21–22 Apr.
Uostadvaris, at the Atmata mouth ~10 km downstream on the same channel, stays flat
(−0.13 to +0.09 m) until 18 Apr, then jumps from 0.09 m to 0.37 m over 18–20 Apr.
Ventė and Nida rise from 18–21 Apr. So for five days the water rose at Rusnė and
did not arrive at the mouth.

**What the model does.** Its Rusnė starts rising on time, so the inflow timing is
right, but it levels off by 17 Apr. Uostadvaris, Ventė and Nida rise from
13–15 Apr, about 4 days early. With nothing between Rusnė and the mouth, the model
passes the freshet straight through.

**Ice.** Uostadvaris's water temperature reads exactly 0.0 °C every day until
12 Apr, then 3.5 °C on 13 Apr — ice at the Atmata mouth — while Nida and Ventė warm
from ~6–10 Apr. Copernicus sea-ice shows the lagoon clear from ~4 Apr, but its grid
is too coarse for the delta channels. Ice jams were observed "almost every second
year near Rusne during the period 1970-1989" (Vaikasas 2005, cited in Valiuškevičius
et al. 2019), who also note that the gauges capture only a fraction of jams. No
report of a 2013 jam was found.

**Three experiments**, kept in `results/experiments/` with their validation
reports and, for the blocked runs, `sfincs.thd` (the dam) and `sfincs.drn` (the
gate):

- **Run A** (`april_2013_riverfix`): the corrected river inputs, no blockage. Its
  verdicts and every scored value match the new baseline's; the tables differ in
  one cell (Uostadvaris whole-period RMSE 0.12 vs 0.11 m) and the A2a crossing by
  10 min (16:50 vs 17:00).
- **Run B** (`april_2013_iceB`): Run A plus a thin dam across the Atmata 4.4 km
  below Rusnė, at (333087, 6136621) EPSG:3346, with one SFINCS type-5 timed gate in
  it — 200 m wide, sill −4.0 m, n 0.03, closed from the start, opened at 18 Apr
  12:00 over 1 day.
- **Experiment 3** (`april_2013_iceC`): the same dam with two 100 m gates, both
  closing on 12 Apr over 1 day, one released on 18 Apr and the other on 21 Apr.

| | observed | Run A (no blockage) | Run B (one release, 18 Apr) | Experiment 3 (releases 18 + 21 Apr) |
| --- | --- | --- | --- | --- |
| A2a +0.20 m crossing at Uostadvaris | 19 Apr 08:00 | 15 Apr 16:50, −87 h, not met | 18 Apr 13:10, **−19 h, met** | 18 Apr 03:10, −29 h, not met |
| A6a Rusnė rise | 1.53 m | 1.33 m, −0.20 m, not met | 1.23 m, −0.30 m, not met | 1.55 m, **+0.03 m, met** |
| A6b Rusnė crest | 20–23 Apr plateau | 21 Apr, met | 18 Apr, not met | 17 Apr, not met |
| Uostadvaris bias, scoring window (r) | — | +0.09 m (0.90) | **+0.02 m (0.94)** | +0.03 m (0.92) |
| A2b Uostadvaris crest | 22–24 Apr plateau | 25 Apr 00:10, not met | 25 Apr 00:20, not met | 25 Apr 00:20, not met |
| flooded area, delta window | — | 63.5 km² | 84.5 km² | 81.3 km² |

- **Run A** is the new baseline. Levels improve (A1 +0.07 m, A3 +0.02 m,
  Uostadvaris bias +0.09 m) but the timing does not (A2a −87 h), and Rusnė now
  rises too little (1.33 m vs 1.53 m).
- **Run B** meets A2a and gives Uostadvaris the observed flat-then-jump shape
  (bias +0.02 m, r 0.94). But Rusnė rises too early behind the dam and falls after
  the release: A6a −0.30 m, crest on 18 Apr.
- **Experiment 3** gets Rusnė's rise right (1.55 m vs 1.53 m) but peaks too early
  (17 Apr) and too sharply, and A2a is −29 h.

None of the three moves A2b: Uostadvaris still crests on 25 Apr.

**Conclusion.** The early delta fill (A2a) and Rusnė's missing rise (A6a) are the
signature of an unmodelled ice jam on the lower Atmata that built up gradually and
gave way over ~18–22 April. Neither input correction fixes them, and only a
blockage reproduces both the Rusnė and the Uostadvaris signatures.

**A2b is not explained by the jam.** No experiment moves the Uostadvaris crest
(25 Apr 00:10–00:20 in every run). It sits on the sea boundary's crest instead —
`inputs/april_2013/forcing_summary.txt`: "crest peak 0.16 m at 2013-04-25 01:00",
19 h after the Klaipėda gauge's observed peak (24 Apr 06:00). Between two daily
06:00 readings the fitted boundary keeps GTSM's shape, so a sea crest GTSM places
late would carry the delta crest with it. That is a lead, not a result: it is
untested, and hourly Klaipėda data for April 2013 would settle it. That
makes A2a and A6a a limitation of what the model is given, not a defect in it. **The jam
is not built into the published model**: there is no observation of when it formed
or released, and fitting a gate's timing to one gauge would be curve-fitting. The
experiments are kept as the evidence.

### Two data fixes behind these numbers

Both landed on 2026-09-17, after the geometry work below, and both change what
the model is built from rather than how it computes.

**The Smalininkai discharge block was re-ingested.** `curonian_db.gpkg`'s
source_id 167 (Jan–Jun 2013) came from an older extraction,
`smalininkai 2013 01-06.xls`, and 124 of its 181 days differed from LHMT's
current published series by up to 142 m³/s; the block mean moved 701.7 →
683.4 m³/s. Checking the neighbours is what made it worth doing: block 168
(Jul–Dec 2013), where Xaver lives, already agreed with LHMT **exactly**, while
blocks 166 and 169 differ as 167 did. So 168 is the outlier that matches, not
167 the outlier that does not — this database's Smalininkai series generally
predates the API's. Only 167 was refreshed, so a step may remain at the block
boundaries; that is recorded in the database's own `source` row and in
`tests/test_forcing_provenance.py`. April's forcing changed by −17 to −0.2 m³/s
across 168 hours, all in the 5–11 April spin-up, with the Smalininkai crest
untouched at 2150 m³/s (1926 m³/s at Rusnė since the river-input corrections).
Xaver's forcing did not change at all.

**Uostadvaris moved onto its gauge** — see *Station positions* below. These two,
plus the two geometry fixes below (the strait centreline and the distributary beds),
are the four changes that explain every number that differed from the 2026-09-16 run
by 2026-09-17. The fifth, the fitted sea boundary of 2026-09-28 (see "Sea boundary:
fitted to the daily Klaipeda readings"), and the sixth, the river-input corrections
re-run the same afternoon (commit 9ace515; see "River inputs: Nemunas share and
measured Minija"), explain every difference since.

### The first cause: a 4 km gap in the burned strait channel

The first April run failed every criterion but A5, over-topping the observed peak
by +0.78 m and shedding only ~26 % of the flood. The cause was in the shared
geometry, not in the event setup.

`inputs/channels.geojson` carries the Klaipėda strait with `rivwth = 400`,
`rivbed = −12.0`, exactly as the design spec requires (section 4 of the Xaver
design). The burn works: every centreline point that lands on an **active** cell
gets `z_zmin = −12.00 m`. But 55 of the line's 131 points — 42 % — fell on cells
excluded from the active mask, in one contiguous ~4 km stretch:

```
320503, 6168707   ACTIVE    -12.00
319568, 6171532   ACTIVE    -12.00
319324, 6172492   inactive     --    <- burn stops
319035, 6174471   inactive     --    <- the flow control section sat here
318580, 6176402   inactive     --
318270, 6177344   ACTIVE    -12.00   <- burn resumes
317239, 6181102   ACTIVE    -12.00
```

The model had a −12 m channel on both sides of a 4 km hole. `channels.geojson`
recorded `source = "fixed"` for this feature: `make_channels`' OSM fairway lookup
found nothing and fell back to three hardcoded coordinates, which interpolate a
line across the Curonian Spit. At the control row the nearest active cell was
579 m away at `z_zmin` **+7.91 m** — the dune ridge.

`prep/derive_strait.py` now derives the centreline from the model's own active
mask: a distance transform gives each water cell its clearance to the nearest
inactive cell, and a Dijkstra path from the lagoon to the boundary arc, costed as
`1/(clearance+1)`, follows mid-channel water. The result runs about 2 km east of
the old line, on the mainland side where the navigable channel is, and its burn is
continuous end to end (112 sample points, all at −12.00 m).

**A regression guard now makes this class of defect loud.** A burn onto an
inactive cell was silent — no warning, no error, the channel simply was not there
— which is how a 4 km hole survived two events and a full spec review. The test
asserts every burned centreline lies on active cells, within 1 %.

What the fix did, measured like for like (before the fitted boundary):

| | broken strait | derived strait |
| --- | --- | --- |
| lagoon shed | ~21 % | **~84 %** |
| A1 Uostadvaris peak | +0.88 m | −0.23 m |
| A2b crest | 144 h late | 18 h late |
| A3 delta-to-sea head | +0.73 m | **met**, −0.13 m |
| A4 Klaipėda RMSE | 0.176 m | 0.176 m |
| Ventė RMSE | 0.82 m | **0.04 m** |

### The second cause: the distributaries were burned to a first estimate

With the strait open, what remained of the gradient error sat between Uostadvaris
and Ventė — +0.235 m of excess head over the scoring window, against +0.024 m on
the Nida–Klaipėda link. The cause was the same class of silent defect, one layer
down.

`prep/make_channels.py` gives Atmata and Skirvytė one `rivbed` constant each
(−4.0 m and −3.0 m, "first estimates" per spec section 4). `burn_river_rect`
resolves elevation against `rivbed` by taking the deeper of the two, so a constant
*shallower* than the real channel throttles it — and that is what happened, because
the elevation it compared against was not the survey. `lagoon_bathy_50m.tif` reads
**0.00 m** along both centrelines (the depth-0 shoreline anchors of
`make_bathymetry`, interpolated together) and, being first in
`build_model.DATASETS_DEP` under `merge_method="first"`, it overrides the 5 m DEM
that does hold the channels. So the burn compared −4.0 m against 0.00 m, won, and
the surveyed bed never entered the model at all. The medians say it plainly: Atmata
was burned at −4.0 m where its thalweg runs at −4.33 m, Skirvytė at −3.0 m where its
thalweg runs at −4.79 m.

`prep/derive_channel_bed.py` now samples each centreline every 200 m and takes the
5 m DEM's thalweg — the minimum within 50 m, since a centreline wobble of a few
metres can land on a bank — floored at the channel's old constant, so a hole in the
DEM cannot make a channel shallower than it already was. The strait keeps a flat
−12.0 m: `dem_5m`'s bounds stop at y = 6,160,704, well south of it, so there is no
survey to sample. The result is `inputs/channel_bed.geojson`, 262 points:

| channel | points | burned bed range | median | deeper than the old constant |
| --- | --- | --- | --- | --- |
| atmata | 98 | −6.48 … −4.00 m | −4.33 m | 64 of 98 |
| skirvyte | 106 | −8.96 … −3.00 m | −4.79 m | 98 of 106 |
| strait | 58 | −12.00 m flat | −12.00 m | — (no DEM coverage) |

The profile is not the smooth apex-to-mouth ramp one might assume: Atmata's deepest
point sits 73 % of the way toward its mouth. A real thalweg has pools and bars, so
the test asserts "not flat" rather than a monotonic claim the data does not support.

**Handing those points to hydromt needed one more change, and the build gate caught
it.** `SubgridTableRegular.build()` calls `burn_river_rect` once per `datasets_riv`
entry *per ~10 km tile*, clipping the centrelines to the tile but passing that
entry's whole `gdf_zb` through unclipped — and `nearest()` inside it has no distance
cutoff. With one combined entry for all three channels, a tile holding only an
isolated fragment of one channel had no local zb points to prefer, so every point in
the domain was "nearest" to that fragment by default. A strait-mouth tile measured
−6.96 m where all 58 of the strait's own points are −12.00 m, and an Atmata cell
picked up the strait's −12.00 m outright. `build_model.datasets_riv()` now emits one
entry per channel, which makes the contamination impossible;
`tests/test_build_model.py` pins it with a test that fails on a combined entry and
passes on the split one. No model was run on the broken build — the gate stopped it.

What the fix did, measured like for like (before the fitted boundary):

| | constant beds | per-segment DEM beds |
| --- | --- | --- |
| A1 Uostadvaris peak | +0.16 m, not met | **+0.05 m, met** |
| A3 delta-to-sea head | +0.37 m | +0.23 m |
| A2a filling rate | 103 h early | 89 h early |
| Uostadvaris bias / RMSE (scoring window) | +0.22 / 0.25 m | **+0.10 / 0.15 m** |
| Uostadvaris − Ventė excess head | +0.235 m | **+0.112 m** |
| flooded extent | 81.0 km² | 66.5 km² |

### A ruled-out cause: the bathymetry dam at the strait

Worth recording because it was a real defect, it was fixed, and fixing it did
**not** resolve the drainage — which is what pointed the search at the channel
burn instead.

`make_bathymetry` anchors depth 0 at every vertex of the lagoon polygon's
boundary, so that the interpolator does not carry isobath depths up to the bank.
Where the polygon narrows into the strait it is only 570–770 m wide, so both banks
are zero-anchored: at (318050, 6179500), 188 of the anchors within 600 m were
depth 0.0, the nearest 12 m away. `LinearNDInterpolator` between all-zero banks
returned ~0 depth, and `elev = -np.clip(z, 0, 10)` made the bed **exactly 0.00 m**
across the neck. Being first in `build_model.DATASETS_DEP`, that bar overrode
EMODnet and the DEM.

The fix (`STRAIT_CLIP_NORTHING = 6174500`) clips the polygon this raster covers at
the measured transition from lagoon (1330–1754 m wide) to strait channel
(570–725 m), so the strait falls back to EMODnet — what the module's docstring
always said it intended. A regression test pins it.

It worked as a bathymetry change and not at all as a fix. The bar became real
varying bed (−3.8 to −0.26 m) and a formerly inactive cell became active, but a
seed-and-bisect connectivity check returned a lagoon-to-sea sill of **+0.02 m both
before and after**: the lagoon was already connected at a low threshold, so the
bar was never the binding constraint. Re-running the event changed no verdict and
moved two the wrong way. Only the channel-burn fix above moved the physics.

### Station positions

`inputs/stations.geojson` placed the Juodkrantė observation point 1.7 km west of
the lagoon shore, on the seaward side of the Curonian Spit. At that latitude the
model holds two separate water bodies — x 316550–317450 and x 318750–325950 — and
the station fell in the western one, so it reported Baltic sea level for entire
runs while the lagoon beside it stood 1.5 m higher. Nothing complained: a station
on open water is a valid station, whichever water it is on.

Fixed by using LHMT's own published coordinate for `juodkrantes-vms`
(21.121437, 55.533293, water body *Kuršių marios*), retrieved from api.meteo.lt.
It lands on a wet lagoon cell unaided and needs no offset at all — the original
1.3 km westward nudge was both unnecessary and wrong.

**Why the positions drift.** Spec section 8 takes gauge coordinates "from
`station_pts` in `curonian_db.gpkg` where present, otherwise from the place
names". `station_pts` holds water-quality stations (LTK1, LTK2, …), not
hydrological gauges — so the fallback applied to every station here. Each
position is a place name nudged onto a wet cell, not a surveyed gauge location.
Measured against LHMT's register:

| station | offset from the LHMT gauge |
| --- | --- |
| Šilutė | 430 m |
| Rusnė | 824 m |
| Klaipėda | 1844 m (model point is the harbour mouth by design) |
| Juodkrantė | 2290 m → **0 m** |
| Uostadvaris | 3583 m → **0 m** |

**Uostadvaris mattered most, and moving it changed the science.** It is a scored
gauge — A1 compares the modelled peak against it to ±0.15 m — and it sat 3.6 km
from `uostadvario-vms`. Sampling the model field at both positions before moving
anything showed that distance is worth **+0.40 m at the April peak**, nearly
three times A1's entire tolerance. The move was made safe by Xaver: C1 reads
−0.06 m at the old position and +0.09 m at the gauge, met either way. April's A1
fails at both, but the sign reverses, and A3 flips from met to not met once the
sampling error stops cancelling an over-built gradient (see *Findings* above; all
before the fitted boundary, under which A1 and A3 are both met).
Nida and Ventė have no entry in LHMT's hydrological register and could not be
checked at all.

`tests/test_make_geometries.py` now bounds every station against its LHMT
coordinate and asserts Juodkrantė lies inside the lagoon polygon. Offsets are
still permitted — they are needed, to reach wet cells — but each must be declared
with a reason and a limit, so the next one cannot drift across a spit in silence.

All four runs in `results/` were rebuilt and re-run after both stations moved, so
they carry the corrected `sfincs.obs`.

## Sensitivity: gridded ERA5 wind and pressure (April)

The same test as Xaver's, on the freshet: `prep/fetch_era5_grid.py --event
april_2013` fetches the 0.25° ERA5 grid for April–May 2013 (same box and
variables) into `inputs/april_2013/era5_grid.nc`, and two runs replace the
uniform Nida wind with it — one with wind only, one with mean sea level
pressure as well (`pavbnd = 0`, `baro = 1`, as for Xaver).
`inputs/april_2013/era5_grid_summary.txt` records the fetch: 651 hourly steps
on the 8×6-cell grid, 2013-04-04 23:00–2013-05-02 01:00; Nida-point wind speed
RMSE 0.000 m/s against the uniform run's source; peak wind 12.7 m/s at
2013-04-25 01:00 (55.50°N, 20.50°E), the same hour as `wind.csv`'s 12.2 m/s;
pressure minimum 99866 Pa at 2013-04-12 18:00.

Numbers pasted from `results/april_2013{,_gridwind,_gridwind_pressure}/validation.md`
(scoring window, 13 Apr–2 May):

| run | A1 Uostadvaris peak err m | A2a crossing dt h | A2b model crest | A3 head err m | A4 Klaipeda fit RMSE m (info) | A6a Rusnė rise err m | Nida bias m | Ventė bias m | flooded area km² | verdicts met |
|---|---|---|---|---|---|---|---|---|---|---|
| baseline (uniform wind) | +0.07 | −87 | 25 Apr 00:10 | +0.02 | 0.002 | −0.20 | −0.06 | +0.07 | 63.5 | A1, A3, A5, A6b |
| gridded wind | +0.05 | −86 | 25 Apr 00:20 | +0.01 | 0.001 | −0.20 | −0.07 | +0.06 | 60.2 | A1, A3, A5, A6b |
| gridded wind + pressure | +0.05 | −86 | 25 Apr 00:20 | +0.01 | 0.001 | −0.20 | −0.07 | +0.06 | 60.0 | A1, A3, A5, A6b |

**Gridded forcing changes no April verdict, and no score by more than 0.02 m.**
The three misses barely move across the three runs: A2a's crossing between −87
and −86 h, A2b's crest between 00:10 and 00:20 on 25 April, A6a −0.20 m in all
three. That is
the expected answer for a freshet under light winds (peak 12–13 m/s, against
Xaver's 20.6), and it is useful as a negative result: wind spatial structure, and
pressure on top of it, can be struck off as causes of the April misses. What
remains is what "Results: April 2013" locates — the delta filling early and
Rusnė rising too little, the signature of an unmodelled ice jam — with Klaipėda's
bias +0.00 m in every variant, since the boundary is fitted to its readings. The
only material change is flooded area (63.5 km² → 60.2 and 60.0 km²), the same
direction as Xaver's gridded runs but smaller, consistent with a weaker wind over
the delta. The earlier versions of these runs gave the same picture on the wind
(no verdict changed): before the river-input corrections 73.3 → 70.2 and 70.0 km²
with A6a met in all three, and on the static offset with A3 and A4 failing in all
three.

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
`build_model.py` will run:

- `inputs/lagoon_bathy_50m.tif` -- `prep.make_bathymetry` (`*.tif` is ignored)
- `inputs/xaver_2013/era5_grid.nc` and `inputs/xaver_2013/era5_raw.nc` --
  `prep.fetch_era5_grid`, needed only for `--wind grid` (`*.nc` is ignored)

`prep.fetch_gtsm`'s CDS download (`inputs/xaver_2013/gtsm.zip` and the directory
it extracts to, `inputs/xaver_2013/gtsm/`) is also ignored, but its *derived*
product `inputs/xaver_2013/gtsm_klaipeda.csv` is committed -- so a clean checkout does not need
`~/.cdsapirc` unless the boundary is being rebuilt from scratch. Everything else
under `inputs/` is committed.

Build and run, from this folder inside the `hydromt-sfincs` env:

    micromamba run -n hydromt-sfincs python -m prep.make_bathymetry
    micromamba run -n hydromt-sfincs python -m prep.make_channels
    micromamba run -n hydromt-sfincs python -m prep.make_geometries
    micromamba run -n hydromt-sfincs python -m prep.fetch_gtsm
    micromamba run -n hydromt-sfincs python -m prep.make_forcing --event xaver_2013
    micromamba run -n hydromt-sfincs python build_model.py
    ../run_sfincs.sh runs/xaver_2013 16
    micromamba run -n hydromt-sfincs python validate.py
    micromamba run -n hydromt-sfincs python -m prep.export_map_cache --run xaver_2013

What `pytest tests` proves at each level:

- `micromamba run -n hydromt-sfincs python -m pytest tests -q` — everything,
  on a machine with the raw sources above mounted. Two `integration` tests
  check for their own prerequisite first and skip silently
  (`pytest.skip(...)`) rather than failing a checkout that hasn't built the
  model yet or fetched GTSM yet: `test_built_model_passes_checks` (needs
  `runs/xaver_2013/sfincs.inp`) and `test_real_gtsm_csv_covers_the_event`
  (needs `inputs/xaver_2013/gtsm_klaipeda.csv`). The other `integration` tests read the
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
