"""Read a live screen: OCR it, classify it, and draw what the bot sees.

This is the tool you use while growing ``screens.json``.  It answers the two
questions you actually have when defining a screen:

1. What text is on this screen, and where (in fractions, so you can paste the
   numbers straight into a Region)?
2. Which spec — if any — does the classifier currently pick, and why not?

Everything it prints is read-only; it never clicks.

Usage
-----
    python tools/probe.py                      # current screen
    python tools/probe.py --full               # OCR the whole frame, not regions
    python tools/probe.py --save out.png       # write an annotated overlay
    python tools/probe.py --image shot.png     # probe a saved frame instead
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import cv2  # noqa: E402

from iwol import ImageBackend, Ocr, ScreenClassifier, open_backend  # noqa: E402

GREEN = (80, 220, 80)
CYAN = (230, 200, 60)
RED = (60, 60, 230)
YELLOW = (60, 220, 230)


def draw_overlay(frame, cls, regions_px, lines, path):
    img = frame.image.copy()
    fw, fh = frame.size

    for name, (x, y, w, h) in regions_px.items():
        cv2.rectangle(img, (x, y), (x + w, y + h), CYAN, 2)
        cv2.putText(img, name, (x + 4, y + 22), cv2.FONT_HERSHEY_SIMPLEX, 0.6, CYAN, 2)

    for line in lines:
        x1, y1, x2, y2 = line.box
        lx1, ly1 = frame.to_local(x1, y1)
        lx2, ly2 = frame.to_local(x2, y2)
        cv2.rectangle(img, (lx1, ly1), (lx2, ly2), GREEN, 1)
        cv2.putText(img, f"{line.text}", (lx1, max(12, ly1 - 4)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, GREEN, 1)

    banner = f"{cls.name}  conf={cls.confidence:.2f}"
    color = GREEN if cls.known else RED
    cv2.rectangle(img, (0, 0), (fw, 34), (0, 0, 0), -1)
    cv2.putText(img, banner, (10, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.8, color, 2)

    cv2.imwrite(str(path), img)
    print(f"\nannotated overlay -> {path}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--window", default="IsekaiWaifuOverlord", help="window title substring")
    ap.add_argument("--image", help="probe a saved image instead of the live game")
    ap.add_argument("--full", action="store_true", help="OCR the whole frame")
    ap.add_argument("--save", help="write an annotated PNG here")
    ap.add_argument("--specs", default=None, help="path to screens.json")
    args = ap.parse_args()

    if args.image:
        backend = ImageBackend(args.image)
    else:
        backend = open_backend(args.window)

    ocr = Ocr()
    try:
        classifier = ScreenClassifier.from_json(args.specs, ocr) if args.specs else ScreenClassifier.from_json(ocr=ocr)
    except FileNotFoundError:
        print("! screens.json not found; running with no specs (everything is 'unknown')")
        classifier = ScreenClassifier([], ocr)

    frame = backend.grab()
    print(f"capture   : {backend.name}  size={frame.size}  origin={frame.origin}")
    print(f"blank     : {frame.is_blank()}")

    fw, fh = frame.size

    if args.full:
        lines = ocr.read(frame)
        regions_px = {}
    else:
        # OCR each region any spec defines, plus report the ones nobody claims.
        pooled: dict[str, list] = {}
        regions_px: dict[str, tuple[int, int, int, int]] = {}
        for spec in classifier.specs:
            regions_px.update(spec.region_px(frame.size))
        pooled = ocr.read_regions(frame, regions_px)
        lines = [ln for group in pooled.values() for ln in group]

    print(f"\n--- OCR ({len(lines)} lines) ---")

    if not args.full:
        for name, (x, y, w, h) in regions_px.items():
            print(
                f"\n[{name}]  px=({x},{y},{w},{h})  frac=({x / fw:.4f}, {y / fh:.4f}, {w / fw:.4f}, {h / fh:.4f})"
            )
            for line in pooled.get(name, []):
                lx1, ly1 = frame.to_local(*line.box[:2])
                print(f"    {line.score:.2f}  {line.text!r}  px=({lx1},{ly1})  frac=({lx1 / fw:.4f}, {ly1 / fh:.4f})")
    else:
        for line in lines:
            lx1, ly1 = frame.to_local(*line.box[:2])
            print(f"    {line.score:.2f}  {line.text!r}  px=({lx1},{ly1})  frac=({lx1 / fw:.4f}, {ly1 / fh:.4f})")

    cls = classifier.classify(frame, texts=None if args.full else pooled)
    print(f"\n--- classification ---")
    print(f"screen     : {cls.name}")
    print(f"confidence : {cls.confidence:.2f}")
    print(f"evidence   : {cls.evidence}")
    print(f"known      : {cls.known}")
    for spec in classifier.specs:
        print(f"  candidate {spec.name!r}: all_of={list(spec.all_of)} any_of={list(spec.any_of)}")

    if args.save:
        draw_overlay(frame, cls, regions_px, lines, args.save)

    backend.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
