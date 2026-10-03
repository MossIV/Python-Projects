"""End-to-end perception on real captured frames.

These use actual screenshots of the Steam build at 2560x1440 and run the real
RapidOCR models, so they're marked ``slow``.  They're the tests that would have
caught the wide-crop padding bug — the nav-bar screen classified as 'unknown'
until OCR could actually read the bar.
"""

from __future__ import annotations

import pytest

from conftest import fixture_image

from iwol import ImageBackend, ScreenClassifier, ScreenSpec
from iwol.screens import Region

pytestmark = pytest.mark.slow

SPECS = None


def _classifier(ocr_engine):
    global SPECS
    if SPECS is None:
        SPECS = ScreenClassifier.from_json(ocr=ocr_engine)
    return SPECS


@pytest.mark.parametrize(
    "fixture,expected",
    [
        ("adventure_hub", "adventure_hub"),
        ("character_sympathy", "character_sympathy"),
    ],
)
def test_real_frames_classify_correctly(ocr_engine, fixture, expected):
    path = fixture_image(fixture)
    if not path.exists():
        pytest.skip(f"fixture {path.name} not present")
    frame = ImageBackend(str(path)).grab()
    classifier = _classifier(ocr_engine)
    cls = classifier.classify(frame)
    assert cls.name == expected, f"got {cls.name!r}: {cls.evidence}"
    assert cls.confidence >= 0.6
    assert cls.known


def test_nav_bar_region_is_readable(ocr_engine):
    """Regression: the bottom nav is a 921x79 strip.  Before the padding fix it
    OCR'd as empty and the whole screen looked unknown."""
    path = fixture_image("adventure_hub")
    if not path.exists():
        pytest.skip("fixture not present")
    frame = ImageBackend(str(path)).grab()
    classifier = _classifier(ocr_engine)
    spec = classifier.get("adventure_hub")
    assert spec is not None

    box = spec.region_px(frame.size)["bottom_nav"]
    lines = ocr_engine.read(frame.crop(box))
    texts = {ln.normalized for ln in lines}
    for label in ("temple", "bank", "residents", "companions", "dungeon"):
        assert label in texts, f"{label} missing from nav bar; read {sorted(texts)}"


def test_top_bar_currency_is_readable(ocr_engine):
    path = fixture_image("adventure_hub")
    if not path.exists():
        pytest.skip("fixture not present")
    frame = ImageBackend(str(path)).grab()
    classifier = _classifier(ocr_engine)
    spec = classifier.get("adventure_hub")
    box = spec.region_px(frame.size)["top_bar"]
    lines = ocr_engine.read(frame.crop(box))
    assert lines, "currency bar read as empty"


def test_unseen_screen_is_unknown_not_a_guess(ocr_engine, sample_frame):
    classifier = _classifier(ocr_engine)
    cls = classifier.classify(sample_frame)  # blank synthetic image
    assert cls.name in {"unknown", "blank"}
    assert not cls.known


# --------------------------------------------------------------------------- #
# Region maths
# --------------------------------------------------------------------------- #


def test_region_round_trips_through_normalised_space():
    size = (2560, 1440)
    box = (102, 388, 256, 648)
    region = Region.from_px(box, size)
    assert region.to_px(size) == box


def test_region_scales_across_resolutions():
    region = Region(0.5, 0.25, 0.1, 0.2)
    assert region.to_px((1000, 1000)) == (500, 250, 100, 200)
    assert region.to_px((2000, 2000)) == (1000, 500, 200, 400)


def test_region_never_returns_zero_size():
    region = Region(0.999, 0.999, 0.0001, 0.0001)
    _x, _y, w, h = region.to_px((100, 100))
    assert w >= 1 and h >= 1


# --------------------------------------------------------------------------- #
# Classifier mechanics
# --------------------------------------------------------------------------- #


def _noisy_frame():
    """A non-flat frame — a flat one is correctly classified as 'blank'."""
    import numpy as np

    from iwol import Frame

    rng = np.random.default_rng(0)
    return Frame(rng.integers(0, 255, (40, 60, 3), dtype=np.uint8))


def test_classifier_prefers_the_higher_scoring_spec(ocr_engine):
    from iwol.ocr import TextLine

    spec = ScreenSpec(name="thing", regions={"r": Region(0, 0, 1, 1)}, all_of=["alpha"])
    classifier = ScreenClassifier([spec], ocr_engine)
    texts = {"r": [TextLine("ALPHA!", 0.9, (0, 0, 10, 10))]}
    cls = classifier.classify(_noisy_frame(), texts=texts)
    assert cls.name == "thing"
    assert cls.known


def test_classifier_requires_all_of(ocr_engine):
    from iwol.ocr import TextLine

    spec = ScreenSpec(name="thing", regions={"r": Region(0, 0, 1, 1)},
                      all_of=["alpha", "beta"])
    classifier = ScreenClassifier([spec], ocr_engine)
    texts = {"r": [TextLine("alpha only", 0.9, (0, 0, 10, 10))]}
    cls = classifier.classify(_noisy_frame(), texts=texts)
    assert cls.name == "unknown"


def test_flat_frame_is_blank_not_unknown(ocr_engine):
    """A failed capture must be distinguishable from an unrecognised screen."""
    import numpy as np

    from iwol import Frame

    spec = ScreenSpec(name="thing", regions={"r": Region(0, 0, 1, 1)}, all_of=["alpha"])
    classifier = ScreenClassifier([spec], ocr_engine)
    cls = classifier.classify(Frame(np.full((40, 60, 3), 90, dtype=np.uint8)))
    assert cls.name == "blank"
    assert not cls.known


def test_classification_helpers_find_text(sample_frame):
    from iwol.screens import Classification
    from iwol.ocr import TextLine

    spec = ScreenSpec(name="s", regions={"a": Region(0, 0, 1, 1)})
    texts = {"a": [TextLine("PROMOTE", 0.9, (1, 2, 30, 40))]}
    cls = Classification("s", 1.0, "", spec, texts)
    assert cls.text_in("a") == "PROMOTE"
    assert cls.find("promote") is not None
    assert cls.find("nope") is None
    assert cls.find_in("a", "promote").center == (15, 21)
