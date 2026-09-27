"""map_data: the Map tab's data layer (no Shiny)."""
import base64
import io
import os
from pathlib import Path

import netCDF4 as nc
import numpy as np
import pandas as pd
import pytest
from PIL import Image

import map_core as mc
import map_data as md
import map_fixture as fx
import sfincs_data as sd


def _decode(uri: str) -> np.ndarray:
    assert uri.startswith("data:image/png;base64,")
    return np.asarray(Image.open(io.BytesIO(base64.b64decode(uri.split(",", 1)[1]))))


def _lonlat(row, col):
    lon, lat = mc.to_lonlat(*fx.cell_xy(row, col))
    return float(lon), float(lat)


def test_load_run_uses_the_cache_when_valid(synthetic):
    mc.export_cache(sd.RUNS_DIR / synthetic)
    rm = md.load_run(synthetic)
    assert rm.cached and rm.series is not None
    assert rm.labels[0] == "2013-04-05 00:00" and len(rm.times) == fx.HOURS


def test_stale_cache_falls_back_to_the_map_file(synthetic):
    run_dir = sd.RUNS_DIR / synthetic
    mc.export_cache(run_dir)
    st = (run_dir / "sfincs_map.nc").stat()
    os.utime(run_dir / "sfincs_map.nc", ns=(st.st_atime_ns, st.st_mtime_ns + 1_000_000_000))
    rm = md.load_run(synthetic)
    assert not rm.cached and rm.series is None
    assert len(rm.labels) == fx.HOURS                      # still plays
    cs = md.cell_series(rm, *_lonlat(10, 12))
    assert cs.slow                                         # never the stale series


def test_a_re_export_is_picked_up(synthetic):
    run_dir = sd.RUNS_DIR / synthetic
    mc.export_cache(run_dir)
    first = md.load_run(synthetic)
    mc.export_cache(run_dir)
    assert md.load_run(synthetic) is not first


def test_frame_level_and_change(synthetic):
    rm = md.load_run(synthetic)
    assert md.frame(rm, 3, "level")[10, 12] == pytest.approx(0.0)
    assert md.frame(rm, 3, "change")[10, 12] == pytest.approx(0.3)
    assert md.frame(rm, "max", "level")[10, 18] == pytest.approx(0.25)
    assert md.frame(rm, "max", "change")[10, 18] == pytest.approx(0.55)


def test_render_png_shape_and_transparency(synthetic):
    rm = md.load_run(synthetic)
    img = _decode(md.frame_image(rm, 0, "level"))
    assert img.shape == rm.warp.index.shape + (4,)
    values = md.frame(rm, 0, "level").ravel()
    idx = rm.warp.index
    wet = np.zeros(idx.shape, bool)
    wet[idx >= 0] = np.isfinite(values[idx[idx >= 0]])
    assert (img[..., 3][~wet] == 0).all()
    assert (img[..., 3][wet] == 255).all() and wet.any()


def test_frame_images_are_memoised(synthetic):
    rm = md.load_run(synthetic)
    assert md.frame_image(rm, 2, "change") is md.frame_image(rm, 2, "change")


def test_cell_series_cached_and_slow_paths_agree(synthetic):
    rm_slow = md.load_run(synthetic)
    slow = md.cell_series(rm_slow, *_lonlat(10, 12))
    mc.export_cache(sd.RUNS_DIR / synthetic)
    fast = md.cell_series(md.load_run(synthetic), *_lonlat(10, 12))
    assert slow.slow and not fast.slow
    assert (fast.row, fast.col) == (10, 12)
    np.testing.assert_allclose(fast.series.values, slow.series.values, atol=2e-3)
    assert fast.zb == pytest.approx(-0.15) and fast.zsmax == pytest.approx(0.25)


def test_locate_rejects_outside_and_inactive(synthetic):
    rm = md.load_run(synthetic)
    assert md.locate(rm, *_lonlat(1, 27)) is None             # inactive, inside the bbox
    lon, lat = mc.to_lonlat(fx.X0 - 0.6 * fx.D, fx.Y0 + 5 * fx.D)
    assert md.locate(rm, float(lon), float(lat)) is None      # just west of the grid edge
    lon, lat = mc.to_lonlat(fx.X0 - 0.4 * fx.D, fx.Y0 + 5 * fx.D)
    assert md.locate(rm, float(lon), float(lat)) == (5, 0)    # still inside cell (5, 0)
    assert md.cell_series(rm, *_lonlat(1, 27)) is None


