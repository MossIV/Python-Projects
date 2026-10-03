"""Find the Village screen's action buttons by colour + shape, not by template.

Template matching only caught 2 of 7 buttons: they are drawn at slightly
different rotations with busy backgrounds behind them, so an exact-pixel
template fails.  The buttons are, however, a very specific saturated gold
diamond, which survives rotation.

This script samples the button's actual HSV, segments that colour, filters the
blobs by area and shape, and draws the result so it can be eyeballed before the
routine relies on it.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import cv2  # noqa: E402
import numpy as np  # noqa: E402

from iwol import ImageBackend  # noqa: E402

FRAME = "tests/fixtures/village.png"
# The village playfield: below the top bars, above the quest panel / bottom nav.
ROI = (0.10, 0.10, 0.80, 0.62)  # x, y, w, h as fractions


def sample_button_hsv(frame):
    """Print HSV stats inside a known button so we threshold the real colour."""
    x, y, w, h = 632, 240, 74, 74
    patch = frame.image[y : y + h, x : x + w]
    hsv = cv2.cvtColor(patch, cv2.COLOR_BGR2HSV)
    print("button patch HSV: H median=%.1f  S median=%.1f  V median=%.1f" % (
        np.median(hsv[:, :, 0]), np.median(hsv[:, :, 1]), np.median(hsv[:, :, 2])))
    sat = hsv[:, :, 1].astype(int)
    core = hsv[sat > np.percentile(sat, 60)]
    print("button CORE HSV:  H %d-%d  S %d-%d  V %d-%d" % (
        core[:, 0].min(), core[:, 0].max(),
        core[:, 1].min(), core[:, 1].max(),
        core[:, 2].min(), core[:, 2].max()))
    return core


def detect(frame, hsv_lo, hsv_hi, min_area, max_area, out=None):
    fw, fh = frame.size
    rx, ry, rw, rh = ROI
    x0, y0 = int(rx * fw), int(ry * fh)
    x1, y1 = int((rx + rw) * fw), int((ry + rh) * fh)

    hsv = cv2.cvtColor(frame.image, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv, np.array(hsv_lo), np.array(hsv_hi))

    # Fill the dark icon inside each button so each one becomes a solid blob.
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((15, 15), np.uint8))

    # Ignore everything outside the playfield.
    keep = np.zeros_like(mask)
    keep[y0:y1, x0:x1] = 255
    mask = cv2.bitwise_and(mask, keep)

    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    hits = []
    for c in contours:
        area = cv2.contourArea(c)
        if not (min_area <= area <= max_area):
            continue
        bx, by, bw, bh = cv2.boundingRect(c)
        aspect = bw / max(bh, 1)
        extent = area / max(bw * bh, 1)
        if not (0.55 <= aspect <= 1.8):
            continue
        if extent < 0.4:
            continue
        hits.append((bx + bw // 2, by + bh // 2, area, extent, c))

    hits.sort(key=lambda t: (t[1], t[0]))
    print(f"\nhsv_lo={hsv_lo} hsv_hi={hsv_hi} area=[{min_area},{max_area}] -> {len(hits)} blobs")
    for cx, cy, area, extent, _c in hits:
        print(f"   center=({cx},{cy}) frac=({cx/fw:.4f}, {cy/fh:.4f}) area={area:.0f} extent={extent:.2f}")

    if out:
        img = frame.image.copy()
        for cx, cy, area, extent, c in hits:
            cv2.drawContours(img, [c], -1, (0, 255, 0), 3)
            cv2.circle(img, (cx, cy), 6, (0, 0, 255), -1)
            cv2.putText(img, f"{area:.0f}", (cx - 30, cy - 40),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)
        cv2.rectangle(img, (x0, y0), (x1, y1), (255, 0, 255), 2)
        cv2.imwrite(out, img)
        print(f"   annotated -> {out}")
    return hits


if __name__ == "__main__":
    frame = ImageBackend(FRAME).grab()
    core = sample_button_hsv(frame)

    h_lo = max(0, int(np.percentile(core[:, 0], 5)) - 4)
    h_hi = min(179, int(np.percentile(core[:, 0], 95)) + 4)
    s_lo = max(0, int(np.percentile(core[:, 1], 5)) - 30)
    v_lo = max(0, int(np.percentile(core[:, 2], 5)) - 30)

    for lo, hi in [
        ((h_lo, s_lo, v_lo), (h_hi, 255, 255)),
        ((h_lo, 150, 180), (h_hi, 255, 255)),
        ((18, 160, 170), (38, 255, 255)),
    ]:
        detect(frame, lo, hi, 1500, 8000)

    detect(frame, (h_lo, s_lo, v_lo), (h_hi, 255, 255), 1500, 8000, out="D:/tmp/btn_color.png")
