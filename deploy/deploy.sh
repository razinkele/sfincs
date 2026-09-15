#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# deploy.sh — publish the SFINCS Curonian Lagoon viewer on laguna.ku.lt
#
# Serves the app from Shiny Server (port 3838, shared micromamba env) behind
# the existing nginx HTTPS block, and registers it in the toolbox catalogue.
#
#   https://laguna.ku.lt/sfincs/
#
# Usage:
#   sudo bash deploy/deploy.sh             # install or update (idempotent)
#   sudo bash deploy/deploy.sh --code-only # ship code, skip config + catalogue
#   sudo bash deploy/deploy.sh --uninstall # remove app, config and entry
#   sudo bash deploy/deploy.sh --check     # report state, change nothing
#
# Every step is idempotent: config blocks are inserted only when their marker
# is absent, so re-running this to push a code change is safe.
#
# WHY Shiny Server and not a standalone uvicorn service: this app is
# read-only and light, and the shared env already carries every dependency
# (shiny, pandas, xarray, netCDF4, matplotlib).  The osmose-style dedicated
# service exists for apps that hit Shiny Server's websocket edge cases; if
# this one ever does, see /srv/shiny-server/osmose-src/deploy.sh.
# ---------------------------------------------------------------------------
set -euo pipefail

APP_NAME="sfincs"
URL_PATH="/sfincs/"
PUBLIC_URL="https://laguna.ku.lt${URL_PATH}"

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SRC_DIR="${REPO_ROOT}/app"
DEPLOY_DIR="${REPO_ROOT}/deploy"

APP_DIR="/srv/shiny-server/${APP_NAME}"
SHINY_PYTHON="/opt/micromamba/envs/shiny/bin/python3"
SHINY_CONF="/etc/shiny-server/shiny-server.conf"
NGINX_CONF="/etc/nginx/sites-available/nid4ocean"
SERVICES_JSON="/var/www/html/services.json"
LOG_DIR="/var/log/shiny-server"

# The model outputs the viewer reads.  Code and data are deliberately
# separate: runs/ is gitignored and stays in the model working tree.
SFINCS_DATA_DIR="${SFINCS_DATA_DIR:-/home/razinka/sfincs/curonian}"

STAMP="$(date +%Y%m%d_%H%M%S)"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
info() { echo -e "${GREEN}[+]${NC} $*"; }
warn() { echo -e "${YELLOW}[!]${NC} $*"; }
fail() { echo -e "${RED}[x]${NC} $*" >&2; exit 1; }

MODE="${1:-install}"

need_root() {
    [[ "$(id -u)" -eq 0 ]] || fail "must run as root:  sudo bash deploy/deploy.sh ${*:-}"
}

# ---------------------------------------------------------------------------
# --check — report state without touching anything
# ---------------------------------------------------------------------------
if [[ "$MODE" == "--check" ]]; then
    echo "SFINCS viewer deployment state"
    echo "  app dir        : $([[ -d $APP_DIR ]] && echo "present  $APP_DIR" || echo "ABSENT   $APP_DIR")"
    echo "  shiny-server   : $(grep -q "location /${APP_NAME}\b" "$SHINY_CONF" && echo "registered" || echo "NOT registered")"
    echo "  nginx          : $(grep -q "location ${URL_PATH}" "$NGINX_CONF" && echo "registered" || echo "NOT registered")"
    echo "  catalogue      : $("$SHINY_PYTHON" - "$SERVICES_JSON" "$APP_NAME" <<'PY'
import json, sys
try:
    data = json.load(open(sys.argv[1]))
except Exception as exc:
    print(f"unreadable ({exc})"); raise SystemExit
for cat in data["categories"]:
    for svc in cat["services"]:
        if svc["id"] == sys.argv[2]:
            print(f"present in '{cat['id']}', visible={svc.get('visible')}"); raise SystemExit
print("ABSENT")
PY
)"
    echo "  data dir       : $([[ -d $SFINCS_DATA_DIR ]] && echo "present  $SFINCS_DATA_DIR" || echo "ABSENT   $SFINCS_DATA_DIR")"
    echo "  live URL       : $(curl -sk -o /dev/null -w '%{http_code}' "$PUBLIC_URL" || echo unreachable)"
    exit 0
fi

