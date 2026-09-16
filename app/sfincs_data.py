"""Read-only access to SFINCS Curonian Lagoon model outputs.

The viewer never writes to the model tree and never opens ``sfincs_map.nc``
(~190 MB per run); station time series come from the small ``sfincs_his.nc``.

Data location is decoupled from the code location: the app is deployed to
``/srv/shiny-server/sfincs`` while ``runs/`` is gitignored and stays in the
model working tree.  Point ``SFINCS_DATA_DIR`` at that tree.
"""

from __future__ import annotations

import os
import re
from functools import lru_cache
from pathlib import Path

import pandas as pd

try:  # written by deploy/deploy.sh; pins SFINCS_DATA_DIR for the deployed copy
    import _sfincs_env  # noqa: F401
except ImportError:  # running from a checkout — fall back to the environment
    pass

DATA_DIR = Path(os.environ.get("SFINCS_DATA_DIR", "/home/razinka/sfincs/curonian"))

RESULTS_DIR = DATA_DIR / "results"
RUNS_DIR = DATA_DIR / "runs"

# Figures published per variant, in display order.
FIGURES = (
    ("validation_timeseries.png", "Modelled vs gauged water level"),
    ("flood_extent_delta.png", "Flood extent, Nemunas delta"),
)

# Human-readable labels for the run variants that exist today.  Unknown
# variants fall back to the directory name, so a new run shows up unaided.
VARIANT_LABELS = {
    "xaver_2013": "Xaver 2013 — uniform wind",
    "xaver_2013_gridwind": "Xaver 2013 — ERA5 gridded wind",
    "xaver_2013_gridwind_pressure": "Xaver 2013 — ERA5 wind + pressure",
    "april_2013": "April 2013 — Nemunas freshet",
}


def variant_label(variant: str) -> str:
    return VARIANT_LABELS.get(variant, variant)


def list_variants() -> list[str]:
    """Variants that have a validation report."""
    if not RESULTS_DIR.is_dir():
        return []
    return sorted(
        p.name
        for p in RESULTS_DIR.iterdir()
        if p.is_dir() and (p / "validation.md").is_file()
    )


def results_path(variant: str, name: str) -> Path:
    return RESULTS_DIR / variant / name


def run_path(variant: str, name: str) -> Path:
    return RUNS_DIR / variant / name


# --------------------------------------------------------------------------
# validation.md
# --------------------------------------------------------------------------

_CRITERION_RE = re.compile(
    r"^-\s+(?P<label>.+?)\s*\[(?P<window>.*?)\]:\s*"
    r"\*\*(?P<verdict>.+?)\*\*\s*--\s*(?P<detail>.*)$"
)
_FLOODED_RE = re.compile(r"Flooded land[^:]*:\s*\*\*([\d.]+)\s*km")
# Xaver's report says "Storm window"; April's says "Scoring window". Both are the
# event's scored sub-window, so the parser accepts either and the UI calls it what
# the report calls it.
_PERIOD_RE = re.compile(r"^(Whole period|Storm window|Scoring window):\s*(.+)$")


@lru_cache(maxsize=32)
def _validation_text(variant: str, mtime: float) -> str:
    """Cached on (variant, mtime) so an edited report reloads automatically."""
    return results_path(variant, "validation.md").read_text(encoding="utf-8")


def validation_text(variant: str) -> str:
    path = results_path(variant, "validation.md")
    if not path.is_file():
        return ""
    return _validation_text(variant, path.stat().st_mtime)


def criteria(variant: str) -> list[dict]:
    """Success-criteria and info lines, in report order."""
    out = []
    for line in validation_text(variant).splitlines():
        m = _CRITERION_RE.match(line.strip())
        if m:
            out.append(m.groupdict())
    return out


def flooded_area_km2(variant: str) -> float | None:
    m = _FLOODED_RE.search(validation_text(variant))
    return float(m.group(1)) if m else None


def periods(variant: str) -> dict[str, str]:
    found = {}
    for line in validation_text(variant).splitlines():
        m = _PERIOD_RE.match(line.strip())
        if m:
            found[m.group(1)] = m.group(2)
    return found


def scored_window_name(variant: str) -> str:
    """The report's own name for its scored sub-window, for labels and lookups."""
    return next((k for k in periods(variant) if k != "Whole period"), "Scoring window")


def _is_rule(cells: list[str]) -> bool:
    """A markdown table separator row, e.g. ``|---|---|``."""
    return all(c and set(c) <= set("-: ") for c in cells)


