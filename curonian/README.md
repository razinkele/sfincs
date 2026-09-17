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

> **Re-run 2026-09-17.** All three variants were rebuilt and re-run after two
> defects were found in the shared geometry — a bathymetry bar at datum across
> the strait, and a 4 km gap in the burned strait channel where its centreline
> ran outside the active mask. Both are described under **Results: April 2013**.
> **C1–C4 remain met in all three variants**, so the published Xaver claim does
> not depend on the broken geometry; the surge pushes water *into* the lagoon,
> which is far less sensitive to outflow capacity than a freshet. The numbers
> did improve, in one respect sharply: Nida's and Ventė's whole-period peak
> timing moves from −67 h and −60 h to +2 h, and C2 goes from "met (marginal)"
> to a clean "met" in every variant. The figures below are the re-run.

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
| Uostadvaris | 13 | -0.06 | 0.08 | 0.91 | -0.06 | -0 |

Storm window: 2013-12-05 00:00 to 2013-12-09 00:00

| station | n | bias m | RMSE m | r | peak err m | peak dt h |
|---|---|---|---|---|---|---|
| Klaipeda | 4 | -0.03 | 0.12 | 0.73 | +0.13 | +10 |
| Nida | 8 | -0.08 | 0.13 | 0.78 | -0.04 | +0 |
| Vente | 8 | +0.01 | 0.12 | 0.71 | +0.07 | -67 |
| Uostadvaris | 4 | -0.11 | 0.12 | 0.92 | -0.06 | -0 |

Flooded land in the delta window (depth > 5 cm, ground > 0 m): **157.3 km²**

