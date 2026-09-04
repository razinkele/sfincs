"""Score the Xaver run against the gauges and draw the delta flood extent."""
from __future__ import annotations

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


def flood_map(run_dir: Path = common.RUN_XAVER, out_png: Path | None = None,
              window=(325_000, 6_105_000, 360_000, 6_145_000)) -> float:
    with nc.Dataset(run_dir / "sfincs_map.nc") as d:
        zsmax = np.ma.filled(d["zsmax"][:], np.nan)
        zsmax = zsmax[-1] if zsmax.ndim == 3 else zsmax
        x = d["x"][:]; y = d["y"][:]
        x = x[0, :] if x.ndim == 2 else x; y = y[:, 0] if y.ndim == 2 else y
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
        ix = np.clip(np.searchsorted(x, gx) - 1, 0, len(x) - 1); iy = np.clip(np.searchsorted(y, gy) - 1, 0, len(y) - 1)
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
    area_km2 = float(flooded.sum() * cell_km2)
    if out_png:
        fig, ax = plt.subplots(figsize=(9, 8))
        ax.imshow(np.where(ground > 0, ground, np.nan), extent=[gx[0], gx[-1], gy[-1], gy[0]], cmap="Greys_r", vmin=-2, vmax=8)
        im = ax.imshow(np.where(flooded, depth, np.nan), extent=[gx[0], gx[-1], gy[-1], gy[0]], cmap="Blues", vmin=0, vmax=2)
        fig.colorbar(im, ax=ax, label="max flood depth on land [m]")
        ax.set_title(f"Xaver 2013: flooded land in the delta window = {area_km2:.1f} km²")
        fig.savefig(out_png, dpi=150); plt.close(fig)
    return area_km2


def main(run_dir: Path = common.RUN_XAVER) -> None:
    his = load_his(run_dir)
    lines = ["# Xaver 2013 validation", "", "| station | n | bias m | RMSE m | r | peak err m | peak dt h |", "|---|---|---|---|---|---|---|"]
    fig, axes = plt.subplots(len(GAUGES), 1, figsize=(10, 3 * len(GAUGES)), sharex=True)
    for ax, g in zip(axes, GAUGES):
        obs = load_gauge_levels(g)
        s = skill(his[g], obs)
        lines.append(f"| {g} | {s['n']} | {s['bias']:+.2f} | {s['rmse']:.2f} | {s['r']:.2f} | {s['peak_err_m']:+.2f} | {s['peak_dt_h']:+.0f} |")
        ax.plot(his.index, his[g], label="SFINCS"); ax.plot(obs.index, obs.values, "o", ms=4, label="gauge (06/18 h)")
        ax.set_ylabel(f"{g} [m]"); ax.grid(alpha=0.3); ax.legend(loc="upper left")
    fig.autofmt_xdate(); fig.tight_layout(); fig.savefig(run_dir / "validation_timeseries.png", dpi=130); plt.close(fig)
    area = flood_map(run_dir, run_dir / "flood_extent_delta.png")
    lines += ["", f"Flooded land in the delta window (depth > 5 cm, ground > 0 m): **{area:.1f} km²**", "",
              "Targets: Uostadvaris peak within ±0.15 m and ±6 h; Nida 8 Dec rise within ±0.15 m; Klaipeda RMSE ≤ 0.15 m."]
    (run_dir / "validation.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
