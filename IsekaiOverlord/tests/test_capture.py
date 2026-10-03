"""Capture: Frame coordinate maths, and the real window backend when available."""

from __future__ import annotations

import numpy as np
import pytest

from iwol import Frame, ImageBackend, MssBackend, PrintWindowBackend, find_windows
from conftest import fixture_image


# --------------------------------------------------------------------------- #
# Frame — coordinates must survive cropping, because clicks are absolute
# --------------------------------------------------------------------------- #


def test_frame_size_and_blank_detection():
    flat = Frame(np.full((10, 20, 3), 7, dtype=np.uint8))
    assert flat.size == (20, 10)
    assert flat.is_blank()
    noisy = Frame(np.random.default_rng(0).integers(0, 255, (10, 20, 3), dtype=np.uint8))
    assert not noisy.is_blank()


def test_frame_crop_shifts_origin_so_coordinates_stay_absolute():
    img = np.zeros((100, 200, 3), dtype=np.uint8)
    frame = Frame(img, (1000, 500))
    crop = frame.crop((10, 20, 50, 40))
    assert crop.size == (50, 40)
    # origin must absorb the crop offset
    assert crop.origin == (1010, 520)
    # a point at (0,0) inside the crop is at (1010,520) on screen
    assert crop.to_screen(0, 0) == (1010, 520)
    assert frame.to_screen(10, 20) == (1010, 520)


def test_frame_local_screen_round_trip():
    frame = Frame(np.zeros((50, 50, 3), dtype=np.uint8), (300, 400))
    assert frame.to_local(*frame.to_screen(7, 9)) == (7, 9)


# --------------------------------------------------------------------------- #
# ImageBackend — replaying saved frames
# --------------------------------------------------------------------------- #


def test_image_backend_reads_a_saved_frame():
    path = fixture_image("adventure_hub")
    if not path.exists():
        pytest.skip("fixture not present")
    backend = ImageBackend(str(path))
    frame = backend.grab()
    assert frame.size == (2560, 1440)
    assert not frame.is_blank()


def test_image_backend_rejects_missing_file():
    with pytest.raises(FileNotFoundError):
        ImageBackend("definitely-not-here.png")


# --------------------------------------------------------------------------- #
# Live window (only runs when the game is actually open)
# --------------------------------------------------------------------------- #


@pytest.mark.live
def test_printwindow_captures_the_game_window():
    matches = find_windows("IsekaiWaifuOverlord")
    if not matches:
        pytest.skip("game window not open")
    backend = PrintWindowBackend(hwnd=matches[0][0])
    try:
        frame = backend.grab()
        assert frame.width > 100 and frame.height > 100
        assert not frame.is_blank(), "PrintWindow returned a flat frame"
        # must be a real image, not a solid colour
        assert frame.image.std() > 5
    finally:
        backend.close()


@pytest.mark.live
def test_repeated_captures_do_not_leak_gdi_handles():
    matches = find_windows("IsekaiWaifuOverlord")
    if not matches:
        pytest.skip("game window not open")
    backend = PrintWindowBackend(hwnd=matches[0][0])
    try:
        for _ in range(30):
            frame = backend.grab()
            assert frame.width > 0
    finally:
        backend.close()


@pytest.mark.live
def test_mss_backend_captures_the_desktop():
    backend = MssBackend()
    try:
        frame = backend.grab()
        assert frame.width > 0 and frame.height > 0
    finally:
        backend.close()
