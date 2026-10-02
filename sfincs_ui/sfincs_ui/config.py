"""Configuration from SFINCS_UI_* environment variables.

Environment values are install-time ceilings and defaults. The ``settings``
table (services/settings_service.py) holds admin-chosen values validated at
or below these ceilings. MIN_FREE_GB and UPLOAD_MAX_MB are env-only.
"""

from __future__ import annotations

import shlex
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# sfincs_ui/sfincs_ui/config.py -> parents[2] is the sfincs checkout.
REPO_ROOT = Path(__file__).resolve().parents[2]


class Config(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="SFINCS_UI_", extra="ignore")

    workspace: Path = Field(description="Directory that holds every project and run the UI creates")
    database_url: str | None = Field(default=None, description="SQLAlchemy URL; default sqlite under the workspace")
    sfincs_bin: Path = Field(default=REPO_ROOT / "sfincs-linux" / "bin" / "sfincs")
    model_python: str = Field(
        default="micromamba -r /opt/micromamba run -n hydromt-sfincs python",
        description="Command prefix that runs python in the model env (not an interpreter path)",
    )
    curonian_dir: Path = Field(default=REPO_ROOT / "curonian")
    url_prefix: str = Field(default="", description="Public mount path, e.g. /sfincs-ui; empty at the root")
    port: int = Field(default=8840, ge=1024, le=65535)
    max_simulations: int = Field(default=1, ge=1)
    max_threads: int = Field(default=8, ge=1)
    min_free_gb: int = Field(default=100, ge=0)
    retention_days: int = Field(default=60, ge=1)
    quota_gb: int = Field(default=20, ge=1)
    upload_max_mb: int = Field(default=500, ge=1)
    session_ttl_hours: int = Field(default=24, ge=1)
    secure_cookies: bool = Field(default=True, description="nginx terminates TLS; set false only for plain-http dev")
    trusted_proxies: list[str] = Field(default=["127.0.0.0/8"])

    @field_validator("url_prefix")
    @classmethod
    def _prefix_shape(cls, v: str) -> str:
        if v == "":
            return v
        if not v.startswith("/") or v.endswith("/"):
            raise ValueError("url_prefix must start with '/' and not end with one, e.g. /sfincs-ui")
        return v

    @property
    def repo_root(self) -> Path:
        return REPO_ROOT

    @property
    def database_url_resolved(self) -> str:
        if self.database_url:
            return self.database_url
        return f"sqlite:///{self.workspace / 'sfincs_ui.db'}"

    @property
    def model_python_argv(self) -> list[str]:
        return shlex.split(self.model_python)


_config: Config | None = None


def get_config() -> Config:
    global _config
    if _config is None:
        _config = Config()
    return _config


def set_config(config: Config) -> None:
    global _config
    _config = config


def reset_config() -> None:
    global _config
    _config = None
