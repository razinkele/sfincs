"""The test template: a plane beach flooded by a rising boundary level (from test_model/)."""

from __future__ import annotations

import sys
from pathlib import Path

from sfincs_ui.config import Config
from sfincs_ui.templates import plane_beach_build
from sfincs_ui.templates.base import SettingField, Template

DOMAIN_X_M, DOMAIN_Y_M = 5000.0, 2000.0
STATIONS = (("offshore", 1050.0, 1050.0), ("shoreline", 2550.0, 1050.0), ("inland", 3250.0, 1050.0))
OVERRIDE_KEYS = ("alpha", "huthresh", "advection")


class PlaneBeachTemplate(Template):
    key = "plane_beach"
    title = "Plane beach (test model)"
    description = ("A 5 km by 2 km plane beach rising from -5 m to +4.8 m, flooded by a water level ramping up "
                   "at the western boundary. Builds in a second; no validation, no map export.")

    def fields(self) -> list[SettingField]:
        return [
            SettingField("resolution_m", "Cell size (m)", "choice", 100, choices=(100, 50, 20, 10, 5),
                         explanation="100 m runs in a second; 5 m takes minutes and is what the restart acceptance uses."),
            SettingField("duration_hours", "Duration (h)", "int", 6, minimum=1, maximum=24,
                         explanation="Length of the simulation and of the boundary ramp."),
            SettingField("boundary_level_m", "Boundary level (m)", "float", 2.0, minimum=0.5, maximum=4.0,
                         explanation="Water level at the western boundary at the end of the ramp."),
            SettingField("manning", "Manning n", "float", 0.04, minimum=0.01, maximum=0.10,
                         explanation="Uniform bed roughness."),
            SettingField("alpha", "alpha", "float", 0.5, minimum=0.1, maximum=0.9, group="Solver overrides",
                         explanation="CFL number; lower is more stable and slower."),
            SettingField("huthresh", "huthresh (m)", "float", 0.05, minimum=0.001, maximum=0.5, group="Solver overrides",
                         explanation="Wet/dry threshold depth."),
            SettingField("advection", "Advection", "bool", True, group="Solver overrides",
                         explanation="Momentum advection on or off."),
        ]

    def build_command(self, run_dir: Path, settings: dict, config: Config) -> list[str]:
        return [sys.executable, "-P", str(Path(plane_beach_build.__file__).resolve()),
                "--run-dir", str(run_dir), "--settings", str(run_dir / "settings.json")]

    def inp_overrides(self, settings: dict) -> dict[str, str]:
        s = self.validate(settings)
        return {"alpha": str(s["alpha"]), "huthresh": str(s["huthresh"]), "advection": "1" if s["advection"] else "0"}

    def model_files(self) -> tuple[str, ...]:
        return ("sfincs.dep", "sfincs.msk", "sfincs.bnd", "sfincs.bzs", "sfincs.obs")

    def geometry_layers(self, project_dir: Path, settings: dict) -> list[dict]:
        box = [[0, 0], [DOMAIN_X_M, 0], [DOMAIN_X_M, DOMAIN_Y_M], [0, DOMAIN_Y_M], [0, 0]]
        return [
            {"name": "domain", "geometry": {"type": "Polygon", "coordinates": [box]}},
            {"name": "boundary", "geometry": {"type": "LineString", "coordinates": [[0, 0], [0, DOMAIN_Y_M]]}},
            {"name": "stations", "geometry": {"type": "MultiPoint", "coordinates": [[x, y] for _, x, y in STATIONS]},
             "labels": [n for n, _, _ in STATIONS]},
        ]

    def example_projects(self) -> list[tuple[str, dict]]:
        return [("Plane beach example", self.defaults())]
