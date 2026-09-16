# April 2013 Nemunas Freshet Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Hindcast the April 2013 Nemunas spring freshet with the existing Curonian Lagoon SFINCS model, scored at four gauges, by making "which event" an explicit parameter instead of a set of module-level constants.

**Architecture:** An `Event` frozen dataclass in `curonian/common.py` holds everything that differs between hindcasts (period, windows, forcing constants, criteria function). It is threaded through every script as an explicit parameter — never selected at import — and every entry point grows `--event`, defaulting to `xaver_2013` so no existing command changes behaviour. Event-specific forcing moves into `inputs/<event>/`; static geometry stays in `inputs/`.

**Tech Stack:** Python 3.11 in the `hydromt-sfincs` micromamba env; pandas, geopandas, netCDF4, rasterio, xarray; hydromt_sfincs 1.2.2; pytest; SFINCS v2.4.0 Galibier (Fortran binary).

**Spec:** [`docs/superpowers/specs/2026-09-16-april-2013-nemunas-flood-design.md`](../specs/2026-09-16-april-2013-nemunas-flood-design.md)

## Global Constraints

- **Env:** every python command runs as `micromamba run -n hydromt-sfincs python ...` from `curonian/`. The app tests use a different env: `micromamba run -n shiny python -m pytest app/test_sfincs_data.py -q` from the repo root.
- **Test gate after every task: `80 passed, 0 skipped`** (plus any new tests). A skip is a failure signal, not a pass — two suite tests skip when a `common.INPUTS / ...` file is missing, which is exactly the mistake Task 2 can make. The one acceptable skip is `test_fixture_still_matches_the_live_lhmt_record` when api.meteo.lt is unreachable, and it must be identified **by name**: `pytest tests -q -rs`.
- **Run the model suite from the main checkout, not a worktree** — two integration tests need git-ignored files and fail rather than skip elsewhere.
- **Never run `prep.make_channels`** (live Overpass API). **Never re-run `prep.make_forcing` for `xaver_2013`** — it overwrites committed, provenance-tested files.
- **CDS calls cost quota**: `prep.fetch_gtsm` and `prep.fetch_era5_grid` hit the Copernicus API. Only Task 9 may call one, and only for April.
- **Xaver's outputs must stay byte-identical.** `git diff --stat curonian/inputs/` must be empty (beyond renames) through Tasks 1–8. `tests/test_forcing_provenance.py` is the instrument.
- **Existing constants stay:** `TREF`, `TSTOP`, `CALM_WINDOW`, `MINIJA_Q_DEC`, `RUN_XAVER` keep their names and values as the Xaver event's data.
- Values copied verbatim from the spec: April `tref=2013-04-05 00:00`, `tstop=2013-05-02 00:00`, `calm_window=(2013-04-05, 2013-04-11)`, `score_window=(2013-04-13, 2013-05-02)`, `data_window=("2013-03-26","2013-05-12")`, `peak_window=("2013-04-19","2013-04-25")`, `gtsm_months=("04","05")`, `minija_q=83.0`, `nemunas_lag_days=1`, `wind_check=None`, `zsini=-0.17`.

---

## File Structure

| File | Responsibility | Task |
| --- | --- | --- |
| `curonian/common.py` | `Event` dataclass, `EVENTS` registry, `MINIJA_Q_APR`; existing constants unchanged | 1 |
| `curonian/inputs/xaver_2013/` | Xaver's forcing, moved out of `inputs/` | 2 |
| `.gitignore` | patterns that survive the move | 2 |
| `curonian/prep/make_forcing.py` | takes `event` + a static root; adds the wind span guard | 3 |
| `curonian/prep/fetch_gtsm.py`, `fetch_era5_grid.py` | per-event CDS request and output paths | 4 |
| `curonian/build_model.py` | `--event` composes with `--run-name`; `zsini` from the event | 5 |
| `curonian/validate.py` | `criteria()` dispatches to `xaver_criteria` / `april_criteria`; event titles | 6, 7 |
| `curonian/tests/data/lhmt_smalininkai_2013_04.csv` | April provenance fixture | 8 |
| `app/sfincs_data.py` | window-heading regex, variant label | 11 |
| `curonian/README.md` | paths (Task 2), commands (Task 3), results (Task 11) | 2, 3, 11 |

---

### Task 1: The Event dataclass and registry

**Files:**
- Modify: `curonian/common.py` (append after `MINIJA_Q_DEC`, around line 45)
- Test: `curonian/tests/test_common.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `common.Event` (frozen dataclass, fields as in spec §4 including `score_label`), `common.EVENTS: dict[str, Event]`, `common.event(name: str) -> Event`, `common.MINIJA_Q_APR: float`. **No `criteria` field** — see Task 6. `Event.inputs_dir -> Path` is a property; **there is deliberately no `run_dir` property** — run directories are keyed by run name, not event name.

- [ ] **Step 1: Write the failing tests**

Append to `curonian/tests/test_common.py`:

```python
def test_registry_holds_both_events_keyed_by_name():
    assert set(common.EVENTS) == {"xaver_2013", "april_2013"}
    for name, ev in common.EVENTS.items():
        assert ev.name == name


def test_xaver_event_carries_todays_constants_unchanged():
    ev = common.event("xaver_2013")
    assert (ev.tref, ev.tstop) == (common.TREF, common.TSTOP)
    assert ev.calm_window == common.CALM_WINDOW
    assert ev.minija_q == common.MINIJA_Q_DEC
    assert ev.data_window == ("2013-11-20", "2013-12-20")   # today's SQL literals
    assert ev.score_window == (pd.Timestamp("2013-12-05"), pd.Timestamp("2013-12-09"))
    assert ev.zsini is None                                  # taken from the boundary
    assert ev.wind_check == (15.0, "the Xaver gale")
    assert ev.score_label == "Storm window"             # today's report heading


def test_april_event_matches_the_spec():
    ev = common.event("april_2013")
    assert ev.tref == pd.Timestamp("2013-04-05 00:00")
    assert ev.tstop == pd.Timestamp("2013-05-02 00:00")
    assert ev.calm_window == (pd.Timestamp("2013-04-05"), pd.Timestamp("2013-04-11"))
    assert ev.score_window == (pd.Timestamp("2013-04-13"), pd.Timestamp("2013-05-02"))
    assert ev.data_window == ("2013-03-26", "2013-05-12")
    assert ev.gtsm_months == ("04", "05")
    assert ev.minija_q == common.MINIJA_Q_APR == 83.0
    assert ev.wind_check is None
    assert ev.zsini == -0.17
    assert ev.score_label == "Scoring window"


def test_inputs_dir_derives_from_the_name_and_run_dir_does_not():
    ev = common.event("april_2013")
    assert ev.inputs_dir == common.INPUTS / "april_2013"
    assert not hasattr(ev, "run_dir"), (
        "run directories are keyed by run name, not event name: one event owns "
        "xaver_2013, xaver_2013_gridwind and xaver_2013_gridwind_pressure")


def test_events_are_frozen():
    with pytest.raises(Exception):
        common.event("xaver_2013").minija_q = 99.0


def test_unknown_event_names_itself_and_the_alternatives():
    with pytest.raises(KeyError, match="april_2013"):
        common.event("april2013")
```

- [ ] **Step 2: Run them to verify they fail**

Run: `cd curonian && micromamba run -n hydromt-sfincs python -m pytest tests/test_common.py -q`
Expected: FAIL with `AttributeError: module 'common' has no attribute 'EVENTS'`

- [ ] **Step 3: Implement the dataclass and registry**

In `curonian/common.py`, add to the imports:

```python
from dataclasses import dataclass
```

and after the `MINIJA_Q_DEC` / `NEMUNAS_LAG_DAYS` block:

```python
# April's Minija constant. The DB's Minija record ends in 2011, so April gets a
# constant as December does. Anomaly-scaled rather than climatological: the Nemunas
# mean over the April run window (1279 m3/s) is 1.56x its April climatology (820
# m3/s over 25 Aprils, 1990-2014), and 1.56 x the Minija's own April climatology at
# Lankupiai (53) = 83. Inside the observed April range there (max 272).
MINIJA_Q_APR = 83.0


