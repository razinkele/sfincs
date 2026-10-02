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

## Layout

`sfincs_ui/` is the project directory (this file, `pyproject.toml`,
`alembic.ini`, `tests/`); `sfincs_ui/sfincs_ui/` is the package. Migrations
live inside the package so `init_db()` finds them from an editable install and
from the source tree alike.

## Run the tests

    cd sfincs_ui && /opt/micromamba/envs/shiny/bin/python -m pytest -q

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

## Acceptance: restart during a run

The milestone 2 gate is a run that survives `systemctl restart sfincs-ui`.
Measured on laguna with 4 threads: a 10 m plane beach takes about 62 s,
a 5 m one about 540 s. Pick the resolution that gives you a few minutes:

1. Log in, open the "Plane beach example" (Projects, Clone), set Cell size to 5 m, Save, Launch run with 4 threads.
2. On the Runs page wait until the status is `running` and the progress bar moves.
3. In a shell: `sudo bash deploy/deploy_ui.sh --restart`. The script warns that a simulation is running and restarts anyway.
4. Reload the page, log in again if asked, select the run: the progress bar keeps moving and the run reaches `finished`
   with `exit code unknown` on the simulate stage. `journalctl -u sfincs-ui -n 50` shows `reconcile: run … simulate -> resumed`;
   systemd also logs `Found left-over process … Ignoring`, which is expected with `KillMode=process`.
5. Download `sfincs_his.nc` from the Runs page.
