# Deploying the SFINCS viewer to laguna.ku.lt

Publishes the read-only SFINCS results viewer (`app/`) at
**<https://laguna.ku.lt/sfincs/>** and registers it in the toolbox catalogue.

```bash
sudo bash deploy/deploy.sh
```

That single command is the whole routine. It is idempotent — re-run it to ship
a code change.

## What it touches

| Target | Change | Backup taken |
|---|---|---|
| `/srv/shiny-server/sfincs/` | app code, rsynced from `app/` | — (replaced wholesale) |
| `/etc/shiny-server/shiny-server.conf` | adds `location /sfincs` | `.bak.<stamp>` |
| `/etc/nginx/sites-available/nid4ocean` | adds `location /sfincs/` + redirect | `.bak.<stamp>` |
| `/var/www/html/services.json` | adds/updates the toolbox entry | `.bak-<stamp>` |
| `/etc/nginx/sites-available/SERVICES.md` | adds a row (best effort) | — |

The two config snippets are kept as reviewable files next to the script:
`sfincs.shiny-server.conf` and `sfincs.nginx`. The catalogue entry lives in
`services-entry.json`.

## Modes

```bash
sudo bash deploy/deploy.sh --check      # report state, change nothing
sudo bash deploy/deploy.sh --code-only  # ship code + reload, skip config
sudo bash deploy/deploy.sh --uninstall  # remove app, config and entry
```

`--uninstall` restores both config files byte-for-byte to their pre-install
content (verified against the live files) and removes the catalogue entry.

## Order of operations

The script deliberately makes the app **visible in the toolbox last**:

1. preflight — dependencies, paths, and whether user `shiny` can read the data
2. rsync the code into `/srv/shiny-server/sfincs`
3. register with Shiny Server, then with nginx
4. `nginx -t`, then **reload** (never restart — a restart drops every live
   session on this server)
5. smoke-test `https://laguna.ku.lt/sfincs/` for HTTP 200 and SFINCS content
6. only then set `visible: true` in `services.json`

If the smoke test fails the script exits non-zero and the toolbox entry stays
hidden, so a broken deploy never shows a dead tile on the landing page.

## Code and data are separate

`app/` holds only code. The model outputs it reads stay in the model working
tree, because `curonian/runs/` is gitignored and `sfincs_map.nc` is ~190 MB
per run.

The path is baked into a generated `_sfincs_env.py` at deploy time (Shiny
Server does not pass this shell's environment to the app). Override it:

```bash
sudo SFINCS_DATA_DIR=/path/to/curonian bash deploy/deploy.sh
```

The `shiny` user must be able to read that tree — it needs `o+x` on every
parent directory and `o+r` on the files. `--check` and the preflight both
report this.

## Dependencies

None to install. The shared env `/opt/micromamba/envs/shiny` already provides
shiny, pandas, xarray, netCDF4 and matplotlib. The viewer never opens
`sfincs_map.nc`; station series come from the ~200 KB `sfincs_his.nc`.

## Tests

The app's tests import `app.py`, so they need the same `shiny` env the app runs
in — **not** `hydromt-sfincs`, which has no `shiny` and fails at collection:

```bash
micromamba run -n shiny python -m pytest app/test_sfincs_data.py -q
```

The model's own suite stays in its own env, run from `curonian/`:

```bash
micromamba run -n hydromt-sfincs python -m pytest tests -q
```

Run the latter from the main checkout, not a git worktree: two integration
tests need `lagoon_bathy_50m.tif` and the SFINCS binary, both git-ignored and
so absent from any worktree, and they fail rather than skip there.

## Why Shiny Server rather than a dedicated service

This app is light and read-only, and matches the `/shyfem-ui/` and `/telemac/`
pattern. Apps that hit Shiny Server's Python websocket edge cases run instead
as a standalone uvicorn unit — see `/srv/shiny-server/osmose-src/deploy.sh` if
this one ever needs to move.

## Catalogue entry note

`services-entry.json` intentionally omits the `github` field. The landing page
uses it to fetch a README from `raw.githubusercontent.com`, and
`razinkele/sfincs` is private, so the button would 404. Add it once the
repository is public:

```json
"github": { "repo": "razinkele/sfincs", "branch": "main" }
```

## Troubleshooting

```bash
sudo bash deploy/deploy.sh --check
tail -n 40 /var/log/shiny-server/sfincs-*.log
```

A 500 with an empty page usually means the `python` directive is missing from
the Shiny Server block — without it the app is treated as an R app.
