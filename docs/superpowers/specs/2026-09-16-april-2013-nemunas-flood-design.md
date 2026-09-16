# Curonian Lagoon SFINCS model — design for the April 2013 Nemunas freshet

**Date:** 2026-09-16 · **Status:** revised after multi-agent spec review, awaiting final approval
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

The Xaver-period flow was 351–653 m³/s (mean 537), so the April crest is about 4×
it. The April 2013 monthly mean of 1187 m³/s is the **fifth highest of the 25 Aprils
on record** (1990–2014), behind 1994 (1679), 2010 (1285), 1996 (1273) and 1999
(1198). A large freshet, not a record one.

Observed water levels, `physical_daily`, 06:00 readings, cm above gauge zero
(subtract `GAUGE_ZERO_CM = 500` for the model datum):

| gauge | peak | date | model datum |
| --- | --- | --- | --- |
| Uostadvaris | 554 cm | 24 Apr | **+0.54 m** |
| Nida | 536 cm | 29 Apr | +0.36 m |
| Ventė | 529 cm | 25 Apr | +0.29 m |
| Klaipėda | 515 cm | 24 Apr | +0.15 m |

Three features define the event and drive the success criteria:

1. **A well-resolved rising limb.** Uostadvaris climbs 481 → 550 cm over 12–22
   April, 10–18 cm on the steepest days, so the daily 06:00 readings resolve the
   *rate* of filling even though they barely resolve the crest. It first reads
   ≥ 520 cm (+0.20 m) on **20 April**.
2. **The crest lags the discharge crest by about five days and is flat.** Q peaks
   19 April; Uostadvaris reads 550, 550, 554 cm on 22, 23, 24 April — a plateau, not
   a spike. The lag is lagoon storage filling against the conveyance of the Klaipėda
   strait: an emergent property of volume ÷ conveyance, not anything prescribed in
   the forcing.
3. **The delta stands above the sea through the crest.** The Uostadvaris − Klaipėda
   head reads 49, 48, 52, **55**, 39, 45, 47 cm on 20–26 April, averaging **47.6 cm**
   over 22–26 April. Under Xaver the gradient ran the other way: the sea pushed the
   lagoon. Here the river holds a head above the sea.

Two cautions about that head, both of which shape criterion A3:

- **It is not monotonic.** It reaches 34 cm on 7 April and falls to **−3 cm on 12
  April** before the flood drives it up, so any "grows from X to Y" summary is a
  choice of endpoints rather than a description.
- **The 24 April value (39 cm) is a local minimum, not the maximum.** Klaipėda
  jumped 20 cm for a single reading (495 → 515 → 501 cm on 23/24/25 April), which
  depresses the head on exactly the day Uostadvaris peaks. The head's true maximum
  is 55 cm on 23 April.

Klaipėda is the control: over the scoring window it spans −0.23 to +0.15 m with a
mean of **−0.05 m** and a standard deviation of 0.087 m. Its +0.15 m on 24 April is
its single highest reading of the event, not its typical state. The Baltic was not
driving this.

## 3. Ice, and why the window starts on 5 April

`wtemp_06` at **Uostadvaris**, in the delta, reads **0.0 °C on every one of the
twelve days 1–12 April** and jumps to 3.5 °C on 13 April. The lagoon proper was
colder than usual but not frozen through: Nida is 0.0–0.1 °C only through 5 April
and is past 1 °C by 10 April; Ventė, nearest the Nemunas outflow, runs 0.1–1.2 °C in
the first week and reaches 2.8 °C by 11 April.

So the ice argument rests on Uostadvaris — which is the gauge in the delta, where
the flooding happens, and the gauge A1–A3 are scored on. The delta was ice-covered
or ice-choked into the second week of April and cleared as the flood rose.

SFINCS has no ice. Ice-jam flooding is a real mechanism in the Rusnė delta and this
model cannot represent it. The design handles that by **placing the ice-affected
days in the spin-up and scoring only ice-free water**:

- **TREF 2013-04-05 00:00**, **TSTOP 2013-05-02 00:00** (27 days)
- **Calm window for GTSM bias correction: 5–11 April.** Klaipėda is flat through it
  (462–475 cm, a 13 cm spread over seven readings) — the sea being quiet is what
  this window needs, and it is, whatever the delta ice was doing.
