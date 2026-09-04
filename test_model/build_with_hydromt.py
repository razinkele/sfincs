#!/usr/bin/env python3
"""Rebuild the plane-beach test model through the HydroMT-SFINCS 1.x API.

Same geometry and forcing as make_test_model.py, but the elevation comes from a
GeoTIFF and the model is written in SFINCS binary format, which is the workflow
you will use for a real domain. Run inside the `hydromt-sfincs` env:

    micromamba run -n hydromt-sfincs python build_with_hydromt.py
"""
import os
from pathlib import Path
import numpy as np, pandas as pd, geopandas as gpd, xarray as xr
from shapely.geometry import Point, box
from hydromt_sfincs import SfincsModel

here = Path(__file__).resolve().parent
root = here.parent / "test_model_hydromt"
EPSG = 3346                                   # LKS-94 / Lithuania TM, as a placeholder CRS

mmax, nmax, dx, dy = 50, 20, 100.0, 100.0
xc = dx / 2 + dx * np.arange(mmax)            # cell centres
yc = dy / 2 + dy * np.arange(nmax)
zb = np.tile(-5.0 + 0.2 * np.arange(mmax), (nmax, 1))

# --- elevation as a GeoTIFF (y descending, as rasters expect)
da = xr.DataArray(zb[::-1], dims=("y", "x"), coords={"y": yc[::-1], "x": xc}, name="elevtn")
da.raster.set_crs(EPSG); da.raster.set_nodata(-9999.0)
dep_tif = here / "plane_beach_dep.tif"
da.raster.to_raster(dep_tif)

sf = SfincsModel(root=str(root), mode="w+", write_gis=os.environ.get("WRITE_GIS", "1") == "1")
sf.setup_grid(x0=0, y0=0, dx=dx, dy=dy, nmax=nmax, mmax=mmax, rotation=0, epsg=EPSG)
sf.setup_dep(datasets_dep=[{"elevtn": str(dep_tif), "reproj_method": "nearest"}])
sf.setup_mask_active(zmin=-10)                                    # every cell active
west_edge = gpd.GeoDataFrame(geometry=[box(-10, -10, 90, nmax * dy + 10)], crs=EPSG)
sf.setup_mask_bounds(btype="waterlevel", include_mask=west_edge)  # column m=1 -> msk=2

sf.setup_config(
    tref="20240101 000000", tstart="20240101 000000", tstop="20240101 060000",
    advection=1, alpha=0.5, huthresh=0.05, manning=0.04, zsini=0.0,
    dtout=1800, dthisout=300, dtmaxout=21600,
)

# --- water-level forcing: two boundary points on the west edge, 0 -> 2 m over 6 h
times = pd.date_range("2024-01-01 00:00", "2024-01-01 06:00", freq="10min")
ramp = 2.0 * (times - times[0]).total_seconds() / 21600.0
bnd = gpd.GeoDataFrame(index=[1, 2], geometry=[Point(50, 50), Point(50, 1950)], crs=EPSG)
sf.setup_waterlevel_forcing(timeseries=pd.DataFrame({1: ramp, 2: ramp}, index=times), locations=bnd)

obs = gpd.GeoDataFrame({"name": ["offshore", "shoreline", "inland"]},
                       geometry=[Point(1050, 1050), Point(2550, 1050), Point(3250, 1050)], crs=EPSG)
sf.setup_observation_points(locations=obs)

sf.write()
print("msk values:", np.unique(sf.grid["msk"].values, return_counts=True))
print("wrote model to", root)
