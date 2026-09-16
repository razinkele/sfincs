# Curonian Lagoon SFINCS model

Whole-lagoon compound-flood model, hindcasting two 2013 events on the same grid,
bathymetry and channels. Storm Xaver (28 Nov – 11 Dec 2013) is a Baltic surge that
pushes water into the lagoon through the Klaipeda strait; all three of its forcing
variants pass their success criteria (see "Results: Xaver 2013" below). The April
2013 Nemunas freshet (5 Apr – 2 May 2013) is the opposite driver — a slow, large
river inflow that has to leave through the same strait — and **the hindcast is a
negative result**: five of its six success criteria are not met, and the mass
balance shows the model retaining roughly three-quarters of the freshet rather
than draining it (see "Results: April 2013" below).
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

Flooded land in the delta window (depth > 5 cm, ground > 0 m): **165.6 km²**

### Success criteria (spec section 9)
- C1 Uostadvaris peak [2013-12-05 00:00 to 2013-12-09 00:00]: **met** -- model peak 2013-12-06 06:20, peak err +0.08 m, dt +0.3 h (threshold: peak err within +/-0.15 m and |dt| <= 6 h)
- C2 Nida 8 Dec rise [2013-12-07 06:00 to 2013-12-08 18:00]: **met (marginal)** -- model 0.46 m -> 0.71 m vs gauge 0.84 m, err -0.13 m, rise reproduced (threshold: err within +/-0.15 m (<=0.10 m for a clean 'met'), rise reproduced in sign)
- C3 Klaipeda RMSE [2013-12-05 00:00 to 2013-12-09 00:00]: **met** -- storm RMSE 0.12 m (whole-period RMSE 0.08 m) (threshold: storm-window RMSE <= 0.15 m)
- C4 Silute uplands [delta window (325000, 6105000, 360000, 6145000)]: **met** -- 0.00% of land with ground > 3 m flooded (threshold: < 1 % flooded)
- Info: Uostadvaris 8 Dec 06:00 [2013-12-08 06:00]: **info** -- model 0.60 m vs gauge 0.83 m, err -0.23 m (threshold: n/a (context only))
- Info: Nida 8 Dec 06:00 [2013-12-08 06:00]: **info** -- model 0.52 m vs gauge 0.74 m, err -0.22 m (threshold: n/a (context only))

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
  the model is −0.23 m low at Uostadvaris (0.60 m vs gauge 0.83 m) and
  −0.22 m low at Nida (0.52 m vs gauge 0.74 m) — almost the same miss at two
  gauges roughly 60 km apart. That similarity is evidence the miss is
  systematic rather than an artefact of moving the Nida station off its
  spec position, and at the time this was written it was read as pointing
  at missing spatial structure in the wind field. It does not: the gridded
  ERA5 wind sensitivity run (see "Sensitivity: gridded ERA5 wind and
  pressure" below) reduced these two errors only from −0.23/−0.22 m to
  −0.21/−0.19 m, so uniform wind does not explain this miss and the sea
  boundary (its timing and high-frequency content, discussed above) is the
  next target — see the reordered Assumptions to revisit below.
- Vente: the table's peak error (+0.19 m at −60 h) is a window-max-to-
  window-max comparison, 60 h apart. At matching 06:00 readings on 6 Dec the
  model overshoots the setup peak by about 0.35 m (0.95 m modelled vs
  0.60 m gauge) and tracks the gauge well afterwards; RMSE 0.12 m overall.
- Flooded area: 165.6 km² of land floods in the delta window (depth > 5 cm,
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
  Vente overshoot (+0.19 m → +0.14 m) and cut flooded area by about 15%
  while leaving the 8 Dec 06:00 miss almost unchanged (−0.23/−0.22 m →
  −0.21/−0.19 m), so a uniform vs. gridded wind field is not the main driver
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
| baseline (uniform wind) | +0.19 | +0.08 | +0.3 | -0.13 (met, marginal) | -0.23 | -0.22 | 0.12 | 165.6 | met | met (marginal) | met | met |
| gridded wind | +0.14 | +0.03 | +0.2 | -0.13 (met, marginal) | -0.21 | -0.19 | 0.12 | 140.3 | met | met (marginal) | met | met |
| gridded wind + pressure | +0.16 | +0.04 | +0.2 | -0.13 (met, marginal) | -0.21 | -0.19 | 0.12 | 140.9 | met | met (marginal) | met | met |

Full validation output: `results/xaver_2013_gridwind/validation.md`,
`results/xaver_2013_gridwind_pressure/validation.md`, and each run's own
`validation_timeseries.png`/`flood_extent_delta.png` in the same two
`results/` subfolders.

### Interpretation

The Vente storm-window overshoot narrows with gridded wind (+0.19 m →
+0.14 m) and stays narrower with pressure added (+0.16 m), an improvement but
not a resolution. The systematic 8 Dec second-rise underestimate flagged in
the baseline Findings is only slightly smaller with gridded forcing
(Uostadvaris -0.23 m → -0.21 m, Nida -0.22 m → -0.19 m at both gridded
variants) — a 0.02 m improvement against a miss of more than 0.20 m, so the sign
and very nearly the size survive: replacing the uniform wind with the actual ERA5
field does not explain that miss on its own;
the GTSM-boundary timing item, now ranked first in the reordered Assumptions
list above, remains the more likely candidate. Klaipeda storm RMSE (0.12 m)
and the Nida C2 rise error (-0.13 m, met marginal) are unchanged to two
decimals across all three runs, all four success criteria still pass in every
run, and adding pressure on top of gridded wind moves every number in the
table by at most 0.02 m or 0.6 km² relative to gridded wind alone (consistent
with `pavbnd = 0` keeping the pressure effect local to the domain) — gridded
forcing is a net neutral-to-positive change here, not a regression. Nida's
storm-window peak-dt swings widely (-67 h baseline, +0 h gridded wind, -68 h
gridded wind + pressure, all in each run's own `validation.md`) because the
window contains two separate maxima of comparable height (the model's own
gale-driven peak on 5-6 Dec and the gauge's later peak on 8 Dec) and which one
the tie-break in `skill()` lands on shifts with small changes in the series,
not with a real change in timing — this figure is not informative here (see
`validate.py`'s own note on peak-tie handling). The flooded-area drop
(165.6 km² → ~140 km² with either gridded variant, about 15%) is consistent
with the ERA5 grid's wind over the delta being weaker or differently oriented
than the Nida point value used everywhere in the baseline, but that mechanism
was not isolated further and should be read as plausible, not confirmed.

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
| Nida | 54 | +0.43 | 0.55 | 0.95 | +0.94 | +78 |
| Vente | 54 | +0.56 | 0.66 | 0.95 | +1.03 | +120 |
| Uostadvaris | 27 | +0.36 | 0.47 | 0.90 | +0.78 | +144 |

Scoring window: 2013-04-13 00:00 to 2013-05-02 00:00

| station | n | bias m | RMSE m | r | peak err m | peak dt h |
|---|---|---|---|---|---|---|
| Klaipeda | 19 | -0.16 | 0.18 | 0.77 | -0.15 | +19 |
| Nida | 38 | +0.60 | 0.66 | 0.96 | +0.93 | +72 |
| Vente | 38 | +0.73 | 0.78 | 0.94 | +1.03 | +120 |
| Uostadvaris | 19 | +0.48 | 0.55 | 0.81 | +0.78 | +144 |

Flooded land in the delta window (depth > 5 cm, ground > 0 m): **166.0 km²**

### Success criteria (spec section 9)
- A1 Uostadvaris peak [2013-04-13 00:00 to 2013-05-02 00:00]: **not met** -- model peak 1.32 m vs gauge 0.54 m, err +0.78 m (threshold: peak err within +/-0.15 m)
- A2a filling rate [first crossing of +0.20 m]: **not met** -- model 2013-04-15 14:10 vs gauge (interpolated) 2013-04-19 08:00, dt -90 h (threshold: within +/-24 h of the observed crossing)
- A2b crest timing [2013-04-21 18:00 to 2013-04-24 18:00]: **not met** -- model peak 2013-04-30 05:30; observed plateau 22 Apr-24 Apr (threshold: model peak inside the observed plateau +/-12 h)
- A3 delta-to-sea head [2013-04-22 00:00 to 2013-04-26 00:00]: **not met** -- model 1.16 m vs gauge 0.48 m over 5 readings, err +0.68 m (threshold: mean head within +/-0.15 m)
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

- **Five of the six criteria are not met; only A5 (Silute uplands) is met.**
  The run itself is not in question: `sfincs.inp`'s `tstart`/`tstop` match the
  event exactly, `sfincs_his.nc` is finite everywhere over the full run with no
  `error`/`nan` in the solver log (Run log above), and per-station ranges are
  physically plausible for a river-delta freshet. The failures below are the
  scored outcome of a valid run, not a symptom of a broken one.
- A4 (Klaipeda control) is the criterion the spec itself flagged in advance as
  "the criterion most likely to fail for reasons outside the lagoon" (spec
  section 10, limitation 5), and it did: RMSE 0.176 m, scoring-window bias
  −0.16 m, against a 0.085 m threshold. The sea boundary is bias-corrected
  once, over the calm window 5–11 April; that static offset does not hold
  once the freshet raises the real Klaipeda gauge, and the model's Klaipeda
  station sits only ~2 km inside the boundary ring, so it inherits the
  boundary's own drift almost 1:1.
- A1 and A3 confirm the *direction* that mechanism predicts — too high — but
  not its *size*. A common ~0.16 m boundary drift could inflate the
  Uostadvaris-minus-Klaipeda head by at most about 0.16 m; A3's actual error
  is +0.68 m (model 1.16 m vs gauge 0.48 m), and A1's peak error is +0.78 m
  (model 1.32 m vs gauge 0.54 m) at Uostadvaris itself, 42 km inside the ring
  where Klaipeda is 2 km. The boundary bias is real and measured, but it is
  not the dominant error.
- **The dominant error is a mass balance: the modelled lagoon does not
  drain.** Integrating the Nemunas + Minija discharge series
  (`inputs/april_2013/dis.csv`) over the whole run (5 Apr–2 May) gives a
  total inflow of about 3.18×10⁹ m³:

  ```
  total inflow over the run           3.18e9 m³
    ÷ lagoon area (1584 km², nominal) =  2.01 m   rise if nothing drained
  modelled rise (−0.17 → 1.32 m)          1.49 m   → only ~26 % of the inflow left the lagoon
  observed (Uostadvaris)                  peaked 0.54 m, receded to 0.10 m by 2 May
  ```

  Spread over the lagoon's nominal 1584 km² surface (not a model-derived
  quantity), that inflow would raise the whole lagoon about 2.01 m if none of
  it drained. The model's own Uostadvaris peak rises 1.49 m over the run
  (from `zsini = -0.17` m to its modelled 1.32 m peak) — so on this simple
  balance only about a quarter of the freshet's volume left through the
  strait; the rest stayed in the lagoon. The real lagoon did the opposite:
  Uostadvaris peaked at 0.54 m and had receded to 0.10 m by 2 May, passing
  essentially all of it through.
- Two signatures corroborate the mass-balance arithmetic independently.
  (1) By the end of the run Uostadvaris, Nida and Vente sit within 0.003 m of
  each other — 1.314 m, 1.317 m and 1.314 m respectively at 2013-05-02 00:00
  (`sfincs_his.nc`) — even though the observed event holds an 0.18 m gradient
  across exactly these three gauges at their own peaks (Uostadvaris 0.54 m,
  Nida 0.36 m, Ventė 0.29 m; spec section 2). A sustained river inflow should
  leave a head from the delta down to the strait; the model erases it instead
  of reproducing it. (2) The peak lag grows with distance from the strait —
  Nida +72 h, Vente +120 h, Uostadvaris +144 h (scoring-window table above) —
  consistent with water working its way in faster than it can work its way
  back out.
- A third, unresolved observation sits alongside those two rather than inside
  them: Juodkrante, a model output point roughly midway between Klaipeda and
  Nida (moved into a wet cell during the Xaver build; see Run log), tracks
  close to sea level all the way through the run — start −0.17 m, a brief
  peak of only +0.07 m on 27 April, end −0.19 m — while Nida, further south
  on the same spit, rises to +1.32 m. Essentially all of the modelled rise
  happens south of Juodkrante rather than building gradually across the
  northern lagoon; the model's internal gradient is a step near Juodkrante,
  not the smooth basin-wide picture the delta-gauge convergence above might
  suggest on its own. Whether that step is a real conveyance restriction in
  the narrow northern lagoon or a Juodkrante siting artefact is not resolved
  here.
- Correlation is 0.81–0.96 at the three lagoon gauges over the scoring window
  (Klaipeda 0.77) — the model reproduces the *shape* of the event, in
  particular the rise, closely, and gets its *throughput* wrong: A2a shows
  the model crossing +0.20 m 90 h too early (it fills fast), while A2b shows
  its actual peak arriving 144 h too late, well outside the observed
  22–24 April plateau (it does not turn over with the gauges once full).
- The excess is not confined to the scored window. 5–13 April is unscored
  spin-up — the delta gauge itself is ice-affected through 12 April (spec
  section 3), so the modelled and observed series are not directly
  comparable there — but within that window the modelled Uostadvaris level
  rises from −0.17 m at `tstart` to about +0.14 m by 13 April (`sfincs_his.nc`;
  the daily mean climbs on every one of the eight days, not a single noisy
  swing), while Nemunas discharge in the forcing is still at or near its
  ~410–532 m³/s pre-event baseline (spec section 2). A lagoon drifting away
  from its prescribed initial level under near-baseline inflow is consistent
  with the same outflow restriction identified above, though not established
  by this alone.
- **Interpretation.** Storm Xaver is a 13-day surge that pushes water into
  the lagoon; it never tested the strait's capacity to let water back out —
  that conveyance was assumed in the shared geometry, not validated by either
  event run so far. The April freshet is the opposite driver, a large,
  sustained river inflow that the lagoon must pass back out to the sea, and
  the model cannot pass a sustained one through: it fills at close to the
  right rate and shape, then holds most of what it filled with.
- This mass balance identifies *that* the lagoon does not drain; it does not
  by itself identify *which* model ingredient is responsible. Three
  candidates are named here, not concluded from this run: the sea boundary's
  static calm-window bias correction (spec section 10, limitation 5) accounts
  for the −0.16 m measured at Klaipeda but not the +0.78 m peak error 42 km
  inside the lagoon; the Klaipeda strait, hand-digitised at roughly 400 m wide
  (`../docs/superpowers/specs/2026-09-04-curonian-lagoon-xaver-model-design.md`,
  section 4) but represented on this model's 100 m grid, may under-resolve
  the cross-section that actually carries the outflow; and the Juodkrante
  step above may point at the same conveyance problem sitting further north,
  in the narrow lagoon rather than the strait itself. None of the three is
  tested by this run; all three remain open items, unranked.

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