- **Scoring window: 13 April 00:00 → 2 May 00:00.** Uostadvaris is above 0 °C for
  every scored hour.

The spin-up days still influence the run: they set the lagoon's initial level and
the model treats them as open water. See section 7 on the initial condition, which
is the other half of this problem, and section 10 on what it costs.

## 4. Structure: an Event object, passed explicitly

`common.py` gains a frozen dataclass and a registry:

```python
@dataclass(frozen=True)
class Event:
    name: str               # "xaver_2013" | "april_2013"
    title: str              # report and figure titles, replaces "Xaver 2013"
    tref: pd.Timestamp
    tstop: pd.Timestamp
    calm_window: tuple[pd.Timestamp, pd.Timestamp]   # GTSM bias correction
    score_window: tuple[pd.Timestamp, pd.Timestamp]  # criteria are judged here
    data_window: tuple[str, str]                     # observation query/slice bounds
    peak_window: tuple[str, str]                     # forcing_summary.txt slice
    peak_label: str                                  # "storm" | "crest"
    gtsm_months: tuple[str, ...]                     # CDS request
    minija_q: float                                  # m3/s, constant (section 6)
    nemunas_lag_days: int
    wind_check: tuple[float, str] | None             # (min peak m/s, what it is)
    zsini: float | None                              # None = take it from the boundary
    score_label: str                                 # the report's window heading

EVENTS = {
    "xaver_2013": Event(
        name="xaver_2013", title="Xaver 2013",
        tref=2013-11-28 00:00, tstop=2013-12-11 00:00,
        calm_window=(2013-11-28, 2013-12-04),
        score_window=(2013-12-05, 2013-12-09),      # today's validate.STORM_WINDOW
        data_window=("2013-11-20", "2013-12-20"),   # today's literals, kept
        peak_window=("2013-12-05", "2013-12-08"), peak_label="storm",
        gtsm_months=("11", "12"), minija_q=46.0, nemunas_lag_days=1,
        wind_check=(15.0, "the Xaver gale"), zsini=None,
        score_label="Storm window"),
    "april_2013": Event(
        name="april_2013", title="April 2013 Nemunas freshet",
        tref=2013-04-05 00:00, tstop=2013-05-02 00:00,
        calm_window=(2013-04-05, 2013-04-11),
        score_window=(2013-04-13, 2013-05-02),
        data_window=("2013-03-26", "2013-05-12"),   # tref-10d .. tstop+10d
        peak_window=("2013-04-19", "2013-04-25"), peak_label="crest",
        gtsm_months=("04", "05"), minija_q=83.0, nemunas_lag_days=1,
        wind_check=None, zsini=-0.17,
        score_label="Scoring window"),
}
```

**Passed as a parameter, never selected at import.** An env var or a module-level
`CURRENT_EVENT` would be a smaller diff and a worse design: it makes test outcomes
depend on import order and hides which event a script actually ran for. The
codebase already threads windows as arguments — `lag_and_resample(daily, lag,
start, stop)` — and this extends that one level up.

`event.inputs_dir` is a derived property (`INPUTS / name`).

**`run_dir` is NOT derived from the event.** One event already owns three run and
result directories — `xaver_2013`, `xaver_2013_gridwind`,
`xaver_2013_gridwind_pressure` — selected by `build_model.py --run-name` and
`validate.py --run`. Those flags stay; they default to `event.name`, i.e.
`run_dir = RUNS / (args.run_name or event.name)`. `common.RUN_XAVER` stays as the
Xaver default so `tests/test_build_model.py:31,81` remain valid. Every entry point
grows `--event` defaulting to `xaver_2013`, so **no existing command changes
behaviour**.

Five of these fields exist to keep the Xaver outputs byte-identical, or because the
code needs a hook the concept does not:

- **`score_window` is not the run span.** Xaver scores C1 and C3 on the four-day
  storm (`validate.STORM_WINDOW`), not the thirteen-day run, and reports the
  whole-period figure as context. Setting this to `(tref, tstop)` for Xaver would
  silently change three existing verdicts.
