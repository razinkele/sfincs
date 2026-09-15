"""Shared constants and helpers for the Curonian Lagoon SFINCS model.

Everything the spec fixes as a project-wide value lives here so that a change
(e.g. the gauge zero) is a single edit.
"""
from __future__ import annotations

import sqlite3
from contextlib import closing
from pathlib import Path
from urllib.parse import quote

import numpy as np
import pandas as pd
from pyproj import Transformer

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parent          # the SFINCS checkout; derived, never hardcoded (the
                           # directory was renamed SFINCS -> sfincs once already)
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
SFINCS_BIN = REPO / "sfincs-linux/bin/sfincs"
RUN_SFINCS_SH = REPO / "run_sfincs.sh"

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


def _db_uri(db: Path | None = None) -> str:
    """Read-only sqlite URI for `db`, with the path percent-encoded.

    quote() leaves "/" alone but escapes space, "?" and "#" -- unescaped, the last
    two would be read as the URI's query and fragment delimiters and silently open
    the wrong file. The current paths contain none of them; this keeps it that way.
    """
    return f"file:{quote(str(DB if db is None else db))}?mode=ro"


# Millimetres in a projected CRS: far below the 100 m model grid and the 5 m DEM, so
# nothing downstream can tell the difference, and the committed files stay diffable.
GEOJSON_PRECISION = 3
# Forcing CSVs: 3 decimals is a millimetre of water level, a mm/s of wind and a
# thousandth of a m3/s -- all far below the accuracy of the sources. pandas otherwise
# writes repr(float), e.g. a bias-corrected level as 0.3886666666666666.
CSV_FLOAT_FMT = "%.3f"


def write_geojson(gdf, path, precision: int = GEOJSON_PRECISION) -> None:
    """Write `gdf` as GeoJSON with coordinates trimmed to `precision` decimals.

    GDAL's COORDINATE_PRECISION layer option; without it every coordinate is written
    at full float64 width (17 significant digits) and any regeneration produces a
    large diff made entirely of noise.
    """
    gdf.to_file(path, driver="GeoJSON", COORDINATE_PRECISION=precision)


def read_table(sql: str, params: tuple = ()) -> pd.DataFrame:
    """Run a read-only SQL query against the attribute tables of curonian_db.gpkg."""
    with closing(sqlite3.connect(_db_uri(), uri=True)) as con:
        return pd.read_sql_query(sql, con, params=params)
