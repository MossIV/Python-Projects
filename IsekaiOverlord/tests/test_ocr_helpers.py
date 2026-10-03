"""OCR helpers: number parsing, text normalisation, and the wide-crop padding fix."""

from __future__ import annotations

import numpy as np
import pytest

from iwol.ocr import TextLine, pad_for_ocr, parse_number


# --------------------------------------------------------------------------- #
# parse_number
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "text,expected",
    [
        ("671B", 671e9),
        ("69", 69),
        ("1,234", 1234),
        ("3430/13.0K", 3430),  # first number wins
        ("13.0K", 13_000),
        ("2.5M", 2.5e6),
        ("5089", 5089),
        ("0/16", 0),
    ],
)
def test_parse_number(text, expected):
    assert parse_number(text) == pytest.approx(expected)


def test_parse_number_handles_thousands_separator():
    # '1.234' in a UI is far more likely one-thousand-two-hundred-thirty-four
    # than 1.234, so a 3-digit tail after a dot is treated as a separator.
    assert parse_number("1.234") == pytest.approx(1234)


def test_parse_number_none_when_no_digits():
    assert parse_number("PROMOTE") is None
    assert parse_number("") is None


def test_parse_number_negative_and_spaces():
    assert parse_number("-500") == pytest.approx(-500)
    assert parse_number("1 234") == pytest.approx(1234)


# --------------------------------------------------------------------------- #
# TextLine
# --------------------------------------------------------------------------- #


def test_textline_normalized_strips_spacing_dropped_by_ocr():
    line = TextLine(text="evasion by 5% for 5 seconds", score=0.9, box=(0, 0, 10, 10))
    assert line.normalized == "evasionby5for5seconds"


def test_textline_center():
    line = TextLine(text="x", score=1.0, box=(10, 20, 30, 40))
    assert line.center == (20, 30)


# --------------------------------------------------------------------------- #
# pad_for_ocr  — regression test for the bug that made nav bars read as empty
# --------------------------------------------------------------------------- #


def test_pad_for_ocr_pads_wide_short_crop():
    wide = np.zeros((79, 921, 3), dtype=np.uint8)  # aspect 11.7:1
    padded, dx, dy = pad_for_ocr(wide)
    assert dx == 0
    assert padded.shape[0] > wide.shape[0]
    assert padded.shape[1] == wide.shape[1]
    # aspect is now inside the detector's working range
    assert padded.shape[1] / padded.shape[0] <= 4.0
    # original content sits `dy` pixels down, so coordinates must shift by dy
    assert dy > 0
    assert padded.shape[0] - dy >= wide.shape[0]


def test_pad_for_ocr_leaves_normal_aspect_alone():
    normal = np.zeros((600, 800, 3), dtype=np.uint8)  # 1.33:1
    padded, dx, dy = pad_for_ocr(normal)
    assert padded.shape == normal.shape
    assert (dx, dy) == (0, 0)


def test_pad_for_ocr_does_not_upscale_narrow_tall():
    tall = np.zeros((400, 100, 3), dtype=np.uint8)
    padded, dx, dy = pad_for_ocr(tall)
    assert padded.shape == tall.shape
    assert (dx, dy) == (0, 0)


def test_pad_for_ocr_handles_degenerate_input():
    empty = np.zeros((0, 0, 3), dtype=np.uint8)
    padded, dx, dy = pad_for_ocr(empty)
    assert (dx, dy) == (0, 0)
