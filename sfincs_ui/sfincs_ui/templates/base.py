"""A template answers the spec's five questions (section 1): settings schema,
build command and inp overrides, validation, geometry, export, plus its
example projects."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from sfincs_ui.config import Config
from sfincs_ui.exceptions import TemplateError

Kind = Literal["int", "float", "choice", "bool"]


@dataclass(frozen=True)
class SettingField:
    key: str
    label: str
    kind: Kind
    default: Any
    minimum: float | None = None
    maximum: float | None = None
    choices: tuple | None = None
    explanation: str = ""
    group: str = "Model"

    def coerce(self, raw: Any) -> Any:
        try:
            if self.kind == "bool":
                if isinstance(raw, str):
                    return raw.strip().lower() in ("1", "true", "yes", "on")
                return bool(raw)
            if self.kind == "int":
                value: Any = int(float(raw))
            elif self.kind == "float":
                value = float(raw)
            else:  # choice: compare as the type of the first choice
                value = type(self.choices[0])(raw)
        except (TypeError, ValueError) as exc:
            raise TemplateError(f"{self.key}: not a valid {self.kind}") from exc
        if self.kind == "choice" and value not in self.choices:
            raise TemplateError(f"{self.key}: must be one of {', '.join(map(str, self.choices))}")
        if self.minimum is not None and value < self.minimum:
            raise TemplateError(f"{self.key}: must be at least {self.minimum}")
        if self.maximum is not None and value > self.maximum:
            raise TemplateError(f"{self.key}: must be at most {self.maximum}")
        return value


class Template(ABC):
    key: str
    title: str
    description: str
    has_validation: bool = False
    has_export: bool = False

    @abstractmethod
    def fields(self) -> list[SettingField]: ...

    def defaults(self) -> dict:
        return {f.key: f.default for f in self.fields()}

    def validate(self, settings: dict) -> dict:
        out = {}
        for f in self.fields():
            out[f.key] = f.coerce(settings.get(f.key, f.default))
        return out

    @abstractmethod
    def build_command(self, run_dir: Path, settings: dict, config: Config) -> list[str]: ...

    def stage_cwd(self, stage: str, run_dir: Path, config: Config) -> Path:
        return run_dir

    @abstractmethod
    def inp_overrides(self, settings: dict) -> dict[str, str]: ...

    @abstractmethod
    def model_files(self) -> tuple[str, ...]: ...

    def validate_command(self, run_dir: Path, settings: dict, config: Config) -> list[str] | None:
        return None

    def export_command(self, run_dir: Path, settings: dict, config: Config) -> list[str] | None:
        return None

    def default_threads(self, settings: dict) -> int:
        return 1

    def geometry_layers(self, project_dir: Path, settings: dict) -> list[dict]:
        return []

    def example_projects(self) -> list[tuple[str, dict]]:
        return []
