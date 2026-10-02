#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# deploy_ui.sh -- publish SFINCS UI on laguna.ku.lt as a standalone uvicorn
# systemd unit behind nginx (the osmose pattern; see spec section 5).
#
#   https://laguna.ku.lt/sfincs-ui/
#
# Usage:
#   sudo bash deploy/deploy_ui.sh              # install or update (idempotent)
#   bash deploy/deploy_ui.sh --check           # report state, change nothing, no root
#   sudo bash deploy/deploy_ui.sh --restart    # restart the service only
#   sudo bash deploy/deploy_ui.sh --wait       # wait for running simulations, then restart
#   sudo bash deploy/deploy_ui.sh --uninstall  # remove unit, nginx block, entry, clone
#
# Prod runs from its OWN git clone, never a symlink to the dev tree: a
# long-running uvicorn process must not see its source edited underneath it
# (see /srv/shiny-server/osmose-src/deploy.sh for the failure). The clone is
# pip-installed editable into the shared shiny env, so the running process
# reads the clone, which changes only here, followed by a restart.
#
# The clone cannot build a Curonian model (binary, inputs and catalogue paths
# are gitignored or machine-specific), so CURONIAN_DIR and SFINCS_BIN point
# at the dev checkout, like the viewer's SFINCS_DATA_DIR already does.
# ---------------------------------------------------------------------------
set -euo pipefail

APP_NAME="sfincs-ui"
URL_PREFIX="/sfincs-ui"
PUBLIC_URL="https://laguna.ku.lt${URL_PREFIX}/"
PORT="${SFINCS_UI_PORT:-8840}"
UPLOAD_MAX_MB="${SFINCS_UI_UPLOAD_MAX_MB:-500}"
ADMIN_USERNAME="${SFINCS_UI_ADMIN_USERNAME:-admin}"

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEPLOY_DIR="${REPO_ROOT}/deploy"
REPO_URL="${SFINCS_UI_REPO_URL:-https://github.com/razinkele/sfincs.git}"
DEPLOY_REF="${SFINCS_UI_DEPLOY_REF:-origin/main}"

SHINY_ROOT="/srv/shiny-server"
PROD_SRC="${SHINY_ROOT}/${APP_NAME}-src"
SHINY_PYTHON="/opt/micromamba/envs/shiny/bin/python3"
SHINY_PIP="/opt/micromamba/envs/shiny/bin/pip"
PIP_INSTALL=("$SHINY_PIP" install --root-user-action=ignore --quiet)
WORKSPACE="/srv/sfincs-ui/workspace"
ENV_FILE="/etc/${APP_NAME}.env"
SERVICE_NAME="${APP_NAME}"
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"
NGINX_CONF="/etc/nginx/sites-available/nid4ocean"
SERVICES_JSON="/var/www/html/services.json"
SERVICES_MD="/etc/nginx/sites-available/SERVICES.md"
NGINX_MARKER="location ${URL_PREFIX}/ {"

STAMP="$(date +%Y%m%d_%H%M%S)"
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
info() { echo -e "${GREEN}[+]${NC} $*"; }
warn() { echo -e "${YELLOW}[!]${NC} $*"; }
fail() { echo -e "${RED}[x]${NC} $*" >&2; exit 1; }

MODE="${1:-install}"
case "$MODE" in install|--check|--restart|--wait|--uninstall) ;; *) fail "unknown mode '${MODE}'; use --check, --restart, --wait, --uninstall or no argument";; esac
need_root() { [[ "$(id -u)" -eq 0 ]] || fail "must run as root:  sudo bash deploy/deploy_ui.sh ${*:-}"; }

