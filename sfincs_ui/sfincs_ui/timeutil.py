"""Clock helper shared by services, models and tests."""

from __future__ import annotations

from datetime import datetime, timezone


def utcnow() -> datetime:
    """Current UTC time as a naive datetime.

    The DateTime columns are filled by ``server_default=func.now()`` (SQLite
    CURRENT_TIMESTAMP, UTC, no tzinfo), so in-memory timestamps must be naive
    UTC too; comparing an aware value against them raises.
    """
    return datetime.now(timezone.utc).replace(tzinfo=None)
