"""Forcing time series for the Xaver run: sea boundary, uniform wind, river discharge."""
from __future__ import annotations

from pathlib import Path

import geopandas as gpd
import netCDF4 as nc
import numpy as np
import pandas as pd
from shapely.geometry import Point

import common

NEMUNAS_APEX_LONLAT = (21.38, 55.30)   # Rusnė, where the Nemunas splits into Atmata and Skirvytė
MINIJA_MOUTH_LONLAT = (21.25, 55.42)

XAVER = common.EVENTS["xaver_2013"]


def load_gauge_levels(site: str) -> pd.Series:
    df = common.read_table(
        "SELECT date, wlevel_06, wlevel_18 FROM physical_daily WHERE site=? AND date BETWEEN '2013-11-20' AND '2013-12-20'",
        (site,))
    rows = []
    for _, r in df.iterrows():
        for col, hh in (("wlevel_06", 6), ("wlevel_18", 18)):
            if pd.notna(r[col]) and r[col] > 0:
                rows.append((pd.Timestamp(r["date"]) + pd.Timedelta(hours=hh), common.gauge_cm_to_m(r[col]).item()))
    s = pd.Series(dict(rows)).sort_index()
    s.name = site
    return s


def bias_correct(model: pd.Series, obs: pd.Series, window) -> tuple[pd.Series, float]:
    obs_w = obs.loc[window[0]:window[1]]
    model_at_obs = model.reindex(obs_w.index, method="nearest", tolerance=pd.Timedelta("1h"))
    offset = float(obs_w.mean() - model_at_obs.mean())
    return model + offset, offset


def boundary_forcing(gtsm: pd.Series, npoints: int) -> pd.DataFrame:
    t = pd.date_range(common.TREF, common.TSTOP, freq="h")
    s = gtsm.reindex(t).interpolate(limit_direction="both")
    if not s.notna().all():
        raise ValueError(f"sea boundary has {int(s.isna().sum())} of {len(s)} steps still NaN after "
                         f"interpolation; the source series covers {gtsm.index.min()}..{gtsm.index.max()}, "
                         f"the run needs {common.TREF}..{common.TSTOP}")
    return pd.DataFrame({i: s.values for i in range(1, npoints + 1)}, index=t)


def wind_from_uv(t, u, v) -> pd.DataFrame:
    mag = np.hypot(u, v)
    direction = (270.0 - np.degrees(np.arctan2(v, u))) % 360.0     # direction the wind comes FROM
    return pd.DataFrame({"mag": mag, "dir": direction}, index=pd.DatetimeIndex(t))


def wind_forcing(era5_path: Path = common.ERA5_2013) -> pd.DataFrame:
    with nc.Dataset(era5_path) as d:
        t = pd.to_datetime(d["valid_time"][:].astype("int64"), unit="s")
        u = d["u10"][:, 0, 0].astype(float); v = d["v10"][:, 0, 0].astype(float)
    df = wind_from_uv(t, u, v)
    df = df.loc[common.TREF - pd.Timedelta("1h"): common.TSTOP + pd.Timedelta("1h")]
    if not df.notna().all().all():
        raise ValueError(f"wind series has NaN in {df.columns[df.isna().any()].tolist()}")
    if df["mag"].max() <= 15:
        raise ValueError(f"peak wind is only {df['mag'].max():.1f} m/s -- expected the Xaver gale "
                         f"(>15 m/s) in {era5_path}")
    return df


def lag_and_resample(daily: pd.Series, lag_days: int, start: pd.Timestamp, stop: pd.Timestamp) -> pd.Series:
    shifted = daily.copy()
    shifted.index = shifted.index + pd.Timedelta(days=lag_days)
    hourly = shifted.resample("h").interpolate("linear")
    return hourly.loc[start:stop]


def cmems_daily_boundary(path: Path = common.HOME / "curonian/shyfem_box/cmems_boundary/cmems_bal_boundary_2009_2014.nc",
                         lonlat=common.KLAIPEDA_MOUTH_LONLAT) -> pd.Series:
    """Fallback sea level: daily-mean CMEMS `sla` at the grid point nearest the mouth, interpolated to hourly."""
    with nc.Dataset(path) as d:
        t = pd.to_datetime([str(x) for x in nc.num2date(d["time"][:], d["time"].units, only_use_cftime_datetimes=False)])
        la, lo = d["latitude"][:], d["longitude"][:]
        i, j = int(np.argmin(abs(la - lonlat[1]))), int(np.argmin(abs(lo - lonlat[0])))
        sla = np.ma.filled(d["sla"][:, i, j], np.nan)
    daily = pd.Series(sla, index=t + pd.Timedelta(hours=12)).loc["2013-11-20":"2013-12-20"]   # daily means -> noon
    hourly = daily.resample("h").interpolate("linear")
    if not hourly.notna().all():
        raise ValueError(f"CMEMS sla has {int(hourly.isna().sum())} gaps near the mouth")
    hourly.name = "waterlevel_m"
    return hourly


