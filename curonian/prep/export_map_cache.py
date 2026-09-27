"""Per-run cache for the viewer's Map tab.

    python -m prep.export_map_cache --run april_2013_gridwind

Writes runs/<run>/{zs_series.npy, map_baseline.npy, map_warp.npz,
map_meta.json} (git-ignored; see app/map_core.export_cache) and
results/<run>/gauge_obs.csv (committed), the gauge readings validate.py scores,
so the viewer never reads curonian_db.gpkg. The event is the longest event name
the run name starts with -- validate.py takes --event separately and defaults to
Xaver, which would give an April run Xaver's gauge window.
Spec: docs/superpowers/specs/2026-09-27-sfincs-map-viewer-design.md
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

import common

if str(common.REPO / "app") not in sys.path:
    sys.path.insert(0, str(common.REPO / "app"))
import map_core as mc  # noqa: E402  -- shared with the viewer


def event_for_run(run: str) -> common.Event:
    matches = [name for name in common.EVENTS if run == name or run.startswith(name + "_")]
    if not matches:
        raise SystemExit(f"no event matches run {run!r}; known events: {', '.join(sorted(common.EVENTS))}")
    return common.event(max(matches, key=len))


def gauge_obs(event: common.Event) -> pd.DataFrame:
    import validate
    from prep.make_forcing import load_gauge_levels
    rows = [(site, t, float(v))
            for site in validate.GAUGES
            for t, v in load_gauge_levels(site, event).items()]
    return pd.DataFrame(rows, columns=["site", "time", "level_m"])


def write_gauge_obs(event: common.Event, results_dir: Path) -> Path:
    results_dir.mkdir(parents=True, exist_ok=True)
    out = results_dir / "gauge_obs.csv"
    frame = gauge_obs(event)
    mc.atomic_save(out, lambda p: frame.to_csv(p, index=False, date_format="%Y-%m-%d %H:%M:%S"))
    return out


def main(run: str, runs_dir: Path = common.RUNS, results_root: Path = common.ROOT / "results") -> dict:
    event = event_for_run(run)
    meta = mc.export_cache(runs_dir / run)
    write_gauge_obs(event, results_root / run)
    print(f"{run} ({event.name}): {meta['n_active']} cells x {len(meta['hours'])} hours, "
          f"ranges {meta['ranges']}")
    return meta


def parse_args(argv=None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--run", required=True, help="runs/<name> to export")
    return p.parse_args(argv)


if __name__ == "__main__":
    main(parse_args().run)