def test_slow_read_releases_the_lock_between_blocks(synthetic, monkeypatch):
    import threading

    class Counting:
        def __init__(self):
            self.n, self._lock = 0, threading.Lock()

        def __enter__(self):
            self.n += 1
            self._lock.acquire()

        def __exit__(self, *exc):
            self._lock.release()

    rm = md.load_run(synthetic)                  # no cache: the slow path
    md.frame(rm, "max", "level")                 # warm zsmax so only the column read counts
    counting = Counting()
    monkeypatch.setattr(mc, "NC_LOCK", counting)
    monkeypatch.setattr(md, "SLOW_BLOCK", 2)
    cs = md.cell_series(rm, *_lonlat(10, 12))
    assert cs.slow and counting.n == 3           # 6 frames in blocks of 2


def _write_obs(run, rows):
    fx.write_gauge_obs(sd.results_path(run, "gauge_obs.csv"), rows)


def _by_name(records):
    return {r["name"]: r for r in records}


def test_gauge_error_only_within_thirty_minutes_of_a_reading(synthetic):
    _write_obs(synthetic, [("Klaipeda", "2013-04-05 01:40:00", -0.16)])
    at2 = _by_name(md.stations_at(synthetic, pd.Timestamp("2013-04-05 02:00")))
    k = at2["Klaipeda"]
    assert k["kind"] == "gauge"
    # model at the READING's time (01:40 -> -0.1333) minus the reading
    assert k["error"] == pytest.approx(fx.level(100 / 60) - (-0.16), abs=1e-3)
    assert "01:40" in k["text"] and "+0.03" in k["text"]
    at4 = _by_name(md.stations_at(synthetic, pd.Timestamp("2013-04-05 04:00")))
    assert at4["Klaipeda"]["kind"] == "no_reading" and at4["Klaipeda"]["error"] is None
    assert "no reading this hour" in at4["Klaipeda"]["text"]


def test_thirty_minute_bound_is_inclusive_and_ties_take_the_earlier_reading(synthetic):
    _write_obs(synthetic, [("Klaipeda", "2013-04-05 01:30:00", -0.20),
                           ("Klaipeda", "2013-04-05 02:30:00", -0.05)])
    k = _by_name(md.stations_at(synthetic, pd.Timestamp("2013-04-05 02:00")))["Klaipeda"]
    assert k["kind"] == "gauge" and "01:30" in k["text"]


def test_modelled_only_stations_are_hollow_and_rusne_is_flagged(synthetic):
    _write_obs(synthetic, [("Klaipeda", "2013-04-05 02:00:00", -0.10)])
    at = _by_name(md.stations_at(synthetic, pd.Timestamp("2013-04-05 02:00")))
    assert at["Rusne"]["kind"] == "modelled" and "gauge zero unknown" in at["Rusne"]["text"]
    assert at["Silute"]["kind"] == "modelled" and at["Silute"]["fill"][3] == 0
    assert at["Klaipeda"]["fill"][3] == 255


def test_error_colour_is_signed_and_clipped(synthetic):
    _write_obs(synthetic, [("Klaipeda", "2013-04-05 02:00:00", -1.0)])   # model 0.9 m too high
    k = _by_name(md.stations_at(synthetic, pd.Timestamp("2013-04-05 02:00")))["Klaipeda"]
    red = k["fill"]
    _write_obs(synthetic, [("Klaipeda", "2013-04-05 02:00:00", 1.0)])    # model far too low
    blue = _by_name(md.stations_at(synthetic, pd.Timestamp("2013-04-05 02:00")))["Klaipeda"]["fill"]
    assert red[0] > red[2] and blue[2] > blue[0]
    _write_obs(synthetic, [("Klaipeda", "2013-04-05 02:00:00", -0.35)])  # +0.25, past the clip
    clipped = _by_name(md.stations_at(synthetic, pd.Timestamp("2013-04-05 02:00")))["Klaipeda"]["fill"]
    assert clipped == red


