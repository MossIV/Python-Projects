"""The probe-first classifier: correctness of the fast path, and that it is fast.

The point of the two-stage path is that identifying a screen should not cost
OCR'ing every region of every screen.  These tests measure the difference in
*regions read* rather than in seconds, which is deterministic and doesn't turn
into a flaky benchmark on a loaded machine.
"""

from __future__ import annotations

import pytest

from conftest import fixture_image

from iwol import ImageBackend, Ocr, ScreenClassifier
from iwol.screens import Region, ScreenSpec

pytestmark = pytest.mark.slow


class CountingOcr:
    """Wraps Ocr and records every region it is asked to read."""

    def __init__(self, inner):
        self.inner = inner
        self.regions_read: list[str] = []
        self.read_calls = 0

    def read(self, img, min_score: float = 0.5):
        self.read_calls += 1
        return self.inner.read(img, min_score=min_score)

    def read_regions(self, frame, regions, min_score: float = 0.5):
        self.regions_read.extend(regions)
        return self.inner.read_regions(frame, regions, min_score=min_score)


@pytest.fixture(scope="session")
def real_ocr():
    return Ocr()


def _all_probe_regions(classifier) -> set[str]:
    """The union of every spec's probe regions — that's what stage 1 reads."""
    out: set[str] = set()
    for spec in classifier.specs:
        out.update(spec.probe_regions)
    return out


@pytest.mark.parametrize(
    "fixture,expected",
    [
        ("adventure_hub", "adventure_hub"),
        ("character_sympathy", "character_sympathy"),
        ("village", "village"),
        ("building_panel", "building_panel"),
    ],
)
def test_probe_first_identifies_every_mapped_screen(real_ocr, fixture, expected):
    path = fixture_image(fixture)
    if not path.exists():
        pytest.skip("fixture not present")
    frame = ImageBackend(str(path)).grab()
    classifier = ScreenClassifier.from_json(ocr=real_ocr)
    cls = classifier.classify(frame)
    assert cls.name == expected
    assert "probe-first" in cls.evidence


def test_identification_only_reads_probe_regions(real_ocr):
    """Classifying must not read the whole screen -- that was ~28 OCR calls.

    Note it reads the union of *all* specs' probes (~4 regions), not just the
    winner's: it has to look before it can decide.
    """
    path = fixture_image("village")
    if not path.exists():
        pytest.skip("fixture not present")
    frame = ImageBackend(str(path)).grab()

    counting = CountingOcr(real_ocr)
    classifier = ScreenClassifier.from_json(ocr=counting)
    cls = classifier.classify(frame)

    assert cls.name == "village"
    spec = classifier.get("village")
    assert set(counting.regions_read) <= _all_probe_regions(classifier)
    assert len(counting.regions_read) < len(spec.regions) / 4


def test_regions_are_read_lazily_on_demand(real_ocr):
    """A routine reading one value must pay for one region, not for all of them."""
    path = fixture_image("village")
    if not path.exists():
        pytest.skip("fixture not present")
    frame = ImageBackend(str(path)).grab()

    counting = CountingOcr(real_ocr)
    classifier = ScreenClassifier.from_json(ocr=counting)
    cls = classifier.classify(frame)

    assert "gold" not in counting.regions_read     # not read just to identify
    before = counting.read_calls                   # single-image reads (lazy path)

    value = cls.text_in("gold")                    # now it should be read
    assert counting.read_calls == before + 1
    assert value                                   # and yield something

    cls.text_in("gold")                            # second access is cached
    assert counting.read_calls == before + 1


def test_a_routine_that_needs_no_text_reads_no_regions(real_ocr):
    """The village routine only needs region geometry to click, so it should be
    able to run without a single extra OCR call."""
    path = fixture_image("village")
    if not path.exists():
        pytest.skip("fixture not present")
    frame = ImageBackend(str(path)).grab()

    counting = CountingOcr(real_ocr)
    classifier = ScreenClassifier.from_json(ocr=counting)
    cls = classifier.classify(frame)

    spec = classifier.get("village")
    for name in spec.regions:
        cls.lines_in(name)  # force everything, so we know it *could* have read
    # restart the count and classify again: identification alone is the cost
    counting.regions_read.clear()
    cls2 = classifier.classify(frame)
    assert set(counting.regions_read) <= _all_probe_regions(classifier)


def test_ambiguous_probe_falls_back_to_reading_everything(real_ocr):
    """Two screens sharing a probe region must not be guessed between."""
    path = fixture_image("village")
    if not path.exists():
        pytest.skip("fixture not present")
    frame = ImageBackend(str(path)).grab()

    # Two specs with identical probe regions and identical all_of keywords.
    twin = ScreenSpec(
        name="village_twin",
        regions={"bottom_nav": Region(*[0.0, 0.945, 0.36, 0.055])},
        all_of=("Temple", "Bank", "Residents", "Journey"),
        any_of=("Income", "Goal"),
        probe_regions=("bottom_nav",),
    )
    base = ScreenClassifier.from_json(ocr=real_ocr)
    ambiguous = ScreenClassifier([*base.specs, twin], real_ocr)

    cls = ambiguous.classify(frame)
    # Both candidates match the probe, so it must not claim the fast path.
    assert "probe-first" not in cls.evidence
    assert cls.name in {"village", "village_twin"}


def test_lazy_reads_do_not_fire_without_a_frame():
    """A classification built by hand (no frame/ocr) must not explode."""
    from iwol.screens import Classification

    cls = Classification("x", 1.0, "", ScreenSpec(name="x", regions={"a": Region(0, 0, 0.1, 0.1)}))
    assert cls.text_in("a") == ""
    assert cls.lines_in("a") == []
    assert cls.find("anything") is None
