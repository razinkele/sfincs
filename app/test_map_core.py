"""map_core: the numerics shared by the export and the Map tab."""
import numpy as np
import pytest
from pyproj import Transformer

import map_core as mc
import map_fixture as fx
import sfincs_data as sd


def _map_nc(run):
    return sd.RUNS_DIR / run / "sfincs_map.nc"


def test_read_grid_matches_the_fixture(synthetic):
    g = mc.read_grid(_map_nc(synthetic))
    assert g.shape == (fx.N, fx.M)
    assert (g.x0, g.y0, g.dx, g.dy) == (fx.X0, fx.Y0, fx.D, fx.D)
    assert g.active.sum() == fx.N * fx.M - 15
    assert np.isnan(g.zb[1, 27]) and g.zb[4, 12] == pytest.approx(-0.15)
    assert mc.hour_labels(g.times) == [f"2013-04-05 0{h}:00" for h in range(fx.HOURS)]


def test_read_frame_is_nan_where_sfincs_wrote_no_level(synthetic):
    f0 = mc.read_frame(_map_nc(synthetic), 0)
    assert f0[10, 9] == pytest.approx(-0.30)
    assert np.isnan(f0[10, 10])            # bed -0.25 above the starting level
    f5 = mc.read_frame(_map_nc(synthetic), 5)
    assert f5[10, 18] == pytest.approx(0.20) and np.isnan(f5[10, 19])
    zmax = mc.read_zsmax(_map_nc(synthetic))
    assert zmax[10, 18] == pytest.approx(0.25) and np.isnan(zmax[10, 19])


def test_read_points_parses_names_and_bare_points(synthetic):
    obs = mc.read_points(sd.RUNS_DIR / synthetic / "sfincs.obs")
    assert [p[2] for p in obs] == ["Klaipeda", "Rusne", "Silute"]
    bnd = mc.read_points(sd.RUNS_DIR / synthetic / "sfincs.bnd")
    assert len(bnd) == 2 and bnd[0][2] is None


def test_lonlat_round_trip():
    lon, lat = mc.to_lonlat(fx.X0, fx.Y0)
    x, y = mc.from_lonlat(lon, lat)
    assert (float(x), float(y)) == pytest.approx((fx.X0, fx.Y0), abs=1e-3)


def test_warp_maps_each_pixel_to_its_nearest_cell_north_up(synthetic):
    g = mc.read_grid(_map_nc(synthetic))
    w = mc.compute_warp(g)
    to_web = Transformer.from_crs(4326, 3857, always_xy=True)
    west, south = to_web.transform(w.bounds[0], w.bounds[1])
    east, north = to_web.transform(w.bounds[2], w.bounds[3])
    height, width = w.index.shape
    assert width == pytest.approx((east - west) / mc.PIXEL_M, abs=1e-6)
    assert height == pytest.approx((north - south) / mc.PIXEL_M, abs=1e-6)
    from_web = Transformer.from_crs(3857, 3346, always_xy=True)
    checked = 0
    for i in range(height):
        for j in range(width):
            k = int(w.index[i, j])
            if k < 0:
                continue
            row, col = divmod(k, fx.M)
            mx, my = from_web.transform(west + (j + 0.5) * mc.PIXEL_M, north - (i + 0.5) * mc.PIXEL_M)
            assert abs(mx - (fx.X0 + col * fx.D)) <= fx.D / 2 + 1e-6
            assert abs(my - (fx.Y0 + row * fx.D)) <= fx.D / 2 + 1e-6
            checked += 1
    assert checked > 100
    # ceil() pads the raster by up to one pixel at the north and east edges, so
    # compare the first and last image rows that actually hold an active cell.
    covered = [i for i in range(height) if (w.index[i] >= 0).any()]
    rows_top = [int(k) // fx.M for k in w.index[covered[0]] if k >= 0]
    rows_bottom = [int(k) // fx.M for k in w.index[covered[-1]] if k >= 0]
    assert min(rows_top) > max(rows_bottom), "image row 0 must be the northern edge"


def test_warp_marks_inactive_cells_minus_one(synthetic):
    g = mc.read_grid(_map_nc(synthetic))
    w = mc.compute_warp(g)
    flat = set(int(k) for k in w.index.ravel() if k >= 0)
    assert 1 * fx.M + 27 not in flat          # inactive corner cell
    assert 10 * fx.M + 12 in flat


def test_map_reads_wait_for_the_netcdf_lock(synthetic):
    """netcdf-c is not thread-safe: a click reads in a worker thread while the
    event loop reads frames, so every read must hold map_core.NC_LOCK."""
    import threading
    done = threading.Event()
    with mc.NC_LOCK:
        t = threading.Thread(target=lambda: (mc.read_frame(_map_nc(synthetic), 0), done.set()))
        t.start()
        assert not done.wait(0.3), "read_frame ran while another thread held NC_LOCK"
    t.join(5)
    assert done.is_set()
