"""Vision primitives: template matching, fingerprints, change detection."""

from __future__ import annotations

import cv2
import numpy as np
import pytest

from iwol import Frame
from iwol.vision import (
    color_distance,
    color_profile,
    diff_ratio,
    dominant_colors,
    match_all,
    match_template,
    mean_brightness,
    phash,
    phash_distance,
)


@pytest.fixture
def canvas_with_patches():
    """A frame with two identical green squares stamped into it."""
    img = np.full((300, 400, 3), (30, 30, 30), dtype=np.uint8)
    patch = np.full((24, 24, 3), (60, 200, 60), dtype=np.uint8)
    cv2.rectangle(patch, (4, 4), (19, 19), (90, 240, 90), -1)
    img[40:64, 50:74] = patch
    img[200:224, 300:324] = patch
    return Frame(img, (0, 0)), patch


def test_match_template_finds_the_patch(canvas_with_patches):
    frame, patch = canvas_with_patches
    hit = match_template(frame, patch, name="green", threshold=0.9)
    assert hit is not None
    assert hit.score > 0.99
    assert hit.name == "green"
    # centre of the first patch
    assert hit.center in {(62, 52), (312, 212)}


def test_match_template_respects_threshold(canvas_with_patches):
    frame, patch = canvas_with_patches
    noise = np.random.default_rng(0).integers(0, 255, (24, 24, 3), dtype=np.uint8)
    assert match_template(frame, noise, threshold=0.99) is None


def test_match_all_finds_both_patches(canvas_with_patches):
    frame, patch = canvas_with_patches
    hits = match_all(frame, patch, threshold=0.9)
    assert len(hits) == 2


def test_match_template_maps_to_screen_coordinates(canvas_with_patches):
    frame, patch = canvas_with_patches
    offset = Frame(frame.image.copy(), (1000, 500))
    hit = match_template(offset, patch, threshold=0.9)
    assert hit is not None
    # every hit must be reported in screen space, not image space
    assert hit.center[0] > 1000 and hit.center[1] > 500


def test_match_template_survives_scale():
    img = np.full((200, 200, 3), (20, 20, 20), dtype=np.uint8)
    cv2.circle(img, (100, 100), 30, (200, 200, 60), -1)
    frame = Frame(img, (0, 0))
    tpl = img[80:120, 80:120].copy()
    hit = match_template(frame, tpl, threshold=0.9, scales=(1.0, 1.5))
    assert hit is not None


# --------------------------------------------------------------------------- #
# change detection — the backbone of action verification
# --------------------------------------------------------------------------- #


def test_diff_ratio_identical_is_zero(sample_frame):
    assert diff_ratio(sample_frame, sample_frame) == 0.0


def test_diff_ratio_detects_change(sample_frame):
    changed = Frame(sample_frame.image.copy(), sample_frame.origin)
    changed.image[0:60, 0:100] = 255
    ratio = diff_ratio(sample_frame, changed)
    assert 0.2 < ratio < 0.3  # 60*100 of 120*200


def test_diff_ratio_rejects_mismatched_sizes(sample_frame):
    other = Frame(np.zeros((10, 10, 3), dtype=np.uint8))
    with pytest.raises(ValueError):
        diff_ratio(sample_frame, other)


# --------------------------------------------------------------------------- #
# fingerprints
# --------------------------------------------------------------------------- #


def test_phash_identical_distance_zero(sample_frame):
    assert phash_distance(phash(sample_frame), phash(sample_frame)) == 0.0


def test_phash_differs_for_different_content():
    a = Frame(np.full((160, 160, 3), 20, dtype=np.uint8))
    b = Frame(np.full((160, 160, 3), 20, dtype=np.uint8))
    cv2.circle(b.image, (80, 80), 50, (255, 255, 255), -1)
    assert phash_distance(phash(a), phash(b)) > 0.1


def test_phash_is_scale_stable():
    img = np.full((400, 400, 3), 30, dtype=np.uint8)
    cv2.rectangle(img, (100, 100), (300, 250), (200, 100, 50), -1)
    big = Frame(img)
    small = Frame(cv2.resize(img, (200, 200), interpolation=cv2.INTER_AREA))
    assert phash_distance(phash(big), phash(small)) < 0.15


def test_color_profile_is_normalised(sample_frame):
    assert color_profile(sample_frame).sum() == pytest.approx(1.0)


def test_color_distance_zero_for_same_image(sample_frame):
    assert color_distance(color_profile(sample_frame), color_profile(sample_frame)) == pytest.approx(0.0)


def test_dominant_colors_returns_shares_summing_to_one():
    img = np.full((100, 100, 3), 200, dtype=np.uint8)
    img[:20, :] = 10
    colors = dominant_colors(Frame(img), k=2)
    assert len(colors) == 2
    assert sum(share for _c, share in colors) == pytest.approx(1.0, abs=0.05)


def test_mean_brightness(sample_frame):
    assert mean_brightness(sample_frame) > 0
    # the bright patch we drew is brighter than the whole frame
    assert mean_brightness(sample_frame, (30, 20, 60, 20)) > mean_brightness(sample_frame)
