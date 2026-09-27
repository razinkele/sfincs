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


def load_rusne_levels(event: common.Event) -> pd.Series:
    """Daily Atmata level at Rusne in metres above the station's OWN gauge zero.

    Deliberately not passed through common.gauge_cm_to_m: Rusne's zero is not
    500 cm below the model datum (it sits ~2 m off), so only differences within
    this series mean anything. Indexed by date, not a reading hour -- LHMT's
    historical endpoint gives one value per day. Empty if the event has no file.
    """
    src = event.inputs_dir / "lhmt_rusne.csv"
    if not src.exists():
        return pd.Series(dtype=float, name="Rusne")
    df = pd.read_csv(src, comment="#", parse_dates=["observationDateUtc"])
    df = df[df["waterLevel"].notna()]
    s = pd.Series(df["waterLevel"].astype(float).values / 100.0, index=df["observationDateUtc"], name="Rusne")
    return s.loc[event.data_window[0]:event.data_window[1]]


MAX_READING_GAP = pd.Timedelta("3D")


def daily_fit_correction(model: pd.Series, obs06: pd.Series,
                         index: pd.DatetimeIndex) -> tuple[pd.Series, dict]:
    """The model series on `index`, corrected by the Klaipeda 06:00 readings.

    The residual (reading - model) at each 06:00 reading is interpolated
    linearly in time and added to the model; beyond the first and last
    reading it is held flat. This replaces a single calm-window offset: GTSM's
    error at Klaipeda is dominated by a slow drift (up to ~0.12 m over an
    event) that one offset cannot follow, while its sub-2-day signal is good
    to ~3 cm. Tested on the EPA hourly tide gauge (Copernicus in-situ
    BO_TS_TG_Klaipeda) over 19 event-sized windows in Oct 2012-Aug 2013,
    where the LHMT 06:00 readings match that gauge within 2.6 cm: median RMSE
    0.052 -> 0.028 m, storm-peak error 0.065 -> 0.021 m, better in 19/19.

    The readings used are those inside `index` plus the nearest one on each
    side; a gap between them longer than MAX_READING_GAP raises rather than
    interpolating across it, and so does a run end that far beyond the
    outermost reading. The residual also absorbs the gauge-zero offset,
    so the result is on the gauges' datum.
    """
    resid = (obs06 - model.reindex(obs06.index)).dropna()
    if resid.empty:
        raise ValueError("no Klaipeda 06:00 reading falls where the model series has values")
    before = resid.index[resid.index <= index[0]]
    after = resid.index[resid.index >= index[-1]]
    used = resid.loc[(before[-1] if len(before) else resid.index[0]):
                     (after[0] if len(after) else resid.index[-1])]
    edges = [(used.index[0] - index[0], "before the first reading"),
             (index[-1] - used.index[-1], "after the last reading")]
    for span, where in edges:
        if span > MAX_READING_GAP:
            raise ValueError(f"the run extends {span} {where} (limit {MAX_READING_GAP}): "
                             "no Klaipeda 06:00 reading constrains the boundary there")
    gaps = used.index.to_series().diff().dropna()
    max_gap = gaps.max() if len(gaps) else pd.Timedelta(0)
    if max_gap > MAX_READING_GAP:
        at = gaps.idxmax()
        raise ValueError(f"Klaipeda 06:00 readings have a gap of {max_gap} ending {at} "
                         f"(limit {MAX_READING_GAP}): too long to interpolate the boundary across")
    corr = (used.reindex(used.index.union(index)).interpolate(method="time")
                .ffill().bfill().reindex(index))
    info = {"n_readings": int(len(used)), "max_gap_h": max_gap / pd.Timedelta("1h"),
            "resid_min": float(used.min()), "resid_max": float(used.max()),
            "resid_mean": float(used.mean())}
    return model.reindex(index) + corr, info


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
    """Nemunas discharge at Smalininkai, from LHMT's own published series.

    Deliberately NOT from curonian_db.gpkg, which other projects share. That
    database keeps an older extraction, `smalininkai 2013 01-06.xls`, as the
    source for its own validated runs: `~/curonian/etl/20_load_lhmt_hydro.py`
    states the policy and its reason -- LHMT and the xls differ by a few percent
    on winter days (2013: 92 of 365 days by >2 %), so mixing them inside the
    validated window would silently change every scored run there.

    Re-ingesting the database to satisfy this model was tried on 2026-09-17 and
    reverted: it broke that project's "Nemunas regenerates byte-identical"
    property, which a 9 h 46 min run depends on. Reading LHMT here instead gives
    this model the authority's current record while leaving theirs alone. The
    divergence is asserted, not assumed -- see tests/test_forcing_provenance.py.
    """
    src = event.inputs_dir / "lhmt_smalininkai.csv"
    df = pd.read_csv(src, comment="#", parse_dates=["observationDateUtc"])
    df = df[df["waterDischarge"].notna()]
    lo, hi = (pd.Timestamp(d) for d in event.data_window)
    df = df[(df["observationDateUtc"] >= lo) & (df["observationDateUtc"] <= hi)]
    daily = pd.Series(df["waterDischarge"].astype(float).values, index=df["observationDateUtc"])
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
    hours = pd.date_range(event.tref, event.tstop, freq="h")
    corrected, fit = daily_fit_correction(gtsm, klaipeda_06, hours)
    bnd_pts = gpd.read_file(static / "boundary_points.geojson")             # static, shared
    bzs = boundary_forcing(corrected, len(bnd_pts), event)
    bzs.to_csv(out / "bzs.csv", index_label="time", float_format=common.CSV_FLOAT_FMT)

    wind = wind_forcing(event)
    wind.to_csv(out / "wind.csv", index_label="time", float_format=common.CSV_FLOAT_FMT)

    dis = discharge_forcing(event)
    dis.to_csv(out / "dis.csv", index_label="time", float_format=common.CSV_FLOAT_FMT)
    common.write_geojson(discharge_points(), static / "dis_points.geojson")  # static, shared: both events discharge at the same two points

    peak = corrected.loc[event.peak_window[0]:event.peak_window[1]]
    summary = (f"GTSM corrected by {fit['n_readings']} Klaipeda 06:00 readings: residual "
               f"{fit['resid_min']:+.3f}..{fit['resid_max']:+.3f} m (mean {fit['resid_mean']:+.3f}), "
               f"largest gap {fit['max_gap_h']:.0f} h\n"
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
