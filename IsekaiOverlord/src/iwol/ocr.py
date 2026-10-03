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
    img: np.ndarray, max_aspect: float = 4.0, min_height: int = 32
) -> tuple[np.ndarray, int, int]:
    """Pad a crop vertically so the detector can actually see its text.

    Why this exists: RapidOCR's detection model silently returns **nothing** for
    very wide, short crops.  Measured on this game's 2560x1440 frames, a
    921x79 strip of the bottom nav (aspect 11.7:1) detects 0 boxes, while the
    same strip padded to 921x231 (aspect 4:1) detects all five labels.  Padding
    with either replicated edges or black both work; upscaling 2x does *not*.

    So any UI region that is a wide strip — nav bars, currency bars, stat rows —
    must be padded before OCR or it reads as empty and the screen looks unknown.

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

        Wide-short crops are padded first — see :func:`pad_for_ocr`.
        """
        img = frame.image if isinstance(frame, Frame) else frame
        origin = frame.origin if isinstance(frame, Frame) else (0, 0)

        img, dx, dy = pad_for_ocr(img)
        origin = (origin[0] + dx, origin[1] + dy)

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

_NUM = re.compile(r"-?\d[\d,._ ]*")


def parse_number(text: str) -> float | None:
    """Best-effort number from a UI string: '1,234' -> 1234, '3.8K' -> 3800.

    The magnitude suffix is read from the character *immediately following* the
    matched number, not from the end of the string.  Getting that wrong turns
    compound strings into nonsense: ``"3430/13.0K"`` must give 3430 (the hero's
    current HP), not 3.43 million, purely because the string happens to end in
    'K'.
    """
    cleaned = text.strip()
    m = _NUM.search(cleaned)
    if not m:
        return None

    raw = m.group()
    rest = cleaned[m.end() :].lstrip()
    mult = 1.0
    if rest and rest[0] in "KkMmBb":
        mult = {"k": 1e3, "m": 1e6, "b": 1e9}[rest[0].lower()]

    raw = raw.replace(",", "").replace("_", "").replace(" ", "")
    # '3.800' style thousands separators vs a real decimal point: a trailing
    # group of exactly 3 digits after a dot is treated as a separator.
    if "." in raw:
        head, _, tail = raw.rpartition(".")
        if len(tail) == 3 and head:
            raw = head + tail
    try:
        return float(raw) * mult
    except ValueError:
        return None
