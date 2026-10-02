# SFINCS UI Milestone 3 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A logged-in user clones a Curonian example project, edits its event, variant, build parameters and solver overrides on a Setup form beside a deck.gl map of the domain, launches it, and the run builds with `build_model.py`, simulates, validates with `validate.py` and exports the map cache with `export_map_cache.py`, all driven by the UI, producing the same validation as the command-line workflow.

**Architecture:** Three bounded changes to the pipeline scripts under `curonian/` (new flags that default to today's behaviour, so the command-line workflow and its tests are unchanged), one environment variable for the gauge database, a `CuronianTemplate` that turns a settings document into those commands and `sfincs.inp` overrides, optional override fields, a stage skip reason recorded by the runner, a reprojected static geometry served to a deck.gl map on the Setup page, and the deploy preflight's gauge check routed through `common.read_table`.

**Tech Stack:** as milestones 1 and 2. The model env `/opt/micromamba/envs/hydromt-sfincs` (hydromt_sfincs 1.2.2, rasterio, geopandas) runs the pipeline scripts and their tests; the UI env `/opt/micromamba/envs/shiny` (shiny 1.8.0, shiny_deckgl 1.9.2, pyproj) runs the app and its tests.

**Spec:** `docs/superpowers/specs/2026-09-30-sfincs-ui-design.md`, sections 1 (template questions), 2 (Curonian settings, bounded pipeline changes), 3 (stage commands, cwd rules), 4 (Setup page), 5 (preflight), 6 (model-env tests, milestone 3). Milestones 1 and 2 (`docs/superpowers/plans/2026-10-01-sfincs-ui-milestone-1.md`, `2026-10-02-sfincs-ui-milestone-2.md`) define the code this plan extends.

## Global Constraints

- **Two test suites, two interpreters.** UI: `cd /home/razinka/sfincs/sfincs_ui && /opt/micromamba/envs/shiny/bin/python -m pytest -q` (237 passing at the start). Pipeline: `cd /home/razinka/sfincs/curonian && micromamba -r /opt/micromamba run -n hydromt-sfincs python -m pytest tests -q -m "not network"` (run it before the first change and record the count; it must not drop). Never `pip install` into either env.
- **Model-env tests in the UI suite** carry the marker `model_env` and are deselected by default (`addopts = "-m 'not model_env'"` in `pyproject.toml`); each task that owns one runs it explicitly with `-m model_env` and reports the measured duration. They skip, not fail, when `micromamba -r /opt/micromamba run -n hydromt-sfincs python -c "import hydromt_sfincs"` fails.
- **Bounded pipeline changes only** (spec section 2): `build_model.py` gains `--run-dir`, `--manning-land`, `--manning-sea`, `--rgh-lev-land`; `validate.py` gains `--run-dir`, `--out-dir`; `prep/export_map_cache.py` gains `--event`, `--run-dir`, `--out-dir`; `common.py` reads the gauge database path from `SFINCS_CURONIAN_DB` with today's default. Every new flag defaults to today's behaviour. The `export_map_cache` `sys.path` shim that imports `map_core` from `app/` stays until milestone 4; reviewers must not flag it.
- **No changes to `app/` or `deploy/deploy.sh`.**
- **Manning values are build parameters, never `sfincs.inp` overrides.** They go to `setup_subgrid` (or `setup_manning_roughness` without subgrid) and to `config_for` together, so the table and the inp agree; `inp_overrides` never contains a `manning` key (a test pins this).
- **Stage commands and cwd (spec section 3).** Build: `MODEL_PYTHON <CURONIAN_DIR>/build_model.py --event E --run-dir D [--wind grid] [--pressure] [--no-subgrid] --manning-land x --manning-sea y --rgh-lev-land z`, cwd `CURONIAN_DIR`. Validate: `MODEL_PYTHON <CURONIAN_DIR>/validate.py --event E --run-dir D --out-dir D/validation`, cwd `CURONIAN_DIR`. Export: `MODEL_PYTHON -m prep.export_map_cache --event E --run-dir D --out-dir D/validation`, cwd `CURONIAN_DIR`. Simulate: cwd `D`, `OMP_NUM_THREADS`.
- **Evidence paths follow the real script outputs:** build = `sfincs.inp`, the template's model files and `overrides.diff`; simulate as before; validate = `D/validation/validation.md`; export = `D/map_meta.json` (the cache lands in the run directory next to `sfincs_map.nc`; the milestone 2 helper looked under `validation/` and is corrected here).
- **Identity and access rules** as before: every page mutation calls `current_user()` first; services enforce.
- **Commits** end with `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>` and `Claude-Session: https://claude.ai/code/session_01K5wxxnsj5oVJ2gHNaNhr9B`.

## Review Focus

Input classes the spec implies but no task's tests exercised at first draft. Each line's test is added to the owning task.

1. **A `tstop` override before the event's scoring window.** Expected: the run builds and simulates, the validate stage is skipped, and the run summary records `skipped: {"validate": "run ends before the scoring window"}` so Results (milestone 4) can say "not scored". Tests in Task 4 (`test_skip_reason_recorded_in_summary`) and Task 5 (`test_tstop_before_score_window_skips_validation`).
2. **A `tstop` outside the event's data window, or before `tref`.** Expected: `TemplateError` naming `tstop` and the allowed window; nothing is launched. Test in Task 5 (`test_tstop_bounds_per_event`).
3. **An override left empty in the form.** Expected: the key is absent from `inp_overrides`, the built value stands, and reloading the project shows the box empty again. Tests in Task 4 (`test_optional_field_round_trip`) and Task 5 (`test_unset_overrides_are_omitted`).
4. **The service user reading the gauge database.** Expected: `common.DB` honours `SFINCS_CURONIAN_DB`, `validate.py` and `export_map_cache.gauge_obs` read through it, and the deploy preflight proves it as user `shiny`. Tests in Task 1 (`test_db_path_from_environment`) and Task 7 (`test_deep_gauge_check_uses_common_read_table`).
5. **A template whose geometry is not georeferenced** (plane beach, local metres). Expected: the Setup map shows "No georeferenced geometry for this template" rather than plotting the domain in the Atlantic. Test in Task 6 (`test_setup_map_ignores_local_crs_layers`).

## File structure

```
curonian/
  common.py                          DB from SFINCS_CURONIAN_DB
  build_model.py                     --run-dir, --manning-*, --rgh-lev-land; build(manning_*, grid=, check=)
  validate.py                        --run-dir, --out-dir; main(event, run_dir, out_dir)
  prep/export_map_cache.py           --event, --run-dir, --out-dir; main(..., event=, run_dir=, out_dir=)
  tests/test_common.py, test_build_model.py, test_validate.py, test_export_map_cache.py   (additions)
sfincs_ui/sfincs_ui/
  templates/base.py                  SettingField.optional, kind "datetime"; Template.skip_reasons
  templates/curonian.py              CuronianTemplate, EVENTS mirror, geometry from inputs/*.geojson
  templates/__init__.py              registry gains "curonian"
  services/job_runner.py             export_evidence fix; skip reasons in summary_json
  services/environment.py            deep gauge check via common.read_table in the model env
  pages/setup.py                     deck.gl map of the template's geometry; optional fields
  pages/runs.py                      shows the skip reason
  app.py                             shiny_deckgl head_includes()
sfincs_ui/tests/
  test_templates_curonian.py, test_curonian_geometry.py, test_model_env_curonian.py (marker model_env),
  test_setup_map.py, plus additions to test_templates.py, test_job_runner.py, test_environment.py, test_pages_m2.py
sfincs_ui/README.md, deploy/README.md
```

---

### Task 1: `common.py` gauge database path and `build_model.py` flags

**Files:**
- Modify: `curonian/common.py`
- Modify: `curonian/build_model.py`
- Test: `curonian/tests/test_common.py`, `curonian/tests/test_build_model.py` (additions)

**Interfaces:**
- Produces: `common.DB` is `Path(os.environ["SFINCS_CURONIAN_DB"])` when set, else today's `HOME / "curonian/curonian_db.gpkg"`; `_db_uri()` unchanged. `build_model.parse_args` accepts `--run-dir PATH` (wins over `--run-name`; `args.run_dir` is a `Path` or `None`), `--manning-land` (default `MANNING_LAND` 0.06), `--manning-sea` (default `MANNING_SEA` 0.02), `--rgh-lev-land` (default `RGH_LEV_LAND` 0.3). `config_for(event, zs_boundary, manning_land=MANNING_LAND, manning_sea=MANNING_SEA)`. `build(event, run_dir=None, subgrid=True, wind="uniform", pressure=False, manning_land=MANNING_LAND, manning_sea=MANNING_SEA, rgh_lev_land=RGH_LEV_LAND, grid=None, check=True)`: `grid` is `(x0, y0, mmax, nmax)` for a small-domain build (default the full domain), `check=False` skips the post-build asserts and `check_model`; `setup_subgrid` gets `write_man_tif=True`.

- [ ] **Step 1: Record the pipeline suite's baseline**

Run: `cd /home/razinka/sfincs/curonian && micromamba -r /opt/micromamba run -n hydromt-sfincs python -m pytest tests -q -m "not network" 2>&1 | tail -3`
Write the count into your report; it is the floor for every later pipeline run.

- [ ] **Step 2: Write the failing tests**

Append to `curonian/tests/test_common.py`:

```python
def test_db_path_from_environment(monkeypatch, tmp_path):
    """The service user has no ~/curonian; SFINCS_CURONIAN_DB names the gauge database."""
    import importlib
    import common as c

    monkeypatch.setenv("SFINCS_CURONIAN_DB", str(tmp_path / "gauges.gpkg"))
    reloaded = importlib.reload(c)
    try:
        assert reloaded.DB == tmp_path / "gauges.gpkg"
        assert reloaded._db_uri().startswith("file:") and str(tmp_path / "gauges.gpkg") in reloaded._db_uri()
    finally:
        monkeypatch.delenv("SFINCS_CURONIAN_DB")
        importlib.reload(c)
    assert c.DB == c.HOME / "curonian/curonian_db.gpkg"
```

Append to `curonian/tests/test_build_model.py`:

```python
def test_parse_args_run_dir_wins_over_run_name(tmp_path):
    args = bm.parse_args(["--run-dir", str(tmp_path / "x"), "--run-name", "ignored"])
    assert args.run_dir == tmp_path / "x"


def test_parse_args_run_dir_defaults_to_none_and_manning_to_constants():
    args = bm.parse_args([])
    assert args.run_dir is None
    assert (args.manning_land, args.manning_sea, args.rgh_lev_land) == (bm.MANNING_LAND, bm.MANNING_SEA, bm.RGH_LEV_LAND)


def test_parse_args_manning_flags():
    args = bm.parse_args(["--manning-land", "0.08", "--manning-sea", "0.03", "--rgh-lev-land", "0.5"])
    assert (args.manning_land, args.manning_sea, args.rgh_lev_land) == (0.08, 0.03, 0.5)


def test_config_for_carries_the_manning_values():
    cfg = bm.config_for(common.EVENTS["xaver_2013"], zs_boundary=0.4, manning_land=0.08, manning_sea=0.03)
    assert cfg["manning_land"] == 0.08 and cfg["manning_sea"] == 0.03
    assert bm.config_for(common.EVENTS["xaver_2013"], zs_boundary=0.4)["manning_land"] == bm.MANNING_LAND


def test_build_signature_has_the_new_knobs_with_todays_defaults():
    import inspect
    p = inspect.signature(bm.build).parameters
    assert p["manning_land"].default == bm.MANNING_LAND and p["manning_sea"].default == bm.MANNING_SEA
    assert p["rgh_lev_land"].default == bm.RGH_LEV_LAND and p["grid"].default is None and p["check"].default is True
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `cd /home/razinka/sfincs/curonian && micromamba -r /opt/micromamba run -n hydromt-sfincs python -m pytest tests/test_common.py tests/test_build_model.py -q 2>&1 | tail -5`
Expected: the 6 new tests fail (`AttributeError`/`SystemExit: 2` on unknown flags); the existing ones pass.

- [ ] **Step 4: Change `common.py`**

Replace `DB = HOME / "curonian/curonian_db.gpkg"` with:

```python
# The gauge database. Under the UI's service user HOME is /home/shiny, so the
# deploy sets SFINCS_CURONIAN_DB; the command-line workflow keeps the default.
DB = Path(os.environ.get("SFINCS_CURONIAN_DB", str(HOME / "curonian/curonian_db.gpkg")))
```

and add `import os` to the imports.

- [ ] **Step 5: Change `build_model.py`**

`parse_args`:

```python
    p.add_argument("--run-name", default=None, help="subdirectory of runs/; defaults to the event name")
    p.add_argument("--run-dir", type=Path, default=None,
                   help="write the model here instead of runs/<run-name> (the UI's workspace)")
    p.add_argument("--manning-land", type=float, default=MANNING_LAND, help="subgrid/inp roughness on land")
    p.add_argument("--manning-sea", type=float, default=MANNING_SEA, help="subgrid/inp roughness below rgh-lev-land")
    p.add_argument("--rgh-lev-land", type=float, default=RGH_LEV_LAND, help="level separating land and sea roughness")
```

`config_for`:

```python
def config_for(event: common.Event, zs_boundary: float, manning_land: float = MANNING_LAND,
               manning_sea: float = MANNING_SEA) -> dict:
    ...
        manning_land=manning_land, manning_sea=manning_sea,
```

`build`:

```python
def build(event: common.Event, run_dir: Path | None = None, subgrid: bool = True,
          wind: str = "uniform", pressure: bool = False, manning_land: float = MANNING_LAND,
          manning_sea: float = MANNING_SEA, rgh_lev_land: float = RGH_LEV_LAND,
          grid: tuple[float, float, int, int] | None = None, check: bool = True):
    """grid=(x0, y0, mmax, nmax) builds a sub-domain (the UI's small-domain test); check=False
    skips the full-domain sanity asserts, which a sub-domain cannot meet."""
    ...
    x0, y0, mmax, nmax = grid or (common.X0, common.Y0, common.MMAX, common.NMAX)
    sf.setup_grid(x0=x0, y0=y0, dx=common.DX, dy=common.DY, nmax=nmax, mmax=mmax, rotation=0, epsg=common.CRS)
    ...
        sf.setup_subgrid(datasets_dep=DATASETS_DEP, datasets_riv=datasets_riv(inputs=static), nr_subgrid_pixels=20, nlevels=10,
                         manning_land=manning_land, manning_sea=manning_sea, rgh_lev_land=rgh_lev_land,
                         write_dep_tif=True, write_man_tif=True)
    else:
        sf.setup_manning_roughness(manning_land=manning_land, manning_sea=manning_sea, rgh_lev_land=rgh_lev_land)
    ...
    sf.setup_config(**config_for(event, zs_boundary=float(bzs.iloc[0].mean()),
                                 manning_land=manning_land, manning_sea=manning_sea))
    ...
    sf.write()
    if not check:
        return sf
    r = check_model(run_dir)
    ... (asserts unchanged)
```

`__main__`:

```python
if __name__ == "__main__":
    args = parse_args()
    build(common.event(args.event), run_dir=args.run_dir or common.RUNS / args.run_name, subgrid=not args.no_subgrid,
          wind=args.wind, pressure=args.pressure, manning_land=args.manning_land, manning_sea=args.manning_sea,
          rgh_lev_land=args.rgh_lev_land)
```

Keep every comment that is there today.

- [ ] **Step 6: Run the pipeline suite**

Run: `cd /home/razinka/sfincs/curonian && micromamba -r /opt/micromamba run -n hydromt-sfincs python -m pytest tests -q -m "not network" 2>&1 | tail -3`
Expected: the baseline count plus 6, no failures.

- [ ] **Step 7: Commit**

```bash
cd /home/razinka/sfincs
git add curonian/common.py curonian/build_model.py curonian/tests/test_common.py curonian/tests/test_build_model.py
git commit -m "curonian: SFINCS_CURONIAN_DB, build_model --run-dir and manning flags, sub-domain build knobs

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01K5wxxnsj5oVJ2gHNaNhr9B"
```

---

### Task 2: `validate.py --run-dir --out-dir`

**Files:**
- Modify: `curonian/validate.py`
- Test: `curonian/tests/test_validate.py` (additions)

**Interfaces:**
- Produces: `parse_args` accepts `--run-dir PATH` (wins over `--run`) and `--out-dir PATH`; `main(event, run_dir=None, out_dir=None)`: with `out_dir` given, `validation.md`, `validation_timeseries.png` and `flood_extent_delta.png` are written into `out_dir` (created) and nothing is copied to `results/`; without it, today's behaviour (write into `run_dir`, copy to `results/<run_dir.name>`).

- [ ] **Step 1: Write the failing tests**

Append to `curonian/tests/test_validate.py`:

```python
def test_parse_args_run_dir_and_out_dir(tmp_path):
    args = va.parse_args(["--event", "april_2013", "--run-dir", str(tmp_path / "r"), "--out-dir", str(tmp_path / "r" / "validation")])
    assert args.run_dir == tmp_path / "r" and args.out_dir == tmp_path / "r" / "validation"
    assert va.parse_args([]).run_dir is None and va.parse_args([]).out_dir is None


def test_main_writes_into_out_dir_without_touching_results(tmp_path, monkeypatch):
    """With --out-dir the report and figures land there and results/ is never written."""
    import pandas as pd

    run_dir = tmp_path / "run"; run_dir.mkdir()
    out_dir = run_dir / "validation"
    idx = pd.date_range("2013-11-28", periods=4, freq="6h")
    his = pd.DataFrame({g: [0.1, 0.2, 0.3, 0.4] for g in va.GAUGES}, index=idx)
    monkeypatch.setattr(va, "load_his", lambda rd: his)
    monkeypatch.setattr(va, "load_gauge_levels", lambda g, e: pd.Series([0.1, 0.4], index=[idx[0], idx[-1]]))
    monkeypatch.setattr(va, "load_rusne_levels", lambda e: pd.Series([1.0, 1.1], index=[idx[0], idx[-1]]))
    monkeypatch.setattr(va, "flood_map", lambda rd, out_png, event: (out_png.write_bytes(b"png") or 12.5))
    monkeypatch.setattr(va, "criteria", lambda his, obs, rd, event: [])
    copied = []
    monkeypatch.setattr(va.shutil, "copy2", lambda a, b: copied.append(b))
    va.main(common.EVENTS["xaver_2013"], run_dir=run_dir, out_dir=out_dir)
    assert (out_dir / "validation.md").is_file() and (out_dir / "validation_timeseries.png").is_file()
    assert (out_dir / "flood_extent_delta.png").read_bytes() == b"png"
    assert copied == [] and not (run_dir / "validation.md").exists()
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd /home/razinka/sfincs/curonian && micromamba -r /opt/micromamba run -n hydromt-sfincs python -m pytest tests/test_validate.py -q 2>&1 | tail -4`
Expected: the 2 new tests fail; the others pass.

- [ ] **Step 3: Change `validate.py`**

`main`:

```python
def main(event: common.Event, run_dir: Path | None = None, out_dir: Path | None = None) -> None:
    """out_dir: where validation.md and the figures go. None (the command-line default) writes
    them into run_dir and copies them to results/<run name>; the UI passes <run>/validation and
    nothing is copied."""
    run_dir = run_dir or common.RUNS / event.name
    target = out_dir or run_dir
    target.mkdir(parents=True, exist_ok=True)
    ...
    fig.savefig(target / "validation_timeseries.png", dpi=130); plt.close(fig)

    area = flood_map(run_dir, target / "flood_extent_delta.png", event=event)
    ...
    (target / "validation.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))

    if out_dir is None:
        results_dir = common.ROOT / "results" / run_dir.name
        results_dir.mkdir(parents=True, exist_ok=True)
        for fname in ("validation.md", "validation_timeseries.png", "flood_extent_delta.png"):
            shutil.copy2(run_dir / fname, results_dir / fname)
```

`parse_args` and `__main__`:

```python
    p.add_argument("--run", default=None, help="runs/<name> to validate; results go to results/<name>; defaults to the event name")
    p.add_argument("--run-dir", type=Path, default=None, help="validate this directory instead of runs/<run>")
    p.add_argument("--out-dir", type=Path, default=None, help="write the report and figures here (no copy to results/)")
    ...
if __name__ == "__main__":
    args = parse_args()
    main(common.event(args.event), run_dir=args.run_dir or common.RUNS / args.run, out_dir=args.out_dir)
```

- [ ] **Step 4: Run the pipeline suite**

Run: `cd /home/razinka/sfincs/curonian && micromamba -r /opt/micromamba run -n hydromt-sfincs python -m pytest tests -q -m "not network" 2>&1 | tail -3`
Expected: Task 1's count plus 2.

- [ ] **Step 5: Commit**

```bash
cd /home/razinka/sfincs
git add curonian/validate.py curonian/tests/test_validate.py
git commit -m "curonian: validate.py --run-dir and --out-dir

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01K5wxxnsj5oVJ2gHNaNhr9B"
```

---

### Task 3: `prep/export_map_cache.py --event --run-dir --out-dir`

**Files:**
- Modify: `curonian/prep/export_map_cache.py`
- Test: `curonian/tests/test_export_map_cache.py` (additions)

**Interfaces:**
- Produces: `parse_args` accepts `--run NAME` (now optional), `--event NAME` (a key of `common.EVENTS`), `--run-dir PATH`, `--out-dir PATH`; at least one of `--run`/`--run-dir` is required. `main(run=None, runs_dir=common.RUNS, results_root=common.ROOT / "results", *, event=None, run_dir=None, out_dir=None) -> dict`: `run_dir = run_dir or runs_dir / run`; `event = common.event(event) if event else event_for_run(run_dir.name)`; `out_dir = out_dir or results_root / run_dir.name`; writes the cache into `run_dir` (`map_meta.json` last, as `map_core.export_cache` does) and `gauge_obs.csv` into `out_dir`. The existing positional call `main("april_2013_synthetic", runs_dir=..., results_root=...)` keeps working.

- [ ] **Step 1: Write the failing tests**

Append to `curonian/tests/test_export_map_cache.py`:

```python
def test_parse_args_event_run_dir_out_dir(tmp_path):
    args = emc.parse_args(["--event", "april_2013", "--run-dir", str(tmp_path / "r"), "--out-dir", str(tmp_path / "r" / "validation")])
    assert (args.event, args.run_dir, args.out_dir) == ("april_2013", tmp_path / "r", tmp_path / "r" / "validation")
    assert args.run is None


def test_parse_args_requires_run_or_run_dir():
    with pytest.raises(SystemExit):
        emc.parse_args([])
    with pytest.raises(SystemExit):
        emc.parse_args(["--event", "nope", "--run-dir", "/x"])


def test_main_with_run_dir_and_explicit_event_writes_the_cache_and_gauge_csv_to_out_dir(tmp_path, monkeypatch):
    run_dir = tmp_path / "ws" / "project" / "run-id"
    fx.make_run(run_dir)
    fake = pd.DataFrame({"site": ["Klaipeda"], "time": [pd.Timestamp("2013-04-05 06:00")], "level_m": [0.12]})
    seen = {}
    monkeypatch.setattr(emc, "gauge_obs", lambda event: seen.setdefault("event", event.name) and fake)
    meta = emc.main(event="april_2013", run_dir=run_dir, out_dir=run_dir / "validation")
    assert mc.cache_valid(run_dir) and (run_dir / "map_meta.json").is_file()
    assert (run_dir / "validation" / "gauge_obs.csv").is_file()
    assert seen["event"] == "april_2013"  # not derived from the directory name, which matches no event
    assert meta["n_active"] == fx.N * fx.M - 15
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd /home/razinka/sfincs/curonian && micromamba -r /opt/micromamba run -n hydromt-sfincs python -m pytest tests/test_export_map_cache.py -q 2>&1 | tail -4`
Expected: the 3 new tests fail; the others pass.

- [ ] **Step 3: Change `export_map_cache.py`**

```python
def main(run: str | None = None, runs_dir: Path = common.RUNS, results_root: Path = common.ROOT / "results", *,
         event: str | None = None, run_dir: Path | None = None, out_dir: Path | None = None) -> dict:
    """Export one run's map cache and gauge readings.

    Command line: --run <name> under runs/, event derived from the name, gauge CSV to results/<name>.
    UI: --run-dir <dir> --event <name> --out-dir <dir>/validation, nothing derived from directory names.
    """
    if run_dir is None:
        if run is None:
            raise SystemExit("one of run or run_dir is required")
        run_dir = runs_dir / run
    ev = common.event(event) if event else event_for_run(run_dir.name)
    meta = mc.export_cache(run_dir)
    write_gauge_obs(ev, out_dir or results_root / run_dir.name)
    print(f"{run_dir.name} ({ev.name}): {meta['n_active']} cells x {len(meta['hours'])} hours, "
          f"ranges {meta['ranges']}")
    return meta


def parse_args(argv=None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--run", default=None, help="runs/<name> to export")
    p.add_argument("--event", default=None, choices=sorted(common.EVENTS), help="the run's event (default: from the run name)")
    p.add_argument("--run-dir", type=Path, default=None, help="export this directory instead of runs/<run>")
    p.add_argument("--out-dir", type=Path, default=None, help="write gauge_obs.csv here (default results/<name>)")
    args = p.parse_args(argv)
    if args.run is None and args.run_dir is None:
        p.error("one of --run or --run-dir is required")
    return args


if __name__ == "__main__":
    a = parse_args()
    main(a.run, event=a.event, run_dir=a.run_dir, out_dir=a.out_dir)
```

`common.event(name)` raises `KeyError` for an unknown name; argparse's `choices` rejects it first.

- [ ] **Step 4: Run the pipeline suite**

Run: `cd /home/razinka/sfincs/curonian && micromamba -r /opt/micromamba run -n hydromt-sfincs python -m pytest tests -q -m "not network" 2>&1 | tail -3`
Expected: Task 2's count plus 3.

- [ ] **Step 5: Commit**

```bash
cd /home/razinka/sfincs
git add curonian/prep/export_map_cache.py curonian/tests/test_export_map_cache.py
git commit -m "curonian: export_map_cache --event, --run-dir and --out-dir

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01K5wxxnsj5oVJ2gHNaNhr9B"
```

---

### Task 4: Optional and datetime fields, stage skip reasons, export evidence fix

**Files:**
- Modify: `sfincs_ui/sfincs_ui/templates/base.py`
- Modify: `sfincs_ui/sfincs_ui/services/job_runner.py`
- Modify: `sfincs_ui/pyproject.toml` (marker and default deselection)
- Test: `sfincs_ui/tests/test_templates.py`, `sfincs_ui/tests/test_job_runner.py` (additions)

**Interfaces:**
- `SettingField` gains `optional: bool = False` and the kind `"datetime"`. `coerce(None)` and `coerce("")` return `None` when `optional`, else raise `TemplateError("<key>: a value is required")`. Kind `"datetime"` accepts `"YYYY-MM-DD HH:MM"` (also `"YYYY-MM-DDTHH:MM"` and a trailing `:SS`), returns the canonical `"YYYY-MM-DD HH:MM"` string; bounds for datetimes are not handled by `SettingField` (templates do cross-field checks in `validate`).
- `Template.skip_reasons(settings) -> dict[str, str]`: stage name → one sentence why that stage is skipped for these settings (default `{}`). The runner records them: `_finish_run` writes `summary_json = {"skipped": {...}}` when non-empty (a finished run's summary was `None` before). `plan_stages` keeps omitting a stage whose command is `None`.
- `export_evidence(run_dir)` checks `run_dir / "map_meta.json"`.
- `pyproject.toml`: `markers = ["model_env: needs the hydromt-sfincs micromamba env; deselected by default"]`, `addopts = "-m 'not model_env'"`.

- [ ] **Step 1: Write the failing tests**

Append to `sfincs_ui/tests/test_templates.py` (`SettingField`, `TemplateError`, `pytest` and the `tpl` fixture are already imported there):

```python
def test_optional_field_round_trip():
    """Review Focus 3: an empty box means 'use the model's value' and survives coercion as None."""
    f = SettingField("dtmax", "dtmax", "float", None, minimum=1, maximum=600, optional=True)
    assert f.coerce(None) is None and f.coerce("") is None and f.coerce("  ") is None
    assert f.coerce("30") == 30.0
    with pytest.raises(TemplateError, match="dtmax"):
        f.coerce("0.5")
    required = SettingField("alpha", "alpha", "float", 0.5, minimum=0.1, maximum=0.9)
    with pytest.raises(TemplateError, match="required"):
        required.coerce(None)


def test_datetime_field_canonical_form():
    f = SettingField("tstop", "tstop", "datetime", None, optional=True)
    assert f.coerce("2013-12-09 06:00") == "2013-12-09 06:00"
    assert f.coerce("2013-12-09T06:00") == "2013-12-09 06:00"
    assert f.coerce("2013-12-09 06:00:00") == "2013-12-09 06:00"
    assert f.coerce(None) is None
    with pytest.raises(TemplateError, match="tstop"):
        f.coerce("9 Dec 2013")


def test_skip_reasons_default_empty(tpl):
    assert tpl.skip_reasons(tpl.defaults()) == {}
```

Append to `sfincs_ui/tests/test_job_runner.py` (uses the existing `runner` fixture and helpers):

```python
async def test_skip_reason_recorded_in_summary(runner, db, tmp_path, monkeypatch):
    """Review Focus 1: a template that skips a stage says why, and the finished run carries it."""
    from tests.fake_template import FakeTemplate

    class SkippingTemplate(FakeTemplate):
        def validate_command(self, run_dir, settings, config):
            return None

        def skip_reasons(self, settings):
            return {"validate": "run ends before the scoring window"}

    runner._templates["skipper"] = SkippingTemplate(with_validation=True)
    run_id = make_run(db, tmp_path, "skipper", S)
    await runner.start()
    runner.submit(run_id)
    await runner.wait(run_id, timeout=20)
    row = run_row(db, run_id)
    assert row["status"] == "finished" and [j["stage"] for j in row["jobs"]] == ["build", "simulate"]
    assert row["summary"] == {"skipped": {"validate": "run ends before the scoring window"}}


def test_export_evidence_looks_in_the_run_directory(tmp_path):
    from sfincs_ui.services.job_runner import export_evidence

    assert not export_evidence(tmp_path)
    (tmp_path / "map_meta.json").write_text("{}")
    assert export_evidence(tmp_path)
    (tmp_path / "map_meta.json").unlink(); (tmp_path / "validation").mkdir(); (tmp_path / "validation" / "map_meta.json").write_text("{}")
    assert not export_evidence(tmp_path)  # the cache lives next to sfincs_map.nc, not under validation/
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd /home/razinka/sfincs/sfincs_ui && /opt/micromamba/envs/shiny/bin/python -m pytest tests/test_templates.py tests/test_job_runner.py -q 2>&1 | tail -5`
Expected: the 5 new tests fail (`TypeError: unexpected keyword 'optional'`, `AttributeError: skip_reasons`, evidence assertion).

- [ ] **Step 3: Change `templates/base.py`**

```python
Kind = Literal["int", "float", "choice", "bool", "datetime"]
_DATETIME_FORMATS = ("%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S")


@dataclass(frozen=True)
class SettingField:
    ...
    group: str = "Model"
    optional: bool = False   # None / empty input means "use the model's value"; the key is then omitted from overrides

    def coerce(self, raw: Any) -> Any:
        if raw is None or (isinstance(raw, str) and not raw.strip()):
            if self.optional:
                return None
            raise TemplateError(f"{self.key}: a value is required")
        try:
            if self.kind == "datetime":
                text = str(raw).strip()
                for fmt in _DATETIME_FORMATS:
                    try:
                        return datetime.strptime(text, fmt).strftime("%Y-%m-%d %H:%M")
                    except ValueError:
                        continue
                raise TemplateError(f"{self.key}: expected a date and time like 2013-12-09 06:00")
            ... (bool / int / float / choice branches unchanged)
```

with `from datetime import datetime` at the top. In `Template`, add:

```python
    def skip_reasons(self, settings: dict) -> dict[str, str]:
        """stage -> why it is skipped for these settings (recorded in the run summary)."""
        return {}
```

- [ ] **Step 4: Change `services/job_runner.py`**

```python
def export_evidence(run_dir: Path) -> bool:
    # map_core.export_cache writes the cache next to sfincs_map.nc and map_meta.json last.
    return (run_dir / "map_meta.json").is_file()
```

In `_finish_run`, after computing `codes`:

```python
            run.status = "finished"; run.finished_at = utcnow()
            run.exit_code = None if any(c is None for c in codes) else 0
            try:
                _r, _p, template, settings, _d = self._load(run_id)
                skipped = template.skip_reasons(settings)
            except Exception:
                logger.exception("skip reasons for run %s unavailable", run_id)
                skipped = {}
            run.summary_json = json.dumps({"skipped": skipped}) if skipped else None
            s.commit()
```

(`_finish_run` opens its own session; call `self._load` before opening it, or inside before the commit as shown; `_load` uses a separate session and is safe to call here.)

- [ ] **Step 5: `pyproject.toml`**

Under `[tool.pytest.ini_options]` add:

```toml
addopts = "-m 'not model_env'"
markers = ["model_env: needs the hydromt-sfincs micromamba env and takes minutes; run with -m model_env"]
```

- [ ] **Step 6: Run the tests**

Run: `cd /home/razinka/sfincs/sfincs_ui && /opt/micromamba/envs/shiny/bin/python -m pytest -q 2>&1 | tail -2`
Expected: 242 passed (237 + 5), the `model_env` deselection line present in the summary header, no leaked processes.

- [ ] **Step 7: Commit**

```bash
cd /home/razinka/sfincs
git add sfincs_ui/sfincs_ui/templates/base.py sfincs_ui/sfincs_ui/services/job_runner.py sfincs_ui/pyproject.toml sfincs_ui/tests/test_templates.py sfincs_ui/tests/test_job_runner.py
git commit -m "sfincs_ui: optional and datetime settings, stage skip reasons in the run summary, export evidence in the run dir

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01K5wxxnsj5oVJ2gHNaNhr9B"
```

---

### Task 5: The Curonian template

**Files:**
- Create: `sfincs_ui/sfincs_ui/templates/curonian.py`
- Modify: `sfincs_ui/sfincs_ui/templates/__init__.py` (register `CuronianTemplate`)
- Modify: `sfincs_ui/pyproject.toml` (add `"pyproj>=3.6"` to `dependencies`; it is already installed in the UI env, 3.7.1)
- Test: `sfincs_ui/tests/test_templates_curonian.py`, `sfincs_ui/tests/test_curonian_geometry.py`, `sfincs_ui/tests/test_model_env_curonian.py` (marker `model_env`)

**Interfaces:**
- Consumes (from Task 1, `curonian/build_model.py`): `build(event, run_dir=None, subgrid=True, wind="uniform", pressure=False, manning_land=0.06, manning_sea=0.02, rgh_lev_land=0.3, grid=None, check=True)` where `grid` is `(x0, y0, mmax, nmax)`: the lower-left origin in EPSG:3346 metres and the cell counts at the 100 m cell size (default: the full domain), and `check=False` skips the post-build asserts and `check_model`'s active-cell bounds; `setup_subgrid` is called with `write_man_tif=True`, so `run_dir/subgrid/manning*.tif` exists after a subgrid build. CLI flags `--run-dir`, `--manning-land`, `--manning-sea`, `--rgh-lev-land`, `--wind {uniform,grid}`, `--pressure`, `--no-subgrid`, `--event`. From Tasks 2 and 3: `validate.py --event E --run-dir D --out-dir O` and `python -m prep.export_map_cache --event E --run-dir D --out-dir O` (both run with cwd = the curonian directory).
- `CURONIAN_EVENTS: dict[str, EventInfo]` mirroring `curonian/common.py`'s `EVENTS` for the fields the UI needs: `EventInfo(name, title, tref, tstop, data_window_end, score_window_end, zsini: float | None)` with ISO strings `"YYYY-MM-DD HH:MM"`. Values: `xaver_2013`: title "Xaver 2013", tref `2013-11-28 00:00`, tstop `2013-12-11 00:00`, data window end `2013-12-20 00:00`, score window end `2013-12-09 00:00`, zsini `None`; `april_2013`: title "April 2013 Nemunas freshet", tref `2013-04-05 00:00`, tstop `2013-05-02 00:00`, data window end `2013-05-12 00:00`, score window end `2013-05-02 00:00`, zsini `-0.17`.
- `CuronianTemplate` (key `"curonian"`, title "Curonian Lagoon and Nemunas delta", `has_validation = True`, `has_export = True`): fields below; `validate` adds the cross-field rule for `tstop` (`tref < tstop <= data_window_end`, else `TemplateError("tstop: must lie after <tref> and no later than <data end> for <event>")`); `build_command` per the Global Constraints (always passes the three manning flags); `stage_cwd` returns `config.curonian_dir` for build, validate and export and `run_dir` for simulate; `inp_overrides` returns `alpha`, `huthresh`, `viscosity` (`"1"`/`"0"`), `advection` (`"1"`/`"0"`) always, plus `zsini`, `dtmax`, `nuvisc` when set and `tstop` as `YYYYMMDD HHMMSS` when set; never a `manning` key; `model_files()` = `("sfincs.msk", "sfincs.ind", "sfincs.bzs", "sfincs.dis", "sfincs.obs")`; `validate_command` returns `None` when `tstop` is set and earlier than the event's score window end, else the validate command; `skip_reasons` returns `{"validate": "run ends before the scoring window"}` in that case; `export_command` always; `default_threads` = 8; `geometry_layers(project_dir, settings)` returns the five static layers from `config.curonian_dir/inputs` reprojected to WGS84 (see below); `example_projects` = `[("Xaver 2013 (uniform wind)", defaults with event xaver_2013), ("April 2013 (uniform wind)", defaults with event april_2013)]`.

Fields:

| key | kind | default | bounds / choices | group | explanation |
|---|---|---|---|---|---|
| `event` | choice | `xaver_2013` | `xaver_2013`, `april_2013` | Event | Which hindcast period and forcing set to run. |
| `wind` | choice | `uniform` | `uniform`, `grid` | Variant | Nida point series or gridded ERA5 wind. |
| `pressure` | bool | False | | Variant | Add gridded ERA5 pressure (needs gridded wind; validated). |
| `subgrid` | bool | True | | Variant | Subgrid tables (recommended); off uses the inp roughness only. |
| `manning_land` | float | 0.06 | 0.01..0.2 | Build parameters (rebuilds the subgrid table) | Roughness above `rgh_lev_land`. |
| `manning_sea` | float | 0.02 | 0.005..0.1 | same | Roughness below `rgh_lev_land`. |
| `rgh_lev_land` | float | 0.3 | 0..2 | same | Level that separates land and sea roughness (m). |
| `alpha` | float | 0.5 | 0.1..0.9 | Solver overrides | CFL number. |
| `huthresh` | float | 0.05 | 0.001..0.5 | Solver overrides | Wet/dry threshold (m); read at run time even in subgrid mode. |
| `zsini` | float, optional | None | -2..3 | Solver overrides | Initial water level (m); empty = the event's value (from the boundary for Xaver, -0.17 for April). |
| `dtmax` | float, optional | None | 1..600 | Solver overrides | Maximum time step (s); empty = the built value (60). |
| `nuvisc` | float, optional | None | 0..1 | Solver overrides | Viscosity coefficient; empty = SFINCS default; the manual recommends 0.01 per metre of cell size. |
| `viscosity` | bool | True | | Solver overrides | Viscosity term on/off. |
| `advection` | bool | True | | Solver overrides | Momentum advection on/off. |
| `tstop` | datetime, optional | None | within the event's window | Solver overrides | Stop time; empty = the event's end. Before the scoring window the run is not validated. |

`validate` also enforces `pressure` requires `wind == "grid"` (`TemplateError("pressure: requires gridded wind")`).

Geometry: module-level `_TO_WGS84 = pyproj.Transformer.from_crs(3346, 4326, always_xy=True)`; `load_geometry(inputs_dir) -> list[dict]` reads `active_region.geojson` (polygon → layer `domain`), `channels.geojson` (lines → `channels`, `labels` from `name`), `boundary_points.geojson` (points → `boundary`), `dis_points.geojson` (points → `inflows`, labels from `name`), `stations.geojson` (points → `stations`, labels from `name`); every layer dict is `{"name", "crs": "EPSG:4326", "geometry": <GeoJSON geometry with reprojected coordinates>, "labels": [...] | absent}`; a missing or unreadable file is skipped with a logged warning (the map shows what it can). Results are cached per `inputs_dir` with `functools.lru_cache` on the resolved path string.

- [ ] **Step 1: Write the failing tests**

`sfincs_ui/tests/test_templates_curonian.py`:

```python
import sys

import pytest

from sfincs_ui.config import Config
from sfincs_ui.exceptions import TemplateError
from sfincs_ui.templates import TEMPLATES, get_template
from sfincs_ui.templates.curonian import CURONIAN_EVENTS, CuronianTemplate


@pytest.fixture
def tpl():
    return get_template("curonian")


@pytest.fixture
def cfg(tmp_path):
    return Config(workspace=tmp_path, curonian_dir=tmp_path / "curonian", model_python="micromamba run -n hydromt-sfincs python")


def test_registered_and_events_mirror():
    assert isinstance(TEMPLATES["curonian"], CuronianTemplate)
    assert set(CURONIAN_EVENTS) == {"xaver_2013", "april_2013"}
    x = CURONIAN_EVENTS["xaver_2013"]
    assert (x.tref, x.tstop, x.score_window_end, x.data_window_end, x.zsini) == ("2013-11-28 00:00", "2013-12-11 00:00", "2013-12-09 00:00", "2013-12-20 00:00", None)
    assert CURONIAN_EVENTS["april_2013"].zsini == -0.17


def test_fields_groups_and_defaults(tpl):
    groups = {f.key: f.group for f in tpl.fields()}
    assert groups["manning_land"] == "Build parameters (rebuilds the subgrid table)"
    assert {k for k, g in groups.items() if g == "Solver overrides"} == {"alpha", "huthresh", "zsini", "dtmax", "nuvisc", "viscosity", "advection", "tstop"}
    d = tpl.defaults()
    assert d["event"] == "xaver_2013" and d["wind"] == "uniform" and d["subgrid"] is True and d["manning_land"] == 0.06
    assert d["zsini"] is None and d["dtmax"] is None and d["nuvisc"] is None and d["tstop"] is None
    assert all(f.optional for f in tpl.fields() if f.key in ("zsini", "dtmax", "nuvisc", "tstop"))


def test_build_command_flags(tpl, cfg):
    s = {**tpl.defaults(), "wind": "grid", "pressure": True, "subgrid": False, "manning_land": 0.08}
    argv = tpl.build_command(cfg.workspace / "run", s, cfg)
    assert argv[:5] == ["micromamba", "run", "-n", "hydromt-sfincs", "python"]
    assert argv[5] == str(cfg.curonian_dir / "build_model.py")
    rest = argv[6:]
    assert rest[:4] == ["--event", "xaver_2013", "--run-dir", str(cfg.workspace / "run")]
    assert "--wind" in rest and rest[rest.index("--wind") + 1] == "grid" and "--pressure" in rest and "--no-subgrid" in rest
    assert rest[rest.index("--manning-land") + 1] == "0.08" and "--manning-sea" in rest and "--rgh-lev-land" in rest
    plain = tpl.build_command(cfg.workspace / "run", tpl.defaults(), cfg)
    assert "--wind" not in plain and "--pressure" not in plain and "--no-subgrid" not in plain
    assert tpl.stage_cwd("build", cfg.workspace / "run", cfg) == cfg.curonian_dir
    assert tpl.stage_cwd("simulate", cfg.workspace / "run", cfg) == cfg.workspace / "run"


def test_unset_overrides_are_omitted(tpl):
    """Review Focus 3 and the manning rule."""
    o = tpl.inp_overrides(tpl.defaults())
    assert o == {"alpha": "0.5", "huthresh": "0.05", "viscosity": "1", "advection": "1"}
    assert not any("manning" in k for k in o)
    s = {**tpl.defaults(), "zsini": 0.4, "dtmax": 30, "nuvisc": 0.02, "viscosity": False, "tstop": "2013-12-09 06:00"}
    o = tpl.inp_overrides(s)
    assert o["zsini"] == "0.4" and o["dtmax"] == "30.0" and o["nuvisc"] == "0.02" and o["viscosity"] == "0"
    assert o["tstop"] == "20131209 060000"


def test_validate_and_export_commands(tpl, cfg):
    run = cfg.workspace / "run"
    v = tpl.validate_command(run, tpl.defaults(), cfg)
    assert v[5] == str(cfg.curonian_dir / "validate.py") and v[6:] == ["--event", "xaver_2013", "--run-dir", str(run), "--out-dir", str(run / "validation")]
    e = tpl.export_command(run, tpl.defaults(), cfg)
    assert e[5:7] == ["-m", "prep.export_map_cache"] and e[7:] == ["--event", "xaver_2013", "--run-dir", str(run), "--out-dir", str(run / "validation")]
    assert tpl.stage_cwd("validate", run, cfg) == cfg.curonian_dir and tpl.stage_cwd("export", run, cfg) == cfg.curonian_dir
    assert tpl.default_threads(tpl.defaults()) == 8
    assert tpl.model_files() == ("sfincs.msk", "sfincs.ind", "sfincs.bzs", "sfincs.dis", "sfincs.obs")


def test_tstop_before_score_window_skips_validation(tpl, cfg):
    """Review Focus 1."""
    s = tpl.validate({**tpl.defaults(), "tstop": "2013-12-07 00:00"})
    assert tpl.validate_command(cfg.workspace / "r", s, cfg) is None
    assert tpl.skip_reasons(s) == {"validate": "run ends before the scoring window"}
    s2 = tpl.validate({**tpl.defaults(), "tstop": "2013-12-09 00:00"})
    assert tpl.validate_command(cfg.workspace / "r", s2, cfg) is not None and tpl.skip_reasons(s2) == {}


def test_tstop_bounds_per_event(tpl):
    """Review Focus 2."""
    with pytest.raises(TemplateError, match="tstop"):
        tpl.validate({**tpl.defaults(), "tstop": "2013-12-25 00:00"})  # after the data window
    with pytest.raises(TemplateError, match="tstop"):
        tpl.validate({**tpl.defaults(), "tstop": "2013-11-28 00:00"})  # not after tref
    ok = tpl.validate({**tpl.defaults(), "event": "april_2013", "tstop": "2013-05-10 12:00"})
    assert ok["tstop"] == "2013-05-10 12:00"
    with pytest.raises(TemplateError, match="tstop"):
        tpl.validate({**tpl.defaults(), "event": "april_2013", "tstop": "2013-12-09 00:00"})


def test_pressure_requires_grid_wind(tpl):
    with pytest.raises(TemplateError, match="pressure"):
        tpl.validate({**tpl.defaults(), "pressure": True})
    assert tpl.validate({**tpl.defaults(), "wind": "grid", "pressure": True})["pressure"] is True


def test_examples(tpl):
    names = [n for n, _ in tpl.example_projects()]
    assert names == ["Xaver 2013 (uniform wind)", "April 2013 (uniform wind)"]
    assert tpl.example_projects()[1][1]["event"] == "april_2013"
```

`sfincs_ui/tests/test_curonian_geometry.py`:

```python
import json
from pathlib import Path

import pytest

from sfincs_ui.config import REPO_ROOT
from sfincs_ui.templates.curonian import load_geometry

INPUTS = REPO_ROOT / "curonian" / "inputs"


def test_layers_from_the_real_inputs_are_wgs84():
    if not (INPUTS / "active_region.geojson").is_file():
        pytest.skip("curonian inputs not in this checkout")
    load_geometry.cache_clear()
    layers = {l["name"]: l for l in load_geometry(INPUTS)}
    assert set(layers) == {"domain", "channels", "boundary", "inflows", "stations"}
    assert all(l["crs"] == "EPSG:4326" for l in layers.values())
    lon, lat = layers["stations"]["geometry"]["coordinates"][0]
    assert 20.5 < lon < 22.5 and 55.0 < lat < 56.0, (lon, lat)  # the lagoon, not the Atlantic
    assert len(layers["stations"]["labels"]) == len(layers["stations"]["geometry"]["coordinates"]) == 9
    assert layers["domain"]["geometry"]["type"] == "Polygon" and layers["channels"]["geometry"]["type"] == "MultiLineString"
    assert layers["channels"]["labels"] == ["strait", "atmata", "skirvyte"]
    assert layers["inflows"]["labels"] == ["Nemunas_Rusne", "Minija_mouth"] and "labels" not in layers["boundary"]
    assert len(layers["boundary"]["geometry"]["coordinates"]) == 7


def test_missing_files_are_skipped_not_fatal(tmp_path):
    (tmp_path / "stations.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": [
        {"type": "Feature", "properties": {"name": "A"}, "geometry": {"type": "Point", "coordinates": [320000.0, 6150000.0]}}]}))
    load_geometry.cache_clear()
    layers = load_geometry(tmp_path)
    assert [l["name"] for l in layers] == ["stations"] and layers[0]["labels"] == ["A"]
    (tmp_path / "channels.geojson").write_text("{not json")
    load_geometry.cache_clear()
    assert [l["name"] for l in load_geometry(tmp_path)] == ["stations"]
```

`sfincs_ui/tests/test_model_env_curonian.py` (marker `model_env`, skipped when the env is absent):

```python
"""Model-env tests (spec section 6): run with `-m model_env`; minutes, not seconds."""

import json
import subprocess
import time
from pathlib import Path

import pytest

from sfincs_ui.config import REPO_ROOT

MODEL_PYTHON = ["micromamba", "-r", "/opt/micromamba", "run", "-n", "hydromt-sfincs", "python"]
CURONIAN = REPO_ROOT / "curonian"
pytestmark = pytest.mark.model_env


def _env_available() -> bool:
    try:
        return subprocess.run([*MODEL_PYTHON, "-c", "import hydromt_sfincs"], capture_output=True, timeout=120).returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


@pytest.fixture(scope="module", autouse=True)
def _need_env():
    if not _env_available():
        pytest.skip("hydromt-sfincs env not available")


def test_events_mirror_matches_common_events():
    """The template's event table must not drift from curonian/common.py."""
    from sfincs_ui.templates.curonian import CURONIAN_EVENTS

    code = ("import common, json; print(json.dumps({n: dict(title=e.title, tref=e.tref.strftime('%Y-%m-%d %H:%M'), "
            "tstop=e.tstop.strftime('%Y-%m-%d %H:%M'), data_end=str(e.data_window[1]) + ' 00:00', "
            "score_end=e.score_window[1].strftime('%Y-%m-%d %H:%M'), zsini=e.zsini) for n, e in common.EVENTS.items()}))")
    out = subprocess.run([*MODEL_PYTHON, "-c", code], cwd=CURONIAN, capture_output=True, text=True, timeout=120)
    assert out.returncode == 0, out.stderr
    real = json.loads(out.stdout)
    assert set(real) == set(CURONIAN_EVENTS)
    for name, e in CURONIAN_EVENTS.items():
        r = real[name]
        assert (e.title, e.tref, e.tstop, e.data_window_end, e.score_window_end, e.zsini) == (r["title"], r["tref"], r["tstop"], r["data_end"], r["score_end"], r["zsini"]), name


def test_export_map_cache_imports_cleanly():
    out = subprocess.run([*MODEL_PYTHON, "-m", "prep.export_map_cache", "--help"], cwd=CURONIAN, capture_output=True, text=True, timeout=120)
    assert out.returncode == 0 and "--run-dir" in out.stdout and "--event" in out.stdout


def test_small_domain_build_applies_manning_land(tmp_path):
    """A sub-domain build with manning_land = 0.08 writes a subgrid roughness raster carrying that value."""
    run_dir = tmp_path / "small"
    code = (
        "import sys, common, build_model as bm\n"
        f"bm.build(common.EVENTS['xaver_2013'], run_dir=sys.argv[1], manning_land=0.08, grid=(330000.0, 6120000.0, 60, 60), check=False)\n"
    )
    t0 = time.monotonic()
    out = subprocess.run([*MODEL_PYTHON, "-c", code, str(run_dir)], cwd=CURONIAN, capture_output=True, text=True, timeout=1800)
    elapsed = time.monotonic() - t0
    assert out.returncode == 0, out.stderr[-3000:]
    tifs = list((run_dir / "subgrid").glob("manning*.tif"))
    assert tifs, "setup_subgrid(write_man_tif=True) must write a manning raster"
    check = ("import sys, numpy as np, rasterio\n"
             "with rasterio.open(sys.argv[1]) as src: a = src.read(1, masked=True)\n"
             "print(float(np.nanmax(a.filled(np.nan))), float(np.nanmin(a.filled(np.nan))))")
    vals = subprocess.run([*MODEL_PYTHON, "-c", check, str(tifs[0])], capture_output=True, text=True, timeout=120)
    assert vals.returncode == 0, vals.stderr
    vmax, vmin = map(float, vals.stdout.split())
    assert vmax == pytest.approx(0.08, abs=1e-6) and vmin == pytest.approx(0.02, abs=1e-6)
    print(f"\nsmall-domain subgrid build: {elapsed:.0f} s")
```

The grid `(330000, 6120000, 60, 60)` is a 6 km square in the delta south-east of the lagoon that holds both land and water; if the roughness raster shows only one value, move the origin so the window straddles the shoreline, and record the final origin in the test comment.

- [ ] **Step 2: Run the UI tests to verify they fail**

Run: `cd /home/razinka/sfincs/sfincs_ui && /opt/micromamba/envs/shiny/bin/python -m pytest tests/test_templates_curonian.py tests/test_curonian_geometry.py -q 2>&1 | tail -3`
Expected: FAIL with `ModuleNotFoundError: No module named 'sfincs_ui.templates.curonian'`.

- [ ] **Step 3: Write `templates/curonian.py`**

```python
"""The Curonian Lagoon template: drives curonian/build_model.py, validate.py and
prep/export_map_cache.py from a settings document (spec sections 1 to 3)."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime
from functools import lru_cache
from pathlib import Path

from pyproj import Transformer

from sfincs_ui.config import Config
from sfincs_ui.exceptions import TemplateError
from sfincs_ui.templates.base import SettingField, Template

logger = logging.getLogger(__name__)
_FMT = "%Y-%m-%d %H:%M"
_TO_WGS84 = Transformer.from_crs(3346, 4326, always_xy=True)
BUILD_GROUP = "Build parameters (rebuilds the subgrid table)"
OVERRIDES = "Solver overrides"
NOT_SCORED = "run ends before the scoring window"


@dataclass(frozen=True)
class EventInfo:
    """Mirror of the fields the UI needs from curonian/common.py EVENTS.

    Kept here so the UI process never imports `common` (it resolves paths under
    Path.home() at import). tests/test_model_env_curonian.py asserts it matches.
    """
    name: str
    title: str
    tref: str
    tstop: str
    data_window_end: str
    score_window_end: str
    zsini: float | None


CURONIAN_EVENTS: dict[str, EventInfo] = {
    "xaver_2013": EventInfo("xaver_2013", "Xaver 2013", "2013-11-28 00:00", "2013-12-11 00:00", "2013-12-20 00:00", "2013-12-09 00:00", None),
    "april_2013": EventInfo("april_2013", "April 2013 Nemunas freshet", "2013-04-05 00:00", "2013-05-02 00:00", "2013-05-12 00:00", "2013-05-02 00:00", -0.17),
}

# Static geometry shown on the Setup map: (layer name, file, label property or None).
_GEOMETRY_FILES = (
    ("domain", "active_region.geojson", None),
    ("channels", "channels.geojson", "name"),
    ("boundary", "boundary_points.geojson", None),
    ("inflows", "dis_points.geojson", "name"),
    ("stations", "stations.geojson", "name"),
)


def _reproject(coords):
    if isinstance(coords[0], (int, float)):
        lon, lat = _TO_WGS84.transform(coords[0], coords[1])
        return [float(lon), float(lat)]
    return [_reproject(c) for c in coords]


@lru_cache(maxsize=8)
def _load_geometry_cached(inputs_dir: str) -> tuple[dict, ...]:
    out = []
    for name, fname, label_prop in _GEOMETRY_FILES:
        path = Path(inputs_dir) / fname
        try:
            data = json.loads(path.read_text())
            features = [f for f in data.get("features", []) if f.get("geometry")]
            geoms = [f["geometry"] for f in features]
            if not geoms:
                continue
            if all(g["type"] == "Point" for g in geoms):
                geometry = {"type": "MultiPoint", "coordinates": [_reproject(g["coordinates"]) for g in geoms]}
            elif all(g["type"] == "LineString" for g in geoms):
                geometry = {"type": "MultiLineString", "coordinates": [_reproject(g["coordinates"]) for g in geoms]}
            elif len(geoms) == 1:
                geometry = {"type": geoms[0]["type"], "coordinates": _reproject(geoms[0]["coordinates"])}
            else:
                geometry = {"type": "GeometryCollection", "geometries": [{"type": g["type"], "coordinates": _reproject(g["coordinates"])} for g in geoms]}
            layer = {"name": name, "crs": "EPSG:4326", "geometry": geometry}
            if label_prop:
                layer["labels"] = [str(f.get("properties", {}).get(label_prop, "")) for f in features]
            out.append(layer)
        except (OSError, ValueError, KeyError, TypeError) as exc:
            logger.warning("Setup map: %s unreadable (%s); layer %s skipped", path, exc, name)
    return tuple(out)


def load_geometry(inputs_dir: Path) -> list[dict]:
    return [dict(l) for l in _load_geometry_cached(str(Path(inputs_dir).resolve()))]


load_geometry.cache_clear = _load_geometry_cached.cache_clear  # tests clear it between fixtures


class CuronianTemplate(Template):
    key = "curonian"
    title = "Curonian Lagoon and Nemunas delta"
    description = ("The 100 m SFINCS model of the Curonian Lagoon with the Nemunas delta: two hindcast events "
                   "(Xaver 2013 storm surge, April 2013 freshet), gridded or uniform wind, subgrid tables, "
                   "validated against four gauges. A run builds for several minutes and simulates for about "
                   "an hour at 8 threads.")
    has_validation = True
    has_export = True

    def fields(self) -> list[SettingField]:
        return [
            SettingField("event", "Event", "choice", "xaver_2013", choices=("xaver_2013", "april_2013"), group="Event",
                         explanation="Which hindcast period and forcing set to run."),
            SettingField("wind", "Wind", "choice", "uniform", choices=("uniform", "grid"), group="Variant",
                         explanation="uniform: the Nida point series; grid: gridded ERA5 wind."),
            SettingField("pressure", "ERA5 pressure", "bool", False, group="Variant",
                         explanation="Add gridded ERA5 mean sea level pressure (needs gridded wind)."),
            SettingField("subgrid", "Subgrid tables", "bool", True, group="Variant",
                         explanation="Subgrid bathymetry and roughness tables (recommended); off uses the grid-cell DEM and inp roughness."),
            SettingField("manning_land", "Manning n, land", "float", 0.06, minimum=0.01, maximum=0.2, group=BUILD_GROUP,
                         explanation="Roughness above rgh_lev_land. Changing it rebuilds the subgrid table."),
            SettingField("manning_sea", "Manning n, sea", "float", 0.02, minimum=0.005, maximum=0.1, group=BUILD_GROUP,
                         explanation="Roughness below rgh_lev_land."),
            SettingField("rgh_lev_land", "Land/sea level (m)", "float", 0.3, minimum=0.0, maximum=2.0, group=BUILD_GROUP,
                         explanation="Elevation separating land and sea roughness."),
            SettingField("alpha", "alpha", "float", 0.5, minimum=0.1, maximum=0.9, group=OVERRIDES, explanation="CFL number."),
            SettingField("huthresh", "huthresh (m)", "float", 0.05, minimum=0.001, maximum=0.5, group=OVERRIDES,
                         explanation="Wet/dry threshold depth; read at run time even in subgrid mode."),
            SettingField("zsini", "zsini (m)", "float", None, minimum=-2.0, maximum=3.0, group=OVERRIDES, optional=True,
                         explanation="Initial water level. Empty: the event's value (the sea boundary for Xaver, -0.17 m for April)."),
            SettingField("dtmax", "dtmax (s)", "float", None, minimum=1.0, maximum=600.0, group=OVERRIDES, optional=True,
                         explanation="Maximum time step. Empty: the built value (60 s)."),
            SettingField("nuvisc", "nuvisc", "float", None, minimum=0.0, maximum=1.0, group=OVERRIDES, optional=True,
                         explanation="Viscosity coefficient per metre of cell size. Empty: the SFINCS default; the manual recommends 0.01."),
            SettingField("viscosity", "Viscosity", "bool", True, group=OVERRIDES, explanation="Viscosity term on or off."),
            SettingField("advection", "Advection", "bool", True, group=OVERRIDES, explanation="Momentum advection on or off."),
            SettingField("tstop", "Stop time", "datetime", None, group=OVERRIDES, optional=True,
                         explanation="YYYY-MM-DD HH:MM within the event's data window. Empty: the event's end. Before the scoring window the run is not validated."),
        ]

    # -- settings ------------------------------------------------------------

    def validate(self, settings: dict) -> dict:
        s = super().validate(settings)
        ev = CURONIAN_EVENTS[s["event"]]
        if s["pressure"] and s["wind"] != "grid":
            raise TemplateError("pressure: requires gridded wind")
        if s["tstop"] is not None and not (ev.tref < s["tstop"] <= ev.data_window_end):
            raise TemplateError(f"tstop: must lie after {ev.tref} and no later than {ev.data_window_end} for {ev.title}")
        return s

    def _event(self, settings: dict) -> EventInfo:
        return CURONIAN_EVENTS[settings["event"]]

    def _not_scored(self, settings: dict) -> bool:
        return settings.get("tstop") is not None and settings["tstop"] < self._event(settings).score_window_end

    # -- commands -----------------------------------------------------------

    def build_command(self, run_dir: Path, settings: dict, config: Config) -> list[str]:
        s = self.validate(settings)
        argv = [*config.model_python_argv, str(config.curonian_dir / "build_model.py"),
                "--event", s["event"], "--run-dir", str(run_dir)]
        if s["wind"] == "grid":
            argv += ["--wind", "grid"]
        if s["pressure"]:
            argv.append("--pressure")
        if not s["subgrid"]:
            argv.append("--no-subgrid")
        argv += ["--manning-land", str(s["manning_land"]), "--manning-sea", str(s["manning_sea"]), "--rgh-lev-land", str(s["rgh_lev_land"])]
        return argv

    def stage_cwd(self, stage: str, run_dir: Path, config: Config) -> Path:
        return run_dir if stage == "simulate" else config.curonian_dir

    def inp_overrides(self, settings: dict) -> dict[str, str]:
        s = self.validate(settings)
        out = {"alpha": str(s["alpha"]), "huthresh": str(s["huthresh"]),
               "viscosity": "1" if s["viscosity"] else "0", "advection": "1" if s["advection"] else "0"}
        for key in ("zsini", "dtmax", "nuvisc"):
            if s[key] is not None:
                out[key] = str(float(s[key]))
        if s["tstop"] is not None:
            out["tstop"] = datetime.strptime(s["tstop"], _FMT).strftime("%Y%m%d %H%M%S")
        return out

    def model_files(self) -> tuple[str, ...]:
        return ("sfincs.msk", "sfincs.ind", "sfincs.bzs", "sfincs.dis", "sfincs.obs")

    def validate_command(self, run_dir: Path, settings: dict, config: Config) -> list[str] | None:
        s = self.validate(settings)
        if self._not_scored(s):
            return None
        return [*config.model_python_argv, str(config.curonian_dir / "validate.py"), "--event", s["event"],
                "--run-dir", str(run_dir), "--out-dir", str(run_dir / "validation")]

    def skip_reasons(self, settings: dict) -> dict[str, str]:
        return {"validate": NOT_SCORED} if self._not_scored(self.validate(settings)) else {}

    def export_command(self, run_dir: Path, settings: dict, config: Config) -> list[str] | None:
        s = self.validate(settings)
        return [*config.model_python_argv, "-m", "prep.export_map_cache", "--event", s["event"],
                "--run-dir", str(run_dir), "--out-dir", str(run_dir / "validation")]

    def default_threads(self, settings: dict) -> int:
        return 8

    def geometry_layers(self, project_dir: Path, settings: dict) -> list[dict]:
        from sfincs_ui.config import get_config
        return load_geometry(get_config().curonian_dir / "inputs")

    def example_projects(self) -> list[tuple[str, dict]]:
        return [("Xaver 2013 (uniform wind)", self.defaults()),
                ("April 2013 (uniform wind)", {**self.defaults(), "event": "april_2013"})]
```

Note on `inp_overrides` numeric formatting: `str(float(30))` gives `"30.0"` (the test expects it), `str(0.5)` gives `"0.5"`.

`templates/__init__.py`: `from sfincs_ui.templates.curonian import CuronianTemplate` and `TEMPLATES = {t.key: t for t in (PlaneBeachTemplate(), CuronianTemplate())}`; export it in `__all__`.

- [ ] **Step 4: Run the UI tests**

Run: `cd /home/razinka/sfincs/sfincs_ui && /opt/micromamba/envs/shiny/bin/python -m pytest tests/test_templates_curonian.py tests/test_curonian_geometry.py -q 2>&1 | tail -3`
Expected: 11 passed. Then the full suite: 253 passed (242 + 11; the model_env tests are deselected). Check `tests/test_app_http_m2.py` and the project-service tests still pass with two templates registered (`ensure_examples` now seeds three example projects: the plane beach and two Curonian ones).

- [ ] **Step 5: Run the model-env tests and record the duration**

Run: `cd /home/razinka/sfincs/sfincs_ui && /opt/micromamba/envs/shiny/bin/python -m pytest tests/test_model_env_curonian.py -m model_env -q -s 2>&1 | tail -6`
Expected: 3 passed; the printed `small-domain subgrid build: N s`. If the build exceeds 10 minutes, shrink the grid to 40×40 and record the new origin and duration. If the roughness raster shows a single value, move the origin as the comment in the test says.

- [ ] **Step 6: Commit**

```bash
cd /home/razinka/sfincs
git add sfincs_ui/sfincs_ui/templates/curonian.py sfincs_ui/sfincs_ui/templates/__init__.py sfincs_ui/pyproject.toml sfincs_ui/tests/test_templates_curonian.py sfincs_ui/tests/test_curonian_geometry.py sfincs_ui/tests/test_model_env_curonian.py
git commit -m "sfincs_ui: the Curonian template (events, variants, build parameters, overrides, geometry) with model-env tests

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01K5wxxnsj5oVJ2gHNaNhr9B"
```

---

### Task 6: Setup page map preview, optional and datetime inputs, Runs page skip reason

**Files:**
- Modify: `sfincs_ui/sfincs_ui/pages/setup.py`
- Modify: `sfincs_ui/sfincs_ui/pages/runs.py`
- Modify: `sfincs_ui/sfincs_ui/app.py` (`head_includes()` in `build_ui`)
- Modify: `sfincs_ui/pyproject.toml` (add `"shiny-deckgl>=1.9"` to `dependencies`; 1.9.2 is installed in the UI env)
- Modify: `sfincs_ui/sfincs_ui/www/sfincs_ui.css` (map height)
- Test: `sfincs_ui/tests/test_pages_m2.py` (additions), `sfincs_ui/tests/test_pages_m3.py`

**Interfaces:**
- Consumes `Template.geometry_layers(project_dir, settings) -> list[dict]` where a layer is `{"name", "geometry", "crs"?, "labels"?}` (Task 5 sets `"crs": "EPSG:4326"`; the plane beach layers carry no `crs`).
- `setup.map_layers(layers: list[dict]) -> list` is the pure function that turns template layers into deck.gl layer objects: it keeps only layers whose `crs` is `"EPSG:4326"` (the plane beach's metre coordinates would otherwise land in the Gulf of Guinea), returns `[]` when none qualify; `domain` → `geojson_layer(id="domain", data=<Feature>, filled=True, get_fill_color=[30, 120, 200, 40], get_line_color=[30, 120, 200, 200], line_width_min_pixels=2)`; `channels` → `geojson_layer(id="channels", data=<Feature>, stroked=True, get_line_color=[200, 80, 30, 220], line_width_min_pixels=2)`; point layers (`boundary`, `inflows`, `stations`) → `scatterplot_layer(id=<name>, data=[{"position": [lon, lat], "name": label}], get_position="position", get_radius=<300 stations, 500 inflows, 400 boundary>, get_fill_color=<stations [220, 40, 40, 220], inflows [40, 160, 60, 220], boundary [40, 40, 220, 220]>, pickable=True, radius_min_pixels=4)`. `setup.map_message(layers) -> str | None` returns `"No georeferenced geometry for this template."` when `map_layers` is empty and `None` otherwise.
- `setup.render_field` handles `kind == "datetime"` with `ui.input_text(key, label, value or "", placeholder="YYYY-MM-DD HH:MM")`, and optional numeric fields with `ui.input_numeric(..., value=None)` plus the label suffix `" (empty: model default)"` instead of `" (default X)"`. `collect_settings` leaves blanks as `None` (Shiny gives `None` for an empty numeric and `""` for an empty text; `coerce` handles both).
- Runs page `detail()` appends, for a finished run whose `summary["skipped"]` is non-empty, `ui.div(ui.strong("Skipped: "), ", ".join(f"{stage} ({reason})" ...), class_="alert alert-secondary")`.
- `app.build_ui` adds `*head_includes()` from `shiny_deckgl` inside the `header` TagList (before the stylesheet).

- [ ] **Step 1: Write the failing tests**

Append to `sfincs_ui/tests/test_pages_m2.py`:

```python
def test_render_optional_and_datetime_fields():
    tpl = get_template("curonian")
    fields = {f.key: f for f in tpl.fields()}
    html = str(setup.render_field(fields["dtmax"], None))
    assert 'type="number"' in html and "empty: model default" in html and "changed" not in html
    assert "changed" in str(setup.render_field(fields["dtmax"], 30.0))
    html = str(setup.render_field(fields["tstop"], None))
    assert 'type="text"' in html and 'placeholder="YYYY-MM-DD HH:MM"' in html
    assert 'value="2013-12-09 06:00"' in str(setup.render_field(fields["tstop"], "2013-12-09 06:00"))
```

Create `sfincs_ui/tests/test_pages_m3.py`:

```python
"""Setup map and Runs skip reason (milestone 3)."""

from shiny import ui

from sfincs_ui.pages import runs, setup
from sfincs_ui.templates import get_template


def test_setup_ui_has_the_map_slot():
    html = str(setup.setup_ui("setup"))
    assert "setup-map" in html and "setup-map_message" in html


def test_setup_map_ignores_local_crs_layers():
    """Review Focus 5: metre coordinates never reach deck.gl as degrees."""
    pb = get_template("plane_beach").geometry_layers(None, get_template("plane_beach").defaults())
    assert pb and all("crs" not in l for l in pb)
    assert setup.map_layers(pb) == []
    assert setup.map_message(pb) == "No georeferenced geometry for this template."
    mixed = pb + [{"name": "stations", "crs": "EPSG:4326", "geometry": {"type": "MultiPoint", "coordinates": [[21.1, 55.3]]}, "labels": ["Nida"]}]
    layers = setup.map_layers(mixed)
    assert len(layers) == 1 and setup.map_message(mixed) is None
    assert [l for l in setup.map_layers([{"name": "domain", "crs": "EPSG:3346", "geometry": {"type": "Polygon", "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 0]]]}}])] == []


def test_map_layers_shapes():
    layers = setup.map_layers([
        {"name": "domain", "crs": "EPSG:4326", "geometry": {"type": "Polygon", "coordinates": [[[21.0, 55.0], [21.5, 55.0], [21.5, 55.5], [21.0, 55.0]]]}},
        {"name": "channels", "crs": "EPSG:4326", "geometry": {"type": "MultiLineString", "coordinates": [[[21.0, 55.0], [21.1, 55.1]]]}, "labels": ["strait"]},
        {"name": "stations", "crs": "EPSG:4326", "geometry": {"type": "MultiPoint", "coordinates": [[21.1, 55.3], [21.2, 55.4]]}, "labels": ["Nida", "Vente"]},
    ])
    kinds = [(l["id"], l["@@type"]) for l in map(_as_dict, layers)]
    assert kinds == [("domain", "GeoJsonLayer"), ("channels", "GeoJsonLayer"), ("stations", "ScatterplotLayer")]
    stations = _as_dict(layers[2])
    assert stations["data"] == [{"position": [21.1, 55.3], "name": "Nida"}, {"position": [21.2, 55.4], "name": "Vente"}]
    assert stations["pickable"] is True


def _as_dict(layer):
    # shiny_deckgl layer helpers return plain dicts in the deck.gl JSON form; if a
    # future version returns objects, adapt here (the test asserts the JSON shape).
    return layer if isinstance(layer, dict) else layer.to_dict()


def test_runs_detail_lists_skipped_stages():
    html = str(runs.skipped_alert({"skipped": {"validate": "run ends before the scoring window"}}))
    assert "Skipped" in html and "validate (run ends before the scoring window)" in html
    assert runs.skipped_alert({}) is None and runs.skipped_alert(None) is None
    assert runs.skipped_alert({"stage": "build", "reason": "x", "log_tail": ""}) is None  # a failure summary, not a skip summary
```

Also in `sfincs_ui/tests/test_pages.py` extend `test_build_ui_without_problems_has_no_banner` (or add `test_build_ui_includes_deckgl_assets`) asserting `"deck" in html.lower()` for the build_ui output, since `head_includes()` must land on every page.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd /home/razinka/sfincs/sfincs_ui && /opt/micromamba/envs/shiny/bin/python -m pytest tests/test_pages_m2.py tests/test_pages_m3.py -q 2>&1 | tail -5`
Expected: FAIL (`setup-map` missing, `AttributeError: map_layers`, `skipped_alert`, label text).

Before implementing, confirm the deck.gl helper shapes once in the UI env and paste the result in the report. Adapt `_as_dict` if the helpers do not return dicts, and adapt the type key in `test_map_layers_shapes` if the layer dict uses `"type"` rather than `"@@type"` (assert whichever key the helper really emits, with the same `GeoJsonLayer` / `ScatterplotLayer` values):

```bash
/opt/micromamba/envs/shiny/bin/python -c "
from shiny_deckgl import geojson_layer, scatterplot_layer, MapWidget, head_includes
l = scatterplot_layer(id='s', data=[{'position':[21.1,55.3],'name':'Nida'}], get_position='position', get_radius=300, get_fill_color=[220,40,40,220], pickable=True, radius_min_pixels=4)
print(type(l), l if isinstance(l, dict) else dir(l)); print(type(head_includes()))"
```

- [ ] **Step 3: Change `pages/setup.py`**

Imports and helpers:

```python
from shiny import module, reactive, render, ui
from shiny_deckgl import MapWidget, geojson_layer, scatterplot_layer

NO_GEOREF = "No georeferenced geometry for this template."
_POINT_STYLE = {  # radius in metres, RGBA
    "stations": (300, [220, 40, 40, 220]),
    "inflows": (500, [40, 160, 60, 220]),
    "boundary": (400, [40, 40, 220, 220]),
}
LAGOON_VIEW = {"longitude": 21.2, "latitude": 55.3, "zoom": 8, "pitch": 0, "bearing": 0}


def render_field(field: SettingField, value) -> ui.Tag:
    changed = "changed" if value != field.default else ""
    if field.group == "Solver overrides":
        hint = " (empty: model default)" if field.optional else f" (default {field.default})"
    else:
        hint = ""
    label = ui.span(field.label, ui.span(hint, class_="text-muted small") if hint else "")
    if field.kind == "bool":
        widget = ui.input_checkbox(field.key, label, bool(value))
    elif field.kind == "choice":
        widget = ui.input_select(field.key, label, {str(c): str(c) for c in field.choices}, selected=str(value))
    elif field.kind == "datetime":
        widget = ui.input_text(field.key, label, value or "", placeholder="YYYY-MM-DD HH:MM")
    else:
        step = 1 if field.kind == "int" else None
        widget = ui.input_numeric(field.key, label, value, min=field.minimum, max=field.maximum, step=step)
    return ui.div(widget, ui.p(field.explanation, class_="text-muted small mb-2"), class_=f"setting {changed}".strip())


def _points(layer: dict) -> list[dict]:
    coords = layer["geometry"]["coordinates"]
    labels = layer.get("labels") or [""] * len(coords)
    return [{"position": [float(x), float(y)], "name": n} for (x, y), n in zip(coords, labels)]


def map_layers(layers: list[dict]) -> list:
    """deck.gl layers for the template geometry; only WGS84 layers are drawn (Review Focus 5)."""
    out = []
    for layer in layers:
        if layer.get("crs") != "EPSG:4326":
            continue
        name, geom = layer["name"], layer["geometry"]
        feature = {"type": "Feature", "properties": {"name": name}, "geometry": geom}
        if name == "domain":
            out.append(geojson_layer(id=name, data=feature, filled=True, stroked=True, get_fill_color=[30, 120, 200, 40],
                                     get_line_color=[30, 120, 200, 200], line_width_min_pixels=2))
        elif name == "channels":
            out.append(geojson_layer(id=name, data=feature, stroked=True, filled=False, get_line_color=[200, 80, 30, 220], line_width_min_pixels=2))
        elif geom["type"] in ("MultiPoint", "Point"):
            if geom["type"] == "Point":
                layer = {**layer, "geometry": {"type": "MultiPoint", "coordinates": [geom["coordinates"]]}}
            radius, colour = _POINT_STYLE.get(name, (300, [120, 120, 120, 220]))
            out.append(scatterplot_layer(id=name, data=_points(layer), get_position="position", get_radius=radius,
                                         get_fill_color=colour, pickable=True, radius_min_pixels=4))
        else:
            out.append(geojson_layer(id=name, data=feature, stroked=True, get_line_color=[120, 120, 120, 220], line_width_min_pixels=1))
    return out


def map_message(layers: list[dict]) -> str | None:
    return None if map_layers(layers) else NO_GEOREF
```

UI: replace the placeholder paragraph in `setup_ui` with the map:

```python
@module.ui
def setup_ui() -> ui.Tag:
    return ui.div(
        ui.output_ui("header"),
        ui.row(
            ui.column(6, ui.output_ui("form")),
            ui.column(6, ui.div(ui.input_action_button("save_btn", "Save settings", class_="btn-outline-primary w-100 mb-2"),
                                ui.input_action_button("launch_btn", "Launch run", class_="btn-primary w-100 mb-3"),
                                ui.output_ui("map_message"),
                                MapWidget(module.resolve_id("map"), view_state=LAGOON_VIEW).ui(height="420px"),
                                class_="card p-3 setup-side")),
        ),
        class_="container py-3",
    )
```

Server: a `_map_layers` reactive and an effect that pushes them:

```python
    _widget = MapWidget(session.ns("map"), view_state=LAGOON_VIEW)

    @reactive.calc
    def _geometry() -> list[dict]:
        p = _project()
        if p is None:
            return []
        try:
            return get_template(p["template"]).geometry_layers(project_service.project_dir(p["id"]), p["settings"])
        except Exception:
            logger.exception("geometry_layers failed")
            return []

    @render.ui
    def map_message():
        msg = map_message_for(_geometry())
        return ui.p(msg, class_="text-muted small") if msg else None

    @reactive.effect
    async def _push_map():
        await _widget.update(session, map_layers(_geometry()))
```

(`map_message_for` is the module-level `map_message`; alias it inside the module to avoid shadowing by the output function: `map_message_for = map_message` at module level, placed right after the function.) In `_launch_dialog`, the thread box's initial value becomes `min(tpl.default_threads(p["settings"]), cap)`: the Curonian default of 8 must not exceed the admin's `max_threads` ceiling on a small host. `collect_settings` is unchanged: Shiny returns `None` for an empty numeric input and `""` for an empty text input, both of which `coerce` turns into `None` for optional fields.

If `MapWidget.ui` does not accept `height=` as a keyword in 1.9.2, pass the height through the CSS rule below instead and note it in the report.

`www/sfincs_ui.css`: `.setup-side .deckgl-map, .setup-side canvas { min-height: 420px; }`.

- [ ] **Step 4: Change `pages/runs.py` and `app.py`**

```python
def skipped_alert(summary: dict | None):
    skipped = (summary or {}).get("skipped") or {}
    if not skipped:
        return None
    return ui.div(ui.strong("Skipped: "), ", ".join(f"{stage} ({reason})" for stage, reason in skipped.items()),
                  class_="alert alert-secondary py-2")
```

and in `detail()` after the failure block: `if r["status"] == "finished": parts.append(skipped_alert(r["summary"]))`.

`app.py`: `from shiny_deckgl import head_includes` and `header=ui.TagList(*head_includes(), ui.head_content(...), _banner(report))`. If `head_includes()` returns a single Tag rather than a list, wrap it: `*(h if isinstance(h, (list, tuple)) else [h])`.

- [ ] **Step 5: Run the tests**

Run: `cd /home/razinka/sfincs/sfincs_ui && /opt/micromamba/envs/shiny/bin/python -m pytest -q 2>&1 | tail -2`
Expected: Task 5's count plus 7 (one in test_pages_m2, five in test_pages_m3, one in test_pages), all passing.

- [ ] **Step 6: Look at it once in a browser**

Run the app locally against a scratch workspace (README "Run locally") with `SFINCS_UI_CURONIAN_DIR=/home/razinka/sfincs/curonian`, log in, open the "Xaver 2013 (uniform wind)" example on Projects, then open Setup fresh: the map must be populated without touching any field (the lagoon outline with channels, seven boundary points at the Klaipėda strait, two inflows and nine stations); hovering a station shows its name. If the map is empty until a field changes, the first `update` ran before the client widget bound: re-push the layers once from `session.on_flushed(..., once=True)` and keep the effect for later changes; note it in the report. Open the plane beach example: the map is empty and the message reads "No georeferenced geometry for this template." Switch dark mode on and off: the form stays readable. Record what you saw in the report; a screenshot is not required.

- [ ] **Step 7: Commit**

```bash
cd /home/razinka/sfincs
git add sfincs_ui/sfincs_ui/pages/setup.py sfincs_ui/sfincs_ui/pages/runs.py sfincs_ui/sfincs_ui/app.py sfincs_ui/sfincs_ui/www/sfincs_ui.css sfincs_ui/pyproject.toml sfincs_ui/tests/test_pages_m2.py sfincs_ui/tests/test_pages_m3.py sfincs_ui/tests/test_pages.py
git commit -m "sfincs_ui: Setup map preview with deck.gl, optional and datetime inputs, skipped stages on the Runs page

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01K5wxxnsj5oVJ2gHNaNhr9B"
```

---

### Task 7: Preflight gauge check through `common.read_table` in the model env

**Files:**
- Modify: `sfincs_ui/sfincs_ui/services/environment.py`
- Test: `sfincs_ui/tests/test_environment.py`

**Interfaces:**
- `_check_deep` no longer opens the gauge database with `sqlite3` from the UI process. It runs, through `_run_model_python` with `cwd=config.curonian_dir`, the snippet `_GAUGE_SNIPPET = "import common; common.read_table('SELECT 1')"`, labelled `"read the gauge database through common.read_table"`. Because the subprocess inherits the environment, `SFINCS_CURONIAN_DB` from `/etc/sfincs-ui.env` is what `common.DB` resolves (Task 1), and the check runs as the service user: the same path, the same user, the same code as `validate.py`. `DEFAULT_GAUGE_DB` and the `sqlite3` import go away.

- [ ] **Step 1: Replace the gauge test**

In `sfincs_ui/tests/test_environment.py` replace `test_deep_gauge_database_opens_read_only` with:

```python
def test_deep_gauge_check_uses_common_read_table(layout, tmp_path, monkeypatch):
    """Review Focus 4: the deploy preflight proves the gauge database the way validate.py reads it, as the service user."""
    (layout.curonian_dir / "inputs").mkdir()
    runner = _fake_runner({str(layout.sfincs_bin): (2, BANNER), "fake-python": (0, b"")})
    report = check_environment(layout, deep=True, runner=runner)
    gauge_calls = [c for c in runner.calls if "common.read_table" in " ".join(map(str, c[0]))]
    assert len(gauge_calls) == 1
    argv, kwargs = gauge_calls[0]
    assert argv[-2] == "-c" and "import common" in argv[-1] and "SELECT 1" in argv[-1]
    assert kwargs["cwd"] == str(layout.curonian_dir)
    assert not any("gauge" in p.lower() for p in report.problems)


def test_deep_gauge_failure_is_reported_with_the_model_env_label(layout, monkeypatch):
    (layout.curonian_dir / "inputs").mkdir()

    inner = _fake_runner({str(layout.sfincs_bin): (2, BANNER), "fake-python": (0, b"")})

    def runner(argv, **kw):
        if "common.read_table" in " ".join(map(str, argv)):
            return subprocess.CompletedProcess(argv, 1, stdout=b"", stderr=b"sqlite3.OperationalError: unable to open database file")
        return inner(argv, **kw)

    report = check_environment(layout, deep=True, runner=runner)
    assert any("read the gauge database through common.read_table" in p and "unable to open database file" in p for p in report.problems)
```

`_fake_runner` already exists in the file (it records `(argv, kwargs)` on `runner.calls` and returns `subprocess.CompletedProcess`); `BANNER` and `layout` too. `_run_model_python` reports the last stderr line, which is what the second test asserts.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd /home/razinka/sfincs/sfincs_ui && /opt/micromamba/envs/shiny/bin/python -m pytest tests/test_environment.py -q 2>&1 | tail -5`
Expected: the two new tests fail (no `common.read_table` call made).

- [ ] **Step 3: Change `services/environment.py`**

Remove `import sqlite3` and `DEFAULT_GAUGE_DB`; add `_GAUGE_SNIPPET = "import common; common.read_table('SELECT 1')"`; replace the gauge block at the end of `_check_deep` with:

```python
    # The gauge database is read by validate.py and export_map_cache through
    # common.read_table, which honours SFINCS_CURONIAN_DB (milestone 3). Run the
    # same read in the model env, from the pipeline directory, so the deploy
    # preflight (run as the service user) fails the way a run would.
    _run_model_python(config, _GAUGE_SNIPPET, runner, "read the gauge database through common.read_table", problems)
```

No `common.py` existence guard: a missing module surfaces as `Model environment cannot read the gauge database through common.read_table: exit 1 ModuleNotFoundError: ...`, which is the report wanted (and the `layout` test fixture writes no `common.py`, so a guard would silence both new tests). Update the module docstring line that mentions the read-only sqlite open.

- [ ] **Step 4: Run the tests**

Run: `cd /home/razinka/sfincs/sfincs_ui && /opt/micromamba/envs/shiny/bin/python -m pytest -q 2>&1 | tail -2`
Expected: Task 6's count plus 1 (one test replaced, one added).

- [ ] **Step 5: Prove it against the real environment**

Run: `cd /home/razinka/sfincs/sfincs_ui && SFINCS_CURONIAN_DB=/home/razinka/curonian/curonian_db.gpkg SFINCS_UI_CURONIAN_DIR=/home/razinka/sfincs/curonian /opt/micromamba/envs/shiny/bin/python -m sfincs_ui preflight --deep 2>&1 | tail -5`
Expected: no gauge problem (the only acceptable problems are ones the shallow preflight also reports on this dev host, such as an unwritable default workspace). Then with `SFINCS_CURONIAN_DB=/nonexistent.gpkg`: the report lists `Model environment cannot read the gauge database through common.read_table: exit 1 sqlite3.OperationalError: unable to open database file`. Paste both tails in the report.

- [ ] **Step 6: Commit**

```bash
cd /home/razinka/sfincs
git add sfincs_ui/sfincs_ui/services/environment.py sfincs_ui/tests/test_environment.py
git commit -m "sfincs_ui: preflight reads the gauge database through common.read_table in the model env

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01K5wxxnsj5oVJ2gHNaNhr9B"
```

---

### Task 8: Wiring: examples, registry, HTTP smoke, deploy env, README

**Files:**
- Modify: `sfincs_ui/tests/test_app_http_m2.py` (the real registry seeds three examples)
- Modify: `sfincs_ui/tests/test_e2e_plane_beach.py` (unchanged behaviour; run it to prove the plane beach still works with the Task 4 runner changes)
- Modify: `deploy/sfincs-ui.env.in` (comment only: `SFINCS_CURONIAN_DB` is now read by `common.py`, so the pipeline and the preflight share it)
- Modify: `deploy/deploy_ui.sh` (the editable install must pick up the two new dependencies: confirm `pip install -e` runs on every deploy; if it is guarded by a "requirements unchanged" check, make the guard include `pyproject.toml`)
- Modify: `sfincs_ui/README.md`
- Modify: `deploy/README.md` (SFINCS UI section: Curonian template needs `inputs/`, `data_catalog.yml`, the gauge database readable by `shiny`, 8 threads default)
- Modify: `docs/superpowers/specs/2026-09-30-sfincs-ui-design.md` only if a decision below contradicts it (none expected)

**Interfaces:** none new. This task proves the pieces fit and documents them.

- [ ] **Step 1: Write the failing test**

Add to `sfincs_ui/tests/test_app_http_m2.py`:

```python
async def test_real_registry_seeds_the_curonian_examples(db, tmp_path):
    from sfincs_ui import config
    from sfincs_ui.app import create_app
    from sfincs_ui.templates import TEMPLATES

    cfg = config.Config(workspace=tmp_path, database_url=f"sqlite:///{tmp_path / 'test.db'}", curonian_dir=tmp_path / "curonian")
    config.set_config(cfg)
    app = create_app(cfg, environment=EnvironmentReport(), templates=TEMPLATES, start_runner=False)
    names = sorted(p["name"] for p in app.services["projects"].examples())
    assert names == ["April 2013 (uniform wind)", "Plane beach example", "Xaver 2013 (uniform wind)"]
    april = next(p for p in app.services["projects"].examples() if p["name"].startswith("April"))
    assert april["settings"]["event"] == "april_2013" and april["settings"]["tstop"] is None
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="https://test") as c:
        r = await c.get("/")
        assert r.status_code == 200 and "deck" in r.text.lower()  # head_includes() on every page
```

- [ ] **Step 2: Run it**

Run: `cd /home/razinka/sfincs/sfincs_ui && /opt/micromamba/envs/shiny/bin/python -m pytest tests/test_app_http_m2.py -q 2>&1 | tail -3`
Expected: passes already if Tasks 5 and 6 are complete; if the stored settings lose `None` keys (JSON round trip keeps them; `validate` must return every key), fix `Template.validate` to emit every field key including optional ones set to `None`.

Then run the end-to-end plane beach test (it drives the real solver for about a minute):

Run: `cd /home/razinka/sfincs/sfincs_ui && /opt/micromamba/envs/shiny/bin/python -m pytest tests/test_e2e_plane_beach.py -q 2>&1 | tail -3`
Expected: passes; a finished plane-beach run has `summary is None` (no skips) and the export evidence check (Task 4) does not break the chain.

- [ ] **Step 3: Deploy files**

`deploy/sfincs-ui.env.in`: next to `SFINCS_CURONIAN_DB=...` add the comment `# read by curonian/common.py (validate, export, preflight) and nothing else in the UI`. In `deploy/deploy_ui.sh` confirm the `$SHINY_PIP install -e` line runs unconditionally on every deploy; if it only runs when the package is missing, change it to always run (the two new dependencies are already present in the env, but the metadata must match). Run `bash deploy/deploy_ui.sh --check` to confirm the script still parses.

- [ ] **Step 4: README**

`sfincs_ui/README.md`: in "Projects, runs and the queue" add a paragraph "Templates" listing the two templates with one sentence each; add a section "Curonian template" with the fields table (copy from Task 5), the sentence "Manning values are build parameters: changing them rebuilds the subgrid table; they are never written as inp overrides", the tstop rule ("a run that stops before the scoring window is not validated; the Runs page says so under Skipped"), the optional-field convention ("an empty box means the model's own value"), and a "Model-env tests" paragraph with the exact command `/opt/micromamba/envs/shiny/bin/python -m pytest tests/test_model_env_curonian.py -m model_env -q -s` and the measured small-domain build duration from Task 5. Replace the "Acceptance: restart during a run" heading with "Acceptance" containing two sub-sections: "Milestone 2: restart during a run" (existing text) and "Milestone 3: Xaver 2013 from the UI" (the recipe in Task 9 step 1). Fix the "Run the tests" section: the default run deselects `model_env`.

`deploy/README.md`, SFINCS UI section: add a "Curonian template prerequisites" paragraph: `curonian/inputs/` and `data_catalog.yml` present in the prod clone (they are tracked), the three absolute catalogue paths and `SFINCS_CURONIAN_DB` readable by user `shiny` (the deep preflight proves it through `common.read_table`), `SFINCS_UI_MAX_THREADS=16` leaves room for the 8-thread default.

- [ ] **Step 5: Commit**

```bash
cd /home/razinka/sfincs
git add sfincs_ui/tests/test_app_http_m2.py deploy/sfincs-ui.env.in deploy/deploy_ui.sh sfincs_ui/README.md deploy/README.md
git commit -m "sfincs_ui: Curonian examples in the real registry, deploy notes, README for milestone 3

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01K5wxxnsj5oVJ2gHNaNhr9B"
```

---

### Task 9: Acceptance: Xaver 2013 from the UI (run after deploy)

**Files:**
- Modify: `sfincs_ui/README.md` (record the measured numbers)

This task runs after the branch is merged, pushed and deployed with `sudo bash deploy/deploy_ui.sh` (the user runs sudo). It is the milestone gate from the spec's milestone list: "a Curonian run launched from the UI reproduces the published validation".

- [ ] **Step 1: The recipe (also the README text)**

1. Log in at https://laguna.ku.lt/sfincs-ui/. On Projects, click "Clone into my projects" on "Xaver 2013 (uniform wind)".
2. On Setup, confirm the map shows the lagoon, channels, seven boundary points, two inflows and nine stations. Leave every field at its default. Launch run with 16 threads, name `xaver-acceptance`.
3. On Runs, the stages go build → simulate → validate → export. Note the build stage's duration from its line (expected 3 to 8 minutes: subgrid tables for about 300 k active cells) and the simulate duration (about an hour at 16 threads on laguna).
4. When the run is `finished`, download `sfincs_his.nc` (the button appears), and compare the validation. In a shell on laguna:

```bash
RUN=$(sudo -u shiny find /srv/sfincs-ui/workspace -maxdepth 2 -mindepth 2 -type d -printf '%T@ %p\n' | sort -n | tail -1 | cut -d' ' -f2)   # newest run dir: workspace/<project id>/<run id>; or read the ids from the Runs page
sudo -u shiny diff <(sed -n '/Success criteria/,$p' $RUN/validation/validation.md) <(sed -n '/Success criteria/,$p' /home/razinka/sfincs/curonian/results/xaver_2013/validation.md) && echo CRITERIA MATCH
sudo -u shiny ls $RUN/map_meta.json $RUN/validation/gauge_obs.csv $RUN/validation/validation_timeseries.png
```

Expected: `CRITERIA MATCH` (the met/not-met lines are identical to the published baseline; the per-station numbers may differ in the second decimal because the published run used the pre-flag build path, record any difference), and the three files exist. `journalctl -u sfincs-ui --since "-2h" | grep -c Traceback` is 0.

- [ ] **Step 2: Record**

Write the measured build and simulate durations and the diff outcome into the README's "Milestone 3: Xaver 2013 from the UI" sub-section, commit with the trailers, push.

If the criteria differ: do not change the template defaults to chase the baseline. Record the difference, keep the run directory, and raise it as the first item of milestone 4's orientation.

---

## Deferred (milestone 4 and later)

- Extracting `sfincs_viewer` into a package and repointing the `sys.path` shim in `prep/export_map_cache.py` (spec section 4 "export"); the shim stays in milestone 3.
- Reading `curonian/common.py` from the UI process (the `EventInfo` mirror plus the drift test stands in for it).
- Showing validation results (the metrics table, the time series plot) inside the UI; milestone 3 only produces the files in `run_dir/validation/`.
- The Results page, run comparison and the viewer hand-off (spec milestone 4).
- Gridded wind presets per event beyond `uniform`/`grid`; per-run editing of the ERA5 inputs.
- Deleting runs and projects with their directories (milestone 2 left run deletion out; still out).
- A manning raster preview on the Setup map (the geometry preview shows static inputs only).
