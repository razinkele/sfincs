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
  was flat at the local bed elevation); moved a few hundred metres into flooded water
  in `prep/make_geometries.STATIONS_LONLAT`, then reran `make_geometries`,
  `build_model.py`, and the full simulation. All 9 stations now vary by more than
  0.2 m over the run.

## Results: Xaver 2013

Full validation output: `results/xaver_2013/validation.md`,
`results/xaver_2013/validation_timeseries.png` (time series) and
`results/xaver_2013/flood_extent_delta.png` (delta flood-extent map).
Table pasted verbatim below.

| station | n | bias m | RMSE m | r | peak err m | peak dt h |
|---|---|---|---|---|---|---|
| Klaipeda | 13 | -0.01 | 0.08 | 0.91 | +0.13 | +10 |
| Nida | 26 | -0.01 | 0.10 | 0.74 | -0.07 | -67 |
| Vente | 26 | +0.05 | 0.12 | 0.70 | +0.19 | -60 |
| Uostadvaris | 13 | -0.06 | 0.10 | 0.85 | +0.08 | +0 |

Flooded land in the delta window (depth > 5 cm, ground > 0 m): **163.2 km²**

Targets: Uostadvaris peak within ±0.15 m and ±6 h; Nida 8 Dec rise within ±0.15 m; Klaipeda RMSE ≤ 0.15 m.

Forcing as run (`inputs/forcing_summary.txt`): GTSM boundary offset +0.092 m
(calm window 28 Nov–4 Dec 2013), boundary peak 1.00 m at 2013-12-07 07:00;
wind peak 19.5 m/s at 2013-12-06 06:00 from 236°; Nemunas discharge
351–653 m³/s, Minija held constant at 46.0 m³/s. The wind peak coincides
with the Klaipeda and Uostadvaris gauge peaks and lands 25 h before the
GTSM boundary peak — the mechanism behind the Nida and wind-field findings
below.

### Success criteria (spec section 9)

- Uostadvaris peak on 6 Dec within ±0.15 m and ±6 h: **met** — model 1.00 m at
  06:30 vs gauge 0.92 m at 06:00, peak error +0.08 m at +0 h.
- Nida rise to 584 cm (0.84 m) on 8 Dec reproduced in sign and within ±0.15 m:
  **met, marginal** — model 0.70–0.77 m vs gauge 0.70–0.84 m on 8–9 Dec, rise
  reproduced in sign, miss at the gauge's own peak about 0.13 m.
- Klaipeda 06:00 series RMSE ≤ 0.15 m: **met** — RMSE 0.08 m (r = 0.91).
- No spurious flooding of the Silute uplands; plausible flood extent at Rusne:
  **met** — Silute uplands stay dry (6.5% of land flooded in a 2 km window
  around the station, centre dry at 2.95 m ground); Rusne island and the
  Silute polders flood field by field.

### Findings

- GTSM offset and timing vs the Klaipeda gauge: the GTSM boundary was bias
  corrected by +0.092 m over the calm window 28 Nov–4 Dec 2013 and peaks at
  1.00 m at 2013-12-07 07:00. The Klaipeda 06:00 gauge peaks at 0.88 m at
  2013-12-06 06:00, 25 h earlier than the raw boundary peak — recorded as a
  FINDING against the 12 h check tolerance in `inputs/forcing_summary.txt`,
  not treated as a blocker. Compared reading-by-reading against the Klaipeda
  06:00 series itself, RMSE is 0.08 m (r = 0.91); the table's "+10 h" peak
  timing is a same-time artefact of a gauge that plateaus at 0.85–0.88 m
  across 6–8 Dec rather than showing one sharp peak, against the model's own
  continuous maximum of about 1.0 m on 6–7 Dec (10–13 cm high at matching
  06:00 readings, correct storm-day timing). Before the storm the model
  shows 0.2–0.6 m oscillations that the once-daily 06:00/18:00 gauge cannot
  confirm or rule out — high-frequency energy carried in on the GTSM
  boundary.
- Uostadvaris peak: model 1.00 m at 06:30 on 6 Dec vs gauge 0.92 m at 06:00,
  peak error +0.08 m at +0 h — inside the ±0.15 m / ±6 h target.
- Nida delayed rise: the model's own peak (0.77 m) arrives with the gale on
  5–6 Dec, well before the gauge's peak of 0.84 m on 8 Dec 18:00 — the
  table's "peak dt −67 h" is the gap between these two different events, not
  a timing error on a single one. On 8–9 Dec specifically, the model sits at
  0.70–0.77 m against a gauge at 0.70–0.84 m, so the 8 Dec rise is
  reproduced in sign; the miss at the gauge's own peak is about 0.13 m,
  inside the ±0.15 m target but marginal. Nida, Juodkrante, Rusne and Silute
  all had to be moved 0.2–1.2 km into wet cells to get a usable point series
  (see Run log); a closer look at the Nida station siting is a candidate
  follow-up.
- Vente: the table's peak error (+0.19 m at −60 h) is a window-max-to-
  window-max comparison, 60 h apart. At matching 06:00 readings on 6 Dec the
  model overshoots the setup peak by about 0.35 m (0.95 m modelled vs
  0.60 m gauge) and tracks the gauge well afterwards; RMSE 0.12 m overall.
- Flooded area: 163.2 km² of land floods in the delta window (depth > 5 cm,
  ground > 0 m only). This is a lower bound on inundation extent — cells at
  or below 0 m ground are excluded — but likely an overestimate of real
  flooding, since the model has no drainage or pumping, the modelled storm
  peak at Klaipeda runs about 0.10 m high of the gauge even though the mean
  bias there is only -0.01 m, and dikes may be under-resolved at 5 m grid
  resolution. Rusne island and the Silute polders flood field by field, a
  plausible pattern; the Silute uplands themselves stay dry.
- Assumptions to revisit, in the order the results suggest: (1) uniform wind
  first — the Vente setup overshoot and the Nida peak-timing mismatch both
  point at missing spatial structure in the wind field that a single uniform
  wind value (taken at Nida) cannot supply; (2) the GTSM boundary next — its
  peak lands 25 h after the wind peak and the Klaipeda/Uostadvaris gauge
  peaks, and it carries high-frequency energy the once-daily gauge cannot
  confirm; (3) the 500 cm gauge-zero assumption looks right as it stands —
  bias is within ±6 cm at all four gauges; (4) channel dimensions and the
  Minija constant discharge — this event gives no evidence either way.