### Success criteria (spec section 9)
- C1 Uostadvaris peak [2013-12-05 00:00 to 2013-12-09 00:00]: **met** -- model peak 2013-12-06 05:50, peak err -0.06 m, dt -0.2 h (threshold: peak err within +/-0.15 m and |dt| <= 6 h)
- C2 Nida 8 Dec rise [2013-12-07 06:00 to 2013-12-08 18:00]: **met** -- model 0.39 m -> 0.80 m vs gauge 0.84 m, err -0.04 m, rise reproduced (threshold: err within +/-0.15 m (<=0.10 m for a clean 'met'), rise reproduced in sign)
- C3 Klaipeda RMSE [2013-12-05 00:00 to 2013-12-09 00:00]: **met** -- storm RMSE 0.12 m (whole-period RMSE 0.08 m) (threshold: storm-window RMSE <= 0.15 m)
- C4 Silute uplands [delta window (325000, 6105000, 360000, 6145000)]: **met** -- 0.00% of land with ground > 3 m flooded (threshold: < 1 % flooded)
- Info: Uostadvaris 8 Dec 06:00 [2013-12-08 06:00]: **info** -- model 0.68 m vs gauge 0.83 m, err -0.15 m (threshold: n/a (context only))
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
- Uostadvaris peak: model peak at 05:50 on 6 Dec against the gauge's 0.92 m at
  06:00 — peak error −0.06 m at −0.2 h, comfortably inside the ±0.15 m / ±6 h
  target (C1: met). Before the geometry fixes this read +0.08 m at +0.3 h; the
  sign flipped and the magnitude fell.
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
  the model is −0.15 m low at Uostadvaris (0.68 m vs gauge 0.83 m) and
  −0.14 m low at Nida (0.60 m vs gauge 0.74 m) — almost the same miss at two
  gauges roughly 60 km apart. That similarity is evidence the miss is
  systematic rather than an artefact of moving the Nida station off its
  spec position, and at the time this was written it was read as pointing
  at missing spatial structure in the wind field. It does not: the gridded
  ERA5 wind sensitivity run (see "Sensitivity: gridded ERA5 wind and
  pressure" below) reduced these two errors only from −0.15/−0.14 m to
  −0.13/−0.11 m, so uniform wind does not explain this miss and the sea
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
  while leaving the 8 Dec 06:00 miss almost unchanged (−0.15/−0.14 m →
  −0.13/−0.11 m), so a uniform vs. gridded wind field is not the main driver
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
| baseline (uniform wind) | +0.07 | -0.06 | -0.2 | -0.04 (met) | -0.15 | -0.14 | 0.12 | 157.3 | met | met | met | met |
| gridded wind | +0.04 | -0.11 | -0.3 | -0.05 (met) | -0.13 | -0.11 | 0.12 | 130.6 | met | met | met | met |
| gridded wind + pressure | +0.03 | -0.10 | -0.2 | -0.06 (met) | -0.14 | -0.12 | 0.12 | 130.1 | met | met | met | met |

Full validation output: `results/xaver_2013_gridwind/validation.md`,
`results/xaver_2013_gridwind_pressure/validation.md`, and each run's own
`validation_timeseries.png`/`flood_extent_delta.png` in the same two
`results/` subfolders.

### Interpretation

All figures here are from the 2026-09-17 re-run on the corrected geometry; the
sensitivity conclusion is unchanged from the original comparison, but the
baseline it is measured against is much closer to the gauges.

The Ventė storm-window overshoot narrows with gridded wind (+0.07 m → +0.04 m)
and stays narrow with pressure added (+0.03 m) — the same direction the original
comparison found, on a baseline that has itself improved from +0.19 m.

The systematic 8 December second-rise underestimate is still present and still
largely unexplained by wind. The geometry fix took about a third off it
(Uostadvaris −0.23 m → −0.15 m, Nida −0.22 m → −0.14 m in the baseline), and
gridded forcing then shaves a further 0.01–0.02 m (−0.13 m and −0.11 m). So
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

The flooded-area drop with gridded forcing persists (157.3 km² → 130.6 and
130.1 km², about 17 %), consistent with the ERA5 grid's wind over the delta being
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
| Nida | 54 | -0.12 | 0.13 | 0.99 | -0.15 | +12 |
| Vente | 54 | +0.01 | 0.04 | 0.97 | -0.02 | -6 |
| Uostadvaris | 27 | -0.16 | 0.21 | 0.92 | -0.23 | +18 |

Scoring window: 2013-04-13 00:00 to 2013-05-02 00:00

| station | n | bias m | RMSE m | r | peak err m | peak dt h |
|---|---|---|---|---|---|---|
| Klaipeda | 19 | -0.16 | 0.18 | 0.77 | -0.15 | +19 |
| Nida | 38 | -0.13 | 0.14 | 0.99 | -0.15 | +12 |
| Vente | 38 | -0.00 | 0.04 | 0.96 | -0.02 | -6 |
| Uostadvaris | 19 | -0.22 | 0.25 | 0.88 | -0.23 | +18 |

Flooded land in the delta window (depth > 5 cm, ground > 0 m): **81.0 km²**

### Success criteria (spec section 9)
- A1 Uostadvaris peak [2013-04-13 00:00 to 2013-05-02 00:00]: **not met** -- model peak 0.31 m vs gauge 0.54 m, err -0.23 m (threshold: peak err within +/-0.15 m)
- A2a filling rate [first crossing of +0.20 m]: **not met** -- model 2013-04-23 17:20 vs gauge (interpolated) 2013-04-19 08:00, dt +105 h (threshold: within +/-24 h of the observed crossing)
- A2b crest timing [2013-04-21 18:00 to 2013-04-24 18:00]: **not met** -- model peak 2013-04-25 00:10; observed plateau 22 Apr-24 Apr (threshold: model peak inside the observed plateau +/-12 h)
- A3 delta-to-sea head [2013-04-22 00:00 to 2013-04-26 00:00]: **met** -- model 0.35 m vs gauge 0.48 m over 5 readings, err -0.13 m (threshold: mean head within +/-0.15 m)
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

- **Two of the six criteria are met (A3, A5); four are not.** The run itself is
  not in question: `sfincs.inp`'s `tstart`/`tstop` match the event, `sfincs_his.nc`
  is finite throughout, and the solver log is clean.
- **The model now reproduces the freshet closely at two of the three lagoon
  gauges.** Over the scoring window Ventė has a bias of −0.00 m, RMSE 0.04 m and a
  peak error of −0.02 m at −6 h; Nida has bias −0.13 m, RMSE 0.14 m and r = 0.99.
  Uostadvaris, furthest up the delta, undershoots: bias −0.22 m, RMSE 0.25 m,
  peak error −0.23 m.
- **The remaining failures are a calibration problem, not a structural one.**
  A1 misses by −0.23 m against a ±0.15 m band, A2a fills 105 h late, A2b crests
  18 h past the observed plateau. All three say the same thing: the lagoon now
  drains slightly too freely and fills slightly too slowly. That is a different
  class of problem from the one this event originally exposed — see *The cause*
  below — and the levers are Manning's n in the strait, the burned bed level, and
  the boundary.
- **A4 is unchanged at RMSE 0.176 m**, exactly as expected. It scores the sea
  boundary's static calm-window bias correction (spec section 10, limitation 5),
  which drifts ~0.16 m once the freshet develops and which none of the geometry
  work touched. The Klaipėda station sits ~2 km from the boundary ring and
  inherits that bias nearly 1:1. It is the one criterion whose cause was
  identified before the first run and has not moved since.
- **Mass balance.** Total inflow over the run is 3.18 × 10⁹ m³, which spread over
  the lagoon's 1584 km² would raise it 2.01 m if nothing drained. The model now
  sheds about 84 % of that (about 76 % at the 25 April peak); the observed lagoon
  peaked at 0.54 m and receded to 0.10 m, so it passed essentially all of it. The
  model's flooded extent is 81.0 km².

### The cause: a 4 km gap in the burned strait channel

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

### Station positions, and a third defect fixed

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
| Juodkrantė | 2290 m → **0 m** after this fix |
| **Uostadvaris** | **3583 m** |

**Uostadvaris is the one that matters and is not fixed here.** It is a scored
gauge — A1 compares the model's peak against it to ±0.15 m — and the model point
sits 3.6 km from `uostadvario-vms`. In a delta carrying a freshet, water level
varies over that distance, so some part of A1's error may be a position error
rather than a model error. Moving it would change a published verdict, so it is
recorded here rather than changed unilaterally. Nida and Ventė have no entry in
LHMT's hydrological register and could not be checked at all.

`tests/test_make_geometries.py` now bounds every station against its LHMT
coordinate and asserts Juodkrantė lies inside the lagoon polygon. Offsets are
still permitted — they are needed, to reach wet cells — but each must be declared
with a reason and a limit, so the next one cannot drift across a spit in silence.

The runs already in `results/` carry the old Juodkrantė position in their
`sfincs.obs`; they were not re-run for this, since Juodkrantė is not among the
four scored gauges and no criterion depends on it.

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
