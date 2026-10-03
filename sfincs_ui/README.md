# sfincs_ui

Web app for laguna.ku.lt through which a logged-in user creates a SFINCS
project from a template, launches a simulation on the server and inspects the
results. Design: `docs/superpowers/specs/2026-09-30-sfincs-ui-design.md`.
Milestone 1: configuration, database, auth, Admin page, CLI, service unit and
deploy script. Milestone 2 (this state): the Projects, Setup and Runs pages, a
job queue with a runner that survives service restarts, and the CLI commands
`active-jobs` and `kill-jobs`.

## Projects, runs and the queue

Projects (created from a template or cloned), Setup (edit a project's
settings) and Runs (launch, watch progress, cancel, download) are pages of the
app. Run directories live at `<workspace>/<project>/<run>/` and hold
`settings.json`, `sfincs.inp`, `sfincs.inp.orig`, `overrides.diff`,
`build.log` and `sfincs.log`, plus the solver outputs such as `sfincs_his.nc`.

    python -m sfincs_ui active-jobs   # exit 0: none; 2: active rows, none alive; 3: a simulation is alive
    python -m sfincs_ui kill-jobs     # cancel active runs, then kill their processes

`deploy_ui.sh --uninstall` runs `kill-jobs` after the unit stops. The unit uses
`KillMode=process`, so a restart leaves a running simulation alive and the
queue reconciles it on the next start. The one test that runs the real solver
is `tests/test_e2e_plane_beach.py` (skipped when `sfincs-linux/bin/sfincs` is
absent).

### Templates

- **Plane beach** (`plane_beach`): a synthetic sloping beach on a regular grid that runs in seconds to minutes; the smoke-test and teaching template. It has no georeferenced geometry, so the Setup map reads "No georeferenced geometry for this template."
- **Curonian Lagoon and Nemunas delta** (`curonian`): the published Curonian hindcast (events Xaver 2013 and April 2013) driven by the `curonian/` pipeline: build, simulate, validate against the gauges, export the map cache. See "Curonian template" below.

## Curonian template

The template runs the scripts in `curonian/` (cwd = the curonian directory, so it needs `curonian/inputs/` and `curonian/data_catalog.yml`) and the model-env interpreter for build, validate and export. Default threads: 8. Fields:

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
| `tstop` | datetime, optional | None | `tref < tstop <=` the event's own end | Solver overrides | Stop time; empty = the event's end. Before the scoring window the run is not validated. |

Manning values are build parameters: changing them rebuilds the subgrid table; they are never written as inp overrides.

Optional fields: an empty box means the model's own value.

`tstop` must lie after the event's start (`tref`) and no later than the event's own end, because the built forcing ends there. A run that stops before the scoring window is not validated; the Runs page says so under Skipped, e.g. "Skipped: validate (run ends before the scoring window)".

The Setup page shows a deck.gl map of the static inputs (lagoon, channels, boundary points, inflows, stations). Before a project is open it shows no message.

### Model-env tests

The Curonian build and the validate/export chain need the model environment, so the tests that run them carry the `model_env` marker and are deselected by default:

    /opt/micromamba/envs/shiny/bin/python -m pytest tests/test_model_env_curonian.py -m model_env -q -s

The small-domain subgrid build they run (grid origin (314000, 6144000), 130 x 390 cells) took 54 s when measured in the model env.

## Layout

`sfincs_ui/` is the project directory (this file, `pyproject.toml`,
`alembic.ini`, `tests/`); `sfincs_ui/sfincs_ui/` is the package. Migrations
live inside the package so `init_db()` finds them from an editable install and
from the source tree alike.

## Run the tests

    cd sfincs_ui && /opt/micromamba/envs/shiny/bin/python -m pytest -q

The default run deselects the `model_env` tests (they need the model
environment and take minutes); see "Model-env tests" above for the command
that runs them.

Do not `pip install` the dev tree into the shared env: production installs the
prod clone editable into the same env (`deploy/deploy_ui.sh`).

## Run locally

    export SFINCS_UI_WORKSPACE=$HOME/sfincs-ui-workspace SFINCS_UI_SECURE_COOKIES=false SFINCS_UI_PORT=8899
    cd sfincs_ui
    /opt/micromamba/envs/shiny/bin/python -m sfincs_ui migrate
    /opt/micromamba/envs/shiny/bin/python -m sfincs_ui create-admin --username admin
    /opt/micromamba/envs/shiny/bin/python -m sfincs_ui serve

Behind nginx the app is mounted at `/sfincs-ui/` and its cookies carry `Path=/sfincs-ui`; when testing a prefixed instance with curl locally, pass the cookies by hand (`-b 'sfincs_ui_csrf=…'`), since curl will not return a `/sfincs-ui`-scoped cookie to `/login`.

