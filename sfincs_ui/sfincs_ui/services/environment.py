"""Is this host able to build and run a SFINCS model?

Shallow checks run once at startup and feed the banner shown on every page
when something is missing (spec section 5, Errors). Deep checks are the deploy
preflight the spec lists under "Preflight", run as user shiny by
``python -m sfincs_ui preflight``. ``runner`` is injectable so tests never
shell out.
"""

from __future__ import annotations

import os
import re
import sqlite3
import subprocess
import tempfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from sfincs_ui.config import Config
from sfincs_ui.timeutil import utcnow

BINARY_TIMEOUT_S = 15
MODEL_ENV_TIMEOUT_S = 120
# The startup import check runs before the app serves; a wedged micromamba must
# cost seconds, not minutes (plan Review Focus 4). Deep checks keep 120 s.
MODEL_ENV_STARTUP_TIMEOUT_S = 20
BANNER = "Welcome to SFINCS"
EVENTS = ("xaver_2013", "april_2013")
# curonian/data_catalog.yml carries three absolute paths on this host (DEM, bathymetry, gauge database).
EXPECTED_CATALOGUE_PATHS = 3

_IMPORT_SNIPPET = "import hydromt_sfincs, rasterio"
_GEOTIFF_SNIPPET = "import rasterio; rasterio.open({path!r}).close()"
DEFAULT_GAUGE_DB = "/home/razinka/curonian/curonian_db.gpkg"


@dataclass
class EnvironmentReport:
    problems: list[str] = field(default_factory=list)
    checked_at: datetime = field(default_factory=utcnow)

    @property
    def ok(self) -> bool:
        return not self.problems


def _run_model_python(config: Config, snippet: str, runner, label: str, problems: list[str],
                      timeout: int = MODEL_ENV_TIMEOUT_S) -> None:
    argv = [*config.model_python_argv, "-c", snippet]
    try:
        proc = runner(argv, cwd=str(config.curonian_dir), capture_output=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        problems.append(f"Model environment check ({label}) timed out after {timeout} s: {config.model_python}")
        return
    except (OSError, FileNotFoundError) as exc:
        problems.append(f"Model environment command cannot start: {config.model_python} ({exc})")
        return
    if proc.returncode != 0:
        tail = (proc.stderr or b"").decode(errors="replace").strip().splitlines()[-1:] or [""]
        problems.append(f"Model environment cannot {label}: exit {proc.returncode} {tail[0]}".rstrip())


def _check_binary(config: Config, runner, problems: list[str]) -> None:
    binary = config.sfincs_bin
    if not binary.exists():
        problems.append(f"SFINCS binary not found at {binary}")
        return
    if not os.access(binary, os.X_OK):
        problems.append(f"SFINCS binary is not executable: {binary}")
        return
    with tempfile.TemporaryDirectory(prefix="sfincs-ui-bincheck-") as tmp:
        try:
            proc = runner([str(binary)], cwd=tmp, capture_output=True, timeout=BINARY_TIMEOUT_S)
        except subprocess.TimeoutExpired:
            problems.append(f"SFINCS binary did not exit within {BINARY_TIMEOUT_S} s in an empty directory: {binary}")
            return
        except OSError as exc:
            problems.append(f"SFINCS binary failed to start: {binary} ({exc})")
            return
    if BANNER not in (proc.stdout or b"").decode(errors="replace"):
        problems.append(f"SFINCS binary ran but printed no SFINCS banner: {binary}")


def _check_dirs(config: Config, problems: list[str]) -> None:
    for script in ("build_model.py", "validate.py"):
        if not (config.curonian_dir / script).is_file():
            problems.append(f"Curonian model directory lacks {script}: {config.curonian_dir}")
    ws = config.workspace
    if not ws.is_dir():
        problems.append(f"Workspace does not exist: {ws}")
    elif not os.access(ws, os.W_OK):
        problems.append(f"Workspace is not writable by this user: {ws}")


def _check_deep(config: Config, runner, problems: list[str]) -> None:
    inputs = config.curonian_dir / "inputs"
    tif = inputs / "lagoon_bathy_50m.tif"
    for rel in ["lagoon_bathy_50m.tif", *(f"{e}/era5_grid.nc" for e in EVENTS), *(f"{e}/gtsm" for e in EVENTS)]:
        if not os.access(inputs / rel, os.R_OK):
            problems.append(f"Input not readable: inputs/{rel}")
    catalogue = config.curonian_dir / "data_catalog.yml"
    if catalogue.is_file():
        try:
            text = catalogue.read_text()
        except (OSError, UnicodeDecodeError) as exc:
            problems.append(f"Catalogue not readable: {catalogue} ({exc})")
        else:
            paths = re.findall(r"^\s*path:\s*(/\S+)", text, re.M)
            if len(paths) < EXPECTED_CATALOGUE_PATHS:
                problems.append(
                    f"Catalogue lists {len(paths)} absolute path(s), expected at least "
                    f"{EXPECTED_CATALOGUE_PATHS} (DEM, bathymetry, gauge database): {catalogue}"
                )
            for p in paths:
                if not os.access(p, os.R_OK):
                    problems.append(f"Catalogue path not readable: {p}")
    if tif.is_file():
        _run_model_python(config, _GEOTIFF_SNIPPET.format(path=str(tif)), runner, "open a GeoTIFF with rasterio", problems)
    # The gauge database is read by validate.py and export_map_cache (milestone
    # 3 routes them through SFINCS_CURONIAN_DB). Open it read-only here so a
    # path the service user cannot read is caught at deploy time.
    gauge_db = os.environ.get("SFINCS_CURONIAN_DB", DEFAULT_GAUGE_DB)
    try:
        sqlite3.connect(f"file:{gauge_db}?mode=ro", uri=True).close()
    except sqlite3.Error as exc:
        problems.append(f"Gauge database cannot be opened read-only: {gauge_db} ({exc})")


def check_environment(config: Config, *, deep: bool = False, runner=subprocess.run) -> EnvironmentReport:
    problems: list[str] = []
    _check_binary(config, runner, problems)
    # The deploy preflight (deep) may meet a cold micromamba cache; give it the long timeout.
    _run_model_python(config, _IMPORT_SNIPPET, runner, "import hydromt_sfincs and rasterio", problems,
                      timeout=MODEL_ENV_TIMEOUT_S if deep else MODEL_ENV_STARTUP_TIMEOUT_S)
    _check_dirs(config, problems)
    if deep:
        _check_deep(config, runner, problems)
    return EnvironmentReport(problems=problems)
