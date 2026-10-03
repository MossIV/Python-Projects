"""Calibrate the Village building regions against known values, with a small search.

The building number regions are small and sit beside a gold coin icon that
confuses OCR.  The search is deliberately tiny (a handful of x-offsets at one
size) because each OCR call costs ~0.3 s and the answer is not that subtle --
we only need to know where the icon ends and the digits begin.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from iwol import ImageBackend, Ocr  # noqa: E402
from iwol.ocr import pad_for_ocr  # noqa: E402

FRAME = "tests/fixtures/village.png"

# name, (ocr_x, ocr_y) of the value text from full-frame OCR, expected string
INCOME = [
    ("B1", 0.1727, 0.1576, "1.02T"),
    ("B2", 0.4004, 0.2014, "1.15T"),
    ("B3", 0.6090, 0.2639, "936B"),
    ("B4", 0.7633, 0.3097, "997B"),
    ("B5", 0.3016, 0.4410, "777B"),
    ("B6", 0.4488, 0.5292, "1.20T"),
    ("B7", 0.6227, 0.6368, "988B"),
]
COST = [
    ("B1", 0.1738, 0.1785, "10+10"),
    ("B2", 0.3969, 0.2222, "100+22"),
    ("B3", 0.6016, 0.2847, "50+3"),
    ("B4", 0.7648, 0.3306, "75+6"),
    ("B5", 0.2938, 0.4611, "100+2"),
    ("B6", 0.4461, 0.5500, "135+3"),
    ("B7", 0.6227, 0.6569, "150+4"),
]

OFFSETS = (0, 24, 30, 36)
WIDTH = 90
HEIGHT = 34


def read_box(ocr, frame, x, y, w, h):
    crop = frame.image[y : y + h, x : x + w]
    padded, _dx, _dy = pad_for_ocr(crop)
    res, _ = ocr._engine(padded)
    if not res:
        return ""
    return "".join(r[1] for r in res).replace(" ", "")


def clean(s: str) -> str:
    return "".join(ch for ch in s.upper() if ch.isalnum() or ch in "+.")


def probe(ocr, frame, entries, label):
    fw, fh = frame.size
    print(f"\n=== {label}  (width={WIDTH} height={HEIGHT}) ===")
    print(f"{'id':4} {'expected':8} " + " ".join(f"x+{o:<3}" for o in OFFSETS))
    winners = {}
    for name, fx, fy, expected in entries:
        base_x, base_y = int(fx * fw), int(fy * fh)
        cells = []
        for ox in OFFSETS:
            got = read_box(ocr, frame, base_x + ox, base_y - 6, WIDTH, HEIGHT)
            hit = clean(got) == clean(expected)
            cells.append(f"{got if got else '-':>6}{'*' if hit else ' '}")
            if hit and name not in winners:
                winners[name] = (base_x + ox, base_y - 6, WIDTH, HEIGHT)
        star = "" if name in winners else "   <-- NO MATCH"
        print(f"{name:4} {expected:8} " + " ".join(cells) + star)
    print("\n(* = matches expected)")
    print("\n--- winning boxes (fraction form for screens.json) ---")
    for name, (x, y, w, h) in winners.items():
        print(f'  "{name}": [{x/fw:.4f}, {y/fh:.4f}, {w/fw:.4f}, {h/fh:.4f}],   # px({x},{y},{w},{h})')
    return winners


if __name__ == "__main__":
    frame = ImageBackend(FRAME).grab()
    ocr = Ocr()
    print(f"frame {frame.size}")
    probe(ocr, frame, INCOME, "INCOME regions")
    probe(ocr, frame, COST, "COST regions")
