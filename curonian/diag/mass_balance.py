"""How much of an event's river inflow the lagoon passes, and how much it holds.

The README's April mass-balance finding quotes these numbers. Stated as a formula,
so "the model sheds 81 %" means something checkable:

    inflow    = the discharge forcing, integrated over the run
    rise_eq   = inflow / lagoon area          -- the rise if nothing drained
    rise_mod  = area-weighted mean water level over the lagoon, peak minus start
    shed      = 1 - rise_mod / rise_eq

"The lagoon" is `lagoon_boundary` intersected with the model's own active mask, so
the area is the one the model actually resolves rather than a figure from a
reference. Flooded land outside that polygon is deliberately not counted: this asks
what the lagoon retained, and `validate.py` already reports flooded extent.

Run it as `python -m diag.mass_balance [event] [run]` from `curonian/`.
"""
from __future__ import annotations

import sys

import geopandas as gpd
import numpy as np
import pandas as pd
import xarray as xr
from affine import Affine
from rasterio.features import rasterize

import common

TIME_CHUNK = 64          # ~280 MB of float32 per slab at 1000 x 1100


def lagoon_cells(lagoon: gpd.GeoDataFrame, msk: np.ndarray) -> np.ndarray:
    """Active cells inside the lagoon polygon, on the model grid.

    Both conditions matter: the polygon alone would count cells the model never
    solves, and the mask alone would count the Baltic and the flooded delta.
    """
    ny, nx = msk.shape
    # y ascending, matching the order SFINCS writes its map arrays in.
    transform = Affine(common.DX, 0, common.X0, 0, common.DY, common.Y0)
    poly = rasterize(lagoon.geometry, out_shape=(ny, nx), transform=transform,
                     fill=0, default_value=1).astype(bool)
    return poly & (msk > 0)


def report(event: common.Event, run: str) -> None:
    run_dir = common.RUNS / run
    ds = xr.open_dataset(run_dir / "sfincs_map.nc")
    lagoon = gpd.read_file(common.DB, layer="lagoon_boundary").to_crs(common.CRS)
    cells = lagoon_cells(lagoon, ds["msk"].values)
    area = cells.sum() * common.DX * common.DY

    means = np.empty(ds.sizes["time"])
    for i0 in range(0, ds.sizes["time"], TIME_CHUNK):
        zs = ds["zs"].isel(time=slice(i0, i0 + TIME_CHUNK)).values
        means[i0:i0 + zs.shape[0]] = np.nanmean(np.where(cells, zs, np.nan), axis=(1, 2))
    t = pd.to_datetime(ds["time"].values)

    dis = pd.read_csv(event.inputs_dir / "dis.csv", index_col=0, parse_dates=True)
    seconds = (dis.index[-1] - dis.index[0]).total_seconds()
    inflow = np.trapezoid(dis.sum(axis=1).values, dx=seconds / (len(dis) - 1))
    rise_eq = inflow / area
    peak = int(np.argmax(means))
    rise_mod = means[peak] - means[0]

    print(f"lagoon      {cells.sum()} active cells inside lagoon_boundary = {area / 1e6:.0f} km2")
    print(f"inflow      {inflow:.3e} m3 over {seconds / 86400:.1f} d  ->  rise_eq {rise_eq:.2f} m")
    print(f"lagoon mean {means[0]:+.3f} m at start, {means[peak]:+.3f} m at peak "
          f"({t[peak]:%Y-%m-%d %H:%M}), {means[-1]:+.3f} m at end")
    print(f"rise_mod    {rise_mod:.3f} m  ->  held {100 * rise_mod / rise_eq:.0f} %, "
          f"shed {100 * (1 - rise_mod / rise_eq):.0f} %")


if __name__ == "__main__":
    name = sys.argv[1] if len(sys.argv) > 1 else "april_2013"
    report(common.event(name), sys.argv[2] if len(sys.argv) > 2 else name)
