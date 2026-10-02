"""Admin-chosen queue policy, retention and quota, bounded by the environment.

Precedence (spec section 5): SFINCS_UI_* values are install-time ceilings and
defaults; the ``settings`` table holds admin-chosen values validated at or
below the ceilings; readers take the table value when present, else the env
value. A stored value above a later-lowered ceiling reads as the ceiling.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from sfincs_ui.config import Config
from sfincs_ui.models.setting import Setting

POLICY_KEYS = ("max_simulations", "max_threads", "retention_days", "quota_gb")

_META = {
    "max_simulations": ("Simulations at once", "How many SFINCS solvers may run concurrently."),
    "max_threads": ("Threads per run", "OpenMP threads a user may request for one simulation."),
    "retention_days": ("Retention (days)", "Unpinned run directories older than this are deleted."),
    "quota_gb": ("Quota per user (GB)", "Total size of a user's run directories."),
}


@dataclass(frozen=True)
class PolicyRow:
    key: str
    label: str
    value: int
    ceiling: int
    explanation: str


class SettingsService:
    def __init__(self, config: Config, session_factory=None):
        if session_factory is None:
            from sfincs_ui.db.base import get_session_factory

            session_factory = get_session_factory()
        self._config = config
        self._session_factory = session_factory

    def ceiling(self, key: str) -> int:
        if key not in POLICY_KEYS:
            raise KeyError(key)
        return int(getattr(self._config, key))

    def _stored(self) -> dict[str, int]:
        session = self._session_factory()
        try:
            rows = session.query(Setting).filter(Setting.key.in_(POLICY_KEYS)).all()
            return {r.key: int(json.loads(r.value_json)) for r in rows}
        finally:
            session.close()

    def get(self, key: str) -> int:
        ceiling = self.ceiling(key)
        stored = self._stored().get(key)
        if stored is None:
            return ceiling
        return min(stored, ceiling)

    def effective(self) -> dict[str, int]:
        stored = self._stored()
        return {k: min(stored.get(k, self.ceiling(k)), self.ceiling(k)) for k in POLICY_KEYS}

    def rows(self) -> list[PolicyRow]:
        eff = self.effective()
        return [
            PolicyRow(key=k, label=_META[k][0], value=eff[k], ceiling=self.ceiling(k), explanation=_META[k][1])
            for k in POLICY_KEYS
        ]

    def validate(self, key: str, value) -> int:
        """Convert and bound-check one value without saving it (ValueError/TypeError/KeyError)."""
        ceiling = self.ceiling(key)
        value = int(value)
        if value < 1:
            raise ValueError(f"{_META[key][0]} must be at least 1")
        if value > ceiling:
            raise ValueError(f"{_META[key][0]} may not exceed the server ceiling of {ceiling}")
        return value

    def set(self, key: str, value: int) -> int:
        value = self.validate(key, value)
        session = self._session_factory()
        try:
            row = session.get(Setting, key)
            if row is None:
                session.add(Setting(key=key, value_json=json.dumps(value)))
            else:
                row.value_json = json.dumps(value)
            session.commit()
            return value
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()
