"""Snap each derived button position to the true button centre.

The derived positions land near the buttons but a few pixels off, and a few
pixels matters once we are clicking.  For each prediction we run a *local*
template search in a small window around it, using the one button whose centre
is already confirmed (found at score 1.000), and snap to the best match.

A low score means the prediction was wrong -- reported rather than silently
accepted, because clicking a wrong pixel in an economy screen spends coins.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import cv2  # noqa: E402

from iwol import ImageBackend  # noqa: E402

FRAME = "tests/fixtures/village.png"

# Confirmed button centre for building 1 (template match score 1.000).
ANCHOR_CENTRE = (674, 277)
TEMPLATE_HALF = 37  # button is ~74 px across

BUTTON_OFFSET = (0.0895, 0.0139)
BUILDINGS = [
    ("B1", 0.1738, 0.1785),
    ("B2", 0.3969, 0.2222),
    ("B3", 0.6016, 0.2847),
    ("B4", 0.7648, 0.3306),
    ("B5", 0.2938, 0.4611),
    ("B6", 0.4461, 0.5500),
    ("B7", 0.6227, 0.6569),
]

SEARCH_RADIUS = 70  # px of slack allowed around each prediction


def main():
    frame = ImageBackend(FRAME).grab()
    fw, fh = frame.size
    ax, ay = ANCHOR_CENTRE
    template = frame.image[ay - TEMPLATE_HALF : ay + TEMPLATE_HALF,
                          ax - TEMPLATE_HALF : ax + TEMPLATE_HALF].copy()
    th, tw = template.shape[:2]
    print(f"template {tw}x{th} from anchor {ANCHOR_CENTRE}\n")

    img = frame.image.copy()
    results = []
    print(f"{'id':4} {'predicted':14} {'snapped':14} {'score':6} {'delta':10} ok")
    for name, cx, cy in BUILDINGS:
        px = int((cx + BUTTON_OFFSET[0]) * fw)
        py = int((cy + BUTTON_OFFSET[1]) * fh)

        # local search window around the prediction
        x0 = max(0, px - SEARCH_RADIUS - tw // 2)
        y0 = max(0, py - SEARCH_RADIUS - th // 2)
        x1 = min(fw, px + SEARCH_RADIUS + tw // 2)
        y1 = min(fh, py + SEARCH_RADIUS + th // 2)
        window = frame.image[y0:y1, x0:x1]

        res = cv2.matchTemplate(window, template, cv2.TM_CCOEFF_NORMED)
        _mn, mx, _ml, loc = cv2.minMaxLoc(res)
        sx = x0 + loc[0] + tw // 2
        sy = y0 + loc[1] + th // 2

        ok = mx >= 0.70
        results.append((name, sx, sy, float(mx), ok))
        print(f"{name:4} ({px:4},{py:4})    ({sx:4},{sy:4})    {mx:.3f}  "
              f"({sx-px:+4d},{sy-py:+4d})  {'YES' if ok else 'NO'}")

        colour = (0, 255, 0) if ok else (0, 0, 255)
        cv2.circle(img, (sx, sy), 40, colour, 3)
        cv2.circle(img, (sx, sy), 5, (255, 0, 255), -1)
        cv2.putText(img, f"{name} {mx:.2f}", (sx - 40, sy - 50),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, colour, 2)

    cv2.imwrite("D:/tmp/btn_snapped.png", img)

    good = [r for r in results if r[4]]
    print(f"\n{len(good)}/{len(results)} buttons located at >=0.70")
    print("\n--- config to paste into village_layout.json ---")
    for name, sx, sy, score, ok in results:
        print(f"  {name}: frac=({sx/fw:.4f}, {sy/fh:.4f})  px=({sx},{sy})  score={score:.3f}")
    print("\nannotated -> D:/tmp/btn_snapped.png")


if __name__ == "__main__":
    main()
