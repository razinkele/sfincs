# /// script
# requires-python = ">=3.11"
# dependencies = ["fastmcp>=4.0,<5", "httpx>=0.27"]
# ///
"""MCP server for api.meteo.lt — the Lithuanian Hydrometeorological Service open API.

Forecasts and meteorological observations (10 years) plus hydrological stations
(hourly for the last 30 days; daily back to 2000).

Data: (c) Lithuanian Hydrometeorological Service under the Ministry of Environment
(LHMT), licensed CC BY-SA 4.0. Attribution is a condition of access -- the licence
notice travels with every response this server returns.
"""
from __future__ import annotations

import csv
import time
from collections import deque
from datetime import date, datetime
from pathlib import Path
from typing import Any, Callable, Iterable, Iterator

import httpx

BASE = "https://api.meteo.lt/v1"
USER_AGENT = "meteo-lt-mcp/0.1 (personal research use; +https://api.meteo.lt/)"
ATTRIBUTION = ("Data (c) Lithuanian Hydrometeorological Service (LHMT), CC BY-SA 4.0. "
               "Attribution is required when this data is republished.")

# api.meteo.lt permits 180 requests/minute and 20,000/day per IP, and states that
# exceeding the daily ceiling can get the IP blocked without notice. We sit at a
# third of the per-minute allowance: a bulk range fetch is never worth a block.
RATE_LIMIT_PER_MINUTE = 60
MAX_RANGE_MONTHS = 360           # 30 years; refuses absurd pulls rather than hammering the API


# --------------------------------------------------------------------------- #
# Pure helpers (unit-tested without network)
# --------------------------------------------------------------------------- #

def months_between(start: str, end: str) -> list[str]:
    """Every YYYY-MM the [start, end] date range touches, inclusive.

    The historical hydro endpoint is addressed one month at a time, so a range
    request becomes one call per month returned here.
    """
    s, e = date.fromisoformat(start), date.fromisoformat(end)
    if e < s:
        raise ValueError(f"end date {end} is before start date {start}")
    out, y, m = [], s.year, s.month
    while (y, m) <= (e.year, e.month):
        out.append(f"{y:04d}-{m:02d}")
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
        if len(out) > MAX_RANGE_MONTHS:
            raise ValueError(f"range spans more than {MAX_RANGE_MONTHS} months; narrow it")
    return out


def clip_to_range(rows: Iterable[dict], start: str, end: str, key: str) -> list[dict]:
    """Keep only rows whose timestamp falls inside [start, end] by calendar date.

    A month request returns the whole month, so the first and last month of a
    range usually overshoot. Handles both date-only and 'YYYY-MM-DD HH:MM:SS'.
    """
    return [r for r in rows if r.get(key) and start <= str(r[key])[:10] <= end]


def rows_to_csv(rows: list[dict], out_path: str | Path) -> int:
    """Write `rows` to CSV using the union of their keys, in first-seen order."""
    if not rows:
        raise ValueError("no observations to write -- the station returned nothing for that range")
    fields: list[str] = []
    for r in rows:
        for k in r:
            if k not in fields:
                fields.append(k)
    out = Path(out_path).expanduser()
    out.parent.mkdir(parents=True, exist_ok=True)
    # lineterminator="\n": csv defaults to "\r\n", which would give every file
    # this tool writes CRLF endings on Linux — invisible until sed, grep -x or a
    # diff anchored on "$" quietly stops matching.
    with out.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fields, lineterminator="\n")
        w.writeheader()
        w.writerows(rows)
    return len(rows)


class RateLimiter:
    """Sliding-window limiter. `sleep`/`now` are injectable so tests need no clock."""

    def __init__(self, per_minute: int = RATE_LIMIT_PER_MINUTE,
                 sleep: Callable[[float], Any] = time.sleep,
                 now: Callable[[], float] = time.monotonic) -> None:
        self.per_minute = per_minute
        self._sleep, self._now = sleep, now
        self._calls: deque[float] = deque()

    def acquire(self) -> None:
        t = self._now()
        while self._calls and t - self._calls[0] >= 60.0:
            self._calls.popleft()
        if len(self._calls) >= self.per_minute:
            self._sleep(60.0 - (t - self._calls[0]))
            self._calls.popleft()
        self._calls.append(t)


_limiter = RateLimiter()


def _get(path: str) -> Any:
    """GET one API path, rate-limited, raising a readable error on failure."""
    _limiter.acquire()
    url = f"{BASE}/{path.lstrip('/')}"
    try:
        r = httpx.get(url, headers={"User-Agent": USER_AGENT}, timeout=30.0)
    except httpx.RequestError as exc:
        raise RuntimeError(f"could not reach {url}: {exc}") from exc
    if r.status_code == 404:
        raise RuntimeError(f"not found: {url} -- check the station or place code")
    if r.status_code == 429:
        raise RuntimeError("api.meteo.lt rate limit hit; back off before retrying")
    r.raise_for_status()
    return r.json()


def _wrap(payload: Any, **extra: Any) -> dict:
    """Attach the licence notice the CC BY-SA terms require to every result."""
    return {"data": payload, "attribution": ATTRIBUTION, **extra}


# --------------------------------------------------------------------------- #
# Tools
# --------------------------------------------------------------------------- #

from fastmcp import FastMCP  # noqa: E402  (after helpers so tests can import them cheaply)