# ---------------------------------------------------------------------------
# --uninstall
# ---------------------------------------------------------------------------
if [[ "$MODE" == "--uninstall" ]]; then
    need_root --uninstall
    info "Removing ${APP_NAME}…"

    if grep -q "location ${URL_PATH}" "$NGINX_CONF"; then
        cp -a "$NGINX_CONF" "${NGINX_CONF}.bak.${STAMP}"
        "$SHINY_PYTHON" - "$NGINX_CONF" <<'PY'
import re, sys
p = sys.argv[1]; t = open(p).read()
t = re.sub(r"\n *# ={10,}\n *# SFINCS.*?\n *location = /sfincs \{\n.*?\n *\}\n\n", "\n", t, flags=re.S)
open(p, "w").write(t)
PY
        info "nginx block removed (backup ${NGINX_CONF}.bak.${STAMP})"
    fi

    if grep -q "location /${APP_NAME}\b" "$SHINY_CONF"; then
        cp -a "$SHINY_CONF" "${SHINY_CONF}.bak.${STAMP}"
        "$SHINY_PYTHON" - "$SHINY_CONF" <<'PY'
import re, sys
p = sys.argv[1]; t = open(p).read()
t = re.sub(r"\n *location /sfincs \{\n.*?\n *\}\n\n", "\n", t, flags=re.S)
open(p, "w").write(t)
PY
        info "shiny-server block removed (backup ${SHINY_CONF}.bak.${STAMP})"
    fi

    cp -a "$SERVICES_JSON" "${SERVICES_JSON}.bak-${STAMP}"
    "$SHINY_PYTHON" - "$SERVICES_JSON" "$APP_NAME" <<'PY'
import json, sys
p, app_id = sys.argv[1], sys.argv[2]
data = json.load(open(p))
for cat in data["categories"]:
    cat["services"] = [s for s in cat["services"] if s["id"] != app_id]
json.dump(data, open(p, "w"), indent=2, ensure_ascii=False)  # matches the file's existing style
PY
    info "catalogue entry removed (backup ${SERVICES_JSON}.bak-${STAMP})"

    rm -rf "$APP_DIR"
    nginx -t && systemctl reload nginx
    systemctl reload shiny-server
    info "Uninstalled. ${PUBLIC_URL} will now 404."
    exit 0
fi

# ---------------------------------------------------------------------------
# install / update
# ---------------------------------------------------------------------------
need_root
CODE_ONLY=false
[[ "$MODE" == "--code-only" ]] && CODE_ONLY=true

# --- preflight ------------------------------------------------------------
info "Preflight"
[[ -f "${SRC_DIR}/app.py" ]]   || fail "app source not found at ${SRC_DIR}/app.py"
[[ -x "$SHINY_PYTHON" ]]       || fail "shiny python missing: ${SHINY_PYTHON}"
[[ -f "$SHINY_CONF" ]]         || fail "shiny-server config missing: ${SHINY_CONF}"
[[ -f "$NGINX_CONF" ]]         || fail "nginx config missing: ${NGINX_CONF}"
[[ -f "$SERVICES_JSON" ]]      || fail "toolbox catalogue missing: ${SERVICES_JSON}"

[[ -d "$SFINCS_DATA_DIR/results" ]] \
    || warn "no results/ under ${SFINCS_DATA_DIR} — the app will load but show no runs"

# The app runs as the 'shiny' user; it must be able to traverse to the data.
if ! sudo -u shiny test -r "${SFINCS_DATA_DIR}/results" 2>/dev/null; then
    warn "user 'shiny' cannot read ${SFINCS_DATA_DIR}/results"
    warn "  fix with:  chmod o+x $(dirname "$(dirname "$SFINCS_DATA_DIR")") ${SFINCS_DATA_DIR%/*} ${SFINCS_DATA_DIR}"
fi

"$SHINY_PYTHON" -c 'import shiny, pandas, xarray, matplotlib, netCDF4' \
    || fail "shared shiny env is missing a dependency (shiny/pandas/xarray/matplotlib/netCDF4)"
info "dependencies present in shared env"

