# Curonian Lagoon SFINCS model — design for the April 2013 Nemunas freshet

**Date:** 2026-09-16 · **Status:** approved in brainstorming, awaiting spec review
**Engine:** SFINCS v2.4.0 Galibier, Linux build at `~/sfincs/sfincs-linux/bin/sfincs`
**Builder:** hydromt_sfincs 1.2.2 on hydromt 0.10.1, env `hydromt-sfincs`
**Predecessor:** [`2026-09-04-curonian-lagoon-xaver-model-design.md`](2026-09-04-curonian-lagoon-xaver-model-design.md)

## 1. Purpose

Hindcast the **April 2013 Nemunas spring freshet** with the model built for Storm
Xaver, unchanged in geometry, and score it at the gauges. Xaver tested the lagoon's
response to a fast sea-level forcing through the Klaipėda strait. April tests the
opposite driver — a slow, large river inflow filling the lagoon — on the same grid,
the same bathymetry and the same channels.

That is the point of the exercise. A model that reproduces both is a compound-flood
model in more than name; one that reproduces only the surge is a surge model that
happens to have rivers in it.

The secondary purpose is structural: make "which event" an explicit, named parameter
rather than a set of module-level constants, so that a third event costs a registry
entry instead of another pass through every script.

## 2. The event

From `curonian_db.gpkg` (LHMT records), Nemunas at Smalininkai, daily:

| date | Q (m³/s) | note |
| --- | --- | --- |
| 6 Apr | 410 | pre-flood minimum |
| 12 Apr | 699 | rise begins |
| 15 Apr | 1660 | |
| **19 Apr** | **2150** | discharge crest |
| 24 Apr | 1850 | |
| 2 May | 1040 | recession |

Roughly 4× the Xaver-period flow (400–550 m³/s). The April 2013 monthly mean of
1187 m³/s is the **fifth highest of the 25 Aprils on record** (1990–2014), behind
1994 (1679), 2010 (1285), 1996 (1273) and 1999 (1198). A large freshet, not a
record one.

Observed water levels, `physical_daily`, 06:00 readings, cm above gauge zero
(subtract `GAUGE_ZERO_CM = 500` for the model datum):

| gauge | peak | date | model datum |
| --- | --- | --- | --- |
| Uostadvaris | 554 cm | 24 Apr | **+0.54 m** |
| Nida | 536 cm | 29 Apr | +0.36 m |
| Ventė | 529 cm | 25 Apr | +0.29 m |
| Klaipėda | 515 cm | 24 Apr | +0.15 m |

Two features define the event and drive the success criteria:

1. **The level crest lags the discharge crest by five days** — Q peaks 19 April,
   Uostadvaris peaks 24 April. This is lagoon storage filling against the
   conveyance of the Klaipėda strait, and it is an emergent property of volume ÷
   conveyance rather than anything prescribed in the forcing.
2. **The delta-to-sea head grows from 13 cm to 39 cm** (Uostadvaris − Klaipėda,
   1 April → 24 April). Under Xaver the gradient ran the other way: the sea pushed
   the lagoon. Here the river holds a head above the sea.

Klaipėda staying at +0.15 m while Uostadvaris reaches +0.54 m is the control: it
says the Baltic was not driving this.

## 3. Ice, and why the window starts on 5 April

`wtemp_06` reads 0.0–0.1 °C through the first eleven days of April at Nida and
Uostadvaris, then rises sharply (Ventė is the exception at 0.4–0.6 °C, being
nearest the Nemunas outflow): Uostadvaris 0.0 °C on 12 April →
3.5 °C on 13 April, 7.5 °C at the level peak. The lagoon and delta were ice-covered
or ice-choked into the second week of April and thawed as the flood rose.

SFINCS has no ice. Ice-jam flooding is a real mechanism in the Rusnė delta and this
model cannot represent it. The design handles that by **placing the ice-affected
days in the spin-up and scoring only ice-free water**:

- **TREF 2013-04-05 00:00**, **TSTOP 2013-05-02 00:00** (27 days)
- **Calm window for GTSM bias correction: 5–11 April.** Klaipėda is flat through it
  (458–475 cm) — the sea being quiet is what this window needs, and it is, whatever
  the lagoon ice was doing.
