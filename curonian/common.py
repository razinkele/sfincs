"""Shared constants and helpers for the Curonian Lagoon SFINCS model.

Everything the spec fixes as a project-wide value lives here so that a change
(e.g. the gauge zero) is a single edit.
"""
from __future__ import annotations

import sqlite3
from contextlib import closing
from dataclasses import dataclass
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

# April's Minija constant. The DB's Minija record ends in 2011, so April gets a
# constant as December does. Anomaly-scaled rather than climatological: the Nemunas
# mean over the April run window (1279 m3/s) is 1.56x its April climatology (820
# m3/s over 25 Aprils, 1990-2014), and 1.56 x the Minija's own April climatology at
# Lankupiai (53) = 83. Inside the observed April range there (max 272).
MINIJA_Q_APR = 83.0


@dataclass(frozen=True)
class Event:
    """One hindcast period and everything that differs between hindcasts.

    Passed explicitly, never selected at import: an import-time global would make
    test outcomes depend on import order and hide which event a script ran for.
    """
    name: str
    title: str                                        # report and figure titles
    tref: pd.Timestamp
    tstop: pd.Timestamp
    calm_window: tuple                                # GTSM bias correction
    score_window: tuple                               # criteria are judged here
    data_window: tuple                                # observation query/slice bounds
    peak_window: tuple                                # forcing_summary.txt slice
    peak_label: str
    gtsm_months: tuple
    minija_q: float
    nemunas_lag_days: int
    wind_check: tuple | None                          # (min peak m/s, what it is)
    zsini: float | None                               # None = take it from the boundary
    score_label: str                                  # the report's window heading

    @property
    def inputs_dir(self) -> Path:
        return INPUTS / self.name


# No run_dir property: run directories are keyed by RUN NAME, not event name.
# xaver_2013 alone owns runs/xaver_2013, runs/xaver_2013_gridwind and
# runs/xaver_2013_gridwind_pressure, selected by --run-name / --run.
EVENTS = {
    "xaver_2013": Event(
        name="xaver_2013", title="Xaver 2013",
        tref=TREF, tstop=TSTOP, calm_window=CALM_WINDOW,
        # Xaver scores C1/C3 on the four-day storm, not the thirteen-day run.
        score_window=(pd.Timestamp("2013-12-05"), pd.Timestamp("2013-12-09")),
        # Today's literals, kept verbatim: test_forcing_provenance proves the
        # refactor changed no bytes, and tref-8d..tstop+9d is not a round pad.
        data_window=("2013-11-20", "2013-12-20"),
        peak_window=("2013-12-05", "2013-12-08"), peak_label="storm",
        gtsm_months=("11", "12"), minija_q=MINIJA_Q_DEC,
        nemunas_lag_days=NEMUNAS_LAG_DAYS,
        wind_check=(15.0, "the Xaver gale"), zsini=None,
        score_label="Storm window"),
    "april_2013": Event(
        name="april_2013", title="April 2013 Nemunas freshet",
        tref=pd.Timestamp("2013-04-05 00:00"), tstop=pd.Timestamp("2013-05-02 00:00"),
        calm_window=(pd.Timestamp("2013-04-05"), pd.Timestamp("2013-04-11")),
        score_window=(pd.Timestamp("2013-04-13"), pd.Timestamp("2013-05-02")),
        data_window=("2013-03-26", "2013-05-12"),
        peak_window=("2013-04-19", "2013-04-25"), peak_label="crest",
        gtsm_months=("04", "05"), minija_q=MINIJA_Q_APR,
        nemunas_lag_days=NEMUNAS_LAG_DAYS,
        # No wind signature to assert in a freshet; the span guard in
        # make_forcing.wind_forcing still runs. See spec section 6.
        wind_check=None,
        # The lagoon stands above the sea at TREF (Nida -0.10, Uostadvaris -0.13,
        # Vente -0.28 m; Klaipeda -0.36), so taking zsini from the boundary would
        # start the whole lagoon ~0.23 m low. Mean of the three lagoon gauges.
        zsini=-0.17,
        score_label="Scoring window"),
}


def event(name: str) -> Event:
    if name not in EVENTS:
        raise KeyError(f"unknown event {name!r}; known: {', '.join(sorted(EVENTS))}")
    return EVENTS[name]


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


def read_active_mask(run_dir: Path):
    """Read a built run's active-cell mask and cell-centre coordinates.

    The mask (msk > 0) is set by setup_dep + setup_mask_active + setup_mask_bounds,
    all of which build_model.build() runs before setup_subgrid's channel burn -- so
    it does not depend on channels.geojson and is safe ground truth to check a
    channel centreline against, or to derive one from.
    """
    from hydromt_sfincs import SfincsModel

    sf = SfincsModel(root=str(run_dir), mode="r")
    sf.read()
    msk = sf.grid["msk"].values
    xs = sf.grid["msk"].raster.xcoords.values
    ys = sf.grid["msk"].raster.ycoords.values
    return msk, xs, ys


def mask_value_at(msk: np.ndarray, xs: np.ndarray, ys: np.ndarray, x: float, y: float) -> int:
    """The mask value of the grid cell whose centre is nearest (x, y)."""
    i = int(np.argmin(np.abs(xs - x)))
    j = int(np.argmin(np.abs(ys - y)))
    return int(msk[j, i])
