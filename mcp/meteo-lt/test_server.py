"""Tests for the pure logic in the meteo.lt MCP server (no network)."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import server as s


# --- month enumeration: the historical endpoint is one request per YYYY-MM ----

def test_months_between_spans_partial_start_and_end_months():
    assert s.months_between("2013-11-15", "2014-02-03") == ["2013-11", "2013-12", "2014-01", "2014-02"]


def test_months_between_single_month():
    assert s.months_between("2013-12-01", "2013-12-31") == ["2013-12"]


def test_months_between_rejects_reversed_range():
    with pytest.raises(ValueError, match="before"):
        s.months_between("2014-01-01", "2013-12-01")


# --- clipping: a month request returns the whole month, caller wants the range -

def test_clip_to_range_drops_days_outside_the_requested_window():
    rows = [{"observationDateUtc": d, "waterLevel": 100} for d in
            ("2013-11-29", "2013-11-30", "2013-12-01", "2013-12-02")]
    kept = s.clip_to_range(rows, "2013-11-30", "2013-12-01", key="observationDateUtc")
    assert [r["observationDateUtc"] for r in kept] == ["2013-11-30", "2013-12-01"]


def test_clip_to_range_handles_hourly_timestamps():
    rows = [{"observationTimeUtc": "2026-09-14 23:00:00"}, {"observationTimeUtc": "2026-09-15 01:00:00"}]
    kept = s.clip_to_range(rows, "2026-09-15", "2026-09-15", key="observationTimeUtc")
    assert len(kept) == 1


# --- CSV shaping ------------------------------------------------------------

def test_rows_to_csv_uses_union_of_keys_and_stable_column_order(tmp_path):
    rows = [{"observationDateUtc": "2013-12-01", "waterLevel": 193},
            {"observationDateUtc": "2013-12-02", "waterLevel": 212, "waterDischarge": 548}]
    out = tmp_path / "x.csv"
    n = s.rows_to_csv(rows, out)
    lines = out.read_text().strip().splitlines()
    assert n == 2
    assert lines[0] == "observationDateUtc,waterLevel,waterDischarge"
    assert lines[1] == "2013-12-01,193,"          # missing key -> empty, not dropped
    assert lines[2] == "2013-12-02,212,548"


def test_rows_to_csv_refuses_to_write_nothing(tmp_path):
    with pytest.raises(ValueError, match="no observations"):
        s.rows_to_csv([], tmp_path / "empty.csv")


# --- rate limiting ----------------------------------------------------------

def test_rate_limiter_allows_a_burst_then_forces_a_wait():
    slept = []
    rl = s.RateLimiter(per_minute=6, sleep=slept.append, now=iter([0.0] * 20).__next__)
    for _ in range(6):
        rl.acquire()
    assert slept == [], "first 6 calls in the window must not sleep"
    rl.acquire()
    assert slept and slept[0] > 0, "7th call in the same window must wait"


def test_rate_limiter_is_well_under_the_published_ceiling():
    """meteo.lt allows 180/min and blocks IPs silently; stay conservative."""
    assert s.RATE_LIMIT_PER_MINUTE <= 60


def test_rows_to_csv_writes_unix_line_endings(tmp_path):
    """csv.writer defaults to lineterminator='\\r\\n', which on Linux gives every
    exported file CRLF endings — invisible until a tool that anchors on '$'
    (sed, grep -x, a diff) silently stops matching."""
    out = tmp_path / "le.csv"
    s.rows_to_csv([{"a": 1, "b": 2}, {"a": 3, "b": 4}], out)
    raw = out.read_bytes()
    assert b"\r\n" not in raw, "CSV written with CRLF line endings"
    assert raw.count(b"\n") == 3, "expected header + 2 data rows, each LF-terminated"
