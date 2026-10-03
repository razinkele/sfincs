"""A template answers the spec's five questions (section 1): settings schema,
build command and inp overrides, validation, geometry, export, plus its
example projects."""

from __future__ import annotations

import math
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from sfincs_ui.config import Config
from sfincs_ui.exceptions import TemplateError

Kind = Literal["int", "float", "choice", "bool", "datetime"]
_DATETIME_FORMATS = ("%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S")


@dataclass(frozen=True)
class SettingField:
    _TRUE = ("1", "true", "yes", "on")
    _FALSE = ("0", "false", "no", "off")

    key: str
    label: str
    kind: Kind
    default: Any
    minimum: float | None = None
    maximum: float | None = None
    choices: tuple | None = None
    explanation: str = ""
    group: str = "Model"
    optional: bool = False  # None / empty input means "use the model's value"; the key is then omitted from overrides

    def coerce(self, raw: Any) -> Any:
        if raw is None or (isinstance(raw, str) and not raw.strip()):
            if self.optional:
                return None
            raise TemplateError(f"{self.key}: a value is required")
        if self.kind == "datetime":
            text = str(raw).strip()
            for fmt in _DATETIME_FORMATS:
                try:
                    return datetime.strptime(text, fmt).strftime("%Y-%m-%d %H:%M")
                except ValueError:
                    continue
            raise TemplateError(f"{self.key}: expected a date and time like 2013-12-09 06:00")
        try:
            if self.kind == "bool":
                if isinstance(raw, bool):
                    return raw
                if isinstance(raw, (int, float)) and raw in (0, 1):
                    return bool(raw)
                text = str(raw).strip().lower()
                if text in self._TRUE:
                    return True
                if text in self._FALSE:
                    return False
                raise TemplateError(f"{self.key}: expected true or false")
            if self.kind == "int":
                number = float(raw)
                if not math.isfinite(number) or number != int(number):
                    raise TemplateError(f"{self.key}: must be a whole number")
                value: Any = int(number)
            elif self.kind == "float":
                value = float(raw)
                if not math.isfinite(value):
                    raise TemplateError(f"{self.key}: must be a finite number")
            else:  # choice: compare as the type of the first choice
                value = type(self.choices[0])(raw)
        except TemplateError:
            raise
        except (TypeError, ValueError, OverflowError) as exc:
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

    def skip_reasons(self, settings: dict) -> dict[str, str]:
        """stage -> why it is skipped for these settings (recorded in the run summary)."""
        return {}

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
