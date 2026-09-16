"""Assemble the Curonian Lagoon SFINCS model for Storm Xaver with HydroMT-SFINCS 1.2."""
from __future__ import annotations

import argparse
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
from scipy import ndimage

import common

# Order is deliberate, not the spec's DEM-first prose: the DEM is a flat 0 inside the
# lagoon, and setup_dep's merge_method="first" keeps the first valid value at each
# cell, so the lagoon bathymetry (masked to the lagoon) must come first or it would
# never be used. Do not reorder to match section 3's listing.
DATASETS_DEP = [
    {"elevtn": "lagoon_bathy_50m", "mask": "lagoon_boundary", "reproj_method": "bilinear"},
    {"elevtn": "dem_5m", "reproj_method": "bilinear"},
    {"elevtn": "emodnet_2022", "reproj_method": "bilinear"},
]
# rivwth/rivbed here are fallbacks only, used where the channels.geojson attributes
# are missing; build_channels() already sets per-channel rivwth/rivbed and those
# GeoJSON attributes win over these defaults.
DATASETS_RIV = [{"centerlines": "channels", "rivwth": 200, "rivbed": -4.0}]

# check_model()'s two tuning numbers, named rather than buried as literals.
# The probe is a point of permanently open water west of Ventė, in the middle of the
# lagoon: check_model() asserts it shares a connected component with the harbour mouth,
# which is how it detects a strait that failed to burn through. It must lie inside the
# active region (tests/test_build_model.py checks that).
OPEN_LAGOON_PROBE = (318_000.0, 6_130_000.0)
# Boundary cells are flagged per 100 m grid cell while the ring is a smooth circle, so a
# cell centre can sit up to ~half a diagonal (71 m) outside it; 150 m covers that with room.
BND_RING_TOL_M = 150.0

# Roughness. In subgrid mode SFINCS takes roughness from the subgrid tables
# (sfincs_subgrid.nc: uv_navg spans manning_sea..manning_land), so the inp keywords are
# inert -- but they are the first thing a reader checks, so they are written to match
# rather than left at the SFINCS defaults.
MANNING_LAND = 0.06
MANNING_SEA = 0.02
RGH_LEV_LAND = 0.3


def _read_ts(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, index_col=0, parse_dates=True)
    df.columns = [int(c) for c in df.columns]
    return df


