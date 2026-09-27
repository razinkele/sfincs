"""Acceptance tests for the Map tab (spec: Testing -> Playback)."""
import statistics

from playwright.sync_api import Page, expect


def _open_map(page: Page, url: str, variant: str) -> None:
    page.goto(url)
    page.select_option("#variant", variant)
    page.get_by_role("tab", name="Map").click()
    expect(page.locator("#map_time")).to_contain_text("UTC", timeout=30_000)
    page.wait_for_function("window.__mapAcks && window.__mapAcks.length > 0", timeout=30_000)


def _acks(page: Page) -> list[dict]:
    return page.evaluate("window.__mapAcks.slice()")


def test_playback_pace_on_april(page: Page, app_url: str):
    _open_map(page, app_url, "april_2013")
    start = len(_acks(page))
    page.click("#map_play")
    page.wait_for_function(f"window.__mapAcks.length >= {start + 101}", timeout=120_000)
    page.click("#map_play")
    times = [a["t"] for a in _acks(page)[start:start + 101]]
    gaps = [b - a for a, b in zip(times, times[1:])]
    assert statistics.median(gaps) <= 300, f"median {statistics.median(gaps):.0f} ms"
    assert max(gaps) <= 1000, f"max {max(gaps):.0f} ms"


def test_slow_link_drops_frames_not_time(page: Page, app_url: str):
    _open_map(page, app_url, "april_2013")
    # Chromium's Network.emulateNetworkConditions does not throttle WebSocket
    # throughput, so a slow link is simulated by delaying each acknowledgement.
    page.evaluate("window.__mapAckDelay = 800")
    start_acks = len(_acks(page))
    page.click("#map_play")
    page.wait_for_timeout(10_000)
    page.click("#map_play")
    page.wait_for_timeout(2_000)      # let the last delayed acks and slider update land
    shown = int(page.locator("#map_hour").input_value())
    sent = len(_acks(page)) - start_acks
    assert shown >= 32, f"hour {shown} after 10 s: time fell behind"        # 0.8 x 40 ticks
    assert sent < shown, "every frame was delivered: no dropping happened with 800 ms acks"


def test_switching_run_mid_playback_resets_cleanly(page: Page, app_url: str):
    _open_map(page, app_url, "april_2013")
    page.click("#map_play")
    page.wait_for_timeout(2_000)
    page.select_option("#variant", "xaver_2013")
    expect(page.locator("#map_time")).to_contain_text("(1/313)", timeout=30_000)
    switch_at = page.evaluate("performance.now()")
    page.wait_for_timeout(1_500)
    late = [a for a in _acks(page) if a["t"] > switch_at + 500 and a["run"] != "xaver_2013"]
    assert late == []
    assert page.locator("#map_play").inner_text() == "Play"


def test_click_on_water_draws_a_series(page: Page, app_url: str):
    _open_map(page, app_url, "april_2013")
    expect(page.locator("#map_cell_caption")).to_have_text("")        # placeholder plot, no series
    box = page.locator("#map canvas").first.bounding_box()
    page.mouse.click(box["x"] + box["width"] * 0.45, box["y"] + box["height"] * 0.55)
    expect(page.locator("#map_cell_caption")).to_contain_text("cell row", timeout=15_000)
