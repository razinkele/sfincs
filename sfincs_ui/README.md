# sfincs_ui

Web app for laguna.ku.lt through which a logged-in user creates a SFINCS
project from a template, launches a simulation on the server and inspects the
results. Design: `docs/superpowers/specs/2026-09-30-sfincs-ui-design.md`.
Milestone 1 (this state): configuration, database, auth, Admin page, CLI,
service unit and deploy script. Projects, runs and the queue arrive in
milestone 2.

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
