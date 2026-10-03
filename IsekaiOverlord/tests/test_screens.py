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
        ("village", "village"),
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


def test_village_building_costs_are_readable(ocr_engine):
    """Regression: the cost regions must actually yield their numbers.

    These are 110x33 crops sitting under a stylised font; without vertical
    padding they read as empty, and at 90px wide the longer values truncate
    ("100+22" -> "100+2"), which would silently misprice an upgrade.
    """
    path = fixture_image("village")
    if not path.exists():
        pytest.skip("fixture not present")
    frame = ImageBackend(str(path)).grab()
    classifier = _classifier(ocr_engine)
    spec = classifier.get("village")
    assert spec is not None

    expected = {
        "b1_cost": "1010", "b2_cost": "10022", "b3_cost": "503",
        "b4_cost": "756", "b5_cost": "1002", "b6_cost": "1353", "b7_cost": "1504",
    }
    regions = spec.region_px(frame.size)
    got = {}
    for name, want in expected.items():
        lines = ocr_engine.read(frame.crop(regions[name]))
        got[name] = "".join(ch for ch in " ".join(ln.text for ln in lines) if ch.isdigit())
    assert got == expected, f"cost regions misread: {got}"


def test_village_building_incomes_are_readable(ocr_engine):
    """Income values carry a magnitude suffix (B/T) -- if OCR drops or mangles it
    the number is wrong by a factor of a billion."""
    path = fixture_image("village")
    if not path.exists():
        pytest.skip("fixture not present")
    frame = ImageBackend(str(path)).grab()
    classifier = _classifier(ocr_engine)
    spec = classifier.get("village")
    regions = spec.region_px(frame.size)

    expected = {
        "b1_income": "1.02T", "b3_income": "936B", "b4_income": "997B",
        "b5_income": "777B", "b6_income": "1.20T", "b7_income": "988B",
    }
    for name, want in expected.items():
        lines = ocr_engine.read(frame.crop(regions[name]))
        text = "".join(ln.text for ln in lines).replace(" ", "")
        assert text == want, f"{name}: expected {want!r}, read {text!r}"


@pytest.mark.xfail(
    reason="known OCR weakness: the 'T' suffix in b2_income reads as '1' "
    "('1.15T' -> '1.151'). A dropped/misread suffix changes a value by 1e9, so "
    "this is tracked rather than hidden. Needs a suffix-plausibility check "
    "before the economy planner is allowed to trust these numbers."
)
def test_village_b2_income_suffix(ocr_engine):
    path = fixture_image("village")
    if not path.exists():
        pytest.skip("fixture not present")
    frame = ImageBackend(str(path)).grab()
    spec = _classifier(ocr_engine).get("village")
    lines = ocr_engine.read(frame.crop(spec.region_px(frame.size)["b2_income"]))
    assert "".join(ln.text for ln in lines).replace(" ", "") == "1.15T"


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