mcp = FastMCP(
    name="meteo-lt",
    instructions=(
        "Lithuanian weather and hydrology from api.meteo.lt (LHMT).\n"
        "Coverage differs sharply by endpoint and you should check it before promising data:\n"
        "  - forecasts: current only\n"
        "  - meteorological observations: last 10 years, hourly\n"
        "  - hydro 'measured': last 30 days, HOURLY (waterLevel, waterTemperature)\n"
        "  - hydro 'historical': since 2000, DAILY (waterLevel, waterDischarge)\n"
        "Per-station coverage varies and some stations have none -- call get_data_range first.\n"
        f"{ATTRIBUTION}"
    ),
)


@mcp.tool
def list_places(name_contains: str | None = None) -> dict:
    """List forecast locations, optionally filtered by a case-insensitive name substring."""
    places = _get("places")
    if name_contains:
        q = name_contains.casefold()
        places = [p for p in places
                  if q in p["name"].casefold() or q in p["code"].casefold()]
    return _wrap(places, count=len(places))


@mcp.tool
def get_forecast(place_code: str, forecast_type: str = "long-term") -> dict:
    """Weather forecast for a place. Use list_places to find a place_code (e.g. 'klaipeda')."""
    return _wrap(_get(f"places/{place_code}/forecasts/{forecast_type}"))


@mcp.tool
def list_stations(name_contains: str | None = None) -> dict:
    """List meteorological observation stations (AMS), optionally filtered by name."""
    stations = _get("stations")
    if name_contains:
        q = name_contains.casefold()
        stations = [s for s in stations
                    if q in s["name"].casefold() or q in s["code"].casefold()]
    return _wrap(stations, count=len(stations))


@mcp.tool
def get_observations(station_code: str, obs_date: str = "latest") -> dict:
    """Hourly meteorological observations for one station on one date.

    obs_date is YYYY-MM-DD, or 'latest'. Available for the last 10 years.
    Fields include airTemperature, windSpeed, windGust, windDirection,
    seaLevelPressure, relativeHumidity, precipitation, cloudCover.
    """
    return _wrap(_get(f"stations/{station_code}/observations/{obs_date}"))


@mcp.tool
def list_hydro_stations(name_contains: str | None = None, water_body: str | None = None) -> dict:
    """List hydrological stations (VMS), filtered by station name and/or water body.

    water_body matches e.g. 'Nemunas', 'Kursiu marios' (the Curonian Lagoon),
    'Baltijos jura' (the Baltic), 'Atmata', 'Minija'.
    """
    stations = _get("hydro-stations")
    if name_contains:
        q = name_contains.casefold()
        stations = [s for s in stations if q in s["name"].casefold() or q in s["code"].casefold()]
    if water_body:
        q = water_body.casefold()
        stations = [s for s in stations if q in (s.get("waterBody") or "").casefold()]
    return _wrap(stations, count=len(stations))


@mcp.tool
def get_data_range(station_code: str, observation_type: str = "historical") -> dict:
    """How far back one hydro station's data actually goes. Call this before a range fetch.

    observation_type is 'historical' (daily, since 2000) or 'measured' (hourly, 30 days).
    A null start/end means the station has no data of that type at all -- several
    stations, including the Klaipeda seaport gauge, return null for 'historical'.
    """
    return _wrap(_get(f"hydro-stations/{station_code}/observations/{observation_type}"))


@mcp.tool
def get_hydro_observations(station_code: str, observation_type: str = "historical",
                           obs_date: str = "latest") -> dict:
    """Hydrological observations for one station.

    observation_type 'historical' gives DAILY waterLevel (cm) and waterDischarge
    (m3/s) since 2000; obs_date may be YYYY-MM (a whole month), YYYY-MM-DD, or 'latest'.
    observation_type 'measured' gives HOURLY waterLevel and waterTemperature, last
    30 days only; obs_date is YYYY-MM-DD or 'latest'.
    """
    return _wrap(_get(f"hydro-stations/{station_code}/observations/{observation_type}/{obs_date}"))


@mcp.tool
def fetch_hydro_range(station_code: str, start_date: str, end_date: str,
                      out_path: str, observation_type: str = "historical") -> dict:
    """Fetch a date range of hydrological observations and write it to a CSV file.

    Pages the API one month at a time (that is how the historical endpoint is
    addressed), throttled to stay well inside the published rate limit, then clips
    to exactly [start_date, end_date] and writes a CSV to out_path.

    Dates are YYYY-MM-DD. Returns the row count, the file path and the observed
    date span, so a short return means the station's coverage is short -- check
    get_data_range rather than assuming the fetch failed.
    """
    if observation_type not in ("historical", "measured"):
        raise ValueError("observation_type must be 'historical' or 'measured'")
    months = months_between(start_date, end_date)
    key = "observationDateUtc" if observation_type == "historical" else "observationTimeUtc"

    rows: list[dict] = []
    for ym in months:
        payload = _get(f"hydro-stations/{station_code}/observations/{observation_type}/{ym}")
        rows.extend(payload.get("observations", []))
    rows = clip_to_range(rows, start_date, end_date, key=key)
    rows.sort(key=lambda r: str(r.get(key, "")))

    n = rows_to_csv(rows, out_path)
    span = (str(rows[0][key])[:10], str(rows[-1][key])[:10])
    return _wrap(
        {"rows_written": n, "path": str(Path(out_path).expanduser()),
         "requests_made": len(months), "covered": {"first": span[0], "last": span[1]},
         "columns": list(rows[0].keys())},
        note=("Row count reflects the station's actual coverage, which is often narrower "
              "than the range requested; get_data_range reports the true extent."),
    )


if __name__ == "__main__":
    mcp.run()
