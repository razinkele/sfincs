"""The Curonian Lagoon template: drives curonian/build_model.py, validate.py and
prep/export_map_cache.py from a settings document (spec sections 1 to 3)."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime
from functools import lru_cache
from pathlib import Path

from pyproj import Transformer

from sfincs_ui.config import Config
from sfincs_ui.exceptions import TemplateError
from sfincs_ui.templates.base import SettingField, Template

logger = logging.getLogger(__name__)
_FMT = "%Y-%m-%d %H:%M"
_TO_WGS84 = Transformer.from_crs(3346, 4326, always_xy=True)
BUILD_GROUP = "Build parameters (rebuilds the subgrid table)"
OVERRIDES = "Solver overrides"
NOT_SCORED = "run ends before the scoring window"


@dataclass(frozen=True)
class EventInfo:
    """Mirror of the fields the UI needs from curonian/common.py EVENTS.

    Kept here so the UI process never imports `common` (it resolves paths under
    Path.home() at import). tests/test_model_env_curonian.py asserts it matches.
    """
    name: str
    title: str
    tref: str
    tstop: str
    data_window_end: str  # the observation window, not a run bound
    score_window_end: str
    zsini: float | None


CURONIAN_EVENTS: dict[str, EventInfo] = {
    "xaver_2013": EventInfo("xaver_2013", "Xaver 2013", "2013-11-28 00:00", "2013-12-11 00:00", "2013-12-20 00:00", "2013-12-09 00:00", None),
    "april_2013": EventInfo("april_2013", "April 2013 Nemunas freshet", "2013-04-05 00:00", "2013-05-02 00:00", "2013-05-12 00:00", "2013-05-02 00:00", -0.17),
}

# Static geometry shown on the Setup map: (layer name, file, label property or None).
_GEOMETRY_FILES = (
    ("domain", "active_region.geojson", None),
    ("channels", "channels.geojson", "name"),
    ("boundary", "boundary_points.geojson", None),
    ("inflows", "dis_points.geojson", "name"),
    ("stations", "stations.geojson", "name"),
)


def _reproject(coords):
    if isinstance(coords[0], (int, float)):
        lon, lat = _TO_WGS84.transform(coords[0], coords[1])
        return [float(lon), float(lat)]
    return [_reproject(c) for c in coords]


@lru_cache(maxsize=8)
def _load_geometry_cached(inputs_dir: str) -> tuple[dict, ...]:
    out = []
    for name, fname, label_prop in _GEOMETRY_FILES:
        path = Path(inputs_dir) / fname
        try:
            data = json.loads(path.read_text())
            features = [f for f in data.get("features", []) if f.get("geometry")]
            geoms = [f["geometry"] for f in features]
            if not geoms:
                continue
            if all(g["type"] == "Point" for g in geoms):
                geometry = {"type": "MultiPoint", "coordinates": [_reproject(g["coordinates"]) for g in geoms]}
            elif all(g["type"] == "LineString" for g in geoms):
                geometry = {"type": "MultiLineString", "coordinates": [_reproject(g["coordinates"]) for g in geoms]}
            elif len(geoms) == 1:
                geometry = {"type": geoms[0]["type"], "coordinates": _reproject(geoms[0]["coordinates"])}
            else:
                geometry = {"type": "GeometryCollection", "geometries": [{"type": g["type"], "coordinates": _reproject(g["coordinates"])} for g in geoms]}
            layer = {"name": name, "crs": "EPSG:4326", "geometry": geometry}
            if label_prop:
                layer["labels"] = [str(f.get("properties", {}).get(label_prop, "")) for f in features]
            out.append(layer)
        except (OSError, ValueError, KeyError, TypeError) as exc:
            logger.warning("Setup map: %s unreadable (%s); layer %s skipped", path, exc, name)
    return tuple(out)


def load_geometry(inputs_dir: Path) -> list[dict]:
    return [dict(l) for l in _load_geometry_cached(str(Path(inputs_dir).resolve()))]


load_geometry.cache_clear = _load_geometry_cached.cache_clear  # tests clear it between fixtures


class CuronianTemplate(Template):
    key = "curonian"
    title = "Curonian Lagoon and Nemunas delta"
    description = ("The 100 m SFINCS model of the Curonian Lagoon with the Nemunas delta: two hindcast events "
                   "(Xaver 2013 storm surge, April 2013 freshet), gridded or uniform wind, subgrid tables, "
                   "validated against four gauges. A run builds for several minutes and simulates for about "
                   "an hour at 8 threads.")
    has_validation = True
    has_export = True

    def fields(self) -> list[SettingField]:
        return [
            SettingField("event", "Event", "choice", "xaver_2013", choices=("xaver_2013", "april_2013"), group="Event",
                         explanation="Which hindcast period and forcing set to run."),
            SettingField("wind", "Wind", "choice", "uniform", choices=("uniform", "grid"), group="Variant",
                         explanation="uniform: the Nida point series; grid: gridded ERA5 wind."),
            SettingField("pressure", "ERA5 pressure", "bool", False, group="Variant",
                         explanation="Add gridded ERA5 mean sea level pressure (needs gridded wind)."),
            SettingField("subgrid", "Subgrid tables", "bool", True, group="Variant",
                         explanation="Subgrid bathymetry and roughness tables (recommended); off uses the grid-cell DEM and inp roughness."),
            SettingField("manning_land", "Manning n, land", "float", 0.06, minimum=0.01, maximum=0.2, group=BUILD_GROUP,
                         explanation="Roughness above rgh_lev_land. Changing it rebuilds the subgrid table."),
            SettingField("manning_sea", "Manning n, sea", "float", 0.02, minimum=0.005, maximum=0.1, group=BUILD_GROUP,
                         explanation="Roughness below rgh_lev_land."),
            SettingField("rgh_lev_land", "Land/sea level (m)", "float", 0.3, minimum=0.0, maximum=2.0, group=BUILD_GROUP,
                         explanation="Elevation separating land and sea roughness."),
            SettingField("alpha", "alpha", "float", 0.5, minimum=0.1, maximum=0.9, group=OVERRIDES, explanation="CFL number."),
            SettingField("huthresh", "huthresh (m)", "float", 0.05, minimum=0.001, maximum=0.5, group=OVERRIDES,
                         explanation="Wet/dry threshold depth; read at run time even in subgrid mode."),
            SettingField("zsini", "zsini (m)", "float", None, minimum=-2.0, maximum=3.0, group=OVERRIDES, optional=True,
                         explanation="Initial water level. Empty: the event's value (the sea boundary for Xaver, -0.17 m for April)."),
            SettingField("dtmax", "dtmax (s)", "float", None, minimum=1.0, maximum=600.0, group=OVERRIDES, optional=True,
                         explanation="Maximum time step. Empty: the built value (60 s)."),
            SettingField("nuvisc", "nuvisc", "float", None, minimum=0.0, maximum=1.0, group=OVERRIDES, optional=True,
                         explanation="Viscosity coefficient per metre of cell size. Empty: the SFINCS default; the manual recommends 0.01."),
            SettingField("viscosity", "Viscosity", "bool", True, group=OVERRIDES, explanation="Viscosity term on or off."),
            SettingField("advection", "Advection", "bool", True, group=OVERRIDES, explanation="Momentum advection on or off."),
            SettingField("tstop", "Stop time", "datetime", None, group=OVERRIDES, optional=True,
                         explanation="YYYY-MM-DD HH:MM within the event's period (tref to its end). Empty: the event's end. Before the scoring window the run is not validated."),
        ]

    # -- settings ------------------------------------------------------------

    def validate(self, settings: dict) -> dict:
        s = super().validate(settings)
        ev = CURONIAN_EVENTS[s["event"]]
        if s["pressure"] and s["wind"] != "grid":
            raise TemplateError("pressure: requires gridded wind")
        if s["tstop"] is not None and not (ev.tref < s["tstop"] <= ev.tstop):
            raise TemplateError(f"tstop: must lie after {ev.tref} and no later than {ev.tstop} for {ev.title}")
        return s

    def _event(self, settings: dict) -> EventInfo:
        return CURONIAN_EVENTS[settings["event"]]

    def _not_scored(self, settings: dict) -> bool:
        return settings.get("tstop") is not None and settings["tstop"] < self._event(settings).score_window_end

    # -- commands -----------------------------------------------------------

    def build_command(self, run_dir: Path, settings: dict, config: Config) -> list[str]:
        s = self.validate(settings)
        argv = [*config.model_python_argv, str(config.curonian_dir / "build_model.py"),
                "--event", s["event"], "--run-dir", str(run_dir)]
        if s["wind"] == "grid":
            argv += ["--wind", "grid"]
        if s["pressure"]:
            argv.append("--pressure")
        if not s["subgrid"]:
            argv.append("--no-subgrid")
        argv += ["--manning-land", str(s["manning_land"]), "--manning-sea", str(s["manning_sea"]), "--rgh-lev-land", str(s["rgh_lev_land"])]
        return argv

    def stage_cwd(self, stage: str, run_dir: Path, config: Config) -> Path:
        return run_dir if stage == "simulate" else config.curonian_dir

    def inp_overrides(self, settings: dict) -> dict[str, str]:
        s = self.validate(settings)
        out = {"alpha": str(s["alpha"]), "huthresh": str(s["huthresh"]),
               "viscosity": "1" if s["viscosity"] else "0", "advection": "1" if s["advection"] else "0"}
        for key in ("zsini", "dtmax", "nuvisc"):
            if s[key] is not None:
                out[key] = str(float(s[key]))
        if s["tstop"] is not None:
            out["tstop"] = datetime.strptime(s["tstop"], _FMT).strftime("%Y%m%d %H%M%S")
        return out

    def model_files(self) -> tuple[str, ...]:
        return ("sfincs.msk", "sfincs.ind", "sfincs.bzs", "sfincs.dis", "sfincs.obs")

    def validate_command(self, run_dir: Path, settings: dict, config: Config) -> list[str] | None:
        s = self.validate(settings)
        if self._not_scored(s):
            return None
        return [*config.model_python_argv, str(config.curonian_dir / "validate.py"), "--event", s["event"],
                "--run-dir", str(run_dir), "--out-dir", str(run_dir / "validation")]

    def skip_reasons(self, settings: dict) -> dict[str, str]:
        return {"validate": NOT_SCORED} if self._not_scored(self.validate(settings)) else {}

    def export_command(self, run_dir: Path, settings: dict, config: Config) -> list[str] | None:
        s = self.validate(settings)
        return [*config.model_python_argv, "-m", "prep.export_map_cache", "--event", s["event"],
                "--run-dir", str(run_dir), "--out-dir", str(run_dir / "validation")]

    def default_threads(self, settings: dict) -> int:
        return 8

    def geometry_layers(self, project_dir: Path, settings: dict) -> list[dict]:
        from sfincs_ui.config import get_config
        return load_geometry(get_config().curonian_dir / "inputs")

    def example_projects(self) -> list[tuple[str, dict]]:
        return [("Xaver 2013 (uniform wind)", self.defaults()),
                ("April 2013 (uniform wind)", {**self.defaults(), "event": "april_2013"})]