@dataclass(frozen=True)
class Event:
    """One hindcast period and everything that differs between hindcasts.

    Passed explicitly, never selected at import: an import-time global would make
    test outcomes depend on import order and hide which event a script ran for.
    """
    name: str
    title: str                                        # report and figure titles
    tref: pd.Timestamp
    tstop: pd.Timestamp
    calm_window: tuple                                # GTSM bias correction
    score_window: tuple                               # criteria are judged here
    data_window: tuple                                # observation query/slice bounds
    peak_window: tuple                                # forcing_summary.txt slice
    peak_label: str
    gtsm_months: tuple
    minija_q: float
    nemunas_lag_days: int
    wind_check: tuple | None                          # (min peak m/s, what it is)
    zsini: float | None                               # None = take it from the boundary
    score_label: str                                  # the report's window heading

    @property
    def inputs_dir(self) -> Path:
        return INPUTS / self.name


# No run_dir property: run directories are keyed by RUN NAME, not event name.
# xaver_2013 alone owns runs/xaver_2013, runs/xaver_2013_gridwind and
# runs/xaver_2013_gridwind_pressure, selected by --run-name / --run.
EVENTS = {
    "xaver_2013": Event(
        name="xaver_2013", title="Xaver 2013",
        tref=TREF, tstop=TSTOP, calm_window=CALM_WINDOW,
        # Xaver scores C1/C3 on the four-day storm, not the thirteen-day run.
        score_window=(pd.Timestamp("2013-12-05"), pd.Timestamp("2013-12-09")),
        # Today's literals, kept verbatim: test_forcing_provenance proves the
        # refactor changed no bytes, and tref-8d..tstop+9d is not a round pad.
        data_window=("2013-11-20", "2013-12-20"),
        peak_window=("2013-12-05", "2013-12-08"), peak_label="storm",
        gtsm_months=("11", "12"), minija_q=MINIJA_Q_DEC,
        nemunas_lag_days=NEMUNAS_LAG_DAYS,
        wind_check=(15.0, "the Xaver gale"), zsini=None,
        score_label="Storm window"),
    "april_2013": Event(
        name="april_2013", title="April 2013 Nemunas freshet",
        tref=pd.Timestamp("2013-04-05 00:00"), tstop=pd.Timestamp("2013-05-02 00:00"),
        calm_window=(pd.Timestamp("2013-04-05"), pd.Timestamp("2013-04-11")),
        score_window=(pd.Timestamp("2013-04-13"), pd.Timestamp("2013-05-02")),
        data_window=("2013-03-26", "2013-05-12"),
        peak_window=("2013-04-19", "2013-04-25"), peak_label="crest",
        gtsm_months=("04", "05"), minija_q=MINIJA_Q_APR,
        nemunas_lag_days=NEMUNAS_LAG_DAYS,
        # No wind signature to assert in a freshet; the span guard in
        # make_forcing.wind_forcing still runs. See spec section 6.
        wind_check=None,
        # The lagoon stands above the sea at TREF (Nida -0.10, Uostadvaris -0.13,
        # Vente -0.28 m; Klaipeda -0.36), so taking zsini from the boundary would
        # start the whole lagoon ~0.23 m low. Mean of the three lagoon gauges.
        zsini=-0.17,
        score_label="Scoring window"),
}


