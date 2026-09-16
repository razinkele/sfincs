"""Score a hindcast event's run against the gauges and draw the delta flood extent."""
from __future__ import annotations

import argparse
import shutil
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import netCDF4 as nc
import numpy as np
import pandas as pd
import rasterio
from rasterio.windows import from_bounds

import common
from prep.make_forcing import load_gauge_levels

GAUGES = ("Klaipeda", "Nida", "Vente", "Uostadvaris")

# Deliberately narrower than make_geometries.DELTA_BOX (325_000, 6_100_000, 370_000,
# 6_150_000): this validation window frames the Rusne/Silute delta itself, not the wider
# Russian-lowland margin DELTA_BOX also covers, so the flood-extent figure and the C4
# uplands check below stay focused on the area the success criteria actually talk about.
VALIDATION_WINDOW = (325_000, 6_105_000, 360_000, 6_145_000)

STORM_WINDOW = (pd.Timestamp("2013-12-05 00:00"), pd.Timestamp("2013-12-09 00:00"))


def station_names(run_dir: Path) -> list[str]:
    """Station order of sfincs.obs; names from its third column, else from inputs/stations.geojson."""
    lines = [l.split() for l in (run_dir / "sfincs.obs").read_text().splitlines() if l.strip()]
    names = [l[2].strip("\"'") for l in lines if len(l) >= 3]
    if len(names) != len(lines):
        import geopandas as gpd
        names = list(gpd.read_file(common.INPUTS / "stations.geojson")["name"])
        assert len(names) == len(lines), "obs file and stations.geojson disagree on station count"
    return names


def load_his(run_dir: Path = common.RUN_XAVER) -> pd.DataFrame:
    with nc.Dataset(run_dir / "sfincs_his.nc") as d:
        t = pd.to_datetime([str(x) for x in nc.num2date(d["time"][:], d["time"].units, only_use_cftime_datetimes=False)])
        zs = np.ma.filled(d["point_zs"][:], np.nan)
    names = station_names(run_dir)
    assert zs.shape[1] == len(names), (zs.shape, names)
    return pd.DataFrame(zs, index=t, columns=names)


PEAK_TIE_M = 0.001  # peaks within 1 mm of the window max are numerically the same peak (floating-point aliasing)


