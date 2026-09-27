"""map_data: the Map tab's data layer (no Shiny)."""
import base64
import io
import os

import numpy as np
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