- **`data_window` is stored, not derived,** and it bounds *three* sites, not two:
  the two SQL windows in `make_forcing.py` (`discharge_forcing`, `load_gauge_levels`)
  **and** the `.loc[...]` slice in `cmems_daily_boundary`. Xaver's literals
  (`tref−8 d`..`tstop+9 d`) are kept verbatim so `test_forcing_provenance` can prove
  the refactor changed no bytes.
- **`peak_window` is the `forcing_summary.txt` slice**, one day shorter than
  `score_window`; keeping it separate keeps that tracked file identical.
- **`score_label`** is the report's own heading for its scored window — `Storm
  window` for Xaver, `Scoring window` for April — so neither `validate.py` nor the
  viewer has to branch on the event's name to label it.

`validate.criteria()` is Xaver-specific in ways no data field can express (it
hardcodes 2013-12-07/08 timestamps and the 0.84 m Nida peak), so it splits into
`xaver_criteria` (today's body, unchanged) and `april_criteria` (section 8). The
dispatch is a **table in `validate.py` keyed by event name**, not a field on
`Event`: a function reference on the dataclass would make `common` depend on
`validate` having been imported, and an unset one would silently score April with
Xaver's criteria instead of raising.
- **`zsini`** — see section 7.

## 5. File layout

Event-specific forcing moves into a per-event directory; static geometry does not
move, because it is genuinely shared:

```
inputs/
  active_region.geojson  boundary_points.geojson  boundary_ring.geojson     <- static,
  channels.geojson       dis_points.geojson       stations.geojson             shared
  lagoon_bathy_50m.tif                                            (ignored, static)
  xaver_2013/    bzs.csv  dis.csv  wind.csv  gtsm_klaipeda.csv  forcing_summary.txt
                 era5_grid_summary.txt
                 era5_grid.nc  era5_raw.nc  gtsm.zip  gtsm/        (all ignored)
  april_2013/    bzs.csv  dis.csv  wind.csv  gtsm_klaipeda.csv  forcing_summary.txt