def skill(model: pd.Series, obs: pd.Series) -> dict:
    m = model.reindex(obs.index, method="nearest", tolerance=pd.Timedelta("30min"))
    ok = m.notna() & obs.notna()
    m, o = m[ok], obs[ok]
    err = m - o
    win = model.loc[obs.index.min():obs.index.max()]
    peak_m = float(win.max())
    # A plain win.idxmax() picks an arbitrary member of a near-exact tie between two peaks of
    # comparable height (floating-point aliasing -- see test_skill_on_synthetic_series's history).
    # Among times within PEAK_TIE_M of the window max, report the *median* time (the plateau
    # centre) rather than whichever is closest to the observation: the model's reported peak
    # time must not be a function of the observed peak time, or peak_dt_h could only ever be
    # pulled toward zero by construction.
    tied = win.index[win >= peak_m - PEAK_TIE_M]
    peak_time = tied[(len(tied) - 1) // 2]     # lower median: for an even count, the earlier of the two middle times
    return {
        "bias": float(err.mean()), "rmse": float(np.sqrt((err ** 2).mean())),
        "r": float(np.corrcoef(m, o)[0, 1]) if len(o) > 2 else np.nan,
        "peak_err_m": peak_m - float(o.max()),
        "peak_time": peak_time,
        "peak_dt_h": float((peak_time - o.idxmax()) / pd.Timedelta("1h")),
        "n": int(ok.sum()),
    }


def _flood_arrays(run_dir: Path, window):
    """Ground elevation, flood depth and a land/flooded mask on the fine grid inside
    `window`, with zsmax mapped onto it from the (coarse) model grid. Extracted from
    flood_map() so criteria()'s C4 uplands check can reuse the same numbers."""
    with nc.Dataset(run_dir / "sfincs_map.nc") as d:
        zsmax = np.ma.filled(d["zsmax"][:], np.nan)
        zsmax = zsmax[-1] if zsmax.ndim == 3 else zsmax
        x = d["x"][:]; y = d["y"][:]
        x = x[0, :] if x.ndim == 2 else x; y = y[:, 0] if y.ndim == 2 else y
    assert np.all(np.diff(x) > 0), "x from sfincs_map.nc must be ascending"
    assert np.all(np.diff(y) > 0), "y from sfincs_map.nc must be ascending"
    dep_tif = run_dir / "subgrid" / "dep_subgrid.tif"
    if dep_tif.exists():
        with rasterio.open(dep_tif) as src:
            w, s, e, n = window
            # dep_subgrid.tif here is stored south-up (transform.e > 0, row 0 = south edge);
            # rasterio.windows.from_bounds requires (bottom-top)/transform.e >= 0, so on a
            # south-up raster the north/south bound arguments must be swapped to pass its
            # consistency check (verified against rasterio's from_bounds source).
            win = (from_bounds(w, s, e, n, transform=src.transform) if src.transform.e < 0
                   else from_bounds(w, n, e, s, transform=src.transform))
            ground = src.read(1, window=win, masked=True).filled(np.nan)
            tr = src.window_transform(win)
            gx = tr.c + tr.a * (np.arange(ground.shape[1]) + 0.5)
            gy = tr.f + tr.e * (np.arange(ground.shape[0]) + 0.5)
            if tr.e > 0:      # normalise south-up storage to north-up (row 0 = north) for correct map orientation
                ground = ground[::-1, :]
                gy = gy[::-1]
        # Map each fine pixel centre to the *nearest* 100 m model-cell centre, not the
        # floor cell: shifting by half a cell before searchsorted means a pixel past the
        # midpoint between two cell centres picks up the far one, matching
        # np.abs(x - gx).argmin() semantics but in O(log n) (grid is uniform and ascending,
        # asserted above).
        dx = x[1] - x[0]; dy = y[1] - y[0]
        ix = np.clip(np.searchsorted(x, gx + dx / 2) - 1, 0, len(x) - 1)
        iy = np.clip(np.searchsorted(y, gy + dy / 2) - 1, 0, len(y) - 1)
        zs_fine = zsmax[np.ix_(iy, ix)]
        depth = zs_fine - ground
        cell_km2 = abs(tr.a * tr.e) / 1e6
    else:
        sel_x = (x >= window[0]) & (x <= window[2]); sel_y = (y >= window[1]) & (y <= window[3])
        with nc.Dataset(run_dir / "sfincs_map.nc") as d:
            zb = np.ma.filled(d["zb"][:], np.nan)
        depth = (zsmax - zb)[np.ix_(sel_y, sel_x)]; gx, gy = x[sel_x], y[sel_y]
        ground = zb[np.ix_(sel_y, sel_x)]; cell_km2 = 0.01
        if len(gy) > 1 and gy[0] < gy[-1]:  # y ascending with row index (south-up storage): normalise to north-up
            depth = depth[::-1, :]; ground = ground[::-1, :]; gy = gy[::-1]
    flooded = np.isfinite(depth) & (depth > 0.05) & (ground > 0.0)      # land only
    return ground, flooded, depth, gx, gy, cell_km2


def flood_map(run_dir: Path = common.RUN_XAVER, out_png: Path | None = None,
              window=VALIDATION_WINDOW, event: common.Event = common.EVENTS["xaver_2013"]) -> float:
    ground, flooded, depth, gx, gy, cell_km2 = _flood_arrays(run_dir, window)
    area_km2 = float(flooded.sum() * cell_km2)
    if out_png:
        fig, ax = plt.subplots(figsize=(9, 8))
        ax.imshow(np.where(ground > 0, ground, np.nan), extent=[gx[0], gx[-1], gy[-1], gy[0]], cmap="Greys_r", vmin=-2, vmax=8)
        im = ax.imshow(np.where(flooded, depth, np.nan), extent=[gx[0], gx[-1], gy[-1], gy[0]], cmap="Blues", vmin=0, vmax=2)
        fig.colorbar(im, ax=ax, label="max flood depth on land [m]")
        ax.set_title(f"{event.title}: flooded land in the delta window = {area_km2:.1f} km²")
        fig.savefig(out_png, dpi=150); plt.close(fig)
    return area_km2


def _fmt_dt(ts: pd.Timestamp) -> str:
    return ts.strftime("%Y-%m-%d %H:%M")


def _window_label(win) -> str:
    return f"{_fmt_dt(win[0])} to {_fmt_dt(win[1])}"


def c4_verdict(frac_pct: float, n_upland_px: int) -> str:
    """Verdict for C4 given the flooded fraction and how many upland pixels there were.

    The <1 % rule is unambiguous whenever the window actually contains land above 3 m.
    When it contains none, `frac_pct` is 0/0 = NaN and `NaN < 1.0` is False, so the
    criterion currently reports "not met" -- reading as a model failure when in fact
    nothing was measured. The delta window always has uplands, so this is unreachable
    today; it is reachable for any other window someone passes in.

    Ruling: report "n/a". A criterion with nothing to measure is neither passed nor
    failed, and criteria() already carries a non-pass/fail verdict ("info"), so the
    vocabulary stretches to it without a new concept.
    """
    if n_upland_px == 0:
        return "n/a"
    return "met" if frac_pct < 1.0 else "not met"


def xaver_criteria(his: pd.DataFrame, obs_by_site: dict, run_dir: Path = common.RUN_XAVER,
                    window=VALIDATION_WINDOW) -> list[dict]:
    """Spec section 9 success criteria, each as {name, window, value, threshold, verdict}."""
    out = []

    # C1: Uostadvaris peak on 6 Dec, judged over the storm window only.
    obs_u = obs_by_site["Uostadvaris"]
    s1 = skill(his["Uostadvaris"], obs_u.loc[STORM_WINDOW[0]:STORM_WINDOW[1]])
    c1_ok = abs(s1["peak_err_m"]) <= 0.15 and abs(s1["peak_dt_h"]) <= 6
    out.append({
        "name": "C1 Uostadvaris peak", "window": _window_label(STORM_WINDOW),
        "value": (f"model peak {s1['peak_time']:%Y-%m-%d %H:%M}, peak err {s1['peak_err_m']:+.2f} m, "
                  f"dt {s1['peak_dt_h']:+.1f} h"),
        "threshold": "peak err within +/-0.15 m and |dt| <= 6 h",
        "verdict": "met" if c1_ok else "not met",
    })

    # C2: Nida 8 Dec rise, comparing the model at the two reading times spanning it.
    t_before, t_peak, gauge_peak = pd.Timestamp("2013-12-07 06:00"), pd.Timestamp("2013-12-08 18:00"), 0.84
    model_before = float(his["Nida"].loc[t_before])
    model_peak = float(his["Nida"].loc[t_peak])
    err2 = model_peak - gauge_peak
    rise_ok = model_peak > model_before
    if not rise_ok or abs(err2) > 0.15:
        verdict2 = "not met"
    elif abs(err2) <= 0.10:
        verdict2 = "met"
    else:
        verdict2 = "met (marginal)"
    out.append({
        "name": "C2 Nida 8 Dec rise", "window": f"{_fmt_dt(t_before)} to {_fmt_dt(t_peak)}",
        "value": (f"model {model_before:.2f} m -> {model_peak:.2f} m vs gauge {gauge_peak:.2f} m, "
                  f"err {err2:+.2f} m, rise {'reproduced' if rise_ok else 'not reproduced'}"),
        "threshold": "err within +/-0.15 m (<=0.10 m for a clean 'met'), rise reproduced in sign",
        "verdict": verdict2,
    })

    # C3: Klaipeda RMSE, storm window (the pass/fail check) vs whole period (context).
    obs_k = obs_by_site["Klaipeda"]
    s3_storm = skill(his["Klaipeda"], obs_k.loc[STORM_WINDOW[0]:STORM_WINDOW[1]])
    s3_full = skill(his["Klaipeda"], obs_k)
    c3_ok = s3_storm["rmse"] <= 0.15
    out.append({
        "name": "C3 Klaipeda RMSE", "window": _window_label(STORM_WINDOW),
        "value": f"storm RMSE {s3_storm['rmse']:.2f} m (whole-period RMSE {s3_full['rmse']:.2f} m)",
        "threshold": "storm-window RMSE <= 0.15 m",
        "verdict": "met" if c3_ok else "not met",
    })

    # C4: no spurious flooding of the Silute uplands.
    ground, flooded, _, _, _, _ = _flood_arrays(run_dir, window)
    uplands = np.isfinite(ground) & (ground > 3.0)
    n_upland_px = int(uplands.sum())
    frac_pct = (100.0 * float(flooded[uplands].sum()) / n_upland_px) if n_upland_px else float("nan")
    out.append({
        "name": "C4 Silute uplands", "window": f"delta window {window}",
        "value": (f"{frac_pct:.2f}% of land with ground > 3 m flooded" if n_upland_px
                  else "no land above 3 m in this window, nothing to measure"),
        "threshold": "< 1 % flooded",
        "verdict": c4_verdict(frac_pct, n_upland_px),
    })

    # Extra context, not itself a spec criterion: the 8 Dec 06:00 error at the two gauges
    # nearest the second (8 Dec) rise, feeding the README finding that the miss is
    # systematic across gauges rather than a Nida-siting artefact.
    t0806 = pd.Timestamp("2013-12-08 06:00")
    for name in ("Uostadvaris", "Nida"):
        obs_val = float(obs_by_site[name].loc[t0806])
        model_val = float(his[name].loc[t0806])
        out.append({
            "name": f"Info: {name} 8 Dec 06:00", "window": _fmt_dt(t0806),
            "value": f"model {model_val:.2f} m vs gauge {obs_val:.2f} m, err {model_val - obs_val:+.2f} m",
            "threshold": "n/a (context only)",
            "verdict": "info",
        })
    return out


# The crest window A3 averages the delta-to-sea head over. Wider than the peak
# itself on purpose: the 24 Apr head is depressed by a one-day 20 cm excursion in
# the Klaipeda gauge, which drags the head (Uostadvaris minus Klaipeda) down to
# 52, 55, 39, 45, 47 cm on 22-26 Apr, so a single instant scores the sea's noise
# rather than the river's head. See spec section 8.
APRIL_CREST = (pd.Timestamp("2013-04-22"), pd.Timestamp("2013-04-26"))
APRIL_FILL_LEVEL = 0.20      # m; the rising limb crosses it at 10-18 cm/day
PLATEAU_TIE_M = 0.05         # daily gauge readings this close are the same crest


def _first_crossing(s: pd.Series, level: float) -> pd.Timestamp:
    above = s[s >= level]
    if above.empty:
        return pd.NaT
    return above.index[0]


def april_criteria(his: pd.DataFrame, obs_by_site: dict, run_dir: Path | None = None,
                    window=VALIDATION_WINDOW) -> list[dict]:
    """Spec section 8 criteria for the April 2013 freshet."""
    out = []
    lo, hi = common.event("april_2013").score_window
    obs_u = obs_by_site["Uostadvaris"].loc[lo:hi]
    obs_k = obs_by_site["Klaipeda"].loc[lo:hi]
    mod_u = his["Uostadvaris"].loc[lo:hi]

    # A1: peak magnitude, observed peak taken from the gauge rather than hardcoded.
    s = skill(mod_u, obs_u)
    out.append({"name": "A1 Uostadvaris peak", "window": _window_label((lo, hi)),
                "value": f"model peak {mod_u.max():.2f} m vs gauge "
                         f"{obs_u.max():.2f} m, err {s['peak_err_m']:+.2f} m",
                "threshold": "peak err within +/-0.15 m",
                "verdict": "met" if abs(s["peak_err_m"]) <= 0.15 else "not met"})

    # A2a: filling rate. The rise is resolved by the daily readings; the crest is not.
    obs_cross = _first_crossing(obs_u, APRIL_FILL_LEVEL)
    mod_cross = _first_crossing(mod_u, APRIL_FILL_LEVEL)
    dt_h = (mod_cross - obs_cross).total_seconds() / 3600 if pd.notna(mod_cross) else float("nan")
    out.append({"name": "A2a filling rate", "window": f"first crossing of +{APRIL_FILL_LEVEL:.2f} m",
                "value": (f"model {mod_cross:%Y-%m-%d %H:%M} vs gauge {obs_cross:%Y-%m-%d %H:%M}, "
                          f"dt {dt_h:+.0f} h" if pd.notna(mod_cross) else "model never reached the level"),
                "threshold": "within +/-24 h of the observed crossing",
                "verdict": "met" if pd.notna(mod_cross) and abs(dt_h) <= 24 else "not met"})

    # A2b: the crest, accepted anywhere in the observed plateau widened by 12 h.
    plateau = obs_u[obs_u >= obs_u.max() - PLATEAU_TIE_M].index
    p0, p1 = plateau.min() - pd.Timedelta("12h"), plateau.max() + pd.Timedelta("12h")
    t_peak = mod_u.idxmax()
    out.append({"name": "A2b crest timing", "window": f"{_fmt_dt(p0)} to {_fmt_dt(p1)}",
                "value": f"model peak {t_peak:%Y-%m-%d %H:%M}; observed plateau "
                         f"{plateau.min():%d %b}-{plateau.max():%d %b}",
                "threshold": "model peak inside the observed plateau +/-12 h",
                "verdict": "met" if p0 <= t_peak <= p1 else "not met"})

    # A3: the head the river holds above the sea, averaged over the crest. Matched
    # on the calendar date (not the exact timestamp) so the 26th's 06:00 reading is
    # included along with 22-25's -- the window is a set of days, not a half-open
    # instant range, and excluding the last day would silently narrow the average
    # the comment above describes.
    stamps = [t for t in obs_u.index if APRIL_CREST[0] <= t.normalize() <= APRIL_CREST[1] and t in obs_k.index]
    obs_head = float(np.mean([obs_u[t] - obs_k[t] for t in stamps]))
    mod_head = float(np.mean([his["Uostadvaris"].loc[t] - his["Klaipeda"].loc[t] for t in stamps]))
    out.append({"name": "A3 delta-to-sea head", "window": _window_label(APRIL_CREST),
                "value": f"model {mod_head:.2f} m vs gauge {obs_head:.2f} m over {len(stamps)} readings, "
                         f"err {mod_head - obs_head:+.2f} m",
                "threshold": "mean head within +/-0.15 m",
                "verdict": "met" if abs(mod_head - obs_head) <= 0.15 else "not met"})

    # A4: the sea must beat the no-skill baseline, not merely sit near the mean.
    s4 = skill(his["Klaipeda"], obs_k)
    sigma = float(obs_k.std(ddof=0))
    out.append({"name": "A4 Klaipeda control", "window": _window_label((lo, hi)),
                "value": f"RMSE {s4['rmse']:.3f} m against an observed sd of {sigma:.3f} m",
                "threshold": "RMSE <= 0.085 m (below the observed sd: a flat series fails)",
                "verdict": "met" if s4["rmse"] <= 0.085 else "not met"})

    # A5: Xaver's C4, same logic including the no-uplands value guard (see
    # c4_verdict's docstring). Whole-run by construction -- dtmaxout gives one
    # zsmax record spanning tstart..tstop, so this cannot be restricted to the
    # scoring window.
    ground, flooded, _, _, _, _ = _flood_arrays(run_dir, window)
    uplands = np.isfinite(ground) & (ground > 3.0)
    n_upland_px = int(uplands.sum())
    frac_pct = (100.0 * float(flooded[uplands].sum()) / n_upland_px) if n_upland_px else float("nan")
    out.append({"name": "A5 Silute uplands", "window": f"whole run, delta window {window}",
                "value": (f"{frac_pct:.2f}% of land with ground > 3 m flooded" if n_upland_px
                          else "no land above 3 m in this window, nothing to measure"),
                "threshold": "< 1 % flooded",
                "verdict": c4_verdict(frac_pct, n_upland_px)})
    return out


# Keyed by event name rather than held on the Event: a function reference on the
# dataclass would make common.py depend on validate.py having been imported, and an
# unset one would silently score April with Xaver's criteria instead of raising.
CRITERIA = {"xaver_2013": xaver_criteria}
CRITERIA["april_2013"] = april_criteria


def criteria(his: pd.DataFrame, obs_by_site: dict, run_dir: Path = common.RUN_XAVER,
             window=VALIDATION_WINDOW, event: common.Event | None = None) -> list[dict]:
    """Dispatch on the event. Defaults to Xaver so the nine existing call sites --
    and the existing verdicts -- are untouched. An unknown event raises KeyError
    rather than falling back to the wrong criteria."""
    return CRITERIA[event.name if event is not None else "xaver_2013"](
        his, obs_by_site, run_dir, window)


def _skill_table_lines(his: pd.DataFrame, obs_by_site: dict, window: tuple | None) -> list[str]:
    lines = ["| station | n | bias m | RMSE m | r | peak err m | peak dt h |", "|---|---|---|---|---|---|---|"]
    for g in GAUGES:
        obs = obs_by_site[g]
        if window is not None:
            obs = obs.loc[window[0]:window[1]]
        s = skill(his[g], obs)
        lines.append(f"| {g} | {s['n']} | {s['bias']:+.2f} | {s['rmse']:.2f} | {s['r']:.2f} | {s['peak_err_m']:+.2f} | {s['peak_dt_h']:+.0f} |")
    return lines


def main(event: common.Event, run_dir: Path | None = None) -> None:
    run_dir = run_dir or common.RUNS / event.name
    his = load_his(run_dir)
    obs_by_site = {g: load_gauge_levels(g, event) for g in GAUGES}

    lines = [f"# {event.title} validation", "", f"Whole period: {_window_label((event.tref, event.tstop))}", ""]
    lines += _skill_table_lines(his, obs_by_site, window=None)
    # event.score_label is what app/sfincs_data._PERIOD_RE looks for -- see Task 11.
    lines += ["", f"{event.score_label}: {_window_label(event.score_window)}", ""]
    lines += _skill_table_lines(his, obs_by_site, window=event.score_window)

    fig, axes = plt.subplots(len(GAUGES), 1, figsize=(10, 3 * len(GAUGES)), sharex=True)
    for ax, g in zip(axes, GAUGES):
        obs = obs_by_site[g]
        ax.plot(his.index, his[g], label="SFINCS"); ax.plot(obs.index, obs.values, "o", ms=4, label="gauge (06/18 h)")
        ax.set_ylabel(f"{g} [m]"); ax.grid(alpha=0.3); ax.legend(loc="upper left")
    fig.autofmt_xdate(); fig.tight_layout(); fig.savefig(run_dir / "validation_timeseries.png", dpi=130); plt.close(fig)

    area = flood_map(run_dir, run_dir / "flood_extent_delta.png", event=event)
    lines += ["", f"Flooded land in the delta window (depth > 5 cm, ground > 0 m): **{area:.1f} km²**"]

    crit = criteria(his, obs_by_site, run_dir, event=event)
    lines += ["", "### Success criteria (spec section 9)"]
    for c in crit:
        lines.append(f"- {c['name']} [{c['window']}]: **{c['verdict']}** -- {c['value']} (threshold: {c['threshold']})")

    (run_dir / "validation.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))

    results_dir = common.ROOT / "results" / run_dir.name
    results_dir.mkdir(parents=True, exist_ok=True)
    for fname in ("validation.md", "validation_timeseries.png", "flood_extent_delta.png"):
        shutil.copy2(run_dir / fname, results_dir / fname)


def parse_args(argv=None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--event", default="xaver_2013", choices=sorted(common.EVENTS))
    p.add_argument("--run", default=None, help="runs/<name> to validate; results go to results/<name>; defaults to the event name")
    args = p.parse_args(argv)
    args.run = args.run or args.event
    return args


if __name__ == "__main__":
    args = parse_args()
    main(common.event(args.event), run_dir=common.RUNS / args.run)
