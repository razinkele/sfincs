"""A template whose stages are the shell fakes under tests/fixtures/."""

from __future__ import annotations

from pathlib import Path

from sfincs_ui.config import Config
from sfincs_ui.templates.base import SettingField, Template

FIXTURES = Path(__file__).resolve().parent / "fixtures"
FAKE_BUILD = FIXTURES / "fake_build.sh"
FAKE_SFINCS = FIXTURES / "fake_sfincs.sh"
FAKE_VALIDATE = FIXTURES / "fake_validate.sh"


class FakeTemplate(Template):
    key = "fake"
    title = "Fake"
    description = "shell fakes"

    def __init__(self, with_validation: bool = False):
        self.has_validation = with_validation

    def fields(self) -> list[SettingField]:
        return [SettingField("alpha", "alpha", "float", 0.5, minimum=0.1, maximum=0.9, group="Solver overrides")]

    def build_command(self, run_dir: Path, settings: dict, config: Config) -> list[str]:
        return ["bash", str(FAKE_BUILD), str(run_dir)]

    def inp_overrides(self, settings: dict) -> dict[str, str]:
        return {"alpha": str(self.validate(settings)["alpha"])}

    def model_files(self) -> tuple[str, ...]:
        return ("sfincs.dep",)

    def validate_command(self, run_dir: Path, settings: dict, config: Config) -> list[str] | None:
        if not self.has_validation:
            return None
        return ["bash", str(FAKE_VALIDATE), str(run_dir), str(run_dir / "validation")]

    def example_projects(self) -> list[tuple[str, dict]]:
        return [("Fake example", self.defaults())]