- **Scoring window: 13 April 00:00 → 2 May 00:00.** Every scored hour is above
  0 °C at all three lagoon gauges.

The spin-up days still influence the run: they set the lagoon's initial level and
the model treats them as open water. That is a stated simplification, not a hidden
one — see section 10.

## 4. Structure: an Event object, passed explicitly

`common.py` gains a frozen dataclass and a registry:

```python
@dataclass(frozen=True)
class Event:
    name: str               # "xaver_2013" | "april_2013"
    tref: pd.Timestamp
    tstop: pd.Timestamp
    calm_window: tuple[pd.Timestamp, pd.Timestamp]   # GTSM bias correction
    score_window: tuple[pd.Timestamp, pd.Timestamp]  # criteria are judged here
    data_window: tuple[str, str]                     # DB query bounds, stored
    peak_window: tuple[str, str]                     # forcing_summary.txt slice
    peak_label: str                                  # "storm" | "crest"
    gtsm_months: tuple[str, ...]                     # CDS request
    minija_q: float                                  # m3/s, constant (section 6)
    nemunas_lag_days: int
    wind_check: tuple[float, str] | None             # (min peak m/s, what it is)

EVENTS = {
    "xaver_2013": Event(
        tref=2013-11-28 00:00, tstop=2013-12-11 00:00,
        calm_window=(2013-11-28, 2013-12-04),
        score_window=(2013-12-05, 2013-12-09),      # today's validate.STORM_WINDOW
        data_window=("2013-11-20", "2013-12-20"),   # today's literals, kept
        peak_window=("2013-12-05", "2013-12-08"), peak_label="storm",
        gtsm_months=("11", "12"), minija_q=46.0, nemunas_lag_days=1,
        wind_check=(15.0, "the Xaver gale")),
    "april_2013": Event(
        tref=2013-04-05 00:00, tstop=2013-05-02 00:00,
        calm_window=(2013-04-05, 2013-04-11),
        score_window=(2013-04-13, 2013-05-02),
        data_window=("2013-03-26", "2013-05-12"),   # tref-10d .. tstop+10d
        peak_window=("2013-04-19", "2013-04-25"), peak_label="crest",
        gtsm_months=("04", "05"), minija_q=83.0, nemunas_lag_days=1,
        wind_check=None),
}
```

Three of those fields exist to keep the Xaver outputs byte-identical rather than
because the concept needs them:

- **`score_window` is not the run span.** Xaver scores C1 and C3 on the four-day
  storm (`validate.STORM_WINDOW`), not the thirteen-day run, and reports the
  whole-period figure as context. April scores the ice-free period. Setting this to
  `(tref, tstop)` for Xaver would silently change three existing verdicts.
- **`data_window` is stored, not derived.** Xaver's DB queries use
  `2013-11-20`..`2013-12-20` — `tref−8 d`..`tstop+9 d`, not a round ±10 d. Keeping
  the literal is what lets `test_forcing_provenance` prove the refactor changed no
  bytes. April uses ±10 d because nothing constrains it to anything else.
- **`peak_window` is the `forcing_summary.txt` slice**, today the literal
  `corrected.loc["2013-12-05":"2013-12-08"]`, one day shorter than `score_window`.
  Keeping it separate keeps that tracked summary file identical; `peak_label` is
  what stops the summary generator from branching on the event's name.

**Passed as a parameter, never selected at import.** An env var or a module-level
`CURRENT_EVENT` would be a smaller diff and a worse design: it makes test outcomes
depend on import order and hides which event a script actually ran for. The
codebase already threads windows as arguments — `lag_and_resample(daily, lag,
start, stop)` — and this extends that one level up.

Every entry point grows `--event`, defaulting to `xaver_2013`, so **no existing
command changes behaviour**.

`event.inputs_dir` and `event.run_dir` are derived properties
(`INPUTS / name`, `RUNS / name`), not stored fields, so they cannot drift from the
name.

The existing `TREF`, `TSTOP`, `CALM_WINDOW` and `MINIJA_Q_DEC` module constants stay
as the Xaver event's values, with `EVENTS["xaver_2013"]` referring to them. Nothing
is renamed for its own sake, and `test_common.py`'s assertions on them stay valid.