def parse_args(argv=None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--no-subgrid", action="store_true", help="skip setup_subgrid (see README Limitations)")
    p.add_argument("--wind", choices=("uniform", "grid"), default="uniform",
                    help="uniform: the Nida point series (wind.csv); grid: gridded ERA5 wind (era5_grid.nc)")
    p.add_argument("--pressure", action="store_true",
                    help="also add gridded ERA5 mean sea level pressure forcing (needs --wind grid's era5_grid.nc)")
    p.add_argument("--event", default="xaver_2013", choices=sorted(common.EVENTS))
    p.add_argument("--run-name", default=None, help="subdirectory of runs/; defaults to the event name")
    args = p.parse_args(argv)
    if args.pressure and args.wind != "grid":
        raise SystemExit("--pressure requires --wind grid")
    args.run_name = args.run_name or args.event
    return args


def config_for(event: common.Event, zs_boundary: float) -> dict:
    """SFINCS config for this event. zsini is the event's if it sets one.

    Xaver leaves zsini=None and takes the sea boundary's first value, which was
    within 0.05-0.11 m of its lagoon gauges. April's lagoon stands ~0.23 m above
    the sea at TREF, so the boundary would start the whole lagoon low.
    """
    return dict(
        tref=event.tref.strftime("%Y%m%d %H%M%S"), tstart=event.tref.strftime("%Y%m%d %H%M%S"),
        tstop=event.tstop.strftime("%Y%m%d %H%M%S"),
        advection=1, alpha=0.5, huthresh=0.05, viscosity=1,
        dtout=3600, dthisout=600, dtmaxout=99999999,
        manning_land=MANNING_LAND, manning_sea=MANNING_SEA,
        zsini=event.zsini if event.zsini is not None else zs_boundary,
    )


def build(event: common.Event, run_dir: Path | None = None, subgrid: bool = True,
          wind: str = "uniform", pressure: bool = False):
    from hydromt_sfincs import SfincsModel

    run_dir = run_dir or common.RUNS / event.name
    inputs, static = event.inputs_dir, common.INPUTS
    sf = SfincsModel(root=str(run_dir), mode="w+", data_libs=[str(common.ROOT / "data_catalog.yml")], write_gis=False)
    sf.setup_grid(x0=common.X0, y0=common.Y0, dx=common.DX, dy=common.DY, nmax=common.NMAX, mmax=common.MMAX,
                  rotation=0, epsg=common.CRS)
    sf.setup_dep(datasets_dep=DATASETS_DEP)
    sf.setup_mask_active(mask="active_region", zmax=10.0, drop_area=0.5, fill_area=10.0, reset_mask=True)
    sf.setup_mask_bounds(btype="waterlevel", include_mask="boundary_ring", reset_bounds=True)
    if subgrid:
        sf.setup_subgrid(datasets_dep=DATASETS_DEP, datasets_riv=DATASETS_RIV, nr_subgrid_pixels=20, nlevels=10,
                         manning_land=MANNING_LAND, manning_sea=MANNING_SEA, rgh_lev_land=RGH_LEV_LAND,
                         write_dep_tif=True)
        # NOTE: hydromt_sfincs 1.2.2's setup_subgrid() always writes the modern NetCDF
        # subgrid table (sbgfile = sfincs_subgrid.nc), not the legacy binary sfincs.sbg
        # the brief names. Forcing the .sbg extension crashes: the new subgrid table
        # (q_table_option=2) stores z_level/u_havg/u_nrep/u_pwet, while the legacy
        # binary writer (SubgridTableRegular.write_binary) still reads the old
        # z_depth/u_hrep/u_navg field names -> AttributeError. Accept the NetCDF
        # default; see tests/test_build_model.py for the corresponding check.
    else:
        sf.setup_manning_roughness(manning_land=MANNING_LAND, manning_sea=MANNING_SEA,
                                   rgh_lev_land=RGH_LEV_LAND)

    bzs = _read_ts(inputs / "bzs.csv")
    # config_for's zsini is the event's if it sets one, else the sea boundary's first
    # value (see config_for's docstring for why that split exists).
    sf.setup_config(**config_for(event, zs_boundary=float(bzs.iloc[0].mean())))
    sf.setup_waterlevel_forcing(timeseries=bzs,
                                locations=gpd.read_file(static / "boundary_points.geojson").set_index("index", drop=False))
    sf.setup_discharge_forcing(timeseries=_read_ts(inputs / "dis.csv"),
                               locations=gpd.read_file(static / "dis_points.geojson").set_index("index", drop=False))
    if wind == "grid":
        sf.setup_wind_forcing_from_grid(wind=str(inputs / "era5_grid.nc"))
    else:
        sf.setup_wind_forcing(timeseries=str(inputs / "wind.csv"))
    if pressure:
        # pavbnd stays 0 (hydromt_sfincs' own default, unchanged here): the GTSM
        # boundary series already carries the inverse-barometer effect baked in from
        # its own reanalysis, so re-applying a boundary pressure correction from this
        # ERA5 grid would double-count it. baro is already 1 in the written config
        # (also hydromt_sfincs' default), so SFINCS still applies the pressure
        # gradient force from netampfile inside the domain.
        sf.setup_pressure_forcing_from_grid(press=str(inputs / "era5_grid.nc"))
    sf.setup_observation_points(locations=gpd.read_file(static / "stations.geojson"))
    sf.write()
    r = check_model(run_dir)
    print(r)
    assert 200_000 <= r["n_active"] <= 400_000, f"n_active out of [200000, 400000]: {r['n_active']}"
    assert 20 <= r["n_bnd"] <= 200, f"n_bnd out of [20, 200]: {r['n_bnd']}"
    assert r["bnd_in_ring"], f"boundary cells outside the boundary ring: {r}"
    assert r["connected"], f"strait not connected to the open lagoon: {r}"
    return sf


def check_model(run_dir: Path = common.RUN_XAVER) -> dict:
    from hydromt_sfincs import SfincsModel

    sf = SfincsModel(root=str(run_dir), mode="r")
    sf.read()
    msk = sf.grid["msk"].values
    active = msk > 0
    labels, _ = ndimage.label(active, structure=np.ones((3, 3)))
    x = sf.grid["msk"].raster.xcoords.values; y = sf.grid["msk"].raster.ycoords.values
    def label_at(px, py):
        return labels[int(np.argmin(abs(y - py))), int(np.argmin(abs(x - px)))]
    mx, my = common.lonlat_to_xy(*common.KLAIPEDA_MOUTH_LONLAT)
    connected = label_at(mx, my) == label_at(*OPEN_LAGOON_PROBE) != 0   # mouth vs open lagoon
    ring = gpd.read_file(common.INPUTS / "boundary_ring.geojson").geometry.iloc[0]
    rows, cols = np.where(msk == 2)
    bnd_in_ring = all(ring.buffer(BND_RING_TOL_M).contains(gpd.points_from_xy([x[c]], [y[r]])[0])
                      for r, c in zip(rows, cols))
    return {"n_active": int(active.sum()), "n_bnd": int((msk == 2).sum()), "connected": bool(connected),
            "bnd_in_ring": bool(bnd_in_ring)}


if __name__ == "__main__":
    args = parse_args()
    build(common.event(args.event), run_dir=common.RUNS / args.run_name, subgrid=not args.no_subgrid,
          wind=args.wind, pressure=args.pressure)
