# SFINCS UI: build, run and inspect SFINCS models from the browser — design

Date: 2026-09-30
Status: revision 2, after a five-lens workflow review (27 findings verified
first-hand against the repo, the server and the HEC-RAS files, merged to 21;
all applied below). Awaiting written-spec review.

## Purpose

A web application on laguna.ku.lt through which a logged-in user can create a
SFINCS project from a template, edit its settings, launch a simulation on this
server, watch it run, and inspect and compare the results. Anonymous visitors can
open runs that their owners marked public, and the published hindcasts, read-only.

The first template is the Curonian Lagoon model that already lives in
`curonian/` (two events, three forcing variants, validation against four
gauges). The architecture is generic: a `hecras` template imports a HEC-RAS 6
model into a SFINCS project (section 7), and a later generic template will let
a user draw a domain and pull a DEM from a data catalogue, DelftDashboard-style,
on the same builder. That generic template's UI is a separate spec.

The existing read-only viewer (`app/`, https://laguna.ku.lt/sfincs/) stays as it
is and keeps publishing the hindcasts in `curonian/results/`. The new app is
`/sfincs-ui/`.

Success for v1: a colleague logs in, clones the "April 2013" example project,
raises `manning_land` (which rebuilds the subgrid roughness table, see section
2) and switches the wind to gridded, launches a run at the admin's thread cap,
sees it progress and finish (the recorded runs take 45–50 min at 16 threads;
longer at the default cap of 8), reads the criteria table and station plots,
and overlays the run on the published April 2013 baseline in Compare.

## Survey of existing SFINCS user interfaces (2026-09-30)

Checked before designing anything new. Nothing web-based exists; the closest
thing anywhere is this repo's own viewer.

| tool | what it is | why not the base |
|---|---|---|
| DelftDashboard Python (Deltares-research/DelftDashboard, PyPI `delftdashboard` 0.3.1) | The only real SFINCS GUI: PySide6 desktop app built on Deltares' `guitares`, with a `sfincs_hmt` module wrapping hydromt_sfincs (domain, boundaries, meteo, structures, observation points, numerics). GPL-3, pushed 2026-09-29, docs marked work in progress, 106 open issues, Windows batch installers, all `cht_*` dependencies from git. | Desktop, not web. Kept as the reference for which setup steps a generic template needs. |
| FloodAdapt (Deltares-research/FloodAdapt) | Decision-support tool over SFINCS + Delft-FIAT. GUI code not in the public repo; developer guide says Linux unsupported; binary paths are `.exe`. | Not open, not Linux. |
| DT-flood (interTwin-eu/DT-flood) | Jupyter notebook chain driving SFINCS in Docker. MIT. | Notebooks, not a UI. |
| HYDRA (Zenodo 10.5281/zenodo.21705293) | FastAPI web platform listing SFINCS among seven models. | Too generic, one star. |
| Zenodo search "SFINCS" | 31 records: the model, HydroMT-SFINCS, datasets, papers, this repo's two records. | None is a UI, viewer or dashboard. |
| SHYFEM UI (this server, `/srv/shiny-server/shyfem-ui`, the author's own) | Shiny for Python app with SQLAlchemy database, argon2 auth and sessions, access control, audit log, asyncio in-process job queue with optional Celery, runs under Shiny Server on this box. | This is the pattern to copy for auth, sessions and audit. Its job runner is not copied (section 3). |

## Decisions taken

| question | decision |
|---|---|
| Scope | Generic architecture, Curonian template first. HEC-RAS import is milestone 5; the generic template's UI is milestone 7 with its own spec. |
| Where it runs | Web app on laguna.ku.lt, in the toolbox next to the viewer. |
| Who may launch runs | Login required to build and run; anonymous read-only access to public runs and to the published baselines. |
| Base | New package in the SHYFEM UI mould, reusing its auth, session and audit modules and extending its access control with per-run rules. Not an extension of `app/`, not DelftDashboard. |
| Framework | Shiny for Python (matches SHYFEM UI, the viewer and the toolbox). Plotly for time series, deck.gl via `shiny_deckgl` for maps. |
| Serving | Standalone uvicorn systemd unit as user `shiny` on port 8840 (free on 2026-09-30; 8838 is osmose, 8839 is econet-py) behind nginx, the osmose pattern, with `KillMode=process` so detached stages outlive a restart (section 3). Not Shiny Server: it reaps an app's process a few seconds after its last client leaves (the eutropy block raises `app_idle_timeout` to 3600 s for this reason) and every deploy restarts the process, which is the wrong lifetime for hour-long runs. |
| Environments | UI process in `/opt/micromamba/envs/shiny`. Builds, validations and exports are subprocesses run as `micromamba -r /opt/micromamba run -n hydromt-sfincs python …` (a command prefix, so the env's activation hooks set PROJ and GDAL data paths; the bare interpreter fails to find PROJ data, and without `MAMBA_ROOT_PREFIX` or `-r` micromamba looks under the service user's home and fails); simulations are subprocesses of `sfincs-linux/bin/sfincs`. No merged environment. |
| Where runs live | A UI-owned workspace outside the repo. Never `curonian/runs` or `curonian/results`, so the published viewer never lists UI runs. The published hindcasts are exposed read-only as "baseline" runs (section 2). |
| External data | The UI does not fetch ERA5, GTSM or CMEMS. Forcing comes from the prepared `curonian/inputs/<event>/` files. Fetching stays a command-line step (credentials, scratch directories). |
| Binary | Referenced by path from configuration, never bundled. The Deltares licence terms stay in the repo root. |
| HEC-RAS import | Own navbar entry. A fresh parser for SFINCS's needs (perimeters, BC lines, cell elevation and roughness, projection, reference points, hydrographs from the plan file); not a copy of the TELEMAC parser, which reads mesh topology SFINCS never uses. Geometry reading verified on the TELEMAC viewer's Muncie and Roseberry Creek fixtures; Coal exercises the incomplete-geometry refusal; the plan-file layout verified on real HEC-RAS 6.0/6.6 plan files on this machine (1D; the 2D boundary-line naming must be confirmed on a 2D plan file before milestone 5). Parsing in a short-lived subprocess of the `shiny` env (h5py is there, not in the model env), building in the model env from plain artefacts. |

## 1. Architecture

Package `sfincs_ui/` at the repo root, sibling of `app/` and `curonian/`.

Layers:

- **Pages**: Shiny UI modules, one per page (Home, Projects, Setup, Runs,
  Results, Compare, Import from HEC-RAS, Admin). Thin: call services, render.
- **Services**: plain Python, testable without Shiny.
  - Copied from SHYFEM UI with SHYFEM specifics removed: `auth_service`,
    `audit_service`, the session middleware (modified so anonymous requests
    pass through with `user=None` on the public pages instead of redirecting
    to login; the websocket keeps SHYFEM's ws-token bridge and resolves
    `user=None` for anonymous sessions), and the `JobStatus`/`JobSpec`
    vocabulary of `job_queue`.
  - Extended: `access_control` gains `can_view_run(user, run)` =
    `run.public or run is a baseline or owner or admin` and
    `can_modify_run(user, run)` = `owner or admin`; SHYFEM's project-membership
    helpers are not carried over.
  - Rewritten, not copied: `job_local` (section 3). SHYFEM's runner pipes
    stdout, kills the process group when its asyncio task is cancelled, and
    fails every active row at restart, which is the opposite of what
    hour-long detached stages need.
  - New: `project_service` (templates, per-project workspace, baselines),
    `model_service` (settings → model directory), `run_service` (launch,
    monitor, cancel, pin, publish), `results_service` (his/map readers,
    validation tables, map frames), `maintenance` (retention, quotas,
    free-space floor).
  - Templates: `templates/base.py` (interface), `templates/curonian.py`,
    `templates/plane_beach.py` (the test template, from `test_model/`),
    `templates/hecras.py` (section 7).
  - HEC-RAS parser: `hecras/` (reader for the geometry `.g##.hdf` and the
    plan `.p##.hdf`, unit conversion, artefact writer), run as a subprocess.
  - Generic builder: `build_generic.py`, run in the model env; reads a
    project's artefacts and calls hydromt_sfincs setup methods. Used by the
    `hecras` template now and by the generic template later. Its export
    entry point runs `map_core.export_cache(run_dir)` alone.
- **Database**: SQLite through SQLAlchemy, Alembic migrations. Tables in
  section 2. Project and run ids are UUIDs, because public URLs expose them.
- **Workspace** on disk: `<workspace>/<project_id>/<run_id>/` holds every
  model directory and output the UI creates.
- **Shared viewer package** (`sfincs_viewer/`, introduced at the start of
  milestone 4, not in milestone 1): the map and validation readers now in
  `app/` (`map_core.py`, `map_data.py`, `map_ui.py`, `sfincs_data.py`) move
  into an importable package that both `app/` and `sfincs_ui/` import. This
  is a signature change, not just a move: `sfincs_data` and `map_data`
  resolve everything through the module globals `DATA_DIR`, `RESULTS_DIR`,
  `RUNS_DIR` and take a variant name, which cannot express
  `<workspace>/<project>/<run>/` in one process serving many projects. Every
  reader gains a `RunPaths(run_dir, results_dir, inputs_dir | None)` argument
  (`inputs_dir` optional: hecras and plane-beach runs have no
  `channels.geojson` overlays); the current globals become the viewer's
  default `RunPaths`, so `app/` and its conftest stay unchanged in intent.
  `map_core` is already path-based (`export_cache(run_dir)`) and needs no
  change. `sfincs_viewer/__init__.py` must not import `map_ui` or
  `sfincs_data` at package level, so `from sfincs_viewer import map_core`
  works from the model env, which has no shiny. `map_core` keeps its
  dependency footprint (stdlib, numpy, scipy, pyproj, netCDF4). The 81 tests
  in `app/` stay green. Both `sfincs_viewer` and `sfincs_ui` get a
  `pyproject.toml` and are pip-installed into the `shiny` env (as SHYFEM UI
  is); the viewer's `deploy.sh` gains that install step, since it copies
  `app/*.py` flat today and `app.py` imports the modules by bare name.
  `deploy_ui.sh` pip-installs `sfincs_viewer` into the model env as well
  (same root-pip pattern as the osmose deploy), which is what lets the
  export shim and `build_generic.py` import `map_core` there without path
  shims; `build_generic.py` is a standalone script with no `sfincs_ui`
  imports, invoked by absolute path under the prod clone. In `sfincs_ui`
  figures are served through a per-run dynamic route, not the viewer's
  single static mount.

Template interface. A template answers five questions:

1. What settings does the user edit? (a schema: fields, defaults, bounds,
   one-line explanations; rendered into the Setup form)
2. How do those settings become a SFINCS model directory? (a build command to
   run in the model env, plus `sfincs.inp` overrides to apply afterwards)
3. What validation applies, if any? (a validate command and how to read its
   output; none for plane-beach and hecras)
4. What geometry does the Setup map show for this project? (a method taking
   the project's workspace path and settings and returning GeoJSON layers;
   Curonian and plane-beach return static geometry, `hecras` reads the
   project's artefacts)
5. What export command produces the map cache? (Curonian: `export_map_cache`
   with `--event/--run-dir/--out-dir`; plane-beach: none, the stage is
   skipped; hecras: the generic export entry point)

plus the list of example projects it ships with.

## 2. Projects, runs and settings

**Project** = template + settings document, owned by a user, with a workspace
directory. **Run** = an immutable snapshot of a project's settings, the model
directory built from it, a simulation and its outputs. Editing a project never
changes an existing run. Every run directory contains `settings.json`, the
exact `sfincs.inp`, `overrides.diff` (the recorded rewrite, section 3), the
build log and the solver log. Shipped example projects have `owner_id NULL`
(system-owned); cloning one copies only the settings document.

**Baselines.** The published hindcasts under `CURONIAN_DIR/runs/<variant>`
(his, map, map cache) with `CURONIAN_DIR/results/<variant>` (validation
outputs, `gauge_obs.csv`) appear as read-only, always-public runs with
synthetic ids `baseline:<variant>`: not deletable, not re-runnable, openable
in Results and selectable in Compare, read through the same `sfincs_viewer`
readers the published viewer uses with a `RunPaths` pointing into
`CURONIAN_DIR`. This is how "overlay on the published baseline" is met
without copying 1.3 GB per variant into the workspace.

Tables:

| table | columns (essentials) |
|---|---|
| `users` | id, username, password_hash (argon2), role (`admin`/`user`), email, created, active |
| `sessions` | token, user_id, created, expires |
| `projects` | id (uuid), owner_id (nullable), name, template, settings_json, created, updated |
| `runs` | id (uuid), project_id, name, status (`queued`/`building`/`running`/`validating`/`exporting`/`finished`/`failed`/`cancelled`/`orphaned`), settings_json, workdir, threads, public, pinned, started, finished, exit_code (nullable: unknown after a reconciled restart), summary_json |
| `jobs` | id, run_id, stage (`build`/`simulate`/`validate`/`export`), status (SHYFEM's `JobStatus`: `pending`/`queued`/`running`/`completed`/`failed`/`cancelled`, plus `orphaned`; active = pending/queued/running), pid, proc_starttime (field 22 of `/proc/<pid>/stat` at launch, for the identity check), log_path, started, finished, exit_code (nullable) |
| `audit_log` | id, user_id, action, target, detail_json, timestamp |
| `settings` | key, value_json (admin-chosen queue policy, retention, quota; see precedence in section 5) |

A run whose job is `orphaned` shows `orphaned` in `runs.status`.

**Threads** are a launch parameter stored in `runs.threads`; a template's
settings document may carry a default that prefills the launch dialog but is
not part of the model definition, and Compare shows threads as a run attribute
beside name and status, not as a settings change.

**Curonian template settings, v1.** Two kinds, because SFINCS in subgrid mode
(the default; `--no-subgrid` opts out) ignores the `manning_*` keywords in
`sfincs.inp` and takes roughness from the subgrid table (`sfincs_domain.f90`
puts the friction block under `if (.not. subgrid)`; `build_model.py` already
documents that the inp keywords are inert and passes the values into
`setup_subgrid`). A post-build rewrite of those keys would change the recorded
inp and the Compare diff but not the simulation, which breaks the provenance
guarantee above.

- Event: `xaver_2013` or `april_2013`.
- Variant: wind `uniform`/`grid`, pressure on/off, subgrid on/off. These map
  one to one onto `build_model.py` flags.
- Build parameters (marked in the Setup form as "rebuilds the subgrid table",
  the slow part of build): `manning_land`, `manning_sea`, `rgh_lev_land`.
  Passed as `--manning-land/--manning-sea/--rgh-lev-land` flags to
  `build_model.py`, which feeds them to `setup_subgrid`,
  `setup_manning_roughness` and `config_for` together so table and inp agree,
  and passes `write_man_tif=True` so the applied roughness is inspectable.
  `setup_subgrid`'s own `huthresh` table parameter stays at its default.
- Solver overrides, rewritten in `sfincs.inp` after the build, each shown with
  the model default and an explanation: numeric with bounds `alpha`,
  `huthresh` (read at run time even in subgrid mode), `zsini`, `dtmax`,
  `nuvisc`; on/off switches `viscosity` and `advection` (SFINCS reads them as
  a logical and an integer, not bounded numbers); `tstop` (must lie within
  the event's data window; if it is set before the end of the event's score
  window the run is not validated and Results says "not scored: run ends
  before the scoring window"). Nothing else in `sfincs.inp` is editable in v1.

**Bounded changes to the pipeline scripts** so the template drives them
without copying code, all defaulting to today's behaviour so the command-line
workflow and its tests are unchanged:

- `build_model.py`: `--run-dir` (today `--run-name` is always under `runs/`),
  `--manning-land`, `--manning-sea`, `--rgh-lev-land`.
- `validate.py`: `--run-dir`, `--out-dir`.
- `prep/export_map_cache.py`: `--event` (today `event_for_run` keys on the
  run *name* and exits for anything not in `EVENTS`), `--run-dir`,
  `--out-dir`; its `sys.path` shim that imports `map_core` from `app/` is
  repointed to `from sfincs_viewer import map_core` in milestone 4, with the
  extraction (in milestone 3 the Curonian export stage keeps the existing
  `app/` shim, which works from the model env today).
- `common.py`: the gauge database path (today `Path.home() /
  "curonian/curonian_db.gpkg"`, which resolves to `/home/shiny/...` under
  the service user) becomes `SFINCS_CURONIAN_DB` from the environment with
  the current default; `validate.py` and `export_map_cache.gauge_obs` read
  every gauge through it.

Validate `--out-dir` and export `--out-dir` both point at `D/validation`, so
`validation.md`, the figures and `gauge_obs.csv` land where
`RunPaths.results_dir` looks.

**Generic template** (milestone 7) has a different settings document: domain
box and resolution, CRS, DEM source from a data catalogue, boundary type,
uploaded forcing series. Same tables; only `template` and the shape of
`settings_json` differ.

## 3. Job execution

A run is a chain of up to four jobs, each a subprocess with its own log file
in the run directory. Model-env stages run with `cwd=CURONIAN_DIR` and
absolute script paths, because `build_model.py`, `validate.py` and `-m
prep.export_map_cache` import `common` and `prep` by bare name and fail from
any other directory. Only `simulate` runs with cwd = run directory (SFINCS
opens `sfincs.log` relative to cwd).

1. **build**: `MODEL_PYTHON <CURONIAN_DIR>/build_model.py --event E --run-dir D
   [--wind grid] [--pressure] [--no-subgrid] [--manning-land x …]`. Then the
   service applies the solver overrides by rewriting the listed keys in
   `sfincs.inp` and writes `overrides.diff` last. Overrides are applied after
   hydromt writes the file so the step is trivially testable; because they
   are fully derivable from the run's `settings.json`, reconciliation can
   re-apply them idempotently.
2. **simulate**: `sfincs-linux/bin/sfincs` in the run directory with
   `OMP_NUM_THREADS=<threads>`. Progress is read by tailing `sfincs.log`,
   which prints lines of the form `  15% complete,  1188.8 s remaining ...`
   every 5 %: the UI shows that percentage, the elapsed time and the
   solver's own remaining-time estimate.
3. **validate**: `MODEL_PYTHON <CURONIAN_DIR>/validate.py --event E --run-dir D
   --out-dir D/validation`. Skipped for templates without validation.
4. **export**: the template's export command (section 1, question 5).
   Curonian: `MODEL_PYTHON -m prep.export_map_cache --event E --run-dir D
   --out-dir D/validation`; hecras: `build_generic.py export --run-dir D`,
   which calls `map_core.export_cache` without `event_for_run` or gauge
   observations; plane-beach: skipped.

**Completion evidence** per stage, used by reconciliation: build = model
files plus `overrides.diff`; simulate = `sfincs_his.nc` closed and the
`---------- Simulation finished -----------` line in `sfincs.log`; validate =
`validation.md`; export = `map_meta.json` (written last by `export_cache`).

**Queue policy** (admin-chosen in `settings`, ceilings from the environment):
at most N simulations at once (default 1); at most T threads per run (default
8, leaving headroom for TELEMAC and the ~25 other apps on the 28-core box;
every recorded Curonian run used 16 and took 45–50 min for April, 25–41 min
for Xaver; an admin may raise the cap to 16); builds and validations up to 2
concurrently. Jobs of a run execute in order. A failed stage stops the chain
and marks the run `failed` with the stage name and the last 50 log lines in
`summary_json`.

**Process lifetime.** Every stage subprocess is launched detached: its own
session (`start_new_session=True`), stdout and stderr redirected to the
stage's log file (never `PIPE`), and its pid and `/proc` start time stored in
`jobs` before it is awaited. The runner's `except asyncio.CancelledError`
never signals the child; only an explicit `cancel()` does. Two things would
otherwise kill a stage on every deploy, and both are designed out: uvicorn's
shutdown cancels every asyncio task (SHYFEM's runner responds by killing the
process group), and systemd's default `KillMode=control-group` SIGTERMs then
SIGKILLs after 10 s everything in the unit's cgroup, which `setsid` does not
leave. The unit therefore sets `KillMode=process` (with a comment citing
`man systemd.kill` and why its "not recommended" is accepted: children are
deliberately detached and reconciled), so `TimeoutStopSec` applies to uvicorn
only. A deploy restart, a crash or a closed browser tab then costs no
compute.

**Reconciliation on startup.** For every job row left in an active status the
queue checks `/proc/<pid>`: alive with the recorded start time → resume
monitoring by polling `/proc/<pid>` (the inherited pid cannot be awaited) and
judging completion from the stage's evidence, recording `exit_code` as
unknown; dead with complete evidence → mark the stage completed and continue
the chain; dead after `build` with model files present but no
`overrides.diff` → re-apply the overrides and continue; otherwise → mark the
run `failed` with reason "interrupted". `orphaned` is reserved for a job
whose directory has gone.

**Cancel** sends SIGTERM to the stage's process group, SIGKILL after 30 s,
then cancels the asyncio task. `deploy_ui.sh` checks the jobs table before
restarting and waits for, or warns about, an active simulate stage; the
uninstall path kills detached stages explicitly, since `systemctl stop` no
longer does.

**Storage.** A Curonian run directory is 1.3 GB with the export cache: map
350 MB, subgrid products about 490 MB (`subgrid/` 290 MB, `sfincs_subgrid.nc`
200 MB), export cache about 410 MB, the rest small. Maintenance deletes
`subgrid/` once a run reaches `finished` (the table `sfincs_subgrid.nc` is
what the solver reads; the `manning*.tif` inside `subgrid/` stays
inspectable while the run is building, running or failed, and the model-env
roughness test of section 6 is a standalone build that maintenance never
touches), deletes the export cache when a run is unpinned and past
retention, and deletes run directories older than the retention (default 60
days) unless pinned. It enforces a per-user quota (default 20 GB). A launch is
also refused when free space on the workspace volume is below a global floor
(`MIN_FREE_GB`, env-only, default 100 GB; the volume is shared with TELEMAC
and some 25 other apps and had 228 GB free of 916 on 2026-09-30). Both
refusals state the current numbers.

**Log streaming.** The Runs page tails the active stage's log every 2 s while
that run is selected. Nothing is pushed to clients that are not looking.

## 4. Pages

Same navbar, shell and theme toggle as SHYFEM UI. Results and Compare take
`?run=<id>` and `?runs=a,b,…` query forms so public runs and baselines have
shareable URLs.

- **Home** (public). What the tool does, the baselines and public runs with
  links, the example projects, login.
- **Projects** (login). My projects: create from template, clone, rename,
  delete (confirmation; deletes the project's runs).
- **Setup** (login). Template settings form on the left; deck.gl map on the
  right with the template's geometry for this project (Curonian: active
  area, channels, sea boundary, river inflows, stations; hecras: perimeters,
  BC lines, reference points from the project's artefacts). Build parameters
  are grouped and labelled "rebuilds the subgrid table"; overrides show the
  default beside the field and highlight when changed. "Launch run" asks for
  run name and threads (prefilled from the settings default), then hands off
  to Runs.
- **Runs** (login). Queue table of my runs; admins also see everyone's
  running jobs. Selected run: stage timeline, progress bar, live log tail,
  cancel, pin, mark public. Failed runs show the failing stage's last lines.
- **Results** (public for public runs and baselines, else owner or admin).
  Headline (criteria met of scored, or "not scored"), criteria table with the
  viewer's verdict badges, per-station observed vs modelled water level
  (Plotly), the map playback of flood depth with the viewer's overlays,
  downloads (`sfincs_his.nc`, `sfincs.inp`, `settings.json`, validation
  markdown; `sfincs_map.nc` only on request).
- **Compare** (public when every selected run is public or a baseline,
  otherwise login). Two to four runs of the same event: overlaid station
  series, criteria side by side, settings diff, depth-difference map at a
  chosen hour.
- **Import from HEC-RAS** (login). Upload widgets for the geometry file, the
  optional plan file and the optional DEM, with the upload limit shown before
  upload; a settings strip (resolution, target CRS override, constant level
  for lines without a hydrograph, time window when no plan file); Preview and
  Convert buttons; a log panel; a deck.gl map of perimeters, BC lines coloured
  by role, reference points, the proposed grid box and the DEM footprint.
  Convert creates the project and opens Setup.
- **Admin**. Users and roles, queue policy, retention, quota, storage by user,
  audit log.

## 5. Auth, configuration, deployment, errors

**Auth.** SHYFEM UI's scheme: argon2 password hashes, session token cookie,
websocket token for the Shiny session, roles `admin` and `user`. No
self-registration in v1; admins create accounts; the first admin is created by
`python -m sfincs_ui create-admin` at install. Public read-only access needs no
account: the copied middleware is changed so anonymous HTTP requests reach
Home, Results and Compare with `user=None` instead of being redirected to
login, and the websocket resolves `user=None` for anonymous sessions.

**Access rules.** Every read path (Results, each download, each run selected
in Compare, the log tail) calls `can_view_run` and every mutation (cancel,
pin, publish, delete, project delete) calls `can_modify_run` inside the
service and raises `NotAllowed` otherwise. Runs and Projects pages list only
the caller's own projects, plus everyone's running jobs for admins.

**Configuration** via environment variables with prefix `SFINCS_UI_`
(pydantic-settings): `WORKSPACE`, `DATABASE_URL` (default SQLite under the
workspace), `SFINCS_BIN`, `MODEL_PYTHON` (a command prefix, default
`micromamba -r /opt/micromamba run -n hydromt-sfincs python`, not an
interpreter path), `CURONIAN_DIR`, `URL_PREFIX`, `PORT`, `MAX_SIMULATIONS`,
`MAX_THREADS`, `MIN_FREE_GB`, `RETENTION_DAYS`, `QUOTA_GB`, `UPLOAD_MAX_MB`.
Precedence: the env vars are install-time ceilings and defaults; the
`settings` table holds admin-chosen values validated at or below the
ceilings; the queue reads `settings` and falls back to env when a key is
absent. `MIN_FREE_GB` and `UPLOAD_MAX_MB` are env-only. The unit's
`Environment=` also carries `MAMBA_ROOT_PREFIX=/opt/micromamba` and
`SFINCS_CURONIAN_DB=/home/razinka/curonian/curonian_db.gpkg`; `HOME` is not
overridden.

**What the prod clone contains.** `/srv/shiny-server/sfincs-ui-src` holds
code only (a dedicated clone, never a symlink to the dev tree, for the reason
recorded in osmose's deploy script: a long-running uvicorn process must not
see its source edited underneath it). It cannot build a Curonian model: the
binary, `curonian/inputs/lagoon_bathy_50m.tif`, each event's `era5_grid.nc`
and `gtsm/`, and three absolute catalogue paths under `/home/razinka` are
gitignored or machine-specific. So `CURONIAN_DIR` is the dev checkout
`/home/razinka/sfincs/curonian` (as the viewer's `SFINCS_DATA_DIR` already
is) and `SFINCS_BIN` likewise points outside the clone; the pipeline scripts
run from there as short-lived subprocesses, so the line-drift argument does
not apply to them.

**Deployment.** `deploy/deploy_ui.sh`, the osmose shape: the prod clone, pip
install of `sfincs_viewer` and `sfincs_ui` into the `shiny` env and of
`sfincs_viewer` into the model env, a
`sfincs-ui.service` unit running `uvicorn` as `shiny` on `PORT` with
`--root-path /sfincs-ui`, `KillMode=process` and the `Environment=` lines
above, an nginx location inserted at the known anchor with
`client_max_body_size` set to `UPLOAD_MAX_MB` (the site default is 50 MB,
which blocks any real DEM or plan file) and the long `proxy_read_timeout`
the other Shiny locations use, registration in the catalogue, then
migrations and `create-admin` run as user `shiny` (`sudo -u shiny env …`, as
the viewer's deploy already does for its checks), never as root, so the
SQLite file and its `-wal`/`-shm` companions are writable by the service.
The port is one variable shared by the unit, the nginx block and the
preflight; the script refuses to install when `ss -ltn` shows it bound, when
the nginx site already proxies to it, or when another unit's `ExecStart`
names it, so a failed publish never leaves `/sfincs-ui/` proxying into
another app. Workspace at `/srv/sfincs-ui/workspace`, owned by `shiny`.

**Preflight**, run as user `shiny` with the unit's environment, not the
deployer's shell: the default `MODEL_PYTHON` prefix runs and imports
hydromt_sfincs and opens a GeoTIFF; `from sfincs_viewer import map_core`
imports in the model env; the binary executes; the gauge database opens
read-only through `common.read_table`; the binary,
`inputs/lagoon_bathy_50m.tif`, each event's `era5_grid.nc` and `gtsm/`, and
the three absolute catalogue paths are readable by name; the workspace and
database file are owned and writable by `shiny`.

**Uploads.** HEC-RAS and DEM files are parsed in a short-lived subprocess of
the `shiny` env (own session, wall-clock timeout, `RLIMIT_AS`) that writes
the artefacts; the UI process reads only `import.json` and the GeoJSON, so a
malformed file cannot take the queue and every session down with it.

**Errors.** Services raise typed exceptions (`TemplateError`, `BuildError`,
`QueueFull`, `QuotaExceeded`, `NotAllowed`); pages show a notification with
the message, never a traceback. Subprocess failures are never swallowed: exit
code, stage and log tail go into the run summary. A missing binary or model
env is detected at startup and shown as a banner on every page. Partial or
corrupt NetCDF files go through the viewer's guarded readers and show a status
note.

## 6. Testing and milestones

Tests (pytest, `shiny` env, like `app/`):

- Services without Shiny. Template: settings → build command (a settings
  document with `manning_land = 0.08` yields `--manning-land 0.08`) and
  `sfincs.inp` overrides; invalid settings rejected; every overridable key is
  one SFINCS reads in the mode the run uses. Queue: chain order, failure
  stops the chain, cancel kills a fake process, task cancellation does not,
  concurrency and thread caps, quota and free-space refusals. Reconciliation:
  a queue restarted over a fake job that is still alive resumes it; over a
  dead one with complete evidence completes it; over a dead build with model
  files but no `overrides.diff` re-applies the overrides; over a dead one
  with partial outputs fails it. Access control: view and modify rules for
  anonymous, owner, other user, admin, baseline. Auth tests come across with
  the code.
- Model-env tests, skipped when the env is absent: a small-domain build with
  `manning_land = 0.08` produces a `subgrid/manning*.tif` carrying that
  value; `python -m prep.export_map_cache` imports cleanly; `build_generic.py`
  builds from fixture artefacts and the window in `sfincs.inp` equals the
  plan's start and end.
- One end-to-end pipeline test on the plane-beach template (seconds):
  finished run with `sfincs_his.nc` and the expected end level. The only test
  touching the real binary; skipped when it is absent.
- Pages: fixture workspace with one finished and one failed run; each page
  renders without a browser. One Playwright pass: log in, create project,
  launch plane-beach run, wait, open Results.
- The `sfincs_viewer/` refactor is protected by the existing `app/` suite.
- HEC-RAS tests are in section 7.

Milestones, each shippable:

1. Package skeleton, database, auth, Admin page, service unit (with
   `KillMode=process`) and deploy script. No changes to `app/` or
   `deploy/deploy.sh`. Login works on laguna.ku.lt.
2. Queue and the plane-beach template end to end: create, launch, watch,
   download `sfincs_his.nc`. Acceptance includes `systemctl restart
   sfincs-ui` against the installed unit mid-run and seeing the run finish.
3. Curonian template: Setup form, map preview, the pipeline-script changes
   of section 2.
4. `sfincs_viewer/` extraction (start of the milestone), Results page,
   baselines, Compare page.
5. HEC-RAS import: parser, artefacts, `build_generic.py`, `hecras`
   template, Import page. Requires one real 2D unsteady plan file to confirm
   the boundary-line naming before the parser is finalised.
6. Retention, quotas, public runs, polish.
7. Generic template UI (draw a domain, DEM from a data catalogue) on
   `build_generic.py` (separate spec).

## 7. Import from HEC-RAS

Added 2026-09-30 after the section review. Modelled on the TELEMAC viewer's
"HEC-RAS → TELEMAC Import" tab (`/srv/shiny-server/telemac/server_import.py`,
`telemac_tools/hecras/`), adapted to a regular-grid model: no meshing, and the
file's projection is read rather than entered.

**Inputs.** A HEC-RAS 6 geometry file (`.g##.hdf`, required), the matching
plan file (`.p##.hdf`, optional: supplies hydrographs and the simulation
window) and a DEM GeoTIFF (optional, recommended). HEC-RAS writes hydrographs
into the plan HDF; the unsteady-flow `.u##.hdf` files on this machine open
with no groups at all, so an uploaded `.u##.hdf` is rejected with "HEC-RAS
writes hydrographs into the plan HDF; upload the .p##.hdf". A plan file also
embeds a `Geometry` group, so a single `.p##.hdf` upload may supply both once
that is verified on a 2D plan fixture. Upload cap `UPLOAD_MAX_MB` (default
500; the catalogue's own 5 m DEM is 455 MB, a real plan file 33 MB).

**What is read.**

Geometry file (verified with h5py on Muncie, HEC-RAS 6.5, and Roseberry
Creek, 6.5): root attributes `Projection` (WKT) and `Units System`;
`Geometry` attribute `Complete Geometry`; `2D Flow Areas/Attributes`
(`Name`, `Mann`, `Spacing dx/dy`, `Cell Count`); per area `Perimeter`,
`Cells Center Coordinate`, `Cells Minimum Elevation`, `Cells Center
Manning's n`, `Cells Surface Area`, `Faces Cell Indexes`; `Boundary
Condition Lines` (`Attributes`: name, area, External/Internal; `Polyline
Points`; `External Faces`; `Internal Cells`); `Reference Points`
(`Attributes`, `Points`).

Plan file (verified on `mwng.p03.hdf`, HEC-RAS 6.6, and `test_1.p03.hdf`,
6.0, both 1D): `Plan Data/Plan Information` attributes `Simulation Start
Time` and `Simulation End Time`; `Event Conditions/Unsteady/Boundary
Conditions/{Flow Hydrographs,Stage Hydrographs}/<name>` as `(N, 2)` float32
with attributes `Interval` (e.g. `Days`), `Start Date` (HEC-RAS `2400` means
the next midnight) and `Coordinates` (the line's polyline). Time = `Start
Date` + column 0 × the `Interval` unit. Each series is matched to a BC line
by its `Coordinates` against `Polyline Points`; whether 2D lines are also
matched by name is unverified until a 2D unsteady plan file is available,
which is a precondition of milestone 5.

**Refusals.** 1D-only models: "SFINCS needs a 2D flow area". Geometry not
preprocessed (`Complete Geometry` absent or not `True`, or `Perimeter` /
`Cells Minimum Elevation` missing for any area, as in the Coal fixture, a
6.4.1 file holding only face-point tables): "Geometry has not been
preprocessed; open it in HEC-RAS, run the 2D geometry preprocessor and save
again". Degrading to face points with a mandatory DEM is a later option, not
v1, because it yields no BC lines and the form has no manual boundary entry.

**Mapping to SFINCS.**

| HEC-RAS | SFINCS |
|---|---|
| 2D flow-area perimeters | active mask (`setup_mask_active` with the perimeter polygons); grid = their bounding box, rotation 0 |
| `Spacing dx` per area (fallback `sqrt(median Cells Surface Area)`; both give 50 on Muncie and Roseberry) | default `dx = dy`; user-editable |
| `Projection` WKT (source CRS) | `pyproj.CRS.from_wkt`, used directly for reprojection, never reduced to an integer (the fixtures' ESRI WKT1 resolves to no EPSG or, at lowered confidence, to a wrong metre CRS; the user's own LKS94 files resolve only at low confidence) |
| target CRS (`setup_grid` needs an integer `epsg`) | (1) a literal trailing `AUTHORITY['EPSG',N]` in the WKT when its linear unit is metre (3346 for the user's LKS94 models); else (2) `crs.to_epsg()` at default confidence when its unit is metre; else (3) the UTM zone of the region centroid; plus a user override in the Import form. Elevation ×0.3048 and flow ×0.028317 keyed on `Units System`; the horizontal decision keyed on the WKT linear unit |
| DEM GeoTIFF, else `Cells Minimum Elevation` rasterised from the first `Cell Count` rows of each area (the rows beyond are ghost cells on the perimeter with NaN elevation) | `setup_dep`; the cell-based fallback is flagged "coarse elevation from HEC-RAS cells" |
| `Cells Center Manning's n` rasterised (same row filter), else the area's `Mann` | `setup_manning_roughness(datasets_rgh=…)` or constant |
| BC line with a stage hydrograph (External only; a stage on an Internal line is refused) | water-level boundary: `setup_mask_bounds(btype="waterlevel", include_mask=line buffer)` + `setup_waterlevel_forcing` |
| BC line with a flow hydrograph, External or Internal (Roseberry's three Internal lines are inflows) | discharge source: `setup_discharge_forcing` at the centre of the line's first HEC-RAS cell (`External Faces` → `Faces Cell Indexes`, or `Internal Cells` → `Cells Center Coordinate`), never at the line midpoint, which sits on the perimeter |
| BC line with normal depth or no hydrograph | free outflow: `setup_mask_bounds(btype="outflow", include_mask=line buffer)`; a user-entered constant water level is an explicit override, not the default |
| breaklines, structures, 1D reaches | drawn on the preview, not used in v1 |
| plan window | `tref = tstart = Simulation Start Time`, `tstop = Simulation End Time`; else user-entered |
| `Reference Points` | `setup_observation_points` (Muncie has 2) |

**Artefacts.** The parser subprocess writes into the project workspace:
`perimeter.geojson`; `bc_lines.geojson` (name, area, External/Internal, role
`waterlevel`/`discharge`/`outflow`, source point, and an integer `index`
property in separate 1..n spaces for water-level and discharge features);
`obs_points.geojson` (name, area, cell index, reprojected point); `bzs.csv`
and `dis.csv` with an ISO datetime index and those integers as column
headers, in SI units; `dep.tif` (uploaded or derived); `manning.tif`;
`import.json` (source file names, WKT verbatim, chosen target EPSG, units
system, conversions applied, per-area `name`, `manning_default`,
`spacing_dx/dy`, `cell_count`, and warnings). Raw HDF uploads are discarded
after conversion, as in the TELEMAC viewer. The `hecras` template's settings
document references these artefacts plus resolution, target CRS, constant
levels, the time window, a threads default and the solver overrides of the
Curonian template (all of them are inp rewrites here; there is no subgrid
table).

**Build.** `build_generic.py` in the model env reads the artefacts and never
opens an HDF file. Order matters, because hydromt_sfincs clips forcing to the
config window and its default window is February 2010 (reproduced: a 2019
series raises `NoDataException` if `setup_config` has not run):
`setup_grid → setup_dep → setup_mask_active → setup_mask_bounds →
setup_manning_roughness → setup_config(tref, tstart, tstop, …) →
setup_waterlevel_forcing → setup_discharge_forcing → setup_observation_points
→ write`, mirroring `build_model.py`. Locations are read with
`gpd.read_file(...).set_index("index", drop=False)` as `build_model.py` does.
Validation: none, so Results shows "not scored" and the station plots come
from `sfincs_his.nc` at the reference points.

**Tests.** Parser: Muncie (2 areas, 2 External lines, 2 reference points),
Roseberry (1 area, 2 External + 3 Internal lines), Coal (incomplete-geometry
refusal), the ghost-cell filter, WKT handling (Muncie → target from
`to_epsg`, Coal → UTM 16N, an LKS94 WKT → 3346), unit conversion of a
US-customary file; hydrographs on a synthetic `.p##.hdf` built with h5py in
the layout verified on `mwng.p03.hdf`, replaced by a real 2D plan fixture
(fema-ffrd/rashdf, per the fixtures README) when one is obtained; artefact
writer round trip; builder on Roseberry artefacts asserting five bnd/src
entries and the plan window in `sfincs.inp` (skipped when the model env is
absent); one page test of the Import UI; the Playwright pass adds "import
Muncie, convert, open Setup", which covers only the no-hydrograph (outflow)
branch because Muncie has no plan file. The fixtures are referenced at the
TELEMAC viewer's path with a skip when absent.

**Later milestones.** Breaklines as thin dams (`setup_structures`), 1D
reaches as burned rivers, comparison of SFINCS against HEC-RAS results
(`.p##.hdf` water surface at reference lines), degrading unpreprocessed
geometry to face points.

## Out of scope for v1

Fetching external forcing; editing geometry (channels, stations) in the
browser; self-registration; Celery or multi-host execution; any change to the
published viewer's behaviour beyond the package move; HEC-RAS breaklines,
structures, 1D reaches and results comparison.
