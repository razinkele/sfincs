"""Hourly total water level near Klaipėda from the GTSM-ERA5 reanalysis (CDS).

Dataset: sis-water-level-change-timeseries-cmip6, experiment reanalysis, hourly.
The download is a zip of monthly NetCDF files with a `stations` dimension.
"""
from __future__ import annotations

import zipfile
from pathlib import Path

import numpy as np
import pandas as pd
import xarray as xr

import common

XAVER = common.EVENTS["xaver_2013"]

DATASET = "sis-water-level-change-timeseries-cmip6"
REQUEST = {
    "variable": ["total_water_level"],
    "experiment": ["reanalysis"],
    "temporal_aggregation": ["hourly"],
    "year": ["2013"],
    "month": ["11", "12"],
    # "model" is not part of the reanalysis experiment's constraints (only
    # historical/future CMIP6 runs need it), but "version" is required even
    # for reanalysis; v2 is deprecated, v3 is current (checked against the
    # dataset's form.json/constraints.json on 2026-09-04).
    "version": ["v3"],
}
VAR_NAMES = ("waterlevel", "total_water_level", "water_level")
LON_NAMES = ("station_x_coordinate", "lon", "longitude")
LAT_NAMES = ("station_y_coordinate", "lat", "latitude")


def download(target: Path = XAVER.inputs_dir / "gtsm.zip") -> Path:
    import cdsapi
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists() and target.stat().st_size > 1_000_000:
        print(f"using cached {target}")
        return target
    cdsapi.Client().retrieve(DATASET, REQUEST, str(target))
    return target


def _pick(ds: xr.Dataset, names) -> str:
    for n in names:
        if n in ds.variables:
            return n
    raise KeyError(f"none of {names} in {list(ds.variables)}")


def _haversine_km(lon1, lat1, lon2, lat2):
    lon1, lat1, lon2, lat2 = map(np.radians, (lon1, lat1, lon2, lat2))
    a = np.sin((lat2 - lat1) / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin((lon2 - lon1) / 2) ** 2
    return 6371.0 * 2 * np.arcsin(np.sqrt(a))


def series_from_files(files: list[Path], lonlat=common.KLAIPEDA_MOUTH_LONLAT):
    parts, meta = [], None
    for f in sorted(files):
        with xr.open_dataset(f) as ds:
            var, lonn, latn = _pick(ds, VAR_NAMES), _pick(ds, LON_NAMES), _pick(ds, LAT_NAMES)
            lon, lat = ds[lonn].values.ravel(), ds[latn].values.ravel()
            d = _haversine_km(lon, lat, lonlat[0], lonlat[1])
            i = int(np.argmin(d))
            if meta is None:
                meta = {"station": i, "lon": float(lon[i]), "lat": float(lat[i]), "distance_km": float(d[i])}
            s = ds[var].isel({ds[var].dims[-1]: i}).to_series() if ds[var].dims[-1] != "time" \
                else ds[var].isel({ds[var].dims[0]: i}).to_series()
            parts.append(s)
    # kind="stable" so that the month files' overlap resolves the same way every run:
    # parts are concatenated in sorted-filename order, a stable sort preserves that
    # order within equal timestamps, and duplicated() then keeps the earlier file's
    # value. The default quicksort leaves the winner to numpy's partitioning.
    series = pd.concat(parts).sort_index(kind="stable")
    series = series[~series.index.duplicated()].astype(float)
    series.index = pd.DatetimeIndex(series.index).tz_localize(None)
    series = series.asfreq("h")
    if not series.notna().all():
        missing = series.index[series.isna()]
        raise ValueError(f"gaps in GTSM series: {len(missing)} missing hours, "
                         f"first {missing[0]}, last {missing[-1]}")
    series.name = "waterlevel_m"
    return series, meta


def extract_nearest(zip_path: Path, lonlat=common.KLAIPEDA_MOUTH_LONLAT):
    outdir = zip_path.with_suffix("")
    outdir.mkdir(exist_ok=True)
    with zipfile.ZipFile(zip_path) as z:
        names = [n for n in z.namelist() if n.endswith(".nc")]
        z.extractall(outdir, members=names)
    return series_from_files([outdir / n for n in names], lonlat)


def main(out: Path = XAVER.inputs_dir / "gtsm_klaipeda.csv") -> pd.Series:
    zip_path = download()
    series, meta = extract_nearest(zip_path)
    if meta["distance_km"] >= 60:
        raise ValueError(f"nearest GTSM station is {meta['distance_km']:.0f} km from the mouth "
                         f"(limit 60 km): station {meta['station']} at {meta['lon']}, {meta['lat']}")
    series.to_csv(out, index_label="time", float_format=common.CSV_FLOAT_FMT)
    print(f"wrote {out}: {series.index.min()} -> {series.index.max()}, station {meta}")
    return series


if __name__ == "__main__":
    main()