## 5. File layout

Event-specific forcing moves into a per-event directory; static geometry does not
move, because it is genuinely shared:

```
inputs/
  active_region.geojson  boundary_points.geojson  boundary_ring.geojson     <- static,
  channels.geojson       dis_points.geojson       stations.geojson             shared
  lagoon_bathy_50m.tif                                                      (ignored, static)
  xaver_2013/    bzs.csv  dis.csv  wind.csv  gtsm_klaipeda.csv  forcing_summary.txt
                 era5_grid_summary.txt  era5_grid.nc (ignored)  gtsm.zip, gtsm/ (ignored)
  april_2013/    bzs.csv  dis.csv  wind.csv  gtsm_klaipeda.csv  forcing_summary.txt
```

**Inside an event directory, file names carry no event suffix** — the directory is
the identity. So `era5_grid_xaver.nc` becomes `xaver_2013/era5_grid.nc` and
`gtsm_2013_11_12.zip` becomes `xaver_2013/gtsm.zip`. Both are git-ignored local
files, so this is a `mv`, not a re-fetch, and it removes the two literal
`era5_grid_xaver.nc` strings in `build_model.py`.

`dis_points.geojson` is static: both events discharge at the same two points
(Nemunas apex, Minija mouth). `runs/<event>` and `results/<event>` already work this
way and need no change.

The six tracked Xaver files move by `git mv`, together with the path literals that
read and write them — a commit that moves files and re-points paths, and does
nothing else. It cannot be a pure move: the moment `inputs/dis.csv` becomes
`inputs/xaver_2013/dis.csv`, `make_forcing.main(inputs=common.INPUTS)` writes to the
old location and `test_forcing_provenance` reads a file that is not there, so a
move-only commit would leave the tree red. Git still records it as a rename, and
`git log --follow` still works. The two ignored bulk files (`era5_grid.nc`,
`gtsm.zip`/`gtsm/`) move in the same step by plain `mv`.

`test_forcing_provenance`'s exact-match assertion against the LHMT fixture is what
proves the move changed no bytes.

## 6. Forcing

| component | source | April treatment |
| --- | --- | --- |
| Sea boundary (`bzs.csv`) | GTSM-ERA5 reanalysis via CDS, bias-corrected to the Klaipėda 06:00 gauge over the calm window | Same method. New CDS fetch: `month: ["04", "05"]`, cached as `april_2013/gtsm.zip`. |
| Wind (`wind.csv`) | ERA5 point series at Nida | **Already on disk** — `era5_wind_nida_2013.nc` covers all of 2013 (8760 hourly steps). No fetch. |
| Nemunas (`dis.csv` col 1) | `river_discharge`, Smalininkai, daily, lagged 1 day, interpolated hourly | Same, `data_window` `2013-03-26`..`2013-05-12`. |
| Minija (`dis.csv` col 2) | constant | **83 m³/s** — see below. |
| Pressure | gridded ERA5 | Out of scope for the first run. |

The `>15 m/s` "expected the Xaver gale" guard in `wind_forcing()` becomes
`event.wind_check`. For Xaver it stays `(15.0, "the Xaver gale")` — a real assertion
that still fails loudly if the wrong file is read. For April it is `None`: this
event has no wind signature to assert, and inventing a threshold to have one would
be a check that tests nothing.

`None` drops **only the peak-magnitude assertion**. The NaN check and the index-span
check in `wind_forcing()` stay unconditional for every event, so a truncated or
empty April slice still fails loudly — the guard is narrowed, not removed. A test
covers exactly this (section 9).

**The Minija constant.** The DB's Minija record ends in 2011, so April gets a
constant exactly as December does (`MINIJA_Q_DEC = 46.0`). Two defensible values:

- **climatological**: April mean at Lankupiai over the six Aprils it recorded
  between 2004 and 2011, **53 m³/s**;
- **anomaly-scaled**: Nemunas April 2013 over the run window (1279 m³/s) ÷ Nemunas
  April climatology (820 m³/s over 25 Aprils, 1990–2014) = 1.56; × Minija April
  climatology
  (53) = **83 m³/s**. Excluding 2013 from its own climatology gives 804 and 84 m³/s,
  so the number is insensitive to that choice at the 1 m³/s level.

