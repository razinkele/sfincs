# SFINCS UI: build, run and inspect SFINCS models from the browser — design

Date: 2026-09-30
Status: draft, design sections approved in conversation. Awaiting written-spec review.

## Purpose

A web application on laguna.ku.lt through which a logged-in user can create a
SFINCS project from a template, edit its settings, launch a simulation on this
server, watch it run, and inspect and compare the results. Anonymous visitors can
open runs that their owners marked public, read-only.

The first template is the Curonian Lagoon model that already lives in
`curonian/` (two events, three forcing variants, validation against four
gauges). The architecture is generic: a later template will wrap hydromt_sfincs
setup steps directly so that a model can be built for any region from a data
catalogue, DelftDashboard-style. That generic template is a separate spec.

The existing read-only viewer (`app/`, https://laguna.ku.lt/sfincs/) stays as it
is and keeps publishing the hindcasts in `curonian/results/`. The new app is
`/sfincs-ui/`.

Success for v1: a colleague logs in, clones the "April 2013" example project,
changes `manning_land` and switches the wind to gridded, launches a run with
8 threads, sees it progress and finish in about an hour, reads the criteria
table and station plots, and overlays the run on the published baseline.

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
| SHYFEM UI (this server, `/srv/shiny-server/shyfem-ui`, the author's own) | Shiny for Python app with SQLAlchemy database, argon2 auth and sessions, access control, audit log, asyncio in-process job queue with optional Celery, runs under Shiny Server on this box. | This is the pattern to copy. |

## Decisions taken

| question | decision |
|---|---|
| Scope | Generic architecture, Curonian template first. Generic hydromt_sfincs template is milestone 6 with its own spec. |
| Where it runs | Web app on laguna.ku.lt, in the toolbox next to the viewer. |
| Who may launch runs | Login required to build and run; anonymous read-only access to public runs. |
| Base | New package in the SHYFEM UI mould, reusing its auth, session, access-control, audit and job-queue modules. Not an extension of `app/`, not DelftDashboard. |
| Framework | Shiny for Python (matches SHYFEM UI, the viewer and the toolbox). Plotly for time series, deck.gl via `shiny_deckgl` for maps. |
| Serving | Shiny Server in the shared `shiny` env, like SHYFEM UI. Fallback if websocket issues appear: the osmose-style standalone uvicorn systemd unit. |
| Environments | UI process in `/opt/micromamba/envs/shiny`. Builds and validations are subprocesses in `/opt/micromamba/envs/hydromt-sfincs`; simulations are subprocesses of `sfincs-linux/bin/sfincs`. No merged environment. |
| Where runs live | A UI-owned workspace outside the repo. Never `curonian/runs` or `curonian/results`, so the published viewer never lists UI runs. |
| External data | The UI does not fetch ERA5, GTSM or CMEMS. Forcing comes from the prepared `curonian/inputs/<event>/` files. Fetching stays a command-line step (credentials, scratch directories). |
| Binary | Referenced by path from configuration, never bundled. The Deltares licence terms stay in the repo root. |

## 1. Architecture

Package `sfincs_ui/` at the repo root, sibling of `app/` and `curonian/`.

Layers:

- **Pages**: Shiny UI modules, one per page (Home, Projects, Setup, Runs,
  Results, Compare, Admin). Thin: call services, render.
- **Services**: plain Python, testable without Shiny.
  - Copied from SHYFEM UI with SHYFEM specifics removed: `auth_service`,
    `access_control`, `audit_service`, `job_queue` (interface), `job_local`
    (asyncio in-process executor).
  - New: `project_service` (templates, per-project workspace),
    `model_service` (settings → model directory), `run_service` (launch,
    monitor, cancel, pin, publish), `results_service` (his/map readers,
    validation tables, map frames), `maintenance` (retention, quotas).
  - Templates: `templates/base.py` (interface), `templates/curonian.py`,
    `templates/plane_beach.py` (the test template, from `test_model/`).
- **Database**: SQLite through SQLAlchemy, Alembic migrations. Tables in
  section 2.
- **Workspace** on disk: `<workspace>/<project_id>/<run_id>/` holds every
  model directory and output the UI creates.
- **Shared viewer package**: the map and validation readers now in `app/`
  (`map_core.py`, `map_data.py`, `map_ui.py`, `sfincs_data.py`) move to an
  importable package `sfincs_viewer/` that both `app/` and `sfincs_ui/`
  import. This is the one refactor of existing code. The 81 tests in `app/`
  stay green and unchanged in intent.

Template interface. A template answers three questions:

1. What settings does the user edit? (a schema: fields, defaults, bounds,
   one-line explanations; rendered into the Setup form)
2. How do those settings become a SFINCS model directory? (a list of build
   commands to run in the model env, plus `sfincs.inp` overrides to apply)
3. What validation applies, if any? (a validate command and how to read its
   output)

plus static geometry for the Setup map (active area, channels, boundary,
inflows, stations as GeoJSON) and the list of example projects it ships with.

## 2. Projects, runs and settings

**Project** = template + settings document, owned by a user, with a workspace
directory. **Run** = an immutable snapshot of a project's settings, the model
directory built from it, a simulation and its outputs. Editing a project never
changes an existing run. Every run directory contains `settings.json`, the
exact `sfincs.inp`, the build log and the solver log.

Tables:

| table | columns (essentials) |
|---|---|
| `users` | id, username, password_hash (argon2), role (`admin`/`user`), email, created, active |
| `sessions` | token, user_id, created, expires |
| `projects` | id, owner_id, name, template, settings_json, created, updated |
| `runs` | id, project_id, name, status (`queued`/`building`/`running`/`validating`/`exporting`/`finished`/`failed`/`cancelled`/`orphaned`), settings_json, workdir, threads, public, pinned, started, finished, exit_code, summary_json |
| `jobs` | id, run_id, stage (`build`/`simulate`/`validate`/`export`), status, pid, log_path, started, finished, exit_code |
| `audit_log` | id, user_id, action, target, detail_json, timestamp |
| `settings` | key, value_json (admin-editable queue policy, retention, quota) |

**Curonian template settings, v1:**

- Event: `xaver_2013` or `april_2013`.
- Variant: wind `uniform`/`grid`, pressure on/off, subgrid on/off. These map
  one to one onto `build_model.py` flags.
- Solver overrides, each shown with the model default, bounds and an
  explanation: `manning_land`, `manning_sea`, `alpha`, `huthresh`, `zsini`,
  `dtmax`, `viscosity`, `advection`, `tstop` (must lie within the event's
  data window). Nothing else in `sfincs.inp` is editable in v1.
- Resources: OpenMP threads, 1 to the admin thread cap.

**Bounded changes to the pipeline scripts** so the template drives them
without copying code: `build_model.py` gains `--run-dir` (today `--run-name`
is always under `runs/`); `validate.py` gains `--run-dir` and `--out-dir`;
`prep.export_map_cache` gains `--run-dir` and `--out-dir` (today `--run` is
always `runs/<name>` and writes to `results/<name>`). Defaults keep today's
behaviour; the command-line workflow and its tests are unchanged.

**Generic template** (milestone 6) has a different settings document: domain
box and resolution, CRS, DEM source from a data catalogue, boundary type,
uploaded forcing series. Same tables; only `template` and the shape of
`settings_json` differ.

## 3. Job execution

A run is a chain of four jobs, each a subprocess with its own log file in the
run directory:

1. **build**: model env, `python build_model.py --event E --run-dir D
   [--wind grid] [--pressure] [--no-subgrid]`. Then the service applies the
   solver overrides by rewriting the listed keys in `sfincs.inp` and records
   the diff. Overrides are applied after hydromt writes the file so the step
   is trivially testable.
2. **simulate**: `sfincs-linux/bin/sfincs` in the run directory with
   `OMP_NUM_THREADS=<threads>`. Progress is read by tailing `sfincs.log`,
   which prints lines of the form `  15% complete,  1188.8 s remaining ...`
   every 5 %: the UI shows that percentage, the elapsed time and the
   solver's own remaining-time estimate.
3. **validate**: model env, `validate.py --event E --run-dir D --out-dir D/validation`.
   Skipped for templates without validation.
4. **export**: model env, `python -m prep.export_map_cache` pointed at the
   run directory, so the Results map reuses the viewer's frame-cache reader.

**Queue policy** (admin-editable, in `settings`): at most N simulations at
once (default 1); at most T threads per run (default 8); builds and
validations up to 2 concurrently. Jobs of a run execute in order. A failed
stage stops the chain and marks the run `failed` with the stage name and the
last 50 log lines in `summary_json`.

**Lifecycle.** Cancel sends SIGTERM to the stage's process group, SIGKILL
after 30 s. On server restart, rows left in an active status are marked
`orphaned` and their directories kept. Maintenance deletes run directories
older than the retention (default 60 days) unless pinned, and enforces a
per-user storage quota (default 20 GB; a Curonian run is about 1.3 GB, mostly
`sfincs_map.nc`). A launch that would exceed the quota is refused with the
current usage in the message.

**Log streaming.** The Runs page tails the active stage's log every 2 s while
that run is selected. Nothing is pushed to clients that are not looking.

## 4. Pages

Same navbar, shell and theme toggle as SHYFEM UI.

- **Home** (public). What the tool does, the published hindcasts as example
  projects, login. Anonymous visitors can open any public run, read-only.
- **Projects** (login). My projects: create from template, clone, rename,
  delete (confirmation; deletes the project's runs).
- **Setup** (login). Template settings form on the left; deck.gl map on the
  right with the template's static geometry (active area, channels, sea
  boundary, river inflows, stations). Overrides show the default beside the
  field and highlight when changed. "Launch run" asks for run name and
  threads, then hands off to Runs.
- **Runs** (login). Queue table of my runs; admins also see everyone's
  running jobs. Selected run: stage timeline, progress bar, live log tail,
  cancel, pin, mark public. Failed runs show the failing stage's last lines.
- **Results** (public for public runs). Headline (criteria met of scored),
  criteria table with the viewer's verdict badges, per-station observed vs
  modelled water level (Plotly), the map playback of flood depth with the
  viewer's overlays, downloads (`sfincs_his.nc`, `sfincs.inp`,
  `settings.json`, validation markdown; `sfincs_map.nc` only on request).
- **Compare**. Two to four runs of the same event: overlaid station series,
  criteria side by side, settings diff, depth-difference map at a chosen hour.
- **Admin**. Users and roles, queue policy, retention, quota, storage by user,
  audit log.

## 5. Auth, configuration, deployment, errors

**Auth.** SHYFEM UI's scheme: argon2 password hashes, session token cookie,
websocket token for the Shiny session, roles `admin` and `user`. No
self-registration in v1; admins create accounts; the first admin is created by
`python -m sfincs_ui create-admin` at install. Public read-only access needs no
account.

**Configuration** via environment variables with prefix `SFINCS_UI_`
(pydantic-settings): `WORKSPACE`, `DATABASE_URL` (default SQLite under the
workspace), `SFINCS_BIN`, `MODEL_PYTHON` (the hydromt-sfincs interpreter),
`CURONIAN_DIR`, `URL_PREFIX`, `MAX_SIMULATIONS`, `MAX_THREADS`. Deploy writes
`_sfincs_ui_env.py` next to `app.py`, as the viewer's deploy does, because
Shiny Server does not pass environment through.

**Deployment.** `deploy/deploy_ui.sh`, the viewer's idempotent shape: install
code under `/srv/shiny-server/sfincs-ui`, insert the Shiny Server and nginx
blocks at the known anchors, register `sfincs-ui` in the catalogue, run
migrations, verify the model env, the binary and read access to
`curonian/inputs` for the `shiny` user, touch `restart.txt`. Workspace at
`/srv/sfincs-ui/workspace`, owned by `shiny`.

**Errors.** Services raise typed exceptions (`TemplateError`, `BuildError`,
`QueueFull`, `QuotaExceeded`, `NotAllowed`); pages show a notification with
the message, never a traceback. Subprocess failures are never swallowed: exit
code, stage and log tail go into the run summary. A missing binary or model
env is detected at startup and shown as a banner on every page. Partial or
corrupt NetCDF files go through the viewer's guarded readers and show a status
note.

## 6. Testing and milestones

Tests (pytest, `shiny` env, like `app/`):

- Services without Shiny. Template: settings → build command and `sfincs.inp`
  overrides; invalid settings rejected. Queue: chain order, failure stops the
  chain, cancel kills a fake process, orphan marking on restart, concurrency
  and thread caps. Auth and access control tests come across with the code.
- One end-to-end pipeline test on the plane-beach template (seconds):
  finished run with `sfincs_his.nc` and the expected end level. The only test
  touching the real binary; skipped when it is absent.
- Pages: fixture workspace with one finished and one failed run; each page
  renders without a browser. One Playwright pass: log in, create project,
  launch plane-beach run, wait, open Results.
- The `sfincs_viewer/` refactor is protected by the existing `app/` suite.

Milestones, each shippable:

1. Package skeleton, database, auth, Admin page, deploy script. Login works
   on laguna.ku.lt.
2. Queue and the plane-beach template end to end: create, launch, watch,
   download `sfincs_his.nc`.
3. Curonian template: Setup form, map preview, `--run-dir` changes to the
   three pipeline scripts.
4. Results page on the shared viewer package; Compare page.
5. Retention, quotas, public runs, polish.
6. Generic hydromt_sfincs template (separate spec).

## Out of scope for v1

Fetching external forcing; editing geometry (channels, stations) in the
browser; self-registration; Celery or multi-host execution; any change to the
published viewer's behaviour beyond the package move.