# --- ship the code --------------------------------------------------------
info "Installing app to ${APP_DIR}"
mkdir -p "$APP_DIR"
# A real directory, not a symlink into a dev tree: a long-running Shiny
# process resolves its own source via inspect(), and source edited underneath
# it makes line numbers drift (see osmose-src/deploy.sh for the failure mode).
rsync -a --delete \
    --exclude '__pycache__/' --exclude '*.pyc' --exclude '.pytest_cache/' \
    --exclude 'test_*.py' \
    "${SRC_DIR}/" "${APP_DIR}/"

# Shiny Server starts the app without inheriting this shell's environment, so
# the data path is baked into a small generated module that sfincs_data
# imports on start-up (it degrades to the env var when absent).
"$SHINY_PYTHON" - "$APP_DIR" "$SFINCS_DATA_DIR" <<'PY'
import pathlib, sys
app_dir, data_dir = pathlib.Path(sys.argv[1]), sys.argv[2]
(app_dir / "_sfincs_env.py").write_text(
    '"""Generated by deploy/deploy.sh — do not edit."""\n'
    "import os\n"
    f'os.environ.setdefault("SFINCS_DATA_DIR", {data_dir!r})\n'
)
PY

# Shiny Server restarts an app when this file's mtime changes.  Without it a
# re-deploy would rsync new code underneath a process that keeps running the
# old one — `systemctl reload` re-reads config but does not cycle app
# processes.  Must come after the rsync, whose --delete would remove it.
touch "${APP_DIR}/restart.txt"

chown -R root:shiny "$APP_DIR"
chmod -R u=rwX,g=rX,o=rX "$APP_DIR"
info "code installed ($(find "$APP_DIR" -name '*.py' | wc -l) python files)"

if $CODE_ONLY; then
    systemctl reload shiny-server
    info "Code updated, app restarted. ${PUBLIC_URL}"
    exit 0
fi

# --- shiny-server registration -------------------------------------------
if grep -q "location /${APP_NAME}\b" "$SHINY_CONF"; then
    info "shiny-server already registers /${APP_NAME}"
else
    cp -a "$SHINY_CONF" "${SHINY_CONF}.bak.${STAMP}"
    "$SHINY_PYTHON" - "$SHINY_CONF" "${DEPLOY_DIR}/sfincs.shiny-server.conf" <<'PY'
import sys
conf_path, block_path = sys.argv[1], sys.argv[2]
text = open(conf_path).read()
# Keep only the location block from the snippet (drop its comment header).
block = open(block_path).read()
block = block[block.index("  location /sfincs {"):].rstrip() + "\n\n"
anchor = "  # ==========================================================================\n  # DEFAULT FALLBACK"
if anchor not in text:
    raise SystemExit("anchor 'DEFAULT FALLBACK' not found in shiny-server.conf")
text = text.replace(anchor, block + anchor, 1)
open(conf_path, "w").write(text)
PY
    info "shiny-server block installed (backup ${SHINY_CONF}.bak.${STAMP})"
fi

# --- nginx registration ---------------------------------------------------
if grep -q "location ${URL_PATH}" "$NGINX_CONF"; then
    info "nginx already registers ${URL_PATH}"
else
    cp -a "$NGINX_CONF" "${NGINX_CONF}.bak.${STAMP}"
    "$SHINY_PYTHON" - "$NGINX_CONF" "${DEPLOY_DIR}/sfincs.nginx" <<'PY'
import sys
conf_path, block_path = sys.argv[1], sys.argv[2]
text = open(conf_path).read()
block = open(block_path).read()
block = block[block.index("    # ="):].rstrip() + "\n\n"
anchor = "    # =========================================================================\n    # Database Admin Tools"
if anchor not in text:
    raise SystemExit("anchor 'Database Admin Tools' not found in nginx config")
text = text.replace(anchor, block + anchor, 1)
open(conf_path, "w").write(text)
PY
    info "nginx block installed (backup ${NGINX_CONF}.bak.${STAMP})"
fi

# --- validate and reload --------------------------------------------------
nginx -t || fail "nginx config test FAILED — restore ${NGINX_CONF}.bak.${STAMP}"
info "nginx -t passed"

# reload, never restart: restart would drop every live session on this server.
systemctl reload shiny-server
systemctl reload nginx
info "shiny-server and nginx reloaded"