def event(name: str) -> Event:
    if name not in EVENTS:
        raise KeyError(f"unknown event {name!r}; known: {', '.join(sorted(EVENTS))}")
    return EVENTS[name]
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd curonian && micromamba run -n hydromt-sfincs python -m pytest tests -q -rs`
Expected: the 80 existing tests plus the 6 new ones, **0 skipped**

- [ ] **Step 5: Commit**

```bash
git add curonian/common.py curonian/tests/test_common.py
git commit -m "Make the hindcast period an Event, not a module constant"
```

---

### Task 2: Move Xaver's forcing into inputs/xaver_2013/

**Files:**
- Move: `curonian/inputs/{bzs,dis,wind,gtsm_klaipeda}.csv`, `forcing_summary.txt`, `era5_grid_summary.txt` → `curonian/inputs/xaver_2013/`
- Move (ignored, plain `mv`): `era5_grid_xaver.nc` → `xaver_2013/era5_grid.nc`; `era5_raw_2013_11_12.nc` → `xaver_2013/era5_raw.nc`; `gtsm_2013_11_12.zip` → `xaver_2013/gtsm.zip`; `gtsm_2013_11_12/` → `xaver_2013/gtsm/`
- Modify: `.gitignore`, `curonian/prep/make_forcing.py`, `curonian/build_model.py`, `curonian/prep/fetch_era5_grid.py`, `curonian/prep/fetch_gtsm.py`, `curonian/tests/test_fetch_era5_grid.py`, `curonian/tests/test_forcing_provenance.py`, `curonian/README.md`

**Interfaces:**
- Consumes: `common.event("xaver_2013").inputs_dir` from Task 1.
- Produces: every Xaver forcing path now under `inputs/xaver_2013/`. Function signatures do **not** change yet — that is Task 3. This task only re-points literals to `common.EVENTS["xaver_2013"].inputs_dir`.

**This cannot be a pure move.** The moment `inputs/dis.csv` moves, `make_forcing.main(inputs=common.INPUTS)` writes to the old place and `test_forcing_provenance` reads a file that is not there. Move and re-point in one commit; git still records the renames.

- [ ] **Step 1: Verify the .gitignore gap before moving anything**

```bash
cd /home/razinka/sfincs
git check-ignore -q curonian/inputs/xaver_2013/gtsm.zip && echo IGNORED || echo "NOT ignored"
```
Expected: `NOT ignored` — `curonian/inputs/*.zip` matches one level only. This is what Step 2 fixes.

- [ ] **Step 2: Fix .gitignore first, so the 79 MB zip is never exposed**

In `.gitignore`, replace:

```
curonian/inputs/*.zip
curonian/inputs/gtsm_2013_11_12/
```

with:

```
curonian/inputs/*.zip
curonian/inputs/*/*.zip
curonian/inputs/*/gtsm/
```

Verify:

```bash
git check-ignore -q curonian/inputs/xaver_2013/gtsm.zip && echo IGNORED || echo "NOT ignored"
git check-ignore -q curonian/inputs/xaver_2013/dis.csv && echo "WRONGLY IGNORED" || echo "tracked, correct"
```
Expected: `IGNORED` then `tracked, correct`.

- [ ] **Step 3: Move the files**

```bash
cd /home/razinka/sfincs/curonian
mkdir -p inputs/xaver_2013
git mv inputs/bzs.csv inputs/dis.csv inputs/wind.csv inputs/gtsm_klaipeda.csv \
       inputs/forcing_summary.txt inputs/era5_grid_summary.txt inputs/xaver_2013/
mv inputs/era5_grid_xaver.nc       inputs/xaver_2013/era5_grid.nc
mv inputs/era5_raw_2013_11_12.nc   inputs/xaver_2013/era5_raw.nc
mv inputs/gtsm_2013_11_12.zip      inputs/xaver_2013/gtsm.zip
mv inputs/gtsm_2013_11_12          inputs/xaver_2013/gtsm
```

- [ ] **Step 4: Run the suite to see exactly what breaks**

Run: `cd curonian && micromamba run -n hydromt-sfincs python -m pytest tests -q -rs`
Expected: failures in `test_forcing_provenance.py` (file not found) and **skips** in the two guarded tests. Note the skip names — they are the ones Step 5 must bring back to green, and a skip here is a failure signal.

- [ ] **Step 5: Re-point every path literal**

`XAVER = common.EVENTS["xaver_2013"]` is the temporary anchor in each module; Task 3 replaces it with the passed-in event.

- `prep/make_forcing.py`: in `main()`, `inputs / "gtsm_klaipeda.csv"`, and the four writes (`bzs.csv`, `wind.csv`, `dis.csv`, `forcing_summary.txt`) → `XAVER.inputs_dir / ...`. **`boundary_points.geojson` (read) and `dis_points.geojson` (write) stay on `common.INPUTS`** — they are static and shared.
- `build_model.py`: `bzs.csv`, `dis.csv`, `wind.csv` → `XAVER.inputs_dir / ...`; `era5_grid_xaver.nc` → `XAVER.inputs_dir / "era5_grid.nc"` at **`:108` and `:118`**, and in the two argparse help strings at **`:57` and `:59`**, which name the file to the user. `boundary_points.geojson`, `dis_points.geojson`, `stations.geojson` stay on `common.INPUTS`.
- `prep/fetch_era5_grid.py`: the **writer** at `:144` (`out = common.INPUTS / "era5_grid_xaver.nc"`) → `XAVER.inputs_dir / "era5_grid.nc"`, the raw cache → `era5_raw.nc`, the summary → `XAVER.inputs_dir / "era5_grid_summary.txt"`, and the docstring references at `:5`, `:101`, `:171`.
- `prep/fetch_gtsm.py`: the `download()` default at `:35` → `XAVER.inputs_dir / "gtsm.zip"`, plus the extract directory and the `gtsm_klaipeda.csv` write.
- `tests/test_fetch_era5_grid.py:102`: `common.INPUTS / "era5_grid_xaver.nc"` → `XAVER.inputs_dir / "era5_grid.nc"`.
- `tests/test_forcing_provenance.py:33`: `common.INPUTS / "dis.csv"` → `XAVER.inputs_dir / "dis.csv"`.
- `curonian/README.md`: the clean-checkout regeneration list and the test-suite paragraph name `inputs/gtsm_klaipeda.csv` and the three ignored files by their pre-move paths. Update all of them here — the README is wrong from this commit onward, not from Task 11.

- [ ] **Step 6: Run the suite and require zero skips**

Run: `cd curonian && micromamba run -n hydromt-sfincs python -m pytest tests -q -rs`
Expected: the same count as after Task 1, **0 skipped**. **If any test skips, a path literal was missed** — find it by name in the `-rs` output rather than accepting the count.

- [ ] **Step 7: Prove no bytes changed**

```bash
cd /home/razinka/sfincs && git diff --cached --stat -M
```
Expected: the six tracked files shown as pure renames (`R100`). Any content diff means something rewrote a file and must be investigated before committing.

- [ ] **Step 8: Commit**

```bash
git add -A .gitignore curonian/
git commit -m "Move Xaver's forcing into inputs/xaver_2013/"
```

---

### Task 3: Thread the event through make_forcing

**Files:**
- Modify: `curonian/prep/make_forcing.py`
- Test: `curonian/tests/test_make_forcing.py`

**Interfaces:**
- Consumes: `common.Event` (Task 1); paths under `event.inputs_dir` (Task 2).
- Produces: `load_gauge_levels(site, event)`, `discharge_forcing(event)`, `wind_forcing(event, era5_path=common.ERA5_2013)`, `boundary_forcing(gtsm, npoints, event)`, `cmems_daily_boundary(event, path=..., lonlat=...)`, `main(event, static=common.INPUTS, use_cmems=False)`, and a module-level `parse_args(argv=None)` accepting `--event`. `bias_correct(model, obs, window)` is unchanged.

- [ ] **Step 1: Write the failing tests**

Add to `curonian/tests/test_make_forcing.py`:

```python
APRIL = common.event("april_2013")
XAVER = common.event("xaver_2013")


@pytest.mark.parametrize("ev", [XAVER, APRIL], ids=lambda e: e.name)
def test_boundary_forcing_spans_whichever_event_it_is_given(ev):
    t = pd.date_range(ev.tref - pd.Timedelta("1D"), ev.tstop + pd.Timedelta("1D"), freq="h")
    gtsm = pd.Series(np.linspace(0, 1, len(t)), index=t)
    df = mf.boundary_forcing(gtsm, npoints=7, event=ev)
    assert df.index[0] == ev.tref and df.index[-1] == ev.tstop
    assert df.notna().all().all()


def test_wind_check_none_skips_the_peak_assertion_but_not_the_span_guard():
    """April has no gale to assert -- but an empty slice must still fail loudly."""
    t = pd.date_range(APRIL.tref - pd.Timedelta("1h"), APRIL.tstop + pd.Timedelta("1h"), freq="h")
    calm = pd.DataFrame({"mag": 5.0, "dir": 180.0}, index=t)
    mf.check_wind(calm, APRIL)                      # no raise: wind_check is None

    with pytest.raises(ValueError, match="does not cover"):
        mf.check_wind(calm.iloc[:10], APRIL)        # truncated -> raises anyway


def test_wind_check_still_demands_the_gale_for_xaver():
    t = pd.date_range(XAVER.tref - pd.Timedelta("1h"), XAVER.tstop + pd.Timedelta("1h"), freq="h")
    calm = pd.DataFrame({"mag": 5.0, "dir": 180.0}, index=t)
    with pytest.raises(ValueError, match="Xaver gale"):
        mf.check_wind(calm, XAVER)


@pytest.mark.integration
def test_april_discharge_carries_the_freshet_and_its_own_minija():
    q = mf.discharge_forcing(APRIL)
    assert q.index[0] == APRIL.tref and q.index[-1] == APRIL.tstop
    assert 2000 < q[1].loc["2013-04-19":"2013-04-21"].max() < 2300      # the crest
    assert (q[2] == common.MINIJA_Q_APR).all()


@pytest.mark.integration
def test_april_gauge_levels_reach_the_observed_crest():
    obs = mf.load_gauge_levels("Uostadvaris", APRIL)
    assert abs(obs.loc["2013-04-24 06:00"] - 0.54) < 1e-9
```

- [ ] **Step 2: Run them to verify they fail**

Run: `cd curonian && micromamba run -n hydromt-sfincs python -m pytest tests/test_make_forcing.py -q`
Expected: FAIL — `boundary_forcing() got an unexpected keyword argument 'event'`, `module 'prep.make_forcing' has no attribute 'check_wind'`.

- [ ] **Step 3: Implement the threading and extract the wind guard**

In `curonian/prep/make_forcing.py`:

```python
def load_gauge_levels(site: str, event: common.Event) -> pd.Series:
    df = common.read_table(
        "SELECT date, wlevel_06, wlevel_18 FROM physical_daily WHERE site=? AND date BETWEEN ? AND ?",
        (site, *event.data_window))
    ...  # body unchanged


def check_wind(df: pd.DataFrame, event: common.Event) -> None:
    """Guard the wind series. The span check runs for every event; the peak check
    only where the event has a signature worth asserting.

    Without the span check, an event with wind_check=None would accept a truncated
    or empty slice and hand SFINCS a wind file that does not cover the run.
    """
    if df.empty or df.index[0] > event.tref - pd.Timedelta("1h") or df.index[-1] < event.tstop + pd.Timedelta("1h"):
        span = f"{df.index[0]}..{df.index[-1]}" if not df.empty else "empty"
        raise ValueError(f"wind series {span} does not cover {event.name} "
                         f"({event.tref}..{event.tstop})")
    if not df.notna().all().all():
        raise ValueError(f"wind series has NaN in {df.columns[df.isna().any()].tolist()}")
    if event.wind_check is not None:
        floor, what = event.wind_check
        if df["mag"].max() <= floor:
            raise ValueError(f"peak wind is only {df['mag'].max():.1f} m/s -- expected "
                             f"{what} (>{floor:g} m/s)")


def wind_forcing(event: common.Event, era5_path: Path = common.ERA5_2013) -> pd.DataFrame:
    ...  # read as today
    df = df.loc[event.tref - pd.Timedelta("1h"): event.tstop + pd.Timedelta("1h")]
    check_wind(df, event)
    return df


def discharge_forcing(event: common.Event) -> pd.DataFrame:
    df = common.read_table(
        "SELECT date, discharge_m3s FROM river_discharge WHERE river='Nemunas' AND gauge='Smalininkai' "
        "AND date BETWEEN ? AND ? ORDER BY date", event.data_window)
    daily = pd.Series(df["discharge_m3s"].values, index=pd.to_datetime(df["date"]))
    nem = lag_and_resample(daily, event.nemunas_lag_days, event.tref, event.tstop)
    if not nem.notna().all() or nem.index[0] != event.tref or nem.index[-1] != event.tstop:
        raise ValueError(f"Nemunas discharge does not cover {event.name} cleanly: "
                         f"{nem.index[0]}..{nem.index[-1]} with {int(nem.isna().sum())} NaN")
    return pd.DataFrame({1: nem.values, 2: event.minija_q}, index=nem.index)
```

`cmems_daily_boundary` takes the event too — it is the **third** copy of the December literal and the one an implementer misses:

```python
def cmems_daily_boundary(event: common.Event, path: Path = ..., lonlat=common.KLAIPEDA_MOUTH_LONLAT) -> pd.Series:
    ...
    daily = pd.Series(sla, index=t + pd.Timedelta(hours=12)).loc[event.data_window[0]:event.data_window[1]]
```

`main()` takes both roots and writes the summary with the event's own labels:

```python
def main(event: common.Event, static: Path = common.INPUTS, use_cmems: bool = False) -> None:
    out = event.inputs_dir
    out.mkdir(parents=True, exist_ok=True)
    gtsm = cmems_daily_boundary(event) if use_cmems else \
        pd.read_csv(out / "gtsm_klaipeda.csv", index_col=0, parse_dates=True)["waterlevel_m"]
    klaipeda = load_gauge_levels("Klaipeda", event)
    klaipeda_06 = klaipeda.loc[klaipeda.index.hour == 6]
    corrected, offset = bias_correct(gtsm, klaipeda_06, event.calm_window)
    bnd_pts = gpd.read_file(static / "boundary_points.geojson")          # static
    boundary_forcing(corrected, len(bnd_pts), event).to_csv(
        out / "bzs.csv", index_label="time", float_format=common.CSV_FLOAT_FMT)

    wind_forcing(event).to_csv(out / "wind.csv", index_label="time", float_format=common.CSV_FLOAT_FMT)
    dis = discharge_forcing(event)
    dis.to_csv(out / "dis.csv", index_label="time", float_format=common.CSV_FLOAT_FMT)
    common.write_geojson(discharge_points(), static / "dis_points.geojson")   # static, shared

    peak = corrected.loc[event.peak_window[0]:event.peak_window[1]]
    summary = (f"GTSM offset applied: {offset:+.3f} m (calm window ...)\n"
               f"boundary level: start {corrected.loc[event.tref]:.2f} m, "
               f"{event.peak_label} peak {peak.max():.2f} m at {peak.idxmax()}\n" ...)
    (out / "forcing_summary.txt").write_text(summary)


def parse_args(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--event", default="xaver_2013", choices=sorted(common.EVENTS))
    p.add_argument("--cmems", action="store_true", help="daily CMEMS fallback sea boundary")
    return p.parse_args(argv)
```

- [ ] **Step 4: Run the tests**

Run: `cd curonian && micromamba run -n hydromt-sfincs python -m pytest tests -q -rs`
Expected: the previous count plus 6 (the boundary test is parametrized over two events), **0 skipped**.

- [ ] **Step 5: Prove Xaver's forcing is untouched**

Do **not** re-run `make_forcing` for Xaver to check this — it would overwrite the
committed, provenance-tested files, which is the thing being protected. Check
instead that nothing wrote to them and that they still match LHMT:

```bash
cd /home/razinka/sfincs
git status --short curonian/inputs/xaver_2013/          # must print nothing
cd curonian && micromamba run -n hydromt-sfincs python -m pytest tests/test_forcing_provenance.py -q -rs
```
Expected: no output from `git status`, and the provenance tests pass — the exact
14-day match against the LHMT fixture is what proves the bytes are the originals.

If you do want to prove the *refactored code* still produces those bytes, do it in
a scratch directory: build a throwaway `Event` with `inputs_dir` pointed at
`tmp_path`, copy `gtsm_klaipeda.csv` in, run `make_forcing.main` against it, and
`filecmp.cmp` the four outputs against the committed ones. That belongs in a test,
not in a manual step.

- [ ] **Step 6: Update the README build commands**

Both copies of the command block in `curonian/README.md` gain `--event xaver_2013` (explicit, even though it is the default, so the second event is discoverable).

- [ ] **Step 7: Commit**

```bash
git add curonian/prep/make_forcing.py curonian/tests/test_make_forcing.py curonian/README.md
git commit -m "Thread the event through make_forcing, and give the wind guard a floor"
```

---

### Task 4: Thread the event through the CDS fetchers

**Files:**
- Modify: `curonian/prep/fetch_gtsm.py`, `curonian/prep/fetch_era5_grid.py`
- Test: `curonian/tests/test_fetch_gtsm.py`, `curonian/tests/test_fetch_era5_grid.py`

**Interfaces:**
- Consumes: `common.Event`.
- Produces: `fetch_gtsm.request(event) -> dict`, `fetch_gtsm.download(event, target=None)`, `fetch_gtsm.main(event)`; `fetch_era5_grid.main(event)`. Both write into `event.inputs_dir`. **Neither is executed in this task** — only its path and request construction is tested.

- [ ] **Step 1: Write the failing tests**

```python
def test_gtsm_request_months_come_from_the_event():
    assert fg.request(common.event("xaver_2013"))["month"] == ["11", "12"]
    assert fg.request(common.event("april_2013"))["month"] == ["04", "05"]


def test_gtsm_downloads_into_the_event_directory():
    assert fg.target_for(common.event("april_2013")) == common.INPUTS / "april_2013" / "gtsm.zip"
    assert fg.target_for(common.event("xaver_2013")) == common.INPUTS / "xaver_2013" / "gtsm.zip"
```

- [ ] **Step 2: Run to verify failure**

Run: `cd curonian && micromamba run -n hydromt-sfincs python -m pytest tests/test_fetch_gtsm.py -q`
Expected: FAIL — `module 'prep.fetch_gtsm' has no attribute 'request'`.

- [ ] **Step 3: Implement**

```python
def request(event: common.Event) -> dict:
    return {**REQUEST_BASE, "month": list(event.gtsm_months)}


def target_for(event: common.Event) -> Path:
    return event.inputs_dir / "gtsm.zip"


def download(event: common.Event, target: Path | None = None) -> Path:
    import cdsapi
    target = target or target_for(event)
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists() and target.stat().st_size > 1_000_000:
        print(f"using cached {target}")
        return target
    cdsapi.Client().retrieve(DATASET, request(event), str(target))
    return target
```

`REQUEST_BASE` is today's `REQUEST` minus `month`. `fetch_era5_grid` takes `event`
the same way, writing `event.inputs_dir / "era5_raw.nc"`, `"era5_grid.nc"` and
`"era5_grid_summary.txt"`, and slicing to `[event.tref - 1h, event.tstop + 1h]`.

**Both modules need a CLI added, not just threaded.** Today `fetch_gtsm.main()`
takes no arguments and the entry point is a bare `main()`:

```python
def parse_args(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--event", default="xaver_2013", choices=sorted(common.EVENTS))
    return p.parse_args(argv)


if __name__ == "__main__":
    main(common.event(parse_args().event))
```

`import argparse` goes at the top of each. Task 9 invokes exactly this interface, so
if it is missed there, `python -m prep.fetch_gtsm --event april_2013` fails with
`unrecognized arguments` before spending any CDS quota — noisy, not silent.

- [ ] **Step 4: Run the tests**

Run: `cd curonian && micromamba run -n hydromt-sfincs python -m pytest tests -q -rs`
Expected: the previous count plus 2, **0 skipped**.

- [ ] **Step 5: Commit**

```bash
git add curonian/prep/fetch_gtsm.py curonian/prep/fetch_era5_grid.py curonian/tests/
git commit -m "Make the CDS fetchers take an event"
```

---

### Task 5: Thread the event through build_model

**Files:**
- Modify: `curonian/build_model.py`
- Test: `curonian/tests/test_build_model.py`

**Interfaces:**
- Consumes: `common.Event`; `event.inputs_dir` forcing from Task 3.
- Produces: `build(event, run_dir=None, subgrid=True, wind="uniform", pressure=False)` where `run_dir` defaults to `common.RUNS / event.name`; `parse_args` accepting `--event` **and** the existing `--run-name`.

- [ ] **Step 1: Write the failing tests**

```python
def test_event_and_run_name_compose():
    args = bm.parse_args([])
    assert args.event == "xaver_2013" and args.run_name == "xaver_2013"

    args = bm.parse_args(["--event", "april_2013"])
    assert args.run_name == "april_2013", "run name defaults to the event's name"

    args = bm.parse_args(["--event", "xaver_2013", "--wind", "grid",
                          "--run-name", "xaver_2013_gridwind"])
    assert (args.event, args.run_name) == ("xaver_2013", "xaver_2013_gridwind")


def test_april_config_uses_the_events_clock_and_initial_level(monkeypatch):
    """zsini comes from the event when it sets one, not from the sea boundary."""
    ev = common.event("april_2013")
    cfg = bm.config_for(ev, zs_boundary=-0.36)
    assert cfg["tstart"] == "20130405 000000" and cfg["tstop"] == "20130502 000000"
    assert cfg["zsini"] == -0.17

    cfg = bm.config_for(common.event("xaver_2013"), zs_boundary=0.389)
    assert cfg["zsini"] == 0.389, "Xaver keeps taking zsini from the boundary"
```

- [ ] **Step 2: Run to verify failure**

Run: `cd curonian && micromamba run -n hydromt-sfincs python -m pytest tests/test_build_model.py -q`
Expected: FAIL — `unrecognized arguments: --event`.

- [ ] **Step 3: Implement**

```python
def config_for(event: common.Event, zs_boundary: float) -> dict:
    """SFINCS config for this event. zsini is the event's if it sets one.

    Xaver leaves zsini=None and takes the sea boundary's first value, which was
    within 0.05-0.11 m of its lagoon gauges. April's lagoon stands ~0.23 m above
    the sea at TREF, so the boundary would start the whole lagoon low.
    """
    return dict(
        tref=event.tref.strftime("%Y%m%d %H%M%S"), tstart=event.tref.strftime("%Y%m%d %H%M%S"),
        tstop=event.tstop.strftime("%Y%m%d %H%M%S"),
        advection=1, alpha=0.5, huthresh=0.05, viscosity=1,
        dtout=3600, dthisout=600, dtmaxout=99999999,
        manning_land=MANNING_LAND, manning_sea=MANNING_SEA,
        zsini=event.zsini if event.zsini is not None else zs_boundary,
    )


def build(event: common.Event, run_dir: Path | None = None, subgrid: bool = True,
          wind: str = "uniform", pressure: bool = False):
    run_dir = run_dir or common.RUNS / event.name
    inputs, static = event.inputs_dir, common.INPUTS
    ...
    bzs = _read_ts(inputs / "bzs.csv")
    sf.setup_config(**config_for(event, zs_boundary=float(bzs.iloc[0].mean())))
    sf.setup_waterlevel_forcing(timeseries=bzs,
        locations=gpd.read_file(static / "boundary_points.geojson").set_index("index", drop=False))
    sf.setup_discharge_forcing(timeseries=_read_ts(inputs / "dis.csv"),
        locations=gpd.read_file(static / "dis_points.geojson").set_index("index", drop=False))
    if wind == "grid":
        sf.setup_wind_forcing_from_grid(wind=str(inputs / "era5_grid.nc"))
    else:
        sf.setup_wind_forcing(timeseries=str(inputs / "wind.csv"))
    if pressure:
        sf.setup_pressure_forcing_from_grid(press=str(inputs / "era5_grid.nc"))
    sf.setup_observation_points(locations=gpd.read_file(static / "stations.geojson"))
```

and in `parse_args`, `--run-name` defaults to `None` and is resolved after parsing:

```python
p.add_argument("--event", default="xaver_2013", choices=sorted(common.EVENTS))
p.add_argument("--run-name", default=None, help="subdirectory of runs/; defaults to the event name")
args = p.parse_args(argv)
args.run_name = args.run_name or args.event
```

- [ ] **Step 4: Run the tests**

Run: `cd curonian && micromamba run -n hydromt-sfincs python -m pytest tests -q -rs`
Expected: the previous count plus 2, **0 skipped**.

- [ ] **Step 5: Commit**

```bash
git add curonian/build_model.py curonian/tests/test_build_model.py
git commit -m "Build for an event, and take April's initial level from the lagoon"
```

---

### Task 6: Split the criteria without changing Xaver's

**Files:**
- Modify: `curonian/validate.py`
- Test: `curonian/tests/test_validate.py`

**Interfaces:**
- Consumes: `common.Event`.
- Produces: `xaver_criteria(his, obs_by_site, run_dir, window)` (today's body verbatim), `criteria(his, obs_by_site, run_dir=common.RUN_XAVER, window=VALIDATION_WINDOW, event=None)` dispatching to `event.criteria`, `main(event, run_dir=None)`, `parse_args` accepting `--event` and `--run`. the dispatch table `validate.CRITERIA` is keyed by event name.

**The dispatch keeps the nine existing `va.criteria(...)` call sites working unchanged**, which is what preserves the test gate.

- [ ] **Step 1: Write the failing test**

```python
def test_criteria_defaults_to_xaver(synth_run_dir):
    got = va.criteria(_base_his(), _base_obs(), synth_run_dir, window=SYNTH_WINDOW)
    assert got[0]["name"].startswith("C1")


def test_criteria_raises_rather_than_scoring_with_the_wrong_events_rules(synth_run_dir):
    class Fake:
        name = "not_an_event"
    with pytest.raises(KeyError):
        va.criteria(_base_his(), _base_obs(), synth_run_dir, window=SYNTH_WINDOW, event=Fake())


def test_event_and_run_compose_in_validate():
    assert va.parse_args([]).run == "xaver_2013"
    assert va.parse_args(["--event", "april_2013"]).run == "april_2013"
    assert va.parse_args(["--event", "april_2013", "--run", "april_2013_test"]).run == "april_2013_test"
```

- [ ] **Step 2: Run to verify failure**

Run: `cd curonian && micromamba run -n hydromt-sfincs python -m pytest tests/test_validate.py -q`
Expected: FAIL — `criteria() got an unexpected keyword argument 'event'`.

- [ ] **Step 3: Implement**

Rename today's `criteria` body to `xaver_criteria` **with no other change** (it keeps using the module-level `STORM_WINDOW`), then add:

```python
# Keyed by event name rather than held on the Event: a function reference on the
# dataclass would make common.py depend on validate.py having been imported, and an
# unset one would silently score April with Xaver's criteria instead of raising.
CRITERIA = {"xaver_2013": xaver_criteria, "april_2013": april_criteria}


def criteria(his, obs_by_site, run_dir=common.RUN_XAVER, window=VALIDATION_WINDOW, event=None):
    """Dispatch on the event. Defaults to Xaver so the nine existing call sites --
    and the existing verdicts -- are untouched. An unknown event raises KeyError
    rather than falling back to the wrong criteria."""
    return CRITERIA[event.name if event is not None else "xaver_2013"](
        his, obs_by_site, run_dir, window)
```

`main` takes the event and uses its title:

```python
def main(event: common.Event, run_dir: Path | None = None) -> None:
    run_dir = run_dir or common.RUNS / event.name
    his = load_his(run_dir)
    obs_by_site = {g: load_gauge_levels(g, event) for g in GAUGES}
    lines = [f"# {event.title} validation", "", f"Whole period: {_window_label((event.tref, event.tstop))}", ""]
    lines += _skill_table_lines(his, obs_by_site, window=None)
    # event.score_label is what app/sfincs_data._PERIOD_RE looks for -- see Task 11.
    lines += ["", f"{event.score_label}: {_window_label(event.score_window)}", ""]
    lines += _skill_table_lines(his, obs_by_site, window=event.score_window)
    ...
    crit = criteria(his, obs_by_site, run_dir, event=event)
```

and `flood_map`'s title uses `event.title` instead of the literal `"Xaver 2013"`.

- [ ] **Step 4: Run the tests**

Run: `cd curonian && micromamba run -n hydromt-sfincs python -m pytest tests -q -rs`
Expected: the previous count plus 2, **0 skipped**.

- [ ] **Step 5: Commit**

```bash
git add curonian/validate.py curonian/tests/test_validate.py
git commit -m "Dispatch the success criteria on the event"
```

---

### Task 7: April's criteria

**Files:**
- Modify: `curonian/validate.py`
- Test: `curonian/tests/test_validate.py`

**Interfaces:**
- Consumes: `xaver_criteria`'s helpers — `skill()`, `_flood_arrays()`, `_window_label()`, `c4_verdict()`.
- Produces: `april_criteria(his, obs_by_site, run_dir, window) -> list[dict]` returning six dicts named `A1 …`, `A2a …`, `A2b …`, `A3 …`, `A4 …`, `A5 …`, each `{name, window, value, threshold, verdict}` — the same shape `validate.main` already formats.

**Observed values are derived from `obs_by_site`, not hardcoded**, so the criteria cannot drift from the database. Only the two window constants are literals.

- [ ] **Step 1: Write the failing tests, each proved by sabotage**

```python
# Reuses the file's existing `synth_run_dir` fixture and `SYNTH_WINDOW` constant,
# and its `_base_his()` / `_base_obs()` helpers for the Xaver cases.
def _april_his(peak_day="2013-04-24", cross_day="2013-04-20", head=0.48):
    """Synthetic hourly model output that passes every April criterion."""
    t = pd.date_range("2013-04-05", "2013-05-02", freq="h")
    u = pd.Series(np.interp(t.asi8,
        pd.to_datetime(["2013-04-05", cross_day, peak_day, "2013-05-02"]).asi8,
        [-0.13, 0.20, 0.54, 0.30]), index=t)
    return pd.DataFrame({"Uostadvaris": u, "Klaipeda": u - head,
                         "Nida": u - 0.18, "Vente": u - 0.25}, index=t)


def _verdict(crit, prefix):
    return next(c["verdict"] for c in crit if c["name"].startswith(prefix))


@pytest.mark.integration
def test_april_criteria_pass_on_a_faithful_model(synth_run_dir):
    obs = {g: mf.load_gauge_levels(g, APRIL) for g in va.GAUGES}
    crit = va.april_criteria(_april_his(), obs, synth_run_dir, SYNTH_WINDOW)
    assert [c["name"][:3] for c in crit] == ["A1 ", "A2a", "A2b", "A3 ", "A4 ", "A5 "]
    for p in ("A1", "A2a", "A2b", "A3"):
        assert _verdict(crit, p) == "met", p


@pytest.mark.integration
def test_a2a_fails_when_the_lagoon_fills_two_days_early(synth_run_dir):
    obs = {g: mf.load_gauge_levels(g, APRIL) for g in va.GAUGES}
    crit = va.april_criteria(_april_his(cross_day="2013-04-18"), obs, synth_run_dir, SYNTH_WINDOW)
    assert _verdict(crit, "A2a") == "not met"
    assert _verdict(crit, "A2b") == "met", "the crest is still in the plateau -- A2a is the sharp half"


@pytest.mark.integration
def test_a3_fails_when_the_delta_does_not_stand_above_the_sea(synth_run_dir):
    obs = {g: mf.load_gauge_levels(g, APRIL) for g in va.GAUGES}
    crit = va.april_criteria(_april_his(head=0.20), obs, synth_run_dir, SYNTH_WINDOW)
    assert _verdict(crit, "A3") == "not met"
```

- [ ] **Step 2: Run to verify failure**

Run: `cd curonian && micromamba run -n hydromt-sfincs python -m pytest tests/test_validate.py -k april -q`
Expected: FAIL — `module 'validate' has no attribute 'april_criteria'`.

- [ ] **Step 3: Implement**

```python
# The crest window A3 averages the delta-to-sea head over. Wider than the peak
# itself on purpose: the 24 Apr head is depressed by a one-day 20 cm excursion in
# the Klaipeda gauge (52, 55, 39, 45, 47 cm on 22-26 Apr), so a single instant
# scores the sea's noise rather than the river's head. See spec section 8.
APRIL_CREST = (pd.Timestamp("2013-04-22"), pd.Timestamp("2013-04-26"))
APRIL_FILL_LEVEL = 0.20      # m; the rising limb crosses it at 10-18 cm/day
PLATEAU_TIE_M = 0.05         # daily gauge readings this close are the same crest


def _first_crossing(s: pd.Series, level: float) -> pd.Timestamp:
    above = s[s >= level]
    if above.empty:
        return pd.NaT
    return above.index[0]


def april_criteria(his, obs_by_site, run_dir=None, window=VALIDATION_WINDOW):
    """Spec section 8 criteria for the April 2013 freshet."""
    out = []
    lo, hi = common.event("april_2013").score_window
    obs_u = obs_by_site["Uostadvaris"].loc[lo:hi]
    obs_k = obs_by_site["Klaipeda"].loc[lo:hi]
    mod_u = his["Uostadvaris"].loc[lo:hi]

    # A1: peak magnitude, observed peak taken from the gauge rather than hardcoded.
    s = skill(mod_u, obs_u)
    out.append({"name": "A1 Uostadvaris peak", "window": _window_label((lo, hi)),
                "value": f"model peak {mod_u.max():.2f} m vs gauge "
                         f"{obs_u.max():.2f} m, err {s['peak_err_m']:+.2f} m",
                "threshold": "peak err within +/-0.15 m",
                "verdict": "met" if abs(s["peak_err_m"]) <= 0.15 else "not met"})

    # A2a: filling rate. The rise is resolved by the daily readings; the crest is not.
    obs_cross = _first_crossing(obs_u, APRIL_FILL_LEVEL)
    mod_cross = _first_crossing(mod_u, APRIL_FILL_LEVEL)
    dt_h = (mod_cross - obs_cross).total_seconds() / 3600 if pd.notna(mod_cross) else float("nan")
    out.append({"name": "A2a filling rate", "window": f"first crossing of +{APRIL_FILL_LEVEL:.2f} m",
                "value": (f"model {mod_cross:%Y-%m-%d %H:%M} vs gauge {obs_cross:%Y-%m-%d %H:%M}, "
                          f"dt {dt_h:+.0f} h" if pd.notna(mod_cross) else "model never reached the level"),
                "threshold": "within +/-24 h of the observed crossing",
                "verdict": "met" if pd.notna(mod_cross) and abs(dt_h) <= 24 else "not met"})

    # A2b: the crest, accepted anywhere in the observed plateau widened by 12 h.
    plateau = obs_u[obs_u >= obs_u.max() - PLATEAU_TIE_M].index
    p0, p1 = plateau.min() - pd.Timedelta("12h"), plateau.max() + pd.Timedelta("12h")
    t_peak = mod_u.idxmax()
    out.append({"name": "A2b crest timing", "window": f"{_fmt_dt(p0)} to {_fmt_dt(p1)}",
                "value": f"model peak {t_peak:%Y-%m-%d %H:%M}; observed plateau "
                         f"{plateau.min():%d %b}-{plateau.max():%d %b}",
                "threshold": "model peak inside the observed plateau +/-12 h",
                "verdict": "met" if p0 <= t_peak <= p1 else "not met"})

    # A3: the head the river holds above the sea, averaged over the crest.
    stamps = [t for t in obs_u.index if APRIL_CREST[0] <= t <= APRIL_CREST[1] and t in obs_k.index]
    obs_head = float(np.mean([obs_u[t] - obs_k[t] for t in stamps]))
    mod_head = float(np.mean([his["Uostadvaris"].loc[t] - his["Klaipeda"].loc[t] for t in stamps]))
    out.append({"name": "A3 delta-to-sea head", "window": _window_label(APRIL_CREST),
                "value": f"model {mod_head:.2f} m vs gauge {obs_head:.2f} m over {len(stamps)} readings, "
                         f"err {mod_head - obs_head:+.2f} m",
                "threshold": "mean head within +/-0.15 m",
                "verdict": "met" if abs(mod_head - obs_head) <= 0.15 else "not met"})

    # A4: the sea must beat the no-skill baseline, not merely sit near the mean.
    s4 = skill(his["Klaipeda"], obs_k)
    sigma = float(obs_k.std(ddof=0))
    out.append({"name": "A4 Klaipeda control", "window": _window_label((lo, hi)),
                "value": f"RMSE {s4['rmse']:.3f} m against an observed sd of {sigma:.3f} m",
                "threshold": "RMSE <= 0.085 m (below the observed sd: a flat series fails)",
                "verdict": "met" if s4["rmse"] <= 0.085 else "not met"})

    # A5: Xaver's C4 verbatim. Whole-run by construction -- dtmaxout gives one zsmax
    # record spanning tstart..tstop, so this cannot be restricted to the scoring window.
    ground, flooded, _, _, _, _ = _flood_arrays(run_dir, window)
    uplands = np.isfinite(ground) & (ground > 3.0)
    n_upland_px = int(uplands.sum())
    frac_pct = (100.0 * float(flooded[uplands].sum()) / n_upland_px) if n_upland_px else float("nan")
    out.append({"name": "A5 Silute uplands", "window": f"whole run, delta window {window}",
                "value": f"{frac_pct:.2f}% of land with ground > 3 m flooded",
                "threshold": "< 1 % flooded",
                "verdict": c4_verdict(frac_pct, n_upland_px)})
    return out
```

- [ ] **Step 4: Run the tests**

Run: `cd curonian && micromamba run -n hydromt-sfincs python -m pytest tests -q -rs`
Expected: the previous count plus 3, **0 skipped**.

- [ ] **Step 5: Commit**

```bash
git add curonian/validate.py curonian/tests/test_validate.py
git commit -m "Score the April freshet on filling rate, crest and the head it holds"
```

---

### Task 8: The April provenance fixture

**Files:**
- Create: `curonian/tests/data/lhmt_smalininkai_2013_04.csv`
- Modify: `curonian/tests/test_forcing_provenance.py`

**Interfaces:**
- Consumes: `common.event("april_2013")`.
- Produces: the April fixture plus parametrized provenance tests. **The April tests skip while `inputs/april_2013/dis.csv` does not exist** — it is not built until Task 9, and the rest of the suite already uses that convention.

- [ ] **Step 1: Fetch the fixture from api.meteo.lt**

```bash
cd /home/razinka/sfincs/curonian && micromamba run -n hydromt-sfincs python - <<'PY'
import requests, csv, pathlib
rows = []
for month in ("2013-03", "2013-04", "2013-05"):
    r = requests.get(f"https://api.meteo.lt/v1/hydro-stations/smalininku-vms/observations/historical/{month}",
                     headers={"User-Agent": "curonian-sfincs-tests/0.1"}, timeout=30)
    r.raise_for_status()
    for o in r.json().get("observations", []):
        if o.get("waterDischarge") is not None:
            rows.append((o["observationDateUtc"], o["waterDischarge"], o.get("waterLevel")))
out = pathlib.Path("tests/data/lhmt_smalininkai_2013_04.csv")
with out.open("w", newline="") as fh:
    fh.write("# Nemunas daily discharge and water level at Smalininkai, 26 Mar - 12 May 2013.\n"
             "#\n"
             "# Source: Lithuanian Hydrometeorological Service (LHMT) open API, api.meteo.lt,\n"
             "#   /v1/hydro-stations/smalininku-vms/observations/historical/<YYYY-MM>\n"
             "# Retrieved 2026-09-16. Licence: CC BY-SA 4.0 -- attribution is a condition of\n"
             "#   access, so it travels with this file.\n"
             "# waterLevel is cm above the station's own local gauge zero, NOT the model\n"
             "#   datum. Only waterDischarge is used.\n")
    w = csv.writer(fh); w.writerow(["observationDateUtc", "waterDischarge", "waterLevel"])
    w.writerows(sorted(r for r in rows if "2013-03-26" <= r[0][:10] <= "2013-05-12"))
print(out, len(rows))
PY
```

- [ ] **Step 2: Verify the fixture contains the crest**

```bash
grep -c . curonian/tests/data/lhmt_smalininkai_2013_04.csv
grep "2013-04-19" curonian/tests/data/lhmt_smalininkai_2013_04.csv
```
Expected: the 19 April row reads `2150`, matching the DB.

- [ ] **Step 3: Parametrize the provenance tests over both events**

In `curonian/tests/test_forcing_provenance.py`, replace the module-level `FIXTURE`/`STATION` with a per-event lookup and add the skip guard:

```python
FIXTURES = {
    "xaver_2013": Path(__file__).parent / "data" / "lhmt_smalininkai_2013.csv",
    "april_2013": Path(__file__).parent / "data" / "lhmt_smalininkai_2013_04.csv",
}
PROV_EVENTS = [common.event("xaver_2013"), common.event("april_2013")]


def lhmt(event) -> pd.Series:
    df = pd.read_csv(FIXTURES[event.name], comment="#", parse_dates=["observationDateUtc"])
    return df.set_index("observationDateUtc")["waterDischarge"].astype(float)


def model(event) -> pd.DataFrame:
    path = event.inputs_dir / "dis.csv"
    if not path.exists():
        pytest.skip(f"{path} not built yet")
    df = pd.read_csv(path, index_col=0, parse_dates=True)
    df.columns = [int(c) for c in df.columns]
    return df
```

**`_midnights()` must take the event too** — at `test_forcing_provenance.py:37` it
reads `common.TREF, common.TSTOP`, so parametrized over April it would iterate
November dates, find none of them in the April fixture, and fail `compared >= 14`
with nothing compared:

```python
def _midnights(event):
    return pd.date_range(event.tref, event.tstop, freq="D")
```

Then add `@pytest.mark.parametrize("event", PROV_EVENTS, ids=lambda e: e.name)` to
each of the four tests, replacing `common.MINIJA_Q_DEC` with `event.minija_q`,
`common.NEMUNAS_LAG_DAYS` with `event.nemunas_lag_days`, and every `_midnights()`
call with `_midnights(event)`. The live-API test's
`for month in ("2013-11", "2013-12")` becomes the event's own months — derive them
from `event.tref`/`event.tstop` rather than from `gtsm_months`, which is a CDS
request field and covers a different span.

- [ ] **Step 4: Run the tests**

Run: `cd curonian && micromamba run -n hydromt-sfincs python -m pytest tests -q -rs`
Expected: four more tests than before (the four provenance tests now run per
event), **with exactly four skips, every one of them naming `april_2013`**
(`dis.csv not built yet`). Any skip that does not name April is a regression from
Task 2 — read the `-rs` block, do not just count.

- [ ] **Step 5: Commit**

```bash
git add curonian/tests/
git commit -m "Extend the discharge provenance check to April"
```

---

### Task 9: Build April's forcing

**Files:**
- Create: `curonian/inputs/april_2013/{gtsm.zip,gtsm/,gtsm_klaipeda.csv,bzs.csv,dis.csv,wind.csv,forcing_summary.txt}`

**Interfaces:**
- Consumes: everything from Tasks 3–4.
- Produces: the April forcing that Task 10 builds from.

**This is the first task that spends CDS quota.** It downloads roughly 80 MB.

- [ ] **Step 1: Fetch the April GTSM series**

Run: `cd curonian && micromamba run -n hydromt-sfincs python -m prep.fetch_gtsm --event april_2013`
Expected: a queued CDS request, then `inputs/april_2013/gtsm.zip` and `gtsm_klaipeda.csv`. Minutes to hours depending on the CDS queue.

- [ ] **Step 2: Sanity-check the series before using it**

```bash
cd curonian && micromamba run -n hydromt-sfincs python -c "
import common, pandas as pd
ev = common.event('april_2013')
s = pd.read_csv(ev.inputs_dir/'gtsm_klaipeda.csv', index_col=0, parse_dates=True)['waterlevel_m']
print(s.index.min(), s.index.max(), len(s))
assert s.index.min() <= ev.tref and s.index.max() >= ev.tstop
print('range %.2f..%.2f m' % (s.min(), s.max()))"
```
Expected: hourly coverage spanning 5 Apr – 2 May, levels within roughly ±1 m.

- [ ] **Step 3: Build the forcing**

Run: `cd curonian && micromamba run -n hydromt-sfincs python -m prep.make_forcing --event april_2013`
Expected: writes five files into `inputs/april_2013/` and prints the summary.

- [ ] **Step 4: Check the summary against the observations**

```bash
cat curonian/inputs/april_2013/forcing_summary.txt
```
Expected: a GTSM offset of order a few centimetres to a decimetre; `Nemunas Q: 410..2150 m3/s`; `Minija constant 83.0 m3/s`; crest peak near 19–21 April.

- [ ] **Step 5: The provenance tests now run for April**

Run: `cd curonian && micromamba run -n hydromt-sfincs python -m pytest tests -q -rs`
Expected: the same count as after Task 8 with **0 skipped** — the four April
provenance tests now execute and must pass. A failure here means the forcing does not match LHMT's record.

- [ ] **Step 6: Commit**

```bash
git add curonian/inputs/april_2013/
git commit -m "Build the April 2013 forcing from GTSM, ERA5 and LHMT"
```

---

### Task 10: Build, run and validate April

**Files:**
- Create: `curonian/runs/april_2013/` (ignored), `curonian/results/april_2013/{validation.md,validation_timeseries.png,flood_extent_delta.png}`

**Interfaces:**
- Consumes: Tasks 5, 7, 9.
- Produces: the scored April result.

- [ ] **Step 1: Check the machine is not loaded**

```bash
uptime && nproc
```
A 27-day run takes ~55–60 minutes on 16 threads at low load; one Xaver run took 38 minutes instead of 27 at load 79.

- [ ] **Step 2: Check the bathymetry is on disk**

```bash
ls -l curonian/inputs/lagoon_bathy_50m.tif
```
It is event-independent but **git-ignored**, so a checkout that has never built it
has nothing to reuse. If it is missing, regenerate it first with
`micromamba run -n hydromt-sfincs python -m prep.make_bathymetry` (~minutes); do
**not** touch `prep.make_channels`, which reads live Overpass data.

- [ ] **Step 3: Build the model**

Run: `cd curonian && micromamba run -n hydromt-sfincs python build_model.py --event april_2013`
Expected: ~5 minutes for the subgrid; the four assertions in `build()` pass (`n_active` in range, boundary cells in the ring, strait connected).

- [ ] **Step 4: Confirm the config took the event's clock and initial level**

```bash
grep -E "tstart|tstop|zsini" curonian/runs/april_2013/sfincs.inp
```
Expected: `tstart = 20130405 000000`, `tstop = 20130502 000000`, `zsini = -0.17`.

- [ ] **Step 5: Run SFINCS**

Run: `cd /home/razinka/sfincs && ./run_sfincs.sh curonian/runs/april_2013 16`
Expected: ~55–60 minutes, ending with `sfincs_map.nc`, `sfincs_his.nc` and a log with no errors.

- [ ] **Step 6: Validate**

Run: `cd curonian && micromamba run -n hydromt-sfincs python validate.py --event april_2013`
Expected: `results/april_2013/validation.md` with the six A-criteria, plus the two figures.

- [ ] **Step 7: Read the verdicts before committing anything**

A criterion reading "not met" is a result, not a bug — record it. Section 10 of the spec names the suspects in order: A1 or A3 biased low → the initial condition or the ice; A2a late → the 1-day Nemunas lag; A4 failing → the GTSM boundary.

- [ ] **Step 8: Commit**

```bash
git add curonian/results/april_2013/
git commit -m "Record the April 2013 freshet hindcast and its verdicts"
```

---

### Task 11: Publish April in the viewer and the README

**Files:**
- Modify: `app/sfincs_data.py`, `app/app.py`, `app/test_sfincs_data.py`, `curonian/README.md`

**Interfaces:**
- Consumes: `results/april_2013/validation.md` from Task 10.
- Produces: the April tab in the deployed viewer.

`list_variants()` already discovers the directory, so the label is cosmetic — but the **report parser is not**: `_PERIOD_RE` hardcodes `^(Whole period|Storm window):` and is the only thing that finds both the headings and the per-station metric tables. April's report says `Scoring window:`, so without this the April metric table silently vanishes.

- [ ] **Step 1: Write the failing test**

`sfincs_data.metric_tables(variant)` and `periods(variant)` take a **variant name**
and read that variant's committed `validation.md` themselves — the suite runs
against real reports rather than inline fixtures, and skips when one is absent. So
the test is a contract over every published variant, and April joins it
automatically once Task 10 commits its report:

```python
@pytest.mark.parametrize("variant", sd.list_variants())
def test_every_variant_exposes_a_whole_period_and_a_scored_window(variant):
    """Both headings must parse, whatever the event calls its scored window.

    Xaver's report says "Storm window"; April's says "Scoring window". The regex
    is the only thing that finds either, and a miss empties the metrics panel
    silently rather than failing.
    """
    found = sd.periods(variant)
    assert "Whole period" in found
    scored = [k for k in found if k != "Whole period"]
    assert len(scored) == 1, f"{variant}: expected one scored window, got {scored}"
    assert set(sd.metric_tables(variant)) == set(found)
```

- [ ] **Step 2: Run to verify it fails for April**

Run: `micromamba run -n shiny python -m pytest app/test_sfincs_data.py -q`
Expected: passes for the three `xaver_*` variants, FAILS for `april_2013` with
`expected one scored window, got []` — `_PERIOD_RE` does not know the word
"Scoring".

(Note: the docstring at the top of `app/test_sfincs_data.py` tells the reader to run
these with `-n hydromt-sfincs`. That is wrong — `app.py` imports `shiny`, which that
env does not have, and collection errors. Fix the docstring to say `-n shiny` in
this task.)

- [ ] **Step 3: Generalise the parser, the lookup and the label**

In `app/sfincs_data.py:77` — note the regex is matched per line with `.match()`, so
no `re.M` flag:

```python
# Xaver's report says "Storm window"; April's says "Scoring window". Both are the
# event's scored sub-window, so the parser accepts either and the UI calls it what
# the report calls it.
_PERIOD_RE = re.compile(r"^(Whole period|Storm window|Scoring window):\s*(.+)$")
```

and add the label:

```python
VARIANT_LABELS = {
    "xaver_2013": "Xaver 2013 — uniform wind",
    "xaver_2013_gridwind": "Xaver 2013 — ERA5 gridded wind",
    "xaver_2013_gridwind_pressure": "Xaver 2013 — ERA5 wind + pressure",
    "april_2013": "April 2013 — Nemunas freshet",
}


def scored_window_name(variant: str) -> str:
    """The report's own name for its scored sub-window, for labels and lookups."""
    return next((k for k in periods(variant) if k != "Whole period"), "Scoring window")
```

In `app/app.py` two places hardcode Xaver's word:

- `:116` — `ui.input_switch("storm_only", "Storm window only", ...)`: the label
  becomes `f"{sd.scored_window_name(variant())} only"`. Keep the input id
  `storm_only` so no other code moves.
- `:287` — `sd.periods(variant()).get("Storm window", "")` becomes
  `sd.periods(variant()).get(sd.scored_window_name(variant()), "")`.

The about text that says the viewer shows Storm Xaver is updated to name both events.

- [ ] **Step 4: Run both suites**

```bash
micromamba run -n shiny python -m pytest app/test_sfincs_data.py -q
cd curonian && micromamba run -n hydromt-sfincs python -m pytest tests -q -rs
```
Expected: the 11 existing app tests plus one per published variant (four, once
April is committed), and the model suite unchanged at **0 skipped**.

- [ ] **Step 5: Update the README with the April results**

`curonian/README.md` gains: a `## Results: April 2013` section mirroring the Xaver one (run log, criteria table, findings), and the second event in the opening description.

- [ ] **Step 6: Commit**

```bash
git add app/ curonian/README.md
git commit -m "Publish the April 2013 freshet in the viewer"
```

- [ ] **Step 7: Deploy**

Ask the user to run `! sudo bash deploy/deploy.sh` — it needs root and there is no tty for a password prompt in this session.

---

## Notes for the executor

- **Tasks 1–8 touch no model data and spend no quota.** They can be done, reviewed and reverted freely. Task 9 is the first irreversible step (CDS quota), Task 10 the first expensive one (~1 hour).
- **If Task 2's suite run shows a skip you cannot name, stop.** It means a path literal was missed and the regression instrument has gone blind, which is precisely the failure this plan is shaped to prevent.
- **Do not "tidy" `data_window` or `peak_window` into derived properties.** Xaver's literals are asymmetric on purpose; deriving them changes tracked files and trips the provenance tests.