def test_max_view_compares_maxima_in_the_scoring_window(synthetic):
    _write_obs(synthetic, [("Klaipeda", "2013-04-05 01:40:00", -0.16),
                           ("Klaipeda", "2013-04-05 03:00:00", -0.02)])
    k = _by_name(md.stations_at(synthetic, "max"))["Klaipeda"]
    assert k["kind"] == "gauge"
    assert k["error"] == pytest.approx(fx.level(5) - (-0.02), abs=1e-3)
    assert "05:00" in k["text"] and "03:00" in k["text"]


def test_max_view_handles_an_all_dry_station_without_crashing(synthetic, monkeypatch):
    _write_obs(synthetic, [("Klaipeda", "2013-04-05 02:00:00", -0.10)])
    his = sd.station_levels(synthetic).copy()
    his["Silute"] = float("nan")     # unscored station, entirely dry
    his["Klaipeda"] = float("nan")   # scored station, entirely dry
    monkeypatch.setattr(sd, "station_levels", lambda run: his)
    at = _by_name(md.stations_at(synthetic, "max"))
    assert set(at) == {"Klaipeda", "Rusne", "Silute"}
    assert at["Silute"]["kind"] == "modelled" and "n/a" in at["Silute"]["text"]
    assert at["Klaipeda"]["kind"] == "no_reading" and "n/a" in at["Klaipeda"]["text"]


def test_no_gauge_csv_means_every_station_is_modelled_only(synthetic):
    kinds = {r["kind"] for r in md.stations_at(synthetic, pd.Timestamp("2013-04-05 02:00"))}
    assert kinds == {"modelled"}


def test_overlays_come_from_the_run_and_inputs_in_lonlat(synthetic):
    ov = md.overlays(synthetic)
    assert ov["missing"] == []
    assert len(ov["boundary"]) == 2 and len(ov["inflows"]) == 1
    lon, lat = ov["inflows"][0]["position"]
    assert 20.0 < lon < 23.0 and 54.0 < lat < 57.0
    ring = ov["outline"]["features"][0]["geometry"]["coordinates"][0]
    assert all(20.0 < p[0] < 23.0 and 54.0 < p[1] < 57.0 for p in ring)
    assert "crs" not in ov["outline"]


def test_a_missing_overlay_is_reported_not_fatal(synthetic):
    (sd.DATA_DIR / "inputs" / "channels.geojson").unlink()
    (sd.RUNS_DIR / synthetic / "sfincs.src").unlink()
    ov = md.overlays(synthetic)
    assert set(ov["missing"]) == {"channels.geojson", "sfincs.src"}
    assert ov["channels"]["features"] == [] and ov["inflows"] == []


def test_legend_titles_and_max_note(synthetic):
    rm = md.load_run(synthetic)
    lg = md.legend(rm, "change", is_max=True)
    assert lg["title"].startswith("Change from start")
    assert lg["vmin"] == -lg["vmax"] and len(lg["colors"]) == 9
    assert any("clipped" in n for n in lg["notes"])


REAL = Path("/home/razinka/sfincs/curonian/runs/april_2013")


@pytest.mark.skipif(not mc.cache_valid(REAL), reason="april_2013 map cache not exported on this machine")
def test_real_april_frame_and_cached_series(monkeypatch):
    monkeypatch.setattr(sd, "RUNS_DIR", REAL.parent)
    rm = md.load_run("april_2013")
    img = _decode(md.frame_image(rm, 300, "level"))
    assert img.shape[:2] == rm.warp.index.shape
    assert 1000 <= img.shape[1] <= 1080 and 1100 <= img.shape[0] <= 1180    # ~1040 x 1138 at 176 m
    assert (img[..., 3] == 0).any() and (img[..., 3] == 255).any()
    row, col = 550, 500
    lon, lat = mc.to_lonlat(rm.grid.x0 + col * rm.grid.dx, rm.grid.y0 + row * rm.grid.dy)
    cs = md.cell_series(rm, float(lon), float(lat))
    with nc.Dataset(REAL / "sfincs_map.nc") as d:
        direct = np.ma.filled(d["zs"][:, row, col], np.nan).astype(float)
    np.testing.assert_allclose(cs.series.values, direct, atol=2e-3)
    assert not cs.slow


def test_stations_without_sfincs_obs_is_empty_not_fatal(synthetic):
    (sd.RUNS_DIR / synthetic / "sfincs.obs").unlink()
    assert md.stations_at(synthetic, pd.Timestamp("2013-04-05 02:00")) == []
    assert md.stations_at(synthetic, "max") == []
    assert "sfincs.obs" in md.overlays(synthetic)["missing"]


