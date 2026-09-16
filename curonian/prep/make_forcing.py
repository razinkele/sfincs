"""Forcing time series for an event: sea boundary, uniform wind, river discharge."""
from __future__ import annotations

import argparse
from pathlib import Path

import geopandas as gpd
import netCDF4 as nc
import numpy as np
import pandas as pd
from shapely.geometry import Point

import common

NEMUNAS_APEX_LONLAT = (21.38, 55.30)   # Rusnė, where the Nemunas splits into Atmata and Skirvytė
MINIJA_MOUTH_LONLAT = (21.25, 55.42)


def load_gauge_levels(site: str, event: common.Event) -> pd.Series:
    df = common.read_table(
        "SELECT date, wlevel_06, wlevel_18 FROM physical_daily WHERE site=? AND date BETWEEN ? AND ?",
        (site, *event.data_window))
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


def boundary_forcing(gtsm: pd.Series, npoints: int, event: common.Event) -> pd.DataFrame:
    t = pd.date_range(event.tref, event.tstop, freq="h")
    s = gtsm.reindex(t).interpolate(limit_direction="both")
    if not s.notna().all():
        raise ValueError(f"sea boundary has {int(s.isna().sum())} of {len(s)} steps still NaN after "
                         f"interpolation; the source series covers {gtsm.index.min()}..{gtsm.index.max()}, "
                         f"the run needs {event.tref}..{event.tstop}")
    return pd.DataFrame({i: s.values for i in range(1, npoints + 1)}, index=t)


def wind_from_uv(t, u, v) -> pd.DataFrame:
    mag = np.hypot(u, v)
    direction = (270.0 - np.degrees(np.arctan2(v, u))) % 360.0     # direction the wind comes FROM
    return pd.DataFrame({"mag": mag, "dir": direction}, index=pd.DatetimeIndex(t))


def check_wind(df: pd.DataFrame, event: common.Event) -> None:
    """Guard the wind series. The span check runs for every event; the peak check
    only where the event has a signature worth asserting.

    Without the span check, an event with wind_check=None would accept a truncated
    or empty slice and hand SFINCS a wind file that does not cover the run.
    """
    if df.empty or df.index[0] > event.tref - pd.Timedelta("1h") or df.index[-1] < event.tstop + pd.Timedelta("1h"):
        span = f"{df.index[0]}..{df.index[-1]}" if not df.empty else "empty"
        raise ValueError(f"wind series {span} does not cover {event.name} "
                         f"({event.tref}..{event.tstop})")
    if not df.notna().all().all():
        raise ValueError(f"wind series has NaN in {df.columns[df.isna().any()].tolist()}")
    if event.wind_check is not None:
        floor, what = event.wind_check
        if df["mag"].max() <= floor:
            raise ValueError(f"peak wind is only {df['mag'].max():.1f} m/s -- expected "
                             f"{what} (>{floor:g} m/s)")


def wind_forcing(event: common.Event, era5_path: Path = common.ERA5_2013) -> pd.DataFrame:
    with nc.Dataset(era5_path) as d:
        t = pd.to_datetime(d["valid_time"][:].astype("int64"), unit="s")
        u = d["u10"][:, 0, 0].astype(float); v = d["v10"][:, 0, 0].astype(float)
    df = wind_from_uv(t, u, v)
    df = df.loc[event.tref - pd.Timedelta("1h"): event.tstop + pd.Timedelta("1h")]
    check_wind(df, event)
    return df


def lag_and_resample(daily: pd.Series, lag_days: int, start: pd.Timestamp, stop: pd.Timestamp) -> pd.Series:
    shifted = daily.copy()
    shifted.index = shifted.index + pd.Timedelta(days=lag_days)
    hourly = shifted.resample("h").interpolate("linear")
    return hourly.loc[start:stop]


def cmems_daily_boundary(event: common.Event,
                         path: Path = common.HOME / "curonian/shyfem_box/cmems_boundary/cmems_bal_boundary_2009_2014.nc",
                         lonlat=common.KLAIPEDA_MOUTH_LONLAT) -> pd.Series:
    """Fallback sea level: daily-mean CMEMS `sla` at the grid point nearest the mouth, interpolated to hourly."""
    with nc.Dataset(path) as d:
        t = pd.to_datetime([str(x) for x in nc.num2date(d["time"][:], d["time"].units, only_use_cftime_datetimes=False)])
        la, lo = d["latitude"][:], d["longitude"][:]
        i, j = int(np.argmin(abs(la - lonlat[1]))), int(np.argmin(abs(lo - lonlat[0])))
        sla = np.ma.filled(d["sla"][:, i, j], np.nan)
    daily = pd.Series(sla, index=t + pd.Timedelta(hours=12)).loc[event.data_window[0]:event.data_window[1]]   # daily means -> noon
    hourly = daily.resample("h").interpolate("linear")
    if not hourly.notna().all():
        raise ValueError(f"CMEMS sla has {int(hourly.isna().sum())} gaps near the mouth")
    hourly.name = "waterlevel_m"
    return hourly