# Run a sfincs_ui CLI command as the service user with the unit's environment,
# never as root, so the SQLite file and its -wal/-shm companions stay writable
# by the service.
as_shiny() {
    local -a env_args=()
    while IFS= read -r line; do
        [[ -z "$line" || "$line" == \#* ]] && continue
        env_args+=("$line")
    done < "$ENV_FILE"
    # --preserve-env keeps an exported SFINCS_UI_ADMIN_PASSWORD out of argv
    # (argv is world-readable in /proc on a shared box); sudo's env_reset
    # would otherwise drop it.
    sudo -u shiny --preserve-env=SFINCS_UI_ADMIN_PASSWORD env "${env_args[@]}" "$SHINY_PYTHON" -P -m sfincs_ui "$@"
}

render_template() {  # render_template <template> <dest>
    sed -e "s|@PORT@|${PORT}|g" -e "s|@PROD_SRC@|${PROD_SRC}|g" \
        -e "s|@URL_PREFIX@|${URL_PREFIX}|g" -e "s|@UPLOAD_MAX_MB@|${UPLOAD_MAX_MB}|g" "$1" > "$2"
}

# Exit 1 from active-jobs means a simulation is alive. The unit's KillMode=process
# keeps it alive across a restart and the queue reconciles it at startup, so a
# restart is safe; we warn so the operator knows a run is in flight.
warn_if_simulating() {
    local out rc=0
    out="$(as_shiny active-jobs 2>/dev/null)" || rc=$?   # exit 1 = alive simulation; errexit must not fire here
    if [[ $rc -eq 1 ]]; then
        warn "a simulation is running; restarting anyway (KillMode=process keeps it alive, the queue reconciles it):"
        echo "$out" | sed 's/^/      /'
    fi
    return 0
}
wait_for_simulations() {  # --wait: poll up to 90 minutes
    local rc
    for _ in $(seq 1 180); do
        rc=0; as_shiny active-jobs >/dev/null 2>&1 || rc=$?
        [[ $rc -ne 1 ]] && return 0
        info "a simulation is running; waiting 30 s (--wait)"
        sleep 30
    done
    warn "simulation still running after 90 minutes; restarting anyway"
}

# ---------------------------------------------------------------------------
# --check
# ---------------------------------------------------------------------------
if [[ "$MODE" == "--check" ]]; then
    echo "SFINCS UI deployment state"
    echo "  prod clone     : $([[ -d $PROD_SRC/.git ]] && echo "present  $(git -C "$PROD_SRC" rev-parse --short HEAD 2>/dev/null)" || echo "ABSENT   $PROD_SRC")"
    enabled="$(systemctl is-enabled "$SERVICE_NAME" 2>/dev/null)" || enabled="absent"
    active="$(systemctl is-active "$SERVICE_NAME" 2>/dev/null)" || active="inactive"
    echo "  unit           : ${enabled} / ${active}"
    echo "  port ${PORT}      : $(ss -ltn 2>/dev/null | grep -q ":${PORT} " && echo bound || echo free)"
    echo "  nginx          : $(grep -qF "$NGINX_MARKER" "$NGINX_CONF" 2>/dev/null && echo registered || echo "NOT registered")"
    echo "  env file       : $([[ -f $ENV_FILE ]] && echo present || echo ABSENT)"
    echo "  workspace      : $([[ -d $WORKSPACE ]] && echo "present  owner $(stat -c %U "$WORKSPACE")" || echo ABSENT)"
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
    live="$(curl -sk -o /dev/null -w '%{http_code}' "$PUBLIC_URL" 2>/dev/null)" || live="unreachable"
    echo "  live URL       : ${live}"
    exit 0
fi

# ---------------------------------------------------------------------------
# --restart
# ---------------------------------------------------------------------------
if [[ "$MODE" == "--restart" ]]; then
    need_root --restart
    warn_if_simulating
    systemctl restart "$SERVICE_NAME" || fail "could not restart ${SERVICE_NAME}; see: journalctl -u ${SERVICE_NAME} -n 40"
    info "restarted ${SERVICE_NAME}"
    exit 0
fi

# ---------------------------------------------------------------------------
# --wait
# ---------------------------------------------------------------------------
if [[ "$MODE" == "--wait" ]]; then
    need_root --wait
    [[ -f "$ENV_FILE" ]] || fail "${ENV_FILE} missing; run a full install first"
    wait_for_simulations
    systemctl restart "$SERVICE_NAME" || fail "could not restart ${SERVICE_NAME}; see: journalctl -u ${SERVICE_NAME} -n 40"
    info "restarted ${SERVICE_NAME}"
    exit 0
fi

# ---------------------------------------------------------------------------
# --uninstall
# ---------------------------------------------------------------------------
if [[ "$MODE" == "--uninstall" ]]; then
    need_root --uninstall
    [[ -f "$ENV_FILE" ]] && as_shiny kill-jobs || true
    if systemctl is-active --quiet "$SERVICE_NAME" 2>/dev/null; then systemctl stop "$SERVICE_NAME"; fi
    if [[ -f "$SERVICE_FILE" ]]; then
        systemctl disable "$SERVICE_NAME" 2>/dev/null || true
        rm -f "$SERVICE_FILE"; systemctl daemon-reload
        info "removed ${SERVICE_FILE}"
    fi
    if grep -qF "$NGINX_MARKER" "$NGINX_CONF"; then
        cp -a "$NGINX_CONF" "${NGINX_CONF}.bak.${STAMP}"
        "$SHINY_PYTHON" - "$NGINX_CONF" "$URL_PREFIX" <<'PY'
import re, sys
p, prefix = sys.argv[1], sys.argv[2]
t = open(p).read()
pat = r"\n *# ={10,}\n *# SFINCS UI.*?\n *location = " + re.escape(prefix) + r" \{\n.*?\n *\}\n\n"
t2 = re.sub(pat, "\n", t, count=1, flags=re.S)
if t2 == t: raise SystemExit("nginx block not found in the expected shape; remove it by hand")
open(p, "w").write(t2)
PY
        nginx -t || fail "nginx config test FAILED after removing the block; restore ${NGINX_CONF}.bak.${STAMP}"
        systemctl reload nginx
        info "nginx block removed (backup ${NGINX_CONF}.bak.${STAMP})"
    fi
    if [[ -f "$SERVICES_JSON" ]]; then
        cp -a "$SERVICES_JSON" "${SERVICES_JSON}.bak-${STAMP}"
        "$SHINY_PYTHON" - "$SERVICES_JSON" "$APP_NAME" <<'PY'
import json, sys
p, app_id = sys.argv[1], sys.argv[2]
data = json.load(open(p))
for cat in data["categories"]:
    cat["services"] = [s for s in cat["services"] if s["id"] != app_id]
json.dump(data, open(p, "w"), indent=2, ensure_ascii=False)
PY
        info "catalogue entry removed"
    fi
    "$SHINY_PIP" uninstall --root-user-action=ignore -y sfincs-ui >/dev/null 2>&1 || true
    rm -rf "$PROD_SRC"; rm -f "$ENV_FILE"
    info "uninstalled. Workspace ${WORKSPACE} (database and runs) was kept; remove it by hand if wanted."
    exit 0
fi

# ---------------------------------------------------------------------------
# install / update
# ---------------------------------------------------------------------------
need_root
info "Preflight (deployer side)"
[[ -x "$SHINY_PYTHON" ]]  || fail "shiny python missing: ${SHINY_PYTHON}"
[[ -f "$NGINX_CONF" ]]    || fail "nginx config missing: ${NGINX_CONF}"
[[ -f "$SERVICES_JSON" ]] || fail "toolbox catalogue missing: ${SERVICES_JSON}"
command -v git >/dev/null || fail "git is required for the prod clone"
id shiny >/dev/null 2>&1  || fail "service user 'shiny' does not exist"
for f in sfincs-ui.service.in sfincs-ui.env.in sfincs-ui.nginx services-entry-ui.json; do
    [[ -f "${DEPLOY_DIR}/${f}" ]] || fail "missing ${DEPLOY_DIR}/${f}"
done

# --- port refusals: a failed publish must never leave /sfincs-ui/ proxying
#     into another app --------------------------------------------------------
if ss -ltn 2>/dev/null | grep -q ":${PORT} " && ! systemctl is-active --quiet "$SERVICE_NAME" 2>/dev/null; then
    fail "port ${PORT} is bound by something other than ${SERVICE_NAME}; pick another with SFINCS_UI_PORT"
fi
if grep -q "127.0.0.1:${PORT}/" "$NGINX_CONF" && ! grep -qF "$NGINX_MARKER" "$NGINX_CONF"; then
    fail "nginx already proxies to port ${PORT} from another location block"
fi
OTHER_UNIT="$(grep -l -- "--port ${PORT}\b" /etc/systemd/system/*.service 2>/dev/null | grep -v "${SERVICE_NAME}.service" || true)"
[[ -z "$OTHER_UNIT" ]] || fail "another unit names port ${PORT}: ${OTHER_UNIT}"
info "port ${PORT} is ours"

# --- prod clone ------------------------------------------------------------
git config --global --add safe.directory "$PROD_SRC" 2>/dev/null || true
[[ -L "$PROD_SRC" ]] && fail "${PROD_SRC} is a symlink; prod must be a dedicated clone, never a link to a dev tree"
if [[ -d "${PROD_SRC}/.git" ]]; then
    git -C "$PROD_SRC" fetch --quiet --prune origin
elif [[ -e "$PROD_SRC" ]]; then
    fail "${PROD_SRC} exists but is not a git clone; remove it by hand"
else
    git clone --quiet "$REPO_URL" "$PROD_SRC"
fi
git -C "$PROD_SRC" checkout --quiet --force --detach "$DEPLOY_REF"
DEPLOYED_SHA="$(git -C "$PROD_SRC" rev-parse --short HEAD)"
chown -R shiny:shiny "$PROD_SRC"
info "prod clone at ${DEPLOY_REF} (${DEPLOYED_SHA})"

# --- install the package into the shiny env --------------------------------
"${PIP_INSTALL[@]}" -e "${PROD_SRC}/sfincs_ui"
"$SHINY_PYTHON" -P - <<'PY'
import sys
from importlib.metadata import version
from packaging.version import Version
floors = {"shiny": "1.8.0", "sqlalchemy": "2.0", "alembic": "1.13", "argon2-cffi": "23.0",
          "pydantic-settings": "2.0", "uvicorn": "0.30"}
bad = [f"{p} {version(p)} < {f}" for p, f in floors.items() if Version(version(p)) < Version(f)]
if bad: print("DEPENDENCY FLOOR CHECK FAILED:", "; ".join(bad)); sys.exit(1)
import sfincs_ui; print("sfincs_ui", sfincs_ui.__version__, "importable from", sfincs_ui.__file__)
PY
info "package installed"

# --- workspace and environment file ----------------------------------------
mkdir -p "$WORKSPACE"
chown shiny:shiny /srv/sfincs-ui "$WORKSPACE"
chmod 750 "$WORKSPACE"
[[ -f "$ENV_FILE" ]] && cp -a "$ENV_FILE" "${ENV_FILE}.bak.${STAMP}"
render_template "${DEPLOY_DIR}/sfincs-ui.env.in" "$ENV_FILE"
chmod 644 "$ENV_FILE"
info "workspace ${WORKSPACE} and ${ENV_FILE} in place"

# --- preflight as the service user -----------------------------------------
info "Preflight (as user shiny, unit environment)"
as_shiny preflight || fail "preflight failed; fix the reported paths before publishing"

# --- migrations and the first admin, as shiny ------------------------------
as_shiny migrate
if [[ -n "${SFINCS_UI_ADMIN_PASSWORD:-}" ]]; then
    export SFINCS_UI_ADMIN_PASSWORD
fi
as_shiny create-admin --username "$ADMIN_USERNAME"
for f in "${WORKSPACE}"/sfincs_ui.db "${WORKSPACE}"/sfincs_ui.db-wal "${WORKSPACE}"/sfincs_ui.db-shm; do
    [[ -e "$f" ]] && [[ "$(stat -c %U "$f")" != "shiny" ]] && fail "${f} is owned by $(stat -c %U "$f"), not shiny"
done
info "database migrated and owned by shiny"

# --- systemd unit ----------------------------------------------------------
render_template "${DEPLOY_DIR}/sfincs-ui.service.in" "$SERVICE_FILE"
systemctl daemon-reload
systemctl enable "$SERVICE_NAME" >/dev/null 2>&1 || fail "could not enable ${SERVICE_NAME}"
warn_if_simulating
systemctl restart "$SERVICE_NAME"
CODE="000"
for _ in $(seq 1 20); do
    CODE="$(curl -s -m 5 -o /dev/null -w '%{http_code}' "http://127.0.0.1:${PORT}/" || echo 000)"
    [[ "$CODE" == "200" ]] && break
    sleep 2
done
[[ "$CODE" == "200" ]] || fail "service did not answer on port ${PORT} (HTTP ${CODE}); see: journalctl -u ${SERVICE_NAME} -n 40"
info "service ${SERVICE_NAME} is up on port ${PORT}"

# --- nginx -----------------------------------------------------------------
if grep -qF "$NGINX_MARKER" "$NGINX_CONF"; then
    info "nginx already registers ${URL_PREFIX}/"
else
    cp -a "$NGINX_CONF" "${NGINX_CONF}.bak.${STAMP}"
    RENDERED_NGINX="$(mktemp)"; render_template "${DEPLOY_DIR}/sfincs-ui.nginx" "$RENDERED_NGINX"
    "$SHINY_PYTHON" - "$NGINX_CONF" "$RENDERED_NGINX" <<'PY'
import sys
conf_path, block_path = sys.argv[1], sys.argv[2]
text = open(conf_path).read()
block = open(block_path).read()
block = block[block.index("    # ="):].rstrip() + "\n\n"
anchor = "    # =========================================================================\n    # Database Admin Tools"
if anchor not in text:
    raise SystemExit("anchor 'Database Admin Tools' not found in nginx config")
open(conf_path, "w").write(text.replace(anchor, block + anchor, 1))
PY
    rm -f "$RENDERED_NGINX"
    info "nginx block installed (backup ${NGINX_CONF}.bak.${STAMP})"
fi
nginx -t || fail "nginx config test FAILED; restore ${NGINX_CONF}.bak.${STAMP}"
systemctl reload nginx

# --- smoke test over HTTPS (no login over plain http; cookies are Secure) ---
CODE=""
for _ in $(seq 1 15); do
    CODE="$(curl -sk -o /dev/null -w '%{http_code}' "$PUBLIC_URL" || true)"
    [[ "$CODE" == "200" ]] && break
    sleep 1
done
[[ "$CODE" == "200" ]] || fail "${PUBLIC_URL} returned HTTP ${CODE:-none}; catalogue entry left hidden"
PAGE="$(curl -sk "$PUBLIC_URL" || true)"
grep -q "SFINCS UI" <<<"$PAGE" || fail "page served but does not look like SFINCS UI"
LOGIN_CODE="$(curl -sk -o /dev/null -w '%{http_code}' "${PUBLIC_URL}login" || true)"
[[ "$LOGIN_CODE" == "200" ]] || fail "${PUBLIC_URL}login returned HTTP ${LOGIN_CODE}"
info "HTTPS smoke test passed (home and login page)"

# --- toolbox catalogue (visible only now) ----------------------------------
cp -a "$SERVICES_JSON" "${SERVICES_JSON}.bak-${STAMP}"
"$SHINY_PYTHON" - "$SERVICES_JSON" "${DEPLOY_DIR}/services-entry-ui.json" <<'PY'
import json, sys
services_path, entry_path = sys.argv[1], sys.argv[2]
data = json.load(open(services_path))
entry = json.load(open(entry_path)); entry["visible"] = True
target = next(c for c in data["categories"] if c["id"] == "modelling")
existing = next((s for s in target["services"] if s["id"] == entry["id"]), None)
if existing: existing.update(entry)
else: target["services"].append(entry)
target["services"].sort(key=lambda s: s.get("order", 999))
json.dump(data, open(services_path, "w"), indent=2, ensure_ascii=False)
json.load(open(services_path))
PY
info "toolbox catalogue updated (backup ${SERVICES_JSON}.bak-${STAMP})"

if [[ -f "$SERVICES_MD" ]] && ! grep -q '`/sfincs-ui/`' "$SERVICES_MD"; then
    "$SHINY_PYTHON" - "$SERVICES_MD" "$PORT" <<'PY' && info "SERVICES.md row added" || warn "SERVICES.md not updated"
import sys
p, port = sys.argv[1], sys.argv[2]
text = open(p).read()
row = f"| `/sfincs-ui/` | SFINCS UI -- build and run flood models | Python Shiny | uvicorn :{port} | `sfincs-ui` | OK |\n"
anchor = "| `/qgisserver`"
if anchor not in text: raise SystemExit(1)
open(p, "w").write(text.replace(anchor, row + anchor, 1))
PY
fi

echo
info "Deployed:   ${PUBLIC_URL}  (${DEPLOYED_SHA})"
info "Service:    systemctl status ${SERVICE_NAME}    journalctl -u ${SERVICE_NAME} -f"
info "Workspace:  ${WORKSPACE}"
info "Admin:      '${ADMIN_USERNAME}' (created only if no admin existed)"
