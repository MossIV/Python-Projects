"""Non-OCR visual matching: template lookup, perceptual hashing, colour stats.

OCR is the slow, semantic layer.  These are the fast, dumb layers that answer
"which screen is this?" and "where is that icon?" in a few milliseconds, so the
brain only pays for OCR on screens that need reading.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

from .capture import Frame


@dataclass(frozen=True)
class Match:
    """A template hit, positioned in screen coordinates."""

    name: str
    score: float
    center: tuple[int, int]  # screen space
    box: tuple[int, int, int, int]  # screen x1, y1, x2, y2

    def __bool__(self) -> bool:
        return True


# --------------------------------------------------------------------------- #
# template matching
# --------------------------------------------------------------------------- #


def match_template(
    frame: Frame,
    template: np.ndarray,
    name: str = "template",
    threshold: float = 0.8,
    scales: tuple[float, ...] = (1.0,),
) -> Match | None:
    """Best template hit above ``threshold``, or None.

    ``scales`` lets one template survive UI scale changes (window resized,
    different resolution).  Cost is linear in the number of scales, so keep the
    tuple short unless you actually need it.
    """
    haystack = frame.image
    best: Match | None = None

    for scale in scales:
        tpl = template
        if scale != 1.0:
            tpl = cv2.resize(
                template, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA
            )
        th, tw = tpl.shape[:2]
        if th > haystack.shape[0] or tw > haystack.shape[1]:
            continue
        res = cv2.matchTemplate(haystack, tpl, cv2.TM_CCOEFF_NORMED)
        _min_v, max_v, _min_l, max_l = cv2.minMaxLoc(res)
        if max_v < threshold:
            continue
        if best is not None and max_v <= best.score:
            continue
        x, y = max_l
        x1, y1 = frame.to_screen(x, y)
        x2, y2 = frame.to_screen(x + tw, y + th)
        best = Match(name, float(max_v), ((x1 + x2) // 2, (y1 + y2) // 2), (x1, y1, x2, y2))

    return best


def match_all(
    frame: Frame,
    template: np.ndarray,
    name: str = "template",
    threshold: float = 0.8,
    max_hits: int = 32,
) -> list[Match]:
    """Every non-overlapping hit above ``threshold`` (e.g. repeated icons)."""
    res = cv2.matchTemplate(frame.image, template, cv2.TM_CCOEFF_NORMED)
    th, tw = template.shape[:2]
    hits: list[Match] = []

    work = res.copy()
    for _ in range(max_hits):
        _min_v, max_v, _min_l, max_l = cv2.minMaxLoc(work)
        if max_v < threshold:
            break
        x, y = max_l
        x1, y1 = frame.to_screen(x, y)
        x2, y2 = frame.to_screen(x + tw, y + th)
        hits.append(Match(name, float(max_v), ((x1 + x2) // 2, (y1 + y2) // 2), (x1, y1, x2, y2)))
        # suppress a neighbourhood so the same icon isn't returned twice
        px0, py0 = max(0, x - tw // 2), max(0, y - th // 2)
        px1, py1 = min(work.shape[1], x + tw // 2 + 1), min(work.shape[0], y + th // 2 + 1)
        work[py0:py1, px0:px1] = -1.0
    return hits


def save_template(frame: Frame, box: tuple[int, int, int, int], path: str | Path) -> Path:
    """Cut a template out of a frame and save it (for building a library)."""
    crop = frame.crop(box).image
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(path), crop)
    return path


def load_template(path: str | Path) -> np.ndarray:
    img = cv2.imread(str(path), cv2.IMREAD_COLOR)
    if img is None:
        raise FileNotFoundError(path)
    return img


# --------------------------------------------------------------------------- #
# fingerprints
# --------------------------------------------------------------------------- #


def phash(frame: Frame | np.ndarray, hash_size: int = 8) -> np.ndarray:
    """Perceptual hash as a flat bool array (DCT-based, robust to scale/JPEG)."""
    img = frame.image if isinstance(frame, Frame) else frame
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    resized = cv2.resize(gray, (hash_size * 4, hash_size * 4), interpolation=cv2.INTER_AREA)
    dct = cv2.dct(np.float32(resized))
    low = dct[:hash_size, :hash_size]
    return (low > low.mean()).flatten()


def phash_distance(a: np.ndarray, b: np.ndarray) -> float:
    """Fraction of differing bits, 0.0 (identical) to 1.0 (unrelated)."""
    if a.shape != b.shape:
        raise ValueError(f"hash shape mismatch: {a.shape} vs {b.shape}")
    return float(np.count_nonzero(a != b) / a.size)


def color_profile(frame: Frame | np.ndarray, bins: int = 8) -> np.ndarray:
    """Normalised 3D BGR histogram — cheap global scene descriptor."""
    img = frame.image if isinstance(frame, Frame) else frame
    hist = cv2.calcHist([img], [0, 1, 2], None, [bins] * 3, [0, 256] * 3)
    hist = hist.flatten()
    total = hist.sum()
    return hist / total if total else hist


def color_distance(a: np.ndarray, b: np.ndarray) -> float:
    """L1 distance between two colour profiles (0 = identical)."""
    return float(np.abs(a - b).sum() / 2.0)


def dominant_colors(frame: Frame | np.ndarray, k: int = 3) -> list[tuple[tuple[int, int, int], float]]:
    """Top-k dominant colours as (BGR, share).  Useful for detecting dark/light UI themes."""
    img = frame.image if isinstance(frame, Frame) else frame
    small = cv2.resize(img, (64, 64), interpolation=cv2.INTER_AREA).reshape(-1, 3).astype(np.float32)
    criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 20, 1.0)
    _compactness, labels, centers = cv2.kmeans(
        small, k, None, criteria, 3, cv2.KMEANS_PP_CENTERS
    )
    counts = np.bincount(labels.flatten(), minlength=k) / len(small)
    order = np.argsort(-counts)
    return [(tuple(int(c) for c in centers[i]), float(counts[i])) for i in order]


def mean_brightness(frame: Frame | np.ndarray, box: tuple[int, int, int, int] | None = None) -> float:
    img = frame.image if isinstance(frame, Frame) else frame
    if box is not None:
        x, y, w, h = box
        img = img[y : y + h, x : x + w]
    return float(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY).mean())


def diff_ratio(a: Frame | np.ndarray, b: Frame | np.ndarray, threshold: int = 12) -> float:
    """Fraction of pixels that changed between two same-size images.

    This is the backbone of action verification: click, re-grab, and ask whether
    the screen actually moved.
    """
    ia = a.image if isinstance(a, Frame) else a
    ib = b.image if isinstance(b, Frame) else b
    if ia.shape != ib.shape:
        raise ValueError(f"size mismatch: {ia.shape} vs {ib.shape}")
    delta = cv2.absdiff(ia, ib).max(axis=2)
    return float(np.count_nonzero(delta > threshold) / delta.size)