def discharge_forcing(event: common.Event) -> pd.DataFrame:
    df = common.read_table(
        "SELECT date, discharge_m3s FROM river_discharge WHERE river='Nemunas' AND gauge='Smalininkai' "
        "AND date BETWEEN ? AND ? ORDER BY date", event.data_window)
    daily = pd.Series(df["discharge_m3s"].values, index=pd.to_datetime(df["date"]))
    nem = lag_and_resample(daily, event.nemunas_lag_days, event.tref, event.tstop)
    if not nem.notna().all() or nem.index[0] != event.tref or nem.index[-1] != event.tstop:
        raise ValueError(f"Nemunas discharge does not cover {event.name} cleanly: "
                         f"{nem.index[0]}..{nem.index[-1]} with {int(nem.isna().sum())} NaN")
    return pd.DataFrame({1: nem.values, 2: event.minija_q}, index=nem.index)


def discharge_points() -> gpd.GeoDataFrame:
    pts = [Point(*common.lonlat_to_xy(*NEMUNAS_APEX_LONLAT)), Point(*common.lonlat_to_xy(*MINIJA_MOUTH_LONLAT))]
    return gpd.GeoDataFrame({"index": [1, 2], "name": ["Nemunas_Rusne", "Minija_mouth"]}, geometry=pts, crs=common.CRS)


def main(event: common.Event, static: Path = common.INPUTS, use_cmems: bool = False) -> None:
    out = event.inputs_dir
    out.mkdir(parents=True, exist_ok=True)
    if use_cmems:
        gtsm = cmems_daily_boundary(event)
        print("using the daily CMEMS cache as sea boundary (fallback)")
    else:
        gtsm = pd.read_csv(out / "gtsm_klaipeda.csv", index_col=0, parse_dates=True)["waterlevel_m"]
    # Spec section 5 checks the boundary against the Klaipeda 06:00 series only; restrict
    # here even though load_gauge_levels("Klaipeda") currently returns only 06:00 readings
    # anyway (no wlevel_18 rows exist for this site).
    klaipeda = load_gauge_levels("Klaipeda", event)
    klaipeda_06 = klaipeda.loc[klaipeda.index.hour == 6]
    corrected, offset = bias_correct(gtsm, klaipeda_06, event.calm_window)
    bnd_pts = gpd.read_file(static / "boundary_points.geojson")             # static, shared
    bzs = boundary_forcing(corrected, len(bnd_pts), event)
    bzs.to_csv(out / "bzs.csv", index_label="time", float_format=common.CSV_FLOAT_FMT)

    wind = wind_forcing(event)
    wind.to_csv(out / "wind.csv", index_label="time", float_format=common.CSV_FLOAT_FMT)

    dis = discharge_forcing(event)
    dis.to_csv(out / "dis.csv", index_label="time", float_format=common.CSV_FLOAT_FMT)
    common.write_geojson(discharge_points(), static / "dis_points.geojson")  # static, shared: both events discharge at the same two points

    peak = corrected.loc[event.peak_window[0]:event.peak_window[1]]
    summary = (f"GTSM offset applied: {offset:+.3f} m (calm window {event.calm_window[0].date()}..{event.calm_window[1].date()})\n"
               f"boundary level: start {corrected.loc[event.tref]:.2f} m, "
               f"{event.peak_label} peak {peak.max():.2f} m at {peak.idxmax()}\n"
               f"Klaipeda 06h obs peak: {klaipeda_06.max():.2f} m at {klaipeda_06.idxmax()}\n"
               f"wind peak: {wind['mag'].max():.1f} m/s at {wind['mag'].idxmax()} from {wind.loc[wind['mag'].idxmax(), 'dir']:.0f} deg\n"
               f"Nemunas Q: {dis[1].min():.0f}..{dis[1].max():.0f} m3/s; Minija constant {event.minija_q} m3/s\n")
    gap = abs(peak.idxmax() - klaipeda_06.idxmax())
    if gap > pd.Timedelta("12h"):
        summary += (f"FINDING: GTSM {event.peak_label} peak ({peak.idxmax()}) is {gap} from the Klaipeda 06:00 gauge peak "
                    f"({klaipeda_06.idxmax()}) -- more than the 12 h check tolerance. Not a blocker: recorded per spec.\n")
    (out / "forcing_summary.txt").write_text(summary)
    print(summary)


def parse_args(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--event", default="xaver_2013", choices=sorted(common.EVENTS))
    p.add_argument("--cmems", action="store_true", help="daily CMEMS fallback sea boundary")
    return p.parse_args(argv)


if __name__ == "__main__":
    args = parse_args()
    main(common.event(args.event), use_cmems=args.cmems)