Then open http://127.0.0.1:8899/ and log in. `SECURE_COOKIES=false` is only
for plain-http development; production keeps the default.

## Configuration

Every setting is an `SFINCS_UI_*` environment variable (`sfincs_ui/config.py`).
`WORKSPACE` is required. Env values are ceilings and defaults; an admin lowers
`max_simulations`, `max_threads`, `retention_days` and `quota_gb` on the Admin
page's Queue policy tab. `MIN_FREE_GB` and `UPLOAD_MAX_MB` are env-only.

## Schema changes

    cd sfincs_ui && SFINCS_UI_WORKSPACE=/tmp/x /opt/micromamba/envs/shiny/bin/python -m alembic -c alembic.ini revision --autogenerate -m "describe"

Review the generated file under `sfincs_ui/migrations/versions/`; `env.py`
must import every model module or autogenerate proposes dropping its tables
(`tests/test_db_init.py` guards this).

## Deployment

`sudo bash deploy/deploy_ui.sh` from the repo root; see `deploy/README.md`.
Merge to main and push to origin before deploying; the prod clone fetches `origin/main`.

## Acceptance

### Milestone 2: restart during a run

The milestone 2 gate is a run that survives `systemctl restart sfincs-ui`.
Measured on laguna with 4 threads: a 10 m plane beach takes about 62 s,
a 5 m one about 540 s. Pick the resolution that gives you a few minutes:

1. Log in. On the Projects page click "Clone into my projects" on the "Plane beach example" (the copy becomes the
   active project). On the Setup page set Cell size to 5 m, Save, and Launch run with 4 threads.
2. On the Runs page wait until the status is `running` and the progress bar moves.
3. In a shell: `sudo bash deploy/deploy_ui.sh --restart`. The script warns that a simulation is running and restarts anyway.
   (`sudo bash deploy/deploy_ui.sh --wait` is the blocking alternative: it waits for running simulations, then restarts.)
4. Reload the page, log in again if asked, select the run: the progress bar keeps moving and the run reaches `finished`.
   The simulate stage shows no exit code (its line reads `simulate: completed`): the restarted service did not spawn the
   solver, so it cannot know the exit status, and the run's exit code is recorded as unknown.
   `journalctl -u sfincs-ui -n 50` shows `reconcile: run … simulate -> resumed`;
   systemd also logs `Found left-over process … Ignoring`, which is expected with `KillMode=process`.
5. Download `sfincs_his.nc` from the Runs page.

### Milestone 3: Xaver 2013 from the UI

The gate: a Curonian run launched from the UI reproduces the published validation. Run after deploying with `sudo bash deploy/deploy_ui.sh`.

1. Log in at https://laguna.ku.lt/sfincs-ui/. On Projects, click "Clone into my projects" on "Xaver 2013 (uniform wind)".
2. On Setup, confirm the map shows the lagoon, channels, seven boundary points, two inflows and nine stations. Leave every field at its default. Launch run with 16 threads, name `xaver-acceptance`.
3. On Runs, the stages go build, simulate, validate, export. Note the build stage's duration from its line (expected 3 to 8 minutes: subgrid tables for about 300 k active cells) and the simulate duration (about an hour at 16 threads on laguna).
4. When the run is `finished`, download `sfincs_his.nc` (the button appears), and compare the validation. In a shell on laguna:

```bash
RUN=$(sudo -u shiny find /srv/sfincs-ui/workspace -maxdepth 2 -mindepth 2 -type d -printf '%T@ %p\n' | sort -n | tail -1 | cut -d' ' -f2)   # newest run dir: workspace/<project id>/<run id>; or read the ids from the Runs page
sudo -u shiny diff <(sed -n '/Success criteria/,$p' $RUN/validation/validation.md | grep -o '\*\*\(not met\|met\|info\)\*\*') <(sed -n '/Success criteria/,$p' /home/razinka/sfincs/curonian/results/xaver_2013/validation.md | grep -o '\*\*\(not met\|met\|info\)\*\*') && echo CRITERIA MATCH
sudo -u shiny ls $RUN/map_meta.json $RUN/validation/gauge_obs.csv $RUN/validation/validation_timeseries.png
```

Expected: `CRITERIA MATCH` (the met/not-met lines are identical to the published baseline; the per-station numbers may differ in the second decimal because the published run used the pre-flag build path, record any difference), and the three files exist. `journalctl -u sfincs-ui --since "-2h" | grep -c Traceback` is 0.

Measured: build duration, simulate duration and diff outcome to be recorded after the first deployed run.
