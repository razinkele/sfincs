# Curonian Lagoon SFINCS model

Whole-lagoon compound-flood model, hindcasting two 2013 events on the same grid,
bathymetry and channels. Storm Xaver (28 Nov – 11 Dec 2013) is a Baltic surge that
pushes water into the lagoon through the Klaipeda strait; all three of its forcing
variants pass their success criteria (see "Results: Xaver 2013" below). The April
2013 Nemunas freshet (5 Apr – 2 May 2013) is the opposite driver — a slow, large
river inflow that has to leave through the same strait — and **the hindcast is a
negative result**: four of its six success criteria are not met, and the model
builds about half again the observed water-surface slope from the delta to the sea.
Most of that error turns out not to be in the lagoon at all, but in the sea boundary
it drains to (see "Results: April 2013" below).
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

    micromamba run -n hydromt-sfincs python -m prep.make_forcing --event april_2013
    micromamba run -n hydromt-sfincs python build_model.py --event april_2013
    ../run_sfincs.sh runs/april_2013 16
    micromamba run -n hydromt-sfincs python validate.py --event april_2013

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

## Results: Xaver 2013

> **Re-run three times on 2026-09-17**, each time after the April hindcast exposed
> a defect in the shared geometry: first a bathymetry bar at datum across the
> strait and a 4 km gap in the burned strait channel; then the Uostadvaris
> observation point, 3.6 km from its LHMT gauge; then the Nemunas distributaries
> burned to a first-estimate constant instead of their surveyed bed. All are
> described under **Results: April 2013**. Xaver's *forcing* is unchanged
> throughout: its Jul–Dec 2013 Smalininkai block agrees with LHMT exactly, so no
> discharge fix touched it.
> **C1–C4 remain met in all three variants**, so the published Xaver claim does
> not depend on any of the broken geometry; the surge pushes water *into* the
> lagoon, which is far less sensitive to outflow capacity than a freshet. The
> strait fixes improved the numbers sharply — Nida's and Ventė's whole-period
> peak timing moved from −67 h and −60 h to +2 h, C2 went from "met (marginal)"
> to a clean "met" in every variant, and at the corrected station Uostadvaris
> reaches RMSE 0.04–0.09 m with r up to 0.96. The distributary beds, the last
> change, moved only the delta and only slightly: C1's error went from +0.09 to
> +0.07 m in the baseline and from +0.01 to −0.01 m with gridded wind
> (and likewise +0.01 to −0.01 m with pressure), the 8 Dec 06:00 Uostadvaris miss widened by
> 0.02 m, and flooded area fell 1–2 km². The figures below are the final re-run.

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
| Nida | 26 | -0.01 | 0.08 | 0.86 | -0.01 | +2 |
| Vente | 26 | +0.05 | 0.10 | 0.77 | +0.08 | +2 |
| Uostadvaris | 13 | -0.01 | 0.06 | 0.91 | +0.07 | +0 |

Storm window: 2013-12-05 00:00 to 2013-12-09 00:00

| station | n | bias m | RMSE m | r | peak err m | peak dt h |
|---|---|---|---|---|---|---|
| Klaipeda | 4 | -0.03 | 0.12 | 0.73 | +0.13 | +10 |
| Nida | 8 | -0.08 | 0.13 | 0.78 | -0.04 | +0 |
| Vente | 8 | +0.01 | 0.12 | 0.71 | +0.07 | -67 |
| Uostadvaris | 4 | -0.03 | 0.09 | 0.90 | +0.07 | +0 |

Flooded land in the delta window (depth > 5 cm, ground > 0 m): **155.6 km²**

### Success criteria (spec section 9)
- C1 Uostadvaris peak [2013-12-05 00:00 to 2013-12-09 00:00]: **met** -- model peak 2013-12-06 06:20, peak err +0.07 m, dt +0.3 h (threshold: peak err within +/-0.15 m and |dt| <= 6 h)
- C2 Nida 8 Dec rise [2013-12-07 06:00 to 2013-12-08 18:00]: **met** -- model 0.39 m -> 0.80 m vs gauge 0.84 m, err -0.04 m, rise reproduced (threshold: err within +/-0.15 m (<=0.10 m for a clean 'met'), rise reproduced in sign)
- C3 Klaipeda RMSE [2013-12-05 00:00 to 2013-12-09 00:00]: **met** -- storm RMSE 0.12 m (whole-period RMSE 0.08 m) (threshold: storm-window RMSE <= 0.15 m)
- C4 Silute uplands [delta window (325000, 6105000, 360000, 6145000)]: **met** -- 0.00% of land with ground > 3 m flooded (threshold: < 1 % flooded)
- Info: Uostadvaris 8 Dec 06:00 [2013-12-08 06:00]: **info** -- model 0.72 m vs gauge 0.83 m, err -0.11 m (threshold: n/a (context only))
- Info: Nida 8 Dec 06:00 [2013-12-08 06:00]: **info** -- model 0.60 m vs gauge 0.74 m, err -0.14 m (threshold: n/a (context only))