The design takes **83 m³/s**, on the reasoning that April 2013 was demonstrably a
regional wet anomaly and the Minija shares the weather even though it does not share
the catchment's size or response. 83 sits well inside the observed April range at
Lankupiai (max 272). Recorded as `MINIJA_Q_APR = 83.0` beside the December constant,
with the derivation in a comment so the number is auditable rather than magic.

This choice is low-stakes by construction: the Minija is about 5 % of total inflow,
so the 53-vs-83 difference is ~2 % of the water entering the lagoon — below the
resolution of every criterion in section 8. It matters locally at the Minija mouth
and nowhere else.

## 7. Run settings

Unchanged from Xaver except the clock: same grid (1000×1100 at 100 m, LKS-94),
same subgrid, same Manning fields, same `dis_points`, same `stations.geojson`,
same `pavbnd = 0`.

- `tref = tstart = 20130405 000000`, `tstop = 20130502 000000`
- One run: `runs/april_2013`, uniform wind, no pressure forcing.

Wind is second-order in a freshet, so the gridded-wind and wind+pressure variants
are **deliberately not built in this pass**. If the gauge errors in section 8 point
at wind, they are a follow-up — each would need its own April CDS grid fetch.

Cost estimate: Xaver's 13-day run took 26–28 minutes on 16 threads; 27 days is
~55–60 minutes at low machine load, plus ~5 minutes for the subgrid build.

## 8. Success criteria

Judged on the scoring window, 13 April – 2 May. Observations are **daily at 06:00**
for Klaipėda and Uostadvaris (Nida and Ventė also have 18:00), so the timing
tolerances are in days, not hours. Xaver's ±6 h tolerance would be meaningless
against a once-a-day reading, and is deliberately not reused.

**The observed crest is a plateau, and A2 is defined against the plateau rather
than a single reading.** Uostadvaris reads 550 (22 Apr), 550 (23 Apr), **554**
(24 Apr), 546 (25 Apr): the 4 cm that make the 24th the maximum are smaller than
the day-to-day change either side of it, so treating "24 Apr 06:00" as the true
peak instant would fail a model that peaked on the 23rd while being
indistinguishable from the data. The plateau is every reading within **0.05 m** of
the observed maximum — 22–24 April — and A2 widens it by 12 h on each side.
`validate.py` already carries this idea for the model side (`PEAK_TIE_M`, 1 mm
against an hourly series); this is the same rule sized for a daily gauge.

