"""Shared constants and helpers for the Curonian Lagoon SFINCS model.

Everything the spec fixes as a project-wide value lives here so that a change
(e.g. the gauge zero) is a single edit.
"""
from __future__ import annotations

import sqlite3
from contextlib import closing
from pathlib import Path

import numpy as np
import pandas as pd
from pyproj import Transformer

ROOT = Path(__file__).resolve().parent
INPUTS = ROOT / "inputs"
RUNS = ROOT / "runs"
RUN_XAVER = RUNS / "xaver_2013"

HOME = Path.home()
DEM_5M = HOME / "telemac/data/LowerNEMUNASdem_5m.tif"
EMODNET = HOME / "telemac/Curonian/data/curonian_bathymetry_hires.nc"
ISOBATHS = HOME / "curonian/isobates.gpkg"
ISOBATH_LAYER = "depth_isobates__isobates__depths"
DB = HOME / "curonian/curonian_db.gpkg"
ERA5_2013 = HOME / "eutropy/era5_raw/era5_wind_nida_2013.nc"
SFINCS_BIN = HOME / "SFINCS/sfincs-linux/bin/sfincs"
RUN_SFINCS_SH = HOME / "SFINCS/run_sfincs.sh"

CRS = 3346  # LKS-94 / Lithuania TM
X0, Y0 = 270_000.0, 6_080_000.0
DX = DY = 100.0
MMAX, NMAX = 1000, 1100

TREF = pd.Timestamp("2013-11-28 00:00")
TSTOP = pd.Timestamp("2013-12-11 00:00")
CALM_WINDOW = (pd.Timestamp("2013-11-28"), pd.Timestamp("2013-12-04"))

GAUGE_ZERO_CM = 500.0
KLAIPEDA_MOUTH_LONLAT = (21.09, 55.72)
MINIJA_Q_DEC = 46.0
NEMUNAS_LAG_DAYS = 1

_TO_XY = Transformer.from_crs(4326, CRS, always_xy=True)


def gauge_cm_to_m(cm) -> np.ndarray:
    """Convert gauge readings in cm above gauge zero to metres in the model datum."""
    return (np.asarray(cm, dtype=float) - GAUGE_ZERO_CM) / 100.0


def lonlat_to_xy(lon: float, lat: float) -> tuple[float, float]:
    x, y = _TO_XY.transform(lon, lat)
    return float(x), float(y)


def read_table(sql: str, params: tuple = ()) -> pd.DataFrame:
    """Run a read-only SQL query against the attribute tables of curonian_db.gpkg."""
    uri = f"file:{DB}?mode=ro"
    with closing(sqlite3.connect(uri, uri=True)) as con:
        return pd.read_sql_query(sql, con, params=params)
