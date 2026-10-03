"""OCR over captured frames.

RapidOCR (PP-OCR models on onnxruntime) is the engine: pip-only, no separate
binary, works offline, and reads this game's stylised UI text well.  Measured on
the Steam build at 2560x1440: ~2.4 s for a full frame, dominated by detection.

That cost is why :func:`Ocr.read_regions` exists — pass the screen regions you
care about and we OCR only those crops (~50 ms each) instead of the whole frame.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache

import numpy as np
import cv2

from .capture import Frame


@dataclass(frozen=True)
class TextLine:
    """One recognised string, positioned in **screen** coordinates."""

    text: str
    score: float
    box: tuple[int, int, int, int]  # x1, y1, x2, y2

    @property
    def center(self) -> tuple[int, int]:
        x1, y1, x2, y2 = self.box
        return ((x1 + x2) // 2, (y1 + y2) // 2)

    @property
    def normalized(self) -> str:
        """Lowercased, stripped of everything but letters/digits.

        OCR reliably mangles spacing on stylised fonts ("evasionby5%for5seconds"),
        so matching against this form is far more robust than exact comparison.
        """
        return re.sub(r"[^a-z0-9]", "", self.text.lower())

    def __str__(self) -> str:
        return f"{self.text!r}@{self.score:.2f}{self.box}"


@lru_cache(maxsize=1)
def _engine():
    """Load RapidOCR once per process — model init costs seconds."""
    from rapidocr_onnxruntime import RapidOCR

    return RapidOCR()


def pad_for_ocr(
    img: np.ndarray, max_aspect: float = 4.0, min_height: int = 96
) -> tuple[np.ndarray, int, int]:
    """Pad a crop vertically so the detector can actually see its text.

    Why this exists: RapidOCR's detection model silently returns **nothing** for
    very wide, short crops, and mangles small ones.  Measured on this game's
    2560x1440 frames:

    * a 921x79 nav bar (aspect 11.7:1) detects 0 boxes; padded to aspect 4:1 it
      detects all five labels;
    * a 90x34 number crop reads as ``[]`` raw, but ``['1.02T']`` once padded to
      a 96px height.  Padding to only 64 px is *unstable* -- it splits the value
      into ``['1.', '02T']`` -- so the floor is deliberately generous.

    Padding with replicated edges or black both work; upscaling 2x does **not**.

    Returns ``(padded, dx, dy)`` where dx/dy are the pixel offsets of the
    original content inside the padded image, so coordinates stay correct.
    """
    h, w = img.shape[:2]
    if h <= 0 or w <= 0:
        return img, 0, 0

    target_h = max(min_height, int(np.ceil(w / max_aspect)))
    if target_h <= h:
        return img, 0, 0

    pad_total = target_h - h
    top = pad_total // 2
    padded = cv2.copyMakeBorder(img, top, pad_total - top, 0, 0, cv2.BORDER_REPLICATE)
    return padded, 0, top


class Ocr:
    """Thin, caching-friendly wrapper around RapidOCR."""

    def __init__(self, engine=None):
        self._engine = engine or _engine()

    def read(self, frame: Frame | np.ndarray, min_score: float = 0.5) -> list[TextLine]:
        """OCR an image, returning lines ordered top-to-bottom.

        Wide-short crops are padded first — see :func:`pad_for_ocr`.  Any
        detected box is then mapped back out of padded space, so returned boxes
        are always in the caller's coordinates.
        """
        img = frame.image if isinstance(frame, Frame) else frame
        origin = frame.origin if isinstance(frame, Frame) else (0, 0)

        img, dx, dy = pad_for_ocr(img)
        # The padded image's (0,0) sits at (-dx, -dy) in the crop, so the crop's
        # screen origin must shift *back* by the padding.  Adding instead of
        # subtracting pushes every box out of the frame: the 921x79 nav bar is
        # padded by +76px at the top, and its labels came back at y=1554 in a
        # 1440-tall frame instead of y=1402.
        origin = (origin[0] - dx, origin[1] - dy)

        result, _elapse = self._engine(img)
        if not result:
            return []

        lines: list[TextLine] = []
        for box, text, score in result:
            try:
                conf = float(score)
            except (TypeError, ValueError):
                conf = 0.0
            if conf < min_score or not str(text).strip():
                continue
            xs = [p[0] for p in box]
            ys = [p[1] for p in box]
            lines.append(
                TextLine(
                    text=str(text),
                    score=conf,
                    box=(
                        int(min(xs)) + origin[0],
                        int(min(ys)) + origin[1],
                        int(max(xs)) + origin[0],
                        int(max(ys)) + origin[1],
                    ),
                )
            )
        lines.sort(key=lambda ln: (ln.box[1], ln.box[0]))
        return lines

    def read_regions(
        self, frame: Frame, regions: dict[str, tuple[int, int, int, int]], min_score: float = 0.5
    ) -> dict[str, list[TextLine]]:
        """OCR several named (x, y, w, h) regions of ``frame``.

        Boxes come back in screen space, so a caller can click a recognised
        button directly.  Crops smaller than 8 px are skipped (OCR needs pixels).
        """
        out: dict[str, list[TextLine]] = {}
        for name, (x, y, w, h) in regions.items():
            if w < 8 or h < 8:
                out[name] = []
                continue
            crop = frame.crop((x, y, w, h))
            out[name] = self.read(crop, min_score=min_score)
        return out


# --------------------------------------------------------------------------- #
# helpers for reading numbers out of OCR text
# --------------------------------------------------------------------------- #

# No space in the character class on purpose.  OCR text from a region is the
# region's lines joined with " ", so a space means "a different value", not a
# thousands separator: '89 1.20T' is gems-then-gold, and a space-tolerant regex
# would fuse it into a single nonsense number (89.1e9 instead of 89 and 1.2e12).
_NUM = re.compile(r"-?\d[\d,._]*")


# Magnitude suffixes as they appear in this game's UI.  Note 'T' for trillion --
# omitting it makes "1.13T" parse as 1.13, a 1e12 error on the number that
# decides whether an upgrade is affordable.
_MULT = {"k": 1e3, "m": 1e6, "b": 1e9, "t": 1e12}


def parse_number(text: str) -> float | None:
    """Best-effort number from a UI string: '1,234' -> 1234, '3.8K' -> 3800.

    The magnitude suffix is read from the character *immediately following* the
    matched number, not from the end of the string.  Getting that wrong turns
    compound strings into nonsense: ``"3430/13.0K"`` must give 3430 (the hero's
    current HP), not 3.43 million, purely because the string happens to end in
    'K'.
    """
    return next(iter(parse_numbers(text)), None)


def parse_numbers(text: str) -> list[float]:
    """Every number in a UI string, in order.

    Some regions legitimately hold several values (a currency bar reads
    ``'89 1.20T'`` = gems then gold).  Taking the first would silently pick the
    wrong currency, so callers that know the layout can index instead.
    """
    out: list[float] = []
    cleaned = text.strip()
    for m in _NUM.finditer(cleaned):
        raw = m.group()
        rest = cleaned[m.end() :].lstrip()
        mult = _MULT.get(rest[0].lower(), 1.0) if rest else 1.0

        raw = raw.replace(",", "").replace("_", "").replace(" ", "")
        if "." in raw:
            head, _, tail = raw.rpartition(".")
            if len(tail) == 3 and head:
                raw = head + tail
        try:
            out.append(float(raw) * mult)
        except ValueError:
            continue
    return out