Forcing as run (`inputs/xaver_2013/forcing_summary.txt`): GTSM boundary offset +0.092 m
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
  FINDING against the 12 h check tolerance in `inputs/xaver_2013/forcing_summary.txt`,
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
- Uostadvaris peak: model peak at 06:20 on 6 Dec against the gauge's 0.92 m at
  06:00 — peak error +0.09 m at +0.3 h, inside the ±0.15 m / ±6 h target
  (C1: met). Sampled at the gauge's own coordinate since 2026-09-17; the
  whole-period bias there is +0.01 m at RMSE 0.06 m, r 0.92.
- Nida delayed rise: the model rises from 0.39 m to 0.80 m across 7–8 December
  against the gauge's peak of 0.84 m, a miss of −0.04 m with the rise reproduced
  in sign — a clean C2 "met". Before the geometry fixes the same comparison read
  0.46 m → 0.71 m for a −0.13 m miss, which passed only marginally. The
  whole-period peak error is −0.01 m at +2 h, where it was −0.07 m at −67 h: the
  old figure was the gap between two different events (the model's own
  gale-driven peak on 5–6 December and the gauge's on the 8th), and that
  ambiguity is gone. Nida, Juodkrante, Rusne and Silute all had to be moved
  0.2–1.2 km into wet cells to get a usable point series (see Run log).
- The second rise is missed at both gauges, not just Nida: at 8 Dec 06:00
  the model is −0.09 m low at Uostadvaris (0.74 m vs gauge 0.83 m) and
  −0.14 m low at Nida (0.60 m vs gauge 0.74 m) — almost the same miss at two
  gauges roughly 60 km apart. That similarity is evidence the miss is
  systematic rather than an artefact of moving the Nida station off its
  spec position, and at the time this was written it was read as pointing
  at missing spatial structure in the wind field. It does not: the gridded
  ERA5 wind sensitivity run (see "Sensitivity: gridded ERA5 wind and
  pressure" below) reduced these two errors only from −0.09/−0.14 m to
  −0.08/−0.11 m, so uniform wind does not explain this miss and the sea
  boundary (its timing and high-frequency content, discussed above) is the
  next target — see the reordered Assumptions to revisit below.
- Vente: the table's peak error (+0.08 m at +2 h) is a window-max-to-
  window-max comparison, 60 h apart. At matching 06:00 readings on 6 Dec the
  model overshoots the setup peak by about 0.35 m (0.95 m modelled vs
  0.60 m gauge) and tracks the gauge well afterwards; RMSE 0.12 m overall.
- Flooded area: 157.3 km² of land floods in the delta window (depth > 5 cm,
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
- Assumptions to revisit, reordered after the gridded-wind sensitivity run
  below: (1) the GTSM boundary now ranks first — its peak lands 25 h after
  the wind peak and the Klaipeda/Uostadvaris gauge peaks, it carries
  high-frequency energy the once-daily gauge cannot confirm, and it is the
  remaining candidate for the systematic 8 Dec 06:00 miss now that wind has
  been tested and largely ruled out (next item); (2) wind spatial structure
  — originally ranked first from the Vente setup overshoot, the Nida
  peak-timing mismatch, and the 8 Dec 06:00 miss (see above), but testing it
  directly (see "Sensitivity: gridded ERA5 wind and pressure") narrowed the
  Vente overshoot (+0.07 m → +0.04 m) and cut flooded area by about 17%
  while leaving the 8 Dec 06:00 miss almost unchanged (−0.09/−0.14 m →
  −0.08/−0.11 m), so a uniform vs. gridded wind field is not the main driver
  of that particular miss; (3) the 500 cm gauge-zero assumption looks right
  as it stands — bias is within ±6 cm at all four gauges; (4) channel
  dimensions and the Minija constant discharge — this event gives no
  evidence either way.

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

| run | Vente storm peak err m | Uostadvaris peak err m | Uostadvaris peak dt h | Nida C2 err m (verdict) | Uostadvaris 8 Dec 06:00 err m | Nida 8 Dec 06:00 err m | Klaipeda storm RMSE m | flooded area km² | C1 | C2 | C3 | C4 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| baseline (uniform wind) | +0.07 | +0.07 | +0.3 | -0.04 (met) | -0.11 | -0.14 | 0.12 | 155.6 | met | met | met | met |
| gridded wind | +0.04 | -0.01 | +0.2 | -0.05 (met) | -0.10 | -0.11 | 0.12 | 128.8 | met | met | met | met |
| gridded wind + pressure | +0.03 | -0.01 | +0.2 | -0.06 (met) | -0.10 | -0.12 | 0.12 | 128.3 | met | met | met | met |

Full validation output: `results/xaver_2013_gridwind/validation.md`,
`results/xaver_2013_gridwind_pressure/validation.md`, and each run's own
`validation_timeseries.png`/`flood_extent_delta.png` in the same two
`results/` subfolders.

### Interpretation

All figures here are from the final 2026-09-17 re-run on the corrected geometry
(strait, stations and distributary beds); the sensitivity conclusion is unchanged
from the original comparison, but the baseline it is measured against is much
closer to the gauges.

The Ventė storm-window overshoot narrows with gridded wind (+0.07 m → +0.04 m)
and stays narrow with pressure added (+0.03 m) — the same direction the original
comparison found, on a baseline that has itself improved from +0.19 m.

The systematic 8 December second-rise underestimate is still present and still
largely unexplained by wind. The geometry fix took about a third off it
(Uostadvaris −0.23 m → −0.11 m, Nida −0.22 m → −0.14 m in the baseline), and
gridded forcing then shaves a further 0.01–0.03 m (−0.10 m and −0.11 m). So
replacing the uniform wind with the real ERA5 field still does not account for
that miss, and the GTSM-boundary timing item remains the more likely candidate.

Klaipėda storm RMSE is 0.12 m in all three runs, unchanged to two decimals. The
Nida C2 rise error is −0.04 to −0.06 m and is now a **clean** "met" in every
variant, where all three were previously "met (marginal)" at −0.13 m — the
clearest single improvement the geometry fix produced for this event. Adding
pressure on top of gridded wind still moves every number by at most 0.02 m or
0.5 km², consistent with `pavbnd = 0` keeping the pressure effect local.

The peak-dt tie-break caveat still applies, though it now bites in one place
rather than several: Ventė's storm-window peak dt reads −67 h in the baseline
while both gridded variants read +0 h, because the window holds two maxima of
comparable height (the model's gale-driven peak on 5–6 December and the gauge's
later peak on 8 December) and which one `skill()`'s tie-break lands on shifts
with small changes in the series. Nida, which previously swung between −67 h and
+0 h across variants, now reads +0 h in all three. Read Ventė's figure as an
artefact of the tie-break, not a timing error.

The flooded-area drop with gridded forcing persists (155.6 km² → 128.8 and
128.3 km², about 17 %), consistent with the ERA5 grid's wind over the delta being
weaker or differently oriented than the Nida point value the baseline applies
everywhere. That mechanism was not isolated further and should be read as
plausible, not confirmed.

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
| Klaipeda | 27 | -0.12 | 0.15 | 0.73 | -0.15 | +19 |
| Nida | 54 | -0.12 | 0.12 | 0.99 | -0.15 | +12 |
| Vente | 54 | +0.01 | 0.04 | 0.97 | -0.01 | -6 |
| Uostadvaris | 27 | +0.09 | 0.13 | 0.93 | +0.05 | +18 |

Scoring window: 2013-04-13 00:00 to 2013-05-02 00:00

| station | n | bias m | RMSE m | r | peak err m | peak dt h |
|---|---|---|---|---|---|---|
| Klaipeda | 19 | -0.16 | 0.18 | 0.77 | -0.15 | +19 |
| Nida | 38 | -0.13 | 0.13 | 0.99 | -0.15 | +12 |
| Vente | 38 | -0.00 | 0.04 | 0.96 | -0.01 | -6 |
| Uostadvaris | 19 | +0.10 | 0.15 | 0.86 | +0.05 | +18 |

Flooded land in the delta window (depth > 5 cm, ground > 0 m): **66.5 km²**

### Success criteria (spec section 9)
- A1 Uostadvaris peak [2013-04-13 00:00 to 2013-05-02 00:00]: **met** -- model peak 0.59 m vs gauge 0.54 m, err +0.05 m (threshold: peak err within +/-0.15 m)
- A2a filling rate [first crossing of +0.20 m]: **not met** -- model 2013-04-15 15:20 vs gauge (interpolated) 2013-04-19 08:00, dt -89 h (threshold: within +/-24 h of the observed crossing)
- A2b crest timing [2013-04-21 18:00 to 2013-04-24 18:00]: **not met** -- model peak 2013-04-25 00:10; observed plateau 22 Apr-24 Apr (threshold: model peak inside the observed plateau +/-12 h)
- A3 delta-to-sea head [2013-04-22 00:00 to 2013-04-26 00:00]: **not met** -- model 0.71 m vs gauge 0.48 m over 5 readings, err +0.23 m (threshold: mean head within +/-0.15 m)
- A4 Klaipeda control [2013-04-13 00:00 to 2013-05-02 00:00]: **not met** -- RMSE 0.176 m against an observed sd of 0.089 m (threshold: RMSE <= 0.085 m (below the observed sd of 0.089 m: a flat series fails))
- A5 Silute uplands [whole run, delta window (325000, 6105000, 360000, 6145000)]: **met** -- 0.00% of land with ground > 3 m flooded (threshold: < 1 % flooded)

Forcing as run (`inputs/april_2013/forcing_summary.txt`): GTSM boundary offset
−0.212 m (calm window 5–11 Apr 2013), boundary level −0.30 m at the start
rising to a crest of −0.01 m at 2013-04-25 01:00; wind peak 12.2 m/s at
2013-04-25 01:00 from 265°; Nemunas discharge 410–2150 m³/s, Minija held
constant at 83.0 m³/s. The GTSM crest lands 19 h from the Klaipeda 06:00 gauge
peak (0.15 m at 2013-04-24 06:00) — past the 12 h check tolerance, recorded as
a FINDING per spec and not treated as a blocker (with only twice-daily gauge
readings, 19 h is inside the observation's own resolution).

### Findings

- **Four of the six criteria are not met** — A2a and A2b on timing, A3 on the
  delta-to-sea head, A4 on the sea boundary. A1 and A5 are met. The run itself is
  not in question: `sfincs.inp`'s `tstart`/`tstop` match the event, `sfincs_his.nc`
  is finite throughout, and the solver log is clean.
- **The model reproduces the freshet closely mid-lagoon, and fills the delta too
  early rather than too high.** Over the scoring window Ventė has a bias of
  −0.00 m, RMSE 0.04 m, r = 0.96; Nida −0.13 m, RMSE 0.13 m, r = 0.99;
  Uostadvaris, in the delta, +0.10 m, RMSE 0.15 m, peak error +0.05 m — inside
  A1's ±0.15 m. Before the distributaries were given their surveyed bed (see *The
  second cause* below) Uostadvaris read +0.22 m, RMSE 0.25 m and peak error
  +0.16 m, and A1 failed.
- **A3's excess sits at the sea end, not in the delta.** A3 scores the mean
  Uostadvaris − Klaipėda head, so its error is exactly the difference of those two
  stations' biases. Over A3's crest window, on the five readings all four gauges
  share:

  | station | model − gauge | sd |
  | --- | --- | --- |
  | Klaipėda (the sea) | **−0.209 m** | 0.053 m |
  | Nida | −0.134 m | 0.008 m |
  | Ventė | −0.041 m | 0.077 m |
  | Uostadvaris (the delta) | **+0.024 m** | 0.016 m |

  A3's +0.233 m is +0.024 − (−0.209) to the millimetre. At the crest the model
  stands within 2.4 cm of the delta gauge; what fails A3 is Klaipėda sitting 21 cm
  low — **A4's static boundary bias correction**, the one error that was identified
  before the first run. The bias decays monotonically inland from the strait, which
  is what a sea boundary held too low does to a lagoon: it pulls hardest where the
  connection is and not at all where the river sets the level. Nida's near-constant
  −0.134 m (sd 0.008 m over the crest, 0.026 m over the whole scoring window) is a
  point on that decay, not a gauge-datum problem — the same station under Xaver has
  a whole-period bias of −0.01 m.

  Averaged over the whole scoring window rather than the crest, the delta carries
  more of the error (Uostadvaris +0.105 m against Klaipėda −0.160 m), and that share
  is what the bed fix moved: the Uostadvaris − Ventė excess head went from +0.235 m
  to **+0.112 m**. Ventė − Nida (+0.124 m) did not move with the bed fix at all, and
  Nida − Klaipėda stayed small (+0.024 → +0.029 m). Both tables come from
  `diag/head_decomposition.py`, which prints them for either event.
- **A2a is the residual.** Reaching +0.20 m at Uostadvaris 89 h early (it was 103 h)
  is what too much conveyance into the delta, or too little storage there, looks
  like on the time axis: the delta fills too soon, then arrives at the right crest.
  It improved with the bed fix and is the clearest remaining conveyance signal.
- **A3 was met until 2026-09-17, and its passing was an artefact.** It read
  −0.13 m while Uostadvaris was sampled 3.6 km down-delta of its gauge, where the
  modelled level is about 0.40 m lower. Two errors were cancelling: an over-built
  gradient and a sampling point part-way down it. With the station on its gauge
  the cancellation is gone and A3 reports the model's actual behaviour. **The
  verdict got worse and the diagnosis got better** — the earlier "the lagoon
  drains slightly too freely and fills too slowly" reading was measuring the
  wrong place.
- **A4 is unchanged at RMSE 0.176 m**, exactly as expected. It scores the sea
  boundary's static calm-window bias correction (spec section 10, limitation 5),
  which drifts ~0.16 m once the freshet develops and which none of the geometry
  or data work touched. The Klaipėda station sits ~2 km from the boundary ring
  and inherits that bias nearly 1:1. It is the one criterion whose cause was
  identified before the first run and has never moved.
- **Mass balance.** Over the 27-day run the two discharge points deliver
  3.17 × 10⁹ m³. Spread over the 1601 km² of lagoon the model actually resolves
  (`lagoon_boundary` intersected with the active mask) that is a 1.98 m rise if
  nothing drained. The area-weighted mean lagoon level goes from −0.170 m at the
  start to a peak of +0.205 m on 28 April — a rise of 0.375 m, so the model passes
  **81 % of the freshet through the strait and holds 19 %**. The observed lagoon
  peaked at 0.54 m at Uostadvaris and had receded to 0.10 m by the end, so it passed
  essentially all of it. Modelled flooded extent is 66.5 km², down from 81.0 km²
  before the bed fix. `diag/mass_balance.py` computes this, definition included.
- **Where to look next.** A3 and A4 look like one problem rather than two: 21 cm of
  A3's 23 is Klaipėda alone. Raising the sea end would lift the lagoon behind it as
  well, so how much of A3 that recovers is untested, but the boundary's static
  calm-window offset (spec section 10, limitation 5) is the single highest-value
  thing left in this model. The route to it is an hourly observed Klaipėda series,
  which `api.meteo.lt` cannot supply — see *Limitations*. What is left that is
  genuinely the delta's is A2a's 89 h, and it points at the other half of the same
  "first estimates": the burned *widths* (200 m Atmata, 150 m Skirvytė, spec
  section 4), Manning's n on the distributaries, and the storage a 100 m grid gives
  a channel a few hundred metres wide. None of those were touched here.

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
across 168 hours, all in the 5–11 April spin-up, with the crest untouched at
2150 m³/s. Xaver's forcing did not change at all.

**Uostadvaris moved onto its gauge** — see *Station positions* below. These two,
plus the two geometry fixes below (the strait centreline and the distributary beds),
are the four changes that explain every number in this section that differs from the
2026-09-16 run.

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

What the fix did, measured like for like:

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

What the fix did, measured like for like:

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
sampling error stops cancelling an over-built gradient (see *Findings* above).
Nida and Ventė have no entry in LHMT's hydrological register and could not be
checked at all.

`tests/test_make_geometries.py` now bounds every station against its LHMT
coordinate and asserts Juodkrantė lies inside the lagoon polygon. Offsets are
still permitted — they are needed, to reach wet cells — but each must be declared
with a reason and a limit, so the next one cannot drift across a spit in silence.

All four runs in `results/` were rebuilt and re-run after both stations moved, so
they carry the corrected `sfincs.obs`.

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