```

**Inside an event directory, file names carry no event suffix** — the directory is
the identity. `era5_grid_xaver.nc` → `xaver_2013/era5_grid.nc`,
`era5_raw_2013_11_12.nc` → `xaver_2013/era5_raw.nc`, `gtsm_2013_11_12.zip` →
`xaver_2013/gtsm.zip`, `gtsm_2013_11_12/` → `xaver_2013/gtsm/`. All four are
git-ignored local files, so this is a `mv`, not a re-fetch.

**Two directories, not one.** `make_forcing.main()` and `build_model.build()` each
take a single `inputs` argument today and use it for files on *both* sides of this
split. They must take both roots:

| function | reads from `event.inputs_dir` | reads/writes in `common.INPUTS` |
| --- | --- | --- |
| `make_forcing.main` | writes `bzs.csv`, `dis.csv`, `wind.csv`, `forcing_summary.txt`; reads `gtsm_klaipeda.csv` | reads `boundary_points.geojson`; **writes `dis_points.geojson`** |
| `build_model.build` | `bzs.csv`, `dis.csv`, `wind.csv`, `era5_grid.nc` | `boundary_points.geojson`, `dis_points.geojson`, `stations.geojson` |
| `fetch_era5_grid` | writes `era5_raw.nc`, `era5_grid.nc`, `era5_grid_summary.txt` | — |
| `fetch_gtsm` | writes `gtsm.zip`, `gtsm/`, `gtsm_klaipeda.csv` | — |

Setting a single `inputs = event.inputs_dir` instead would make `make_forcing` raise
`FileNotFoundError` on `boundary_points.geojson` and write a duplicate
`dis_points.geojson` into the event directory.

**The `era5_grid.nc` rename touches six places, not two:** `build_model.py:57,59`
(argparse help strings that name the file to the user), `:108`, `:118`,
`prep/fetch_era5_grid.py:144` (**the writer** — miss this and the builder looks for a
file the fetcher never produces), `:171`, `tests/test_fetch_era5_grid.py:102`, and
`README.md:179,277`. The zip rename touches `prep/fetch_gtsm.py:35`.

**`.gitignore` must be updated in the same commit.** `curonian/inputs/*.zip` matches
one level only, so after the move the 79 MB `xaver_2013/gtsm.zip` stops being
ignored; `curonian/inputs/gtsm_2013_11_12/` becomes a dead pattern. The `*.nc` and
`*.tif` patterns at the top of the file are global and keep working. Verified:

```
$ git check-ignore -q curonian/inputs/xaver_2013/gtsm.zip   ; echo $?   # 1 = NOT ignored
$ git check-ignore -q curonian/inputs/xaver_2013/era5_grid.nc ; echo $? # 0 = ignored
```

New patterns: `curonian/inputs/*/*.zip` and `curonian/inputs/*/gtsm/`.

`runs/` and `results/` are keyed by **run name**, not event name, and need no
change — see section 4.

## 6. Forcing

| component | source | April treatment |
| --- | --- | --- |
| Sea boundary (`bzs.csv`) | GTSM-ERA5 reanalysis via CDS, bias-corrected to the Klaipėda 06:00 gauge over the calm window | Same method. New CDS fetch: `month: ["04", "05"]`, cached as `april_2013/gtsm.zip`. |
| Wind (`wind.csv`) | ERA5 point series at Nida | **Already on disk** — `era5_wind_nida_2013.nc` covers all of 2013 (8760 hourly steps). No fetch. |
| Nemunas (`dis.csv` col 1) | `river_discharge`, Smalininkai, daily, lagged 1 day, interpolated hourly | Same, `data_window` `2013-03-26`..`2013-05-12`. |
| Minija (`dis.csv` col 2) | constant | **83 m³/s** — see below. |
| Pressure | gridded ERA5 | Out of scope for the first run. |

**The wind guard.** `wind_forcing()` today asserts a peak above 15 m/s ("expected the
Xaver gale"). April's peak will not clear it, so the threshold becomes
`event.wind_check`, `None` for April. **But `None` must not leave the function
without a floor:** contrary to what an earlier draft of this spec asserted, there is
today *no* index-span check in `wind_forcing()`, and its NaN check does not fire on
an empty frame — so with `wind_check=None` a truncated or empty April slice would
pass silently and SFINCS would get a wind file that does not cover the run. This
design therefore **adds** an unconditional span guard for every event:

```python
if df.index[0] > event.tref - pd.Timedelta("1h") or df.index[-1] < event.tstop + pd.Timedelta("1h"):
    raise ValueError(f"wind series {df.index[0]}..{df.index[-1]} does not cover {event.name}")
```

Xaver keeps `(15.0, "the Xaver gale")`, which still fails loudly if the wrong file is
read. Section 9 tests both halves.

**The Minija constant.** The DB's Minija record ends in 2011, so April gets a
constant exactly as December does (`MINIJA_Q_DEC = 46.0`). Two defensible values:

- **climatological**: April mean at Lankupiai over the six Aprils it recorded
  between 2004 and 2011, **53 m³/s**;
- **anomaly-scaled**: Nemunas April 2013 over the run window (1279 m³/s) ÷ Nemunas
  April climatology (820 m³/s over 25 Aprils, 1990–2014) = 1.56; × Minija April
  climatology (53) = **83 m³/s**. Excluding 2013 from its own climatology gives 804
  and 84 m³/s, so the number is insensitive to that choice at the 1 m³/s level.

The design takes **83 m³/s**, on the reasoning that April 2013 was demonstrably a
regional wet anomaly and the Minija shares the weather even though it does not share
the catchment's size or response. 83 sits well inside the observed April range at
Lankupiai (max 272). Recorded as `MINIJA_Q_APR = 83.0` beside the December constant,
with the derivation in a comment so the number is auditable rather than magic.

This choice is low-stakes by construction: the Minija is about 5 % of total inflow,
so the 53-vs-83 difference is ~2 % of the water entering the lagoon — below the
resolution of every criterion in section 8.

## 7. Run settings and the initial condition

Same grid (1000×1100 at 100 m, LKS-94), same subgrid, same Manning fields, same
`dis_points`, same `stations.geojson`, same `pavbnd = 0`.

- `tref = tstart = 20130405 000000`, `tstop = 20130502 000000`
- One run: `runs/april_2013`, uniform wind, no pressure forcing.

**The initial condition is not unchanged, and this is the one substantive model
change.** `build_model.build()` sets `zsini = bzs.iloc[0].mean()` — the whole lagoon
starts at the *sea boundary's* first value. For Xaver that was harmless: `zsini`
came out at 0.389 m against observed 28 Nov levels of 0.35 (Klaipėda), 0.32 (Nida)
and 0.50 m (Uostadvaris), within 0.05–0.11 m. April is different. At 05 Apr 06:00
the sea is at −0.36 m (Klaipėda 464 cm) while the lagoon sits at −0.10 (Nida),
−0.13 (Uostadvaris) and −0.28 m (Ventė): taking `zsini` from the boundary would
start the lagoon roughly **0.23 m low** against criteria stated in absolute metres
(A1 is ±0.15 m). Over ~1600 km² that deficit is ~3.7 × 10⁸ m³; river inflow alone at
~500 m³/s would need about eight days to make it up — the entire spin-up.

So `Event.zsini` is an explicit field: `None` for Xaver (derive from the boundary,
preserving today's behaviour and outputs exactly) and **−0.17 m for April**, the
mean of the three lagoon gauges (Nida, Uostadvaris, Ventė) at TREF. The derivation
goes in a comment beside the value.

Wind is second-order in a freshet, so the gridded-wind and wind+pressure variants
are **deliberately not built in this pass**. If the gauge errors in section 8 point
at wind, they are a follow-up — each would need its own April CDS grid fetch.

Cost estimate: Xaver's 13-day run took 26–28 minutes on 16 threads; 27 days is
~55–60 minutes at low machine load, plus ~5 minutes for the subgrid build.

## 8. Success criteria

A1–A4 are judged on the scoring window, 13 April – 2 May; **A5 is a whole-run
guard** (see below). Observations are **daily at 06:00** for Klaipėda and
Uostadvaris (Nida and Ventė also have 18:00), so timing tolerances are in days, not
hours. Xaver's ±6 h tolerance would be meaningless against a once-a-day reading and
is deliberately not reused.

| # | criterion | threshold |
| --- | --- | --- |
| **A1** | Uostadvaris peak level | within **±0.15 m** of the observed +0.54 m |
| **A2a** | filling rate | model Uostadvaris first reaches **+0.20 m** within **±24 h** of the observed crossing (20 Apr 06:00) |
| **A2b** | crest timing | model Uostadvaris peak inside the observed plateau widened by 12 h: **21 Apr 18:00 – 24 Apr 18:00** |
| **A3** | delta-to-sea head | **mean of the daily 06:00 head** (Uostadvaris − Klaipėda) over **22–26 Apr** within **±0.15 m** of the observed **0.476 m** |
| **A4** | Klaipėda control | RMSE ≤ **0.085 m**, i.e. below the observed σ of 0.087 m |
| **A5** | no spurious upland flooding | < 1 % of land above 3 m flooded (Xaver's C4, unchanged) |

Reported as context, not scored: Nida and Ventė peak errors and RMSE; the whole-run
Uostadvaris RMSE; the modelled flood extent in the delta window.

**A2 is split because the rise is better resolved than the crest.** The observed
crest is a plateau — Uostadvaris reads 550, 550, 554 cm on 22–24 April, and the 4 cm
that make the 24th the maximum are smaller than the day-to-day change either side —
so a criterion that pins the peak to an instant would fail a model peaking on the
23rd for no defensible reason. A2b therefore accepts the whole plateau (readings
within 0.05 m of the maximum) widened by 12 h. But the plateau alone accepts model
lags of 2.75–5.75 days, which is a weak test of the filling rate that section 2
calls the event's defining property. **A2a supplies the sharp half**: on the rising
limb Uostadvaris climbs 10–18 cm/day, so the day it crosses +0.20 m is resolved to
within a reading, and ±24 h is a real constraint. A model that fills the lagoon 40 %
too fast fails A2a while still clearing A2b.

(An earlier draft used a one-sided "lag ≥ 3 days" clause and justified it as
excluding models that peak late. A minimum lag can only exclude peaks that are too
*early*; the clause was near-redundant against A2b's lower edge and its rationale
was backwards. A2a replaces it.)

**A3 is scored over the crest, not at an instant.** The 24 April head of 0.39 m is a
local minimum caused by a one-day 20 cm excursion in the Klaipėda gauge, not by the
river (section 2). Anchoring A3 there would fail a model that correctly holds the
0.45–0.55 m head prevailing across the crest, and reward one that happens to
reproduce a synoptic sea-level blip — inverting the criterion's purpose. The mean
over 22–26 April (0.476 m) is robust to that single reading, and ±0.15 m matches
A1's tolerance rather than pretending to finer resolution than daily gauge data
supports.

**A4 must beat the no-skill baseline.** Klaipėda's 06:00 series over the scoring
window has n = 20, mean −0.052 m, σ = 0.087 m. Xaver's 0.15 m threshold was a real
test there, where the storm signal spanned ~0.9 m — here a flat line at the window
mean would score RMSE 0.087 m and pass it. The threshold is therefore 0.085 m: the
model must do better than predicting the mean. If A4 fails, the first suspect is the
GTSM boundary rather than the lagoon (section 10, item 5).

**A5 is a whole-run guard, not a scoring-window criterion.** `_flood_arrays()` reads
`zsmax` from `sfincs_map.nc`, and `dtmaxout = 99999999` means a single `zsmax` record
spanning the entire run — so A5 necessarily covers the ice-affected spin-up too.
Rather than reconfigure `dtmaxout`, the spec states the scope: A5 asks "did this run
ever flood the uplands", which is the sanity question it was always answering.

**Flood extent is drawn and published but carries no verdict — and the reason is
cost, not data availability.** An earlier draft of this spec claimed no reference
imagery exists for April 2013. That was wrong on two of three counts, and the review
checked it against the public Landsat Collection 2 archive:

| scene | date | window coverage | usable |
| --- | --- | --- | --- |
| `LC08_L2SP_189021_20130424_02_T1` | 24 Apr (crest day) | 100 % | 64 % (36 % cloud+shadow) |
| `LE07_L2SP_188022_20130425_02_T1` | 25 Apr | 94 % | 74 % (0 % cloud, 25.7 % SLC gaps) |
| `LE07_L2SP_189021_20130416_02_T1` | 16 Apr (rising limb) | 100 % | 75 % |

Landsat 8 was in commissioning in April 2013 but *was* acquiring, and its scenes are
distributed as Tier 1. Only the Sentinel-1A premise (launch April 2014) was correct.
So a scored extent criterion is feasible — against an MNDWI/NIR water mask from the
25 April L7 scene gap-filled with the 24 April L8 scene — and it is excluded here
because building and validating that mask is a project of its own, with real caveats
(optical cannot see water under canopy, minor in a pre-leaf-out April delta;
overpasses ~03:40 and ~09:40 UTC against a 06:00 gauge). It is the obvious follow-up,
recorded in section 12 rather than silently dropped.

**The report's window heading is `Scoring window:`** (`event.score_label`). `app/sfincs_data._PERIOD_RE`
hardcodes `^(Whole period|Storm window):` and is the only thing that finds both the
period headings and the per-station metric tables, so it must learn the third word or
April's metric table silently vanishes from the viewer (section 11, step 10).

## 9. Testing

The existing 80 tests must pass unchanged — that is the regression check on the
refactor, and `test_forcing_provenance`'s exact match against the LHMT fixture is the
sharpest instrument in it.

**The gate is "80 passed, 0 skipped", not "80 tests pass".** Two tests skip rather
than fail when a `common.INPUTS / ...` file is missing, so a missed path literal in
the move would turn them into silent skips — exactly the mistake that step most
easily makes. (Baseline measured 2026-09-16 from the main checkout: 80 passed,
0 skipped, 25 s. A run with api.meteo.lt unreachable reports 79 passed, 1 skipped —
the live-API provenance check skipping by design. That is the *only* acceptable
skip, and it must be identified by name, not by count.)

New tests:

- `test_common.py`: the registry — both events present, `april_2013` has the agreed
  window, `inputs_dir` derives from the name, `run_dir` does **not**, the dataclass
  is frozen.
- `test_make_forcing.py`: parametrized over both events where the assertion is
  event-independent (index spans `tref`..`tstop`, no NaN, Minija constant held);
  April-specific values where it is not.
- `test_make_forcing.py`: the wind guard, both halves — `wind_check=None` skips the
  peak-magnitude assertion; a Xaver-shaped check still raises on a calm series; **and
  an empty or truncated slice raises for both events**, which is the guard section 6
  adds.
- `test_validate.py`: `--event april_2013` parses; `april_criteria` returns the six
  expected names; each verdict is computed from a synthetic `his` frame with a known
  answer (peak in the plateau → A2b met; +0.20 m crossed two days late → A2a not
  met; head mean 0.30 m → A3 not met).
- `test_forcing_provenance.py`: extended to April against an April LHMT fixture, and
  given a **skip-if-missing guard** matching the rest of the suite, since the April
  `dis.csv` does not exist until the forcing is built.
- `app/test_sfincs_data.py`: a report headed `Scoring window:` parses, and its metric
  table is found.

Per the repo's habit (`aa6f912`), each new criterion test is **proved by sabotage**:
shift the modelled peak and confirm the specific criterion flips.

## 10. Known limitations

1. **Ice is not modelled.** 1–12 April was ice-affected at Uostadvaris; those days
   are spin-up and unscored, but the model treats them as open water.
2. **The initial condition is prescribed, not spun up** (section 7): −0.17 m from
   three lagoon gauges at TREF. If the 13 April level is biased, this and the ice are
   the first two suspects, in that order.
3. **No scored flood extent** — by cost, not data availability (section 8). The
   reference scenes exist and are named there.
4. **Minija is a constant**, derived not observed (section 6).
5. **The sea boundary is still GTSM + bias correction**, not observed hourly
   Klaipėda levels — the same open item as Xaver
   (`~/curonian/docs/curonian_sla_boundary_correction.md`). A4 makes the boundary's
   behaviour a scored quantity rather than an assumption, and is the criterion most
   likely to fail for reasons outside the lagoon.
6. **The 1-day Nemunas lag is inherited from Xaver.** A flood wave travels faster
   than a low-flow wave, so 1 day may be too long at 2150 m³/s. Kept for
   comparability; the obvious sensitivity test if A2a fails.
7. **One forcing variant only** (section 7).

## 11. Build sequence

Geometry is **not** rebuilt — it is event-independent and already committed.
`make_channels` in particular must not be re-run casually: it reads live Overpass
data. The bathymetry is event-independent but **git-ignored**, so it is reused from
disk if present and regenerated with `prep.make_bathymetry` if not.

```
1. common.py            Event dataclass + registry; both events              (no run)
2. move + re-point      inputs/*.csv -> inputs/xaver_2013/, plus the four
                        ignored bulk files, every path literal, .gitignore,
                        and the README paths; gate: 80 passed 0 skipped      (no run)
3. prep/*, build_model, validate   thread `event` through; --event flag;
                        criteria() splits; README commands gain --event      (no run)
4. tests                80 still green; new tests per section 9
5. fetch April LHMT fixture   tests/data/lhmt_smalininkai_2013_04.csv via api.meteo.lt
6. prep.fetch_gtsm --event april_2013        CDS fetch, months 04-05
7. prep.make_forcing --event april_2013      writes inputs/april_2013/*
8. build_model.py --event april_2013         builds runs/april_2013 (~5 min)
9. ../run_sfincs.sh runs/april_2013 16       (~55-60 min)
10. validate.py --event april_2013           writes results/april_2013/*
11. app/sfincs_data.py   VARIANT_LABELS entry AND _PERIOD_RE + the "Storm window
                         only" switch label generalised; parser test
12. curonian/README.md   results section, run log, criteria table
```

Steps 1–4 are a complete, independently valuable unit: the refactor lands with the
existing event still green before any April data is fetched. If the CDS fetch or the
run fails, the repository is not left mid-surgery.

## 12. Out of scope

Gridded wind and pressure variants for April; a third event; re-running Xaver; any
change to geometry, bathymetry, channels or the subgrid; the observed-hourly sea
boundary; ice modelling of any kind.

**Recorded follow-up, not scope:** a scored flood-extent criterion against the
Landsat scenes named in section 8. It needs a water mask (MNDWI or NIR threshold),
SLC-gap filling, cloud masking, and a chosen skill metric (critical success index
against the modelled extent) — a spec of its own.
