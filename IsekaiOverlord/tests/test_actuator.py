"""Actuator safety: dry-run is inert, the kill switch works, coordinates are checked.

No test here injects real input.  ``SendInputActuator`` is exercised only through
its pure helpers (``_check`` / ``_to_absolute``), which never call SendInput.
"""

from __future__ import annotations

import pytest

import iwol.actuator as act


# --------------------------------------------------------------------------- #
# dry run — must be completely inert
# --------------------------------------------------------------------------- #


def test_dry_run_records_and_never_touches_the_machine():
    a = act.DryRunActuator()
    assert a.dry_run is True
    assert a.click(10, 20).ok
    assert a.move(1, 2).ok
    assert a.drag(0, 0, 5, 5).ok
    assert a.scroll(1, 1, 3).ok
    assert a.key("esc").ok
    assert [name for name, _ in a.actions] == ["click", "move", "drag", "scroll", "key"]
    assert a.actions[0][1] == (10, 20, "left")


# --------------------------------------------------------------------------- #
# kill switch
# --------------------------------------------------------------------------- #


def test_sentinel_raises_when_stopped():
    armed = {"stop": False}
    s = act.SentinelActuator(act.DryRunActuator(), should_stop=lambda: armed["stop"])
    assert s.click(1, 1).ok
    armed["stop"] = True
    with pytest.raises(act.Aborted):
        s.click(1, 1)


def test_sentinel_forwards_dry_run_flag():
    assert act.SentinelActuator(act.DryRunActuator()).dry_run is True
    assert act.SentinelActuator(act.SendInputActuator(hwnd=None)).dry_run is False


# --------------------------------------------------------------------------- #
# coordinate guards — a bot that clicks outside the game is worse than no bot
# --------------------------------------------------------------------------- #


def test_sendinput_rejects_click_outside_the_game_window(monkeypatch):
    monkeypatch.setattr(act, "window_rect", lambda hwnd: (100, 100, 900, 700))
    a = act.SendInputActuator(hwnd=1234)

    inside = a._check(500, 400)
    assert inside is None

    assert a._check(50, 400) is not None      # left of the window
    assert a._check(500, 50) is not None      # above the window
    assert a._check(950, 400) is not None     # right of the window
    assert a._check(500, 800) is not None     # below the window


def test_sendinput_without_hwnd_skips_the_window_check():
    a = act.SendInputActuator(hwnd=None)
    assert a._check(99999, 99999) is None


def test_out_of_window_click_is_refused_not_sent(monkeypatch):
    monkeypatch.setattr(act, "window_rect", lambda hwnd: (0, 0, 100, 100))
    a = act.SendInputActuator(hwnd=1)
    res = a.click(500, 500)  # must return a failure, never reach SendInput
    assert res.ok is False
    assert "outside window" in res.detail


def test_absolute_coordinate_normalisation_is_in_range():
    a = act.SendInputActuator(hwnd=None)
    for x, y in [(0, 0), (2560, 1440), (1280, 720)]:
        nx, ny = a._to_absolute(x, y)
        assert 0 <= nx <= 65535
        assert 0 <= ny <= 65535


@pytest.mark.live
def test_screen_to_client_is_relative_to_the_window():
    """Screen->client conversion is what makes PostMessage clicks land correctly.

    Verified against the real game window (its client origin is the window
    origin, so a point inside the window must map to itself minus that origin).
    """
    from iwol.capture import find_windows

    matches = find_windows("IsekaiWaifuOverlord")
    if not matches:
        pytest.skip("game window not open")
    hwnd = matches[0][0]

    left, top, _right, _bottom = act.window_rect(hwnd)
    cx, cy = act.screen_to_client(hwnd, left + 100, top + 50)
    assert (cx, cy) == (100, 50)


# --------------------------------------------------------------------------- #
# PostMessage path
# --------------------------------------------------------------------------- #


def test_postmessage_converts_screen_to_client_coords(monkeypatch):
    sent = []
    a = act.PostMessageActuator(hwnd=42)
    monkeypatch.setattr(a, "_post", lambda msg, wp, lp: sent.append((msg, wp, lp)) or True)
    monkeypatch.setattr(act, "screen_to_client", lambda hwnd, x, y: (x - 100, y - 50))

    a.click(150, 90)
    msgs = [m for m, _w, _l in sent]
    assert msgs == [act.WM_MOUSEMOVE, act.WM_LBUTTONDOWN, act.WM_LBUTTONUP]
    # lParam must carry *client* coordinates, not screen coordinates
    assert act._make_lparam(50, 40) == sent[1][2]


def test_make_lparam_packs_x_and_y():
    assert act._make_lparam(0x1234, 0x5678) == (0x5678 << 16) | 0x1234
