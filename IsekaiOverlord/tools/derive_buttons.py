"""Derive the Village screen's 7 action-button positions and verify them visually.

Two buttons were located reliably by template match.  Comparing those against the
OCR positions of their building's cost text gives a consistent offset, so the
remaining five can be *derived* rather than guessed -- then drawn on the frame so
the derivation can be checked by eye before any code depends on it.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import cv2  # noqa: E402

from iwol import ImageBackend  # noqa: E402

FRAME = "tests/fixtures/village.png"

# Cost-text anchor (fraction) -> this is where OCR read the "N+M" row.
# Button centre sits this far right/below that anchor.  Value confirmed twice:
#   building 1: cost (0.1738,0.1785) -> expected button (0.2633,0.1924)  [matched 0.2633,0.1924]
#   building 4: cost (0.7648,0.3306) -> expected button (0.8543,0.3445)  [matched 0.8516,0.3444]
BUTTON_OFFSET = (0.0895, 0.0139)

BUILDINGS = [
    ("B1", 0.1738, 0.1785, "1.02T", "10+10"),
    ("B2", 0.3969, 0.2222, "1.15T", "100+22"),
    ("B3", 0.6016, 0.2847, "936B", "50+3"),
    ("B4", 0.7648, 0.3306, "997B", "75+6"),
    ("B5", 0.2938, 0.4611, "777B", "100+2"),
    ("B6", 0.4461, 0.5500, "1.20T", "135+3"),
    ("B7", 0.6227, 0.6569, "988B", "150+4"),
]


def button_position(cost_x, cost_y):
    return (cost_x + BUTTON_OFFSET[0], cost_y + BUTTON_OFFSET[1])


def main():
    frame = ImageBackend(FRAME).grab()
    fw, fh = frame.size
    img = frame.image.copy()

    print(f"frame {frame.size}, button offset {BUTTON_OFFSET}\n")
    print(f"{'id':4} {'income':7} {'cost':8} {'btn px':14} {'btn frac':18}")
    for name, cx, cy, income, cost in BUILDINGS:
        bx, by = button_position(cx, cy)
        px, py = int(bx * fw), int(by * fh)
        print(f"{name:4} {income:7} {cost:8} ({px:4},{py:4})     ({bx:.4f},{by:.4f})")

        # button ring
        cv2.circle(img, (px, py), 40, (0, 255, 0), 3)
        cv2.circle(img, (px, py), 5, (0, 0, 255), -1)
        cv2.putText(img, name, (px - 22, py - 52), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 255, 0), 2)

        # cost anchor ring (magenta) so the offset is visible
        ax, ay = int(cx * fw), int(cy * fh)
        cv2.circle(img, (ax, ay), 8, (255, 0, 255), -1)

    cv2.imwrite("D:/tmp/btn_derived.png", img)
    print("\nannotated -> D:/tmp/btn_derived.png  (green = derived button, magenta = OCR cost anchor)")


if __name__ == "__main__":
    main()