| # | criterion | threshold |
| --- | --- | --- |
| **A1** | Uostadvaris peak level | within **±0.15 m** of the observed +0.54 m |
| **A2** | Uostadvaris peak timing | model peak inside the observed plateau widened by 12 h (**21 Apr 18:00 – 24 Apr 18:00**), **and** lagging the 19 Apr discharge crest by ≥ 3 days |
| **A3** | delta-to-sea head | model (Uostadvaris − Klaipėda) **at 24 Apr 06:00** within **±0.10 m** of the observed 0.39 m |
| **A4** | Klaipėda control | RMSE ≤ **0.15 m** over the scoring window |
| **A5** | no spurious upland flooding | < 1 % of land above 3 m flooded (Xaver's C4, unchanged) |

Reported as context, not scored: Nida and Ventė peak errors and RMSE; the whole-run
Uostadvaris RMSE; the modelled flood extent in the delta window.

**A2 is the criterion that matters.** A model with the wrong bathymetry or the wrong
strait conveyance can still get A1 approximately right by mass balance — the water
has to go somewhere — while getting the filling rate badly wrong. The lag is what
distinguishes a lagoon that fills correctly from a bucket. The ≥ 3 day clause is the
discriminating half: the plateau window alone could be cleared by a model that
happens to peak late for the wrong reason.

A3 is partly implied by A1 and A4, intentionally: it holds the two jointly to a
tighter tolerance than either alone, and it is the quantity that states the event
was river-driven.

**Flood extent is drawn and published but carries no verdict.** There is no
reference extent to score against: Sentinel-1A did not launch until April 2014,
Landsat 8 was still in commissioning in April 2013, and Landsat 7 was SLC-off. That
leaves MODIS at 250 m over a delta ~20 km across, cloud permitting. A pass/fail
against a reference we would have to assume is not a validation, and the figure is
more honest without one.

## 9. Testing

The existing 80 tests must pass unchanged — that is the regression check on the
refactor, and `test_forcing_provenance`'s exact match against the LHMT fixture is
the sharpest instrument in it. (Baseline measured 2026-09-16: 80 passed in 25 s from
the main checkout. A run with api.meteo.lt unreachable reports 79 passed, 1 skipped —
the live-API provenance check skipping by design.)

New tests:

- `test_common.py`: the registry — both events present, `april_2013` has the agreed
  window, `inputs_dir`/`run_dir` derive from the name, the dataclass is frozen.
- `test_make_forcing.py`: parametrized over both events where the assertion is
  event-independent (index spans `tref`..`tstop`, no NaN, Minija constant held);
  April-specific values where it is not.
- `test_make_forcing.py`: `wind_check=None` skips the gale assertion; a Xaver-shaped
  check still raises when handed a calm series. This is the one place the refactor
  could silently delete a real guard, so it gets a test that fails if it does.
- `test_validate.py`: `--event april_2013` parses; the April criteria functions
  return the five expected names; each verdict is computed from a synthetic `his`
  frame with a known answer (peak on the right day → A2 met; peak three days early →
  A2 not met).
- `test_forcing_provenance.py`: extended to April — the same exact-match check
  against an LHMT fixture for the April window, fetched the way the December one was.

Per the repo's habit (`aa6f912`), each new criterion test is **proved by sabotage**:
shift the modelled peak and confirm the specific criterion flips.

## 10. Known limitations

1. **Ice is not modelled.** 1–12 April was ice-affected; those days are spin-up and
   unscored, but they still set the initial lagoon level as though open water. If
   the modelled level on 13 April is biased, this is the first suspect.
2. **No scored flood extent** (section 8) — the April extent map is illustrative.
3. **Minija is a constant**, derived not observed (section 6).
4. **The 1-day Nemunas lag is inherited from Xaver.** A flood wave travels faster
   than a low-flow wave, so 1 day may be too long at 2150 m³/s. Kept for
   comparability; flagged as the obvious sensitivity test if A2 fails on timing.
5. **The sea boundary is still GTSM + bias correction**, not observed hourly
   Klaipėda levels — the same open item as Xaver
   (`~/curonian/docs/curonian_sla_boundary_correction.md`). It matters less here:
   Klaipėda varies by 0.5 m over the whole event against Uostadvaris's rise, and A4
   makes the boundary's behaviour a scored quantity rather than an assumption.
6. **One forcing variant only** (section 7).

## 11. Build sequence

Geometry and bathymetry are **not** rebuilt — they are event-independent and already
committed. `make_channels` in particular must not be re-run casually: it reads live
Overpass data.

```
1. common.py            Event dataclass + registry; both events              (no run)
2. move + re-point      inputs/*.csv -> inputs/xaver_2013/, and every
                        literal INPUTS / "x.csv" with them; 80 tests green   (no run)
3. prep/*, build_model, validate   thread `event` through; --event flag      (no run)
4. tests                existing 80 still green; new tests per section 9
5. prep.fetch_gtsm --event april_2013        CDS fetch, months 04-05
6. prep.make_forcing --event april_2013      writes inputs/april_2013/*
7. build_model.py --event april_2013         builds runs/april_2013 (~5 min)
8. ../run_sfincs.sh runs/april_2013 16       (~55-60 min)
9. validate.py --event april_2013            writes results/april_2013/*
10. app/sfincs_data.py VARIANT_LABELS        one entry, "April 2013 — Nemunas freshet"
11. curonian/README.md                       results section, run log, criteria table
```

Steps 1–4 are a complete, independently valuable unit: the refactor lands with the
existing event still green before any April data is fetched. If the CDS fetch or the
run fails, the repository is not left mid-surgery.

## 12. Out of scope

Gridded wind and pressure variants for April; a third event; re-running Xaver;
any change to geometry, bathymetry, channels or the subgrid; the observed-hourly sea
boundary; ice modelling of any kind.
