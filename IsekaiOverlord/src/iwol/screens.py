"""Data-driven screen classification.

A screen is described by *what it looks like*, not by hardcoded pixel offsets:

* ``regions`` — named sub-rectangles, stored as fractions of the frame so the
  same definition works at 720p, 1080p or 1440p.
* ``all_of`` / ``any_of`` — normalised keyword sets that must (or may) appear in
  those regions.  Normalisation strips punctuation and spaces, because OCR
  reliably drops spaces on stylised fonts.
* optional ``fingerprint`` — a perceptual hash for screens with no usable text.

Definitions live in ``screens.json`` next to the package so they can be grown
from recorded frames without touching code.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from .capture import Frame
from .ocr import Ocr, TextLine

DEFAULT_SPEC_PATH = Path(__file__).with_name("screens.json")


@dataclass(frozen=True)
class Region:
    """A sub-rectangle in frame-relative coordinates (0..1)."""

    x: float
    y: float
    w: float
    h: float

    def to_px(self, size: tuple[int, int]) -> tuple[int, int, int, int]:
        fw, fh = size
        return (
            int(self.x * fw),
            int(self.y * fh),
            max(1, int(self.w * fw)),
            max(1, int(self.h * fh)),
        )

    @classmethod
    def from_px(cls, box: tuple[int, int, int, int], size: tuple[int, int]) -> "Region":
        fw, fh = size
        x, y, w, h = box
        return cls(x / fw, y / fh, w / fw, h / fh)


@dataclass
class ScreenSpec:
    name: str
    regions: dict[str, Region] = field(default_factory=dict)
    all_of: tuple[str, ...] = ()
    any_of: tuple[str, ...] = ()
    min_score: float = 0.5
    description: str = ""

    def region_px(self, size: tuple[int, int]) -> dict[str, tuple[int, int, int, int]]:
        return {name: reg.to_px(size) for name, reg in self.regions.items()}


@dataclass
class Classification:
    """The classifier's verdict, with the evidence that produced it."""

    name: str
    confidence: float
    evidence: str
    spec: ScreenSpec | None = None
    texts: dict[str, list[TextLine]] = field(default_factory=dict)

    @property
    def known(self) -> bool:
        return self.spec is not None

    def text_in(self, region: str) -> str:
        """All OCR text found in one region, joined."""
        return " ".join(line.text for line in self.texts.get(region, []))

    def lines_in(self, region: str) -> list[TextLine]:
        return list(self.texts.get(region, []))

    def find(self, needle: str) -> TextLine | None:
        """First OCR line anywhere on the screen whose normalised text contains
        the normalised ``needle``."""
        key = "".join(ch for ch in needle.lower() if ch.isalnum())
        for lines in self.texts.values():
            for line in lines:
                if key and key in line.normalized:
                    return line
        return None

    def find_in(self, region: str, needle: str) -> TextLine | None:
        key = "".join(ch for ch in needle.lower() if ch.isalnum())
        for line in self.texts.get(region, []):
            if key and key in line.normalized:
                return line
        return None


def _normalize(text: str) -> str:
    return "".join(ch for ch in text.lower() if ch.isalnum())


class ScreenClassifier:
    """Chooses which screen we're looking at, and reads its regions."""

    def __init__(self, specs: list[ScreenSpec], ocr: Ocr, min_confidence: float = 0.6):
        self.specs = list(specs)
        self.ocr = ocr
        self.min_confidence = min_confidence

    # -- construction ----------------------------------------------------- #

    @classmethod
    def from_json(cls, path: str | Path = DEFAULT_SPEC_PATH, ocr: Ocr | None = None):
        path = Path(path)
        raw = json.loads(path.read_text(encoding="utf-8"))
        specs = []
        for entry in raw.get("screens", []):
            specs.append(
                ScreenSpec(
                    name=entry["name"],
                    regions={
                        rname: Region(*vals) for rname, vals in entry.get("regions", {}).items()
                    },
                    all_of=tuple(entry.get("all_of", ())),
                    any_of=tuple(entry.get("any_of", ())),
                    min_score=entry.get("min_score", 0.5),
                    description=entry.get("description", ""),
                )
            )
        return cls(specs, ocr or Ocr())

    def save_json(self, path: str | Path = DEFAULT_SPEC_PATH) -> None:
        payload = {
            "screens": [
                {
                    "name": s.name,
                    "description": s.description,
                    "regions": {k: [v.x, v.y, v.w, v.h] for k, v in s.regions.items()},
                    "all_of": list(s.all_of),
                    "any_of": list(s.any_of),
                    "min_score": s.min_score,
                }
                for s in self.specs
            ]
        }
        Path(path).write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def add(self, spec: ScreenSpec) -> None:
        self.specs = [s for s in self.specs if s.name != spec.name] + [spec]

    def get(self, name: str) -> ScreenSpec | None:
        return next((s for s in self.specs if s.name == name), None)

    # -- classification --------------------------------------------------- #

    def _read_all_regions(self, frame: Frame) -> dict[str, list[TextLine]]:
        """OCR every region any spec cares about, once, in a single pass."""
        wanted: dict[str, tuple[int, int, int, int]] = {}
        for spec in self.specs:
            for rname, box in spec.region_px(frame.size).items():
                wanted.setdefault(rname, box)
        return self.ocr.read_regions(frame, wanted)

    def classify(self, frame: Frame, texts: dict[str, list[TextLine]] | None = None) -> Classification:
        """Identify the screen.

        Reads each distinct region once (not once per spec), then scores every
        spec against the pooled text.  Unknown screens come back as
        ``Classification('unknown', ...)`` rather than raising — the brain needs
        to be able to *see* that it's lost, not crash.
        """
        if frame.is_blank():
            return Classification("blank", 1.0, "capture returned a flat frame")

        pooled = texts if texts is not None else self._read_all_regions(frame)

        best = Classification("unknown", 0.0, "no spec matched")
        for spec in self.specs:
            regions_here = {r: pooled.get(r, []) for r in spec.regions}
            blob = _normalize(" ".join(ln.text for lines in regions_here.values() for ln in lines))
            if not blob:
                continue

            missing = [k for k in spec.all_of if _normalize(k) not in blob]
            if missing:
                continue
            hits = [k for k in spec.any_of if _normalize(k) in blob]
            if spec.any_of and not hits:
                continue

            total = len(spec.all_of) + len(spec.any_of)
            score = 1.0 if total == 0 else (len(spec.all_of) - len(missing) + len(hits)) / total
            if score < spec.min_score or score <= best.confidence:
                continue
            evidence = f"all_of={list(spec.all_of)} any_hits={hits}"
            best = Classification(spec.name, score, evidence, spec, regions_here)

        # Attach the text we read so callers can reuse it without re-OCR'ing.
        if best.spec is None:
            best.texts = pooled
        return best