def metric_tables(variant: str) -> dict[str, pd.DataFrame]:
    """The two per-station metric tables, keyed by their heading line."""
    tables: dict[str, pd.DataFrame] = {}
    heading: str | None = None
    rows: list[list[str]] = []

    def flush() -> None:
        nonlocal heading, rows
        if heading and len(rows) >= 2:
            header = rows[0]
            body = rows[2:] if _is_rule(rows[1]) else rows[1:]
            if body:
                tables[heading] = pd.DataFrame(body, columns=header)
        rows = []

    for line in validation_text(variant).splitlines():
        stripped = line.strip()
        m = _PERIOD_RE.match(stripped)
        if m:
            flush()
            heading = f"{m.group(1)}: {m.group(2)}"
            continue
        if stripped.startswith("|") and heading:
            rows.append([c.strip() for c in stripped.strip("|").split("|")])
        elif not stripped.startswith("|") and rows:
            flush()
            heading = None
    flush()
    return tables


# --------------------------------------------------------------------------
# sfincs.inp
# --------------------------------------------------------------------------

def inp_settings(variant: str) -> dict[str, str]:
    """Parse the ``key = value`` SFINCS input file."""
    path = run_path(variant, "sfincs.inp")
    if not path.is_file():
        return {}
    settings = {}
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if "=" in line:
            key, _, value = line.partition("=")
            settings[key.strip()] = value.strip()
    return settings


def _fmt_time(raw: str) -> str:
    """SFINCS writes ``YYYYMMDD HHMMSS``; render it readably."""
    try:
        return pd.to_datetime(raw, format="%Y%m%d %H%M%S").strftime("%Y-%m-%d %H:%M")
    except (ValueError, TypeError):
        return raw or "?"


def _fmt_minutes(raw: str | None) -> str:
    try:
        return f"{float(raw) / 60:g} min"
    except (TypeError, ValueError):
        return "?"


def run_summary(variant: str) -> list[tuple[str, str]]:
    """Label/value pairs describing the model set-up, for the overview table."""
    s = inp_settings(variant)
    if not s:
        return []
    grid = "?"
    if {"mmax", "nmax", "dx", "dy"} <= s.keys():
        grid = f"{s['mmax']} x {s['nmax']} cells at {float(s['dx']):g} x {float(s['dy']):g} m"
    try:
        zsini = f"{float(s['zsini']):.3f} m"
    except (KeyError, ValueError):
        zsini = "?"
    return [
        ("Grid", grid),
        ("Projection", f"EPSG:{s.get('epsg', '?')}"),
        ("Simulated period", f"{_fmt_time(s.get('tstart', ''))} to {_fmt_time(s.get('tstop', ''))}"),
        ("Map output interval", _fmt_minutes(s.get("dtout"))),
        ("Station output interval", _fmt_minutes(s.get("dthisout"))),
        ("Manning (land / sea)", f"{s.get('manning_land', '?')} / {s.get('manning_sea', '?')}"),
        ("Initial water level", zsini),
        ("Advection / barotropic", f"{s.get('advection', '?')} / {s.get('baro', '?')}"),
        ("Boundary pressure (pavbnd)", s.get("pavbnd", "?")),
    ]


# --------------------------------------------------------------------------
# sfincs_his.nc — station water levels
# --------------------------------------------------------------------------

def observation_names(variant: str) -> list[str]:
    """Station labels from sfincs.obs, which carries the human-given names."""
    path = run_path(variant, "sfincs.obs")
    if not path.is_file():
        return []
    names = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        parts = line.split()
        if len(parts) >= 3:
            names.append(" ".join(parts[2:]).strip("\"'"))
    return names


def _station_names(ds, variant: str) -> list[str]:
    """Prefer names from sfincs.obs; fall back to positional labels."""
    count = ds.sizes["stations"]
    names = observation_names(variant)
    if len(names) == count:
        return names
    return [f"point {i + 1}" for i in range(count)]


@lru_cache(maxsize=8)
def _station_frame(variant: str, mtime: float) -> pd.DataFrame:
    import xarray as xr

    with xr.open_dataset(run_path(variant, "sfincs_his.nc")) as ds:
        values = ds["point_zs"].load().values
        index = pd.to_datetime(ds["time"].values)
        frame = pd.DataFrame(values, index=index, columns=_station_names(ds, variant))
    frame.index.name = "time"
    return frame


def station_levels(variant: str) -> pd.DataFrame:
    """Water level (m) per observation point; empty frame when unavailable."""
    path = run_path(variant, "sfincs_his.nc")
    if not path.is_file():
        return pd.DataFrame()
    try:
        return _station_frame(variant, path.stat().st_mtime)
    except (OSError, KeyError, ValueError):
        return pd.DataFrame()


def run_log_tail(variant: str, lines: int = 200) -> str:
    path = run_path(variant, "sfincs.log")
    if not path.is_file():
        return "No sfincs.log for this run."
    text = path.read_text(encoding="utf-8", errors="replace").splitlines()
    return "\n".join(text[-lines:])
