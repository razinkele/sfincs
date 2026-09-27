"""map_ui: the playback state machine, layer specs and the tab's UI."""
import pytest

import map_data as md
import map_ui as mu
import sfincs_data as sd


def test_ticks_advance_on_schedule_and_stop_at_the_end():
    pb = mu.Playback()
    pb.switch("a")
    pb.play(3)
    assert pb.tick(3) and pb.hour == 1
    assert pb.tick(3) and pb.hour == 2
    assert not pb.tick(3) and not pb.playing and pb.hour == 2


def test_play_at_the_end_restarts_from_zero():
    pb = mu.Playback()
    pb.switch("a")
    pb.hour = 2
    pb.play(3)
    assert pb.playing and pb.hour == 0


def test_an_unacknowledged_frame_defers_sending_but_not_time():
    pb = mu.Playback()
    pb.switch("a")
    pb.play(10)
    assert pb.claim_send() == 1
    assert pb.tick(10) and pb.hour == 1            # time moves on regardless
    assert pb.claim_send() is None and pb.pending  # frame 1 not acked yet: hold
    assert pb.tick(10) and pb.hour == 2
    assert pb.ack("a", 1) is True                  # ack arrives: send the latest hour now
    assert pb.claim_send() == 2 and not pb.pending


def test_stale_ack_from_previous_run_is_ignored():
    pb = mu.Playback()
    pb.switch("april")
    assert pb.claim_send() == 1                    # april frame in flight
    pb.switch("xaver")                             # switch resets the gate
    assert pb.claim_send() == 2                    # xaver's first frame goes straight out
    assert pb.claim_send() is None                 # ...and gates the next one
    assert pb.ack("april", 1) is False             # late april ack: must not unlock xaver
    assert pb.claim_send() is None
    assert pb.ack("xaver", 2) is True
    assert pb.claim_send() == 3


def test_switch_stops_and_rewinds():
    pb = mu.Playback()
    pb.switch("a")
    pb.play(5)
    pb.tick(5)
    pb.switch("b")
    assert (pb.run, pb.hour, pb.playing) == ("b", 0, False)


def test_layers_build_for_the_synthetic_run(synthetic):
    rm = md.load_run(synthetic)
    layers = mu.map_layers(rm, md.overlays(synthetic), md.frame_image(rm, 0, "level"))
    assert [l["id"] for l in layers] == ["water", "outline", "channels", "boundary", "inflows", "stations"]
    water = layers[0]
    assert water["bounds"] == list(rm.warp.bounds)
    assert all(l.get("pickable") is False for l in layers if l["id"] != "stations")
    assert layers[-1]["pickable"] is True


def test_panel_builds():
    from shiny import ui
    # a nav_panel only renders inside a navset, and a NavSet has no HTML __str__
    html = str(ui.TagList(ui.navset_tab(mu.map_panel())))
    for element in ("map_play", "map_hour", "map_quantity", "map_cell_plot", "map_cell_caption",
                    "www/map_ack.js"):
        assert element in html


@pytest.mark.parametrize("variant", sd.list_variants())
def test_layers_build_for_every_published_variant(variant):
    if not md.map_available(variant):
        pytest.skip(f"no sfincs_map.nc for {variant}")
    rm = md.load_run(variant)
    layers = mu.map_layers(rm, md.overlays(variant), "data:image/png;base64,")
    assert layers[0]["id"] == "water"


def test_current_series_keeps_only_the_current_runs_result():
    cs = object()
    assert mu.current_series(("april", cs), "april") is cs
    assert mu.current_series(("april", cs), "xaver") is None     # stale: previous run's cell
    assert mu.current_series(None, "april") is None


def test_an_unsent_frame_releases_the_gate():
    """A frame claimed but never sent (its render failed) must not leave the
    gate waiting for an acknowledgement that can never arrive."""
    pb = mu.Playback()
    pb.switch("a")
    seq = pb.claim_send()
    pb.release(seq)
    assert pb.claim_send() == seq + 1        # the next frame goes straight out