def test_safe_load_reports_an_unreadable_map_instead_of_raising(synthetic, monkeypatch):
    rm, err = md.safe_load(synthetic)
    assert rm is not None and err is None
    for exc in (ValueError("bad header"), OSError("HDF error"), KeyError("zs")):
        def boom(run, exc=exc):
            raise exc
        monkeypatch.setattr(md, "load_run", boom)
        rm, err = md.safe_load(synthetic)
        assert rm is None and err and type(exc).__name__ in err


@pytest.mark.parametrize("missing", ["zs", "zb", "msk"])
def test_safe_load_reports_a_map_file_missing_a_variable(synthetic, missing):
    """A map file that opens but lacks a variable (truncated write, wrong file
    swapped in): netCDF4 raises IndexError for the missing name, which must
    become a message, not an exception that closes the session."""
    path = sd.RUNS_DIR / synthetic / "sfincs_map.nc"
    with nc.Dataset(path) as src, nc.Dataset(path.with_suffix(".tmp"), "w") as dst:
        for name, dim in src.dimensions.items():
            dst.createDimension(name, len(dim))
        for name, var in src.variables.items():
            if name == missing:
                continue
            out = dst.createVariable(name, var.dtype, var.dimensions,
                                     fill_value=getattr(var, "_FillValue", None))
            out.setncatts({k: var.getncattr(k) for k in var.ncattrs() if k != "_FillValue"})
            out[:] = var[:]
    path.with_suffix(".tmp").replace(path)
    rm, err = md.safe_load(synthetic)
    assert rm is None
    assert err and missing in err


def test_safe_load_without_a_map_file_is_none_without_error(synthetic):
    (sd.RUNS_DIR / synthetic / "sfincs_map.nc").unlink()
    assert md.safe_load(synthetic) == (None, None)


def test_read_errors_cover_what_netcdf_raises_for_a_missing_variable():
    assert IndexError in md.READ_ERRORS


# ---- corrupt (not missing) run files degrade, never raise --------------------

@pytest.mark.parametrize("fname, key", [("sfincs.bnd", "boundary"), ("sfincs.src", "inflows")])
def test_a_corrupt_point_file_is_reported_not_fatal(synthetic, fname, key):
    (sd.RUNS_DIR / synthetic / fname).write_text("330050.0 not-a-number\n")
    ov = md.overlays(synthetic)
    assert ov[key] == [] and fname in ov["unreadable"]


def test_a_corrupt_obs_file_means_no_stations(synthetic):
    (sd.RUNS_DIR / synthetic / "sfincs.obs").write_text('x y "Klaipeda"\n')
    assert md.stations_at(synthetic, pd.Timestamp("2013-04-05 02:00")) == []
    assert "sfincs.obs" in md.overlays(synthetic)["unreadable"]


def test_a_corrupt_geojson_is_reported_not_fatal(synthetic):
    (sd.DATA_DIR / "inputs" / "channels.geojson").write_text("{not json")
    ov = md.overlays(synthetic)
    assert ov["channels"]["features"] == [] and "channels.geojson" in ov["unreadable"]


@pytest.mark.parametrize("content", ["not,a,gauge,file\n1,2,3,4\n",
                                     "site,time,level_m\nKlaipeda,yesterday-ish,0.1\n",
                                     "site,time,level_m\nKlaipeda,2013-04-05 02:00:00,high\n"])
def test_a_corrupt_gauge_csv_means_modelled_only(synthetic, content):
    path = sd.results_path(synthetic, "gauge_obs.csv")
    path.write_text(content)
    assert md.gauge_obs(synthetic).empty
    assert md.gauge_obs_unreadable(synthetic)
    kinds = {r["kind"] for r in md.stations_at(synthetic, pd.Timestamp("2013-04-05 02:00"))}
    assert kinds == {"modelled"}


def test_a_corrupt_his_file_means_no_model_levels(synthetic):
    (sd.RUNS_DIR / synthetic / "sfincs_his.nc").write_bytes(b"\x89HDF garbage" * 10)
    assert sd.station_levels(synthetic).empty
    assert md.his_unreadable(synthetic)
    records = md.stations_at(synthetic, pd.Timestamp("2013-04-05 02:00"))
    assert len(records) == 3 and all("n/a" in r["text"] for r in records)