# --- smoke test -----------------------------------------------------------
info "Smoke test"
CODE=""
for _ in $(seq 1 15); do
    CODE="$(curl -sk -o /dev/null -w '%{http_code}' "$PUBLIC_URL" || true)"
    [[ "$CODE" == "200" ]] && break
    sleep 1
done

if [[ "$CODE" != "200" ]]; then
    warn "${PUBLIC_URL} returned HTTP ${CODE:-none}"
    warn "check: tail -n 40 ${LOG_DIR}/${APP_NAME}-*.log"
    fail "deployment incomplete — catalogue entry left hidden"
fi

curl -sk "$PUBLIC_URL" | grep -qi "SFINCS" \
    || fail "page served but does not look like the SFINCS app"
info "HTTP 200 and page content verified"

# Fetch one published figure through the proxy.  This single request proves
# two things reasoning alone cannot: that the /sfincs prefix is stripped
# correctly on the way to the app, and that user 'shiny' can actually read
# the model tree (the figure is streamed from SFINCS_DATA_DIR at request
# time, not bundled with the code).
FIRST_VARIANT="$(ls "${SFINCS_DATA_DIR}/results" 2>/dev/null | head -1 || true)"
if [[ -n "$FIRST_VARIANT" ]]; then
    FIG_URL="${PUBLIC_URL}figures/${FIRST_VARIANT}/validation_timeseries.png"
    read -r FIG_CODE FIG_SIZE < <(curl -sk -o /dev/null -w '%{http_code} %{size_download}' "$FIG_URL" || echo "000 0")
    if [[ "$FIG_CODE" == "200" && "${FIG_SIZE:-0}" -gt 0 ]]; then
        info "figure route verified (${FIG_SIZE} bytes from ${FIRST_VARIANT})"
    else
        warn "figure request returned HTTP ${FIG_CODE}, ${FIG_SIZE} bytes"
        warn "  the page works, but figures will be blank — check that user"
        warn "  'shiny' can read ${SFINCS_DATA_DIR}/results"
    fi
else
    warn "no run directories under ${SFINCS_DATA_DIR}/results — skipping figure check"
fi

# --- toolbox catalogue ----------------------------------------------------
cp -a "$SERVICES_JSON" "${SERVICES_JSON}.bak-${STAMP}"
"$SHINY_PYTHON" - "$SERVICES_JSON" "${DEPLOY_DIR}/services-entry.json" <<'PY'
import json, sys
services_path, entry_path = sys.argv[1], sys.argv[2]
data = json.load(open(services_path))
entry = json.load(open(entry_path))
entry["visible"] = True          # smoke test passed, so show it

target = next(c for c in data["categories"] if c["id"] == "modelling")
existing = next((s for s in target["services"] if s["id"] == entry["id"]), None)
if existing:
    existing.update(entry)
    action = "updated"
else:
    target["services"].append(entry)
    action = "added"
target["services"].sort(key=lambda s: s.get("order", 999))

json.dump(data, open(services_path, "w"), indent=2, ensure_ascii=False)
json.load(open(services_path))   # re-parse: never leave a broken catalogue
print(f"    catalogue entry {action} and made visible")
PY
info "toolbox catalogue updated (backup ${SERVICES_JSON}.bak-${STAMP})"

# --- server documentation (best effort; never fails a deploy) -------------
SERVICES_MD="/etc/nginx/sites-available/SERVICES.md"
if [[ -f "$SERVICES_MD" ]] && ! grep -q '`/sfincs/`' "$SERVICES_MD"; then
    if "$SHINY_PYTHON" - "$SERVICES_MD" <<'PY'
import sys
p = sys.argv[1]
text = open(p).read()
row = ("| `/sfincs/` | SFINCS — Curonian Lagoon flood model viewer | Python Shiny "
       "| Shiny Server :3838 | `shiny-server` | OK |\n")
anchor = "| `/qgisserver`"
if anchor not in text:
    raise SystemExit("anchor row not found")
open(p, "w").write(text.replace(anchor, row + anchor, 1))
PY
    then info "SERVICES.md row added"; else warn "SERVICES.md not updated (add the row by hand)"; fi
fi

echo
info "Deployed:  ${PUBLIC_URL}"
info "Logs:      ${LOG_DIR}/${APP_NAME}-*.log"
info "Data:      ${SFINCS_DATA_DIR}"