def discharge_forcing() -> pd.DataFrame:
    df = common.read_table(
        "SELECT date, discharge_m3s FROM river_discharge WHERE river='Nemunas' AND gauge='Smalininkai' "
        "AND date BETWEEN '2013-11-20' AND '2013-12-20' ORDER BY date")
    daily = pd.Series(df["discharge_m3s"].values, index=pd.to_datetime(df["date"]))
    nem = lag_and_resample(daily, common.NEMUNAS_LAG_DAYS, common.TREF, common.TSTOP)
    if not nem.notna().all() or nem.index[0] != common.TREF or nem.index[-1] != common.TSTOP:
        raise ValueError(f"Nemunas discharge does not cover the run period cleanly: "
                         f"{nem.index[0]}..{nem.index[-1]} with {int(nem.isna().sum())} NaN")
    return pd.DataFrame({1: nem.values, 2: common.MINIJA_Q_DEC}, index=nem.index)


def discharge_points() -> gpd.GeoDataFrame:
    pts = [Point(*common.lonlat_to_xy(*NEMUNAS_APEX_LONLAT)), Point(*common.lonlat_to_xy(*MINIJA_MOUTH_LONLAT))]
    return gpd.GeoDataFrame({"index": [1, 2], "name": ["Nemunas_Rusne", "Minija_mouth"]}, geometry=pts, crs=common.CRS)


def main(inputs: Path = common.INPUTS, use_cmems: bool = False) -> None:
    if use_cmems:
        gtsm = cmems_daily_boundary()
        print("using the daily CMEMS cache as sea boundary (fallback)")
    else:
        gtsm = pd.read_csv(XAVER.inputs_dir / "gtsm_klaipeda.csv", index_col=0, parse_dates=True)["waterlevel_m"]
    # Spec section 5 checks the boundary against the Klaipeda 06:00 series only; restrict
    # here even though load_gauge_levels("Klaipeda") currently returns only 06:00 readings
    # anyway (no wlevel_18 rows exist for this site).
    klaipeda = load_gauge_levels("Klaipeda")
    klaipeda_06 = klaipeda.loc[klaipeda.index.hour == 6]
    corrected, offset = bias_correct(gtsm, klaipeda_06, common.CALM_WINDOW)
    bnd_pts = gpd.read_file(inputs / "boundary_points.geojson")
    bzs = boundary_forcing(corrected, len(bnd_pts))
    bzs.to_csv(XAVER.inputs_dir / "bzs.csv", index_label="time", float_format=common.CSV_FLOAT_FMT)

    wind = wind_forcing()
    wind.to_csv(XAVER.inputs_dir / "wind.csv", index_label="time", float_format=common.CSV_FLOAT_FMT)

    dis = discharge_forcing()
    dis.to_csv(XAVER.inputs_dir / "dis.csv", index_label="time", float_format=common.CSV_FLOAT_FMT)
    common.write_geojson(discharge_points(), inputs / "dis_points.geojson")

    storm = corrected.loc["2013-12-05":"2013-12-08"]
    summary = (f"GTSM offset applied: {offset:+.3f} m (calm window {common.CALM_WINDOW[0].date()}..{common.CALM_WINDOW[1].date()})\n"
               f"boundary level: start {corrected.loc[common.TREF]:.2f} m, storm peak {storm.max():.2f} m at {storm.idxmax()}\n"
               f"Klaipeda 06h obs peak: {klaipeda_06.max():.2f} m at {klaipeda_06.idxmax()}\n"
               f"wind peak: {wind['mag'].max():.1f} m/s at {wind['mag'].idxmax()} from {wind.loc[wind['mag'].idxmax(), 'dir']:.0f} deg\n"
               f"Nemunas Q: {dis[1].min():.0f}..{dis[1].max():.0f} m3/s; Minija constant {common.MINIJA_Q_DEC} m3/s\n")
    gap = abs(storm.idxmax() - klaipeda_06.idxmax())
    if gap > pd.Timedelta("12h"):
        summary += (f"FINDING: GTSM storm peak ({storm.idxmax()}) is {gap} from the Klaipeda 06:00 gauge peak "
                    f"({klaipeda_06.idxmax()}) -- more than the 12 h check tolerance. Not a blocker: recorded per spec.\n")
    (XAVER.inputs_dir / "forcing_summary.txt").write_text(summary)
    print(summary)


if __name__ == "__main__":
    import sys
    main(use_cmems="--cmems" in sys.argv)
