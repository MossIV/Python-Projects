"""The tour recorder — build a labelled frame library of the game's screens.

The bot can only recognise screens we've seen.  This walks the game and saves
frames, so a human can click through the UI once and hand the CV layer a
labelled dataset.

It never clicks.  You drive; it records.

Two modes
---------
interactive   press Enter to grab a frame (name it as you go) — best for
              deliberately touring every menu
timed         grab a frame every N seconds while you play normally

Usage
-----
    python tools/tour.py --out tours/ --timed 2.0
    python tools/tour.py --out tours/               # Enter to capture, 'q' to quit
    python tools/tour.py --image-dir shots/         # label frames already on disk
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import cv2  # noqa: E402

from iwol import Ocr, open_backend  # noqa: E402

MANIFEST = "manifest.jsonl"


def slugify(text: str) -> str:
    keep = [c.lower() if c.isalnum() else "-" for c in text.strip()]
    out = "".join(keep).strip("-")
    while "--" in out:
        out = out.replace("--", "-")
    return out or "unnamed"


class Tour:
    def __init__(self, out_dir: Path, window: str, ocr: Ocr | None = None):
        self.out = Path(out_dir)
        self.out.mkdir(parents=True, exist_ok=True)
        self.backend = open_backend(window)
        self.ocr = ocr  # optional: OCR on save to help label
        self.count = 0
        self.manifest = self.out / MANIFEST

    def capture(self, label: str) -> Path | None:
        frame = self.backend.grab()
        if frame.is_blank():
            print("  ! blank frame — skipping")
            return None
        self.count += 1
        name = f"{self.count:04d}-{slugify(label)}.png"
        path = self.out / name
        cv2.imwrite(str(path), frame.image)

        text = ""
        if self.ocr is not None:
            lines = self.ocr.read(frame)
            text = " | ".join(ln.text for ln in lines)[:400]

        with self.manifest.open("a", encoding="utf-8") as fh:
            import json

            fh.write(
                json.dumps(
                    {
                        "file": name,
                        "label": label,
                        "ts": time.time(),
                        "size": list(frame.size),
                        "text": text,
                    }
                )
                + "\n"
            )
        print(f"  saved {name}  ({frame.width}x{frame.height})")
        return path

    def run_interactive(self):
        print("Enter a label and press Enter to capture (blank line = reuse last).")
        print("Type 'q' to finish.\n")
        last = "screen"
        while True:
            try:
                label = input(f"label [{last}]: ").strip()
            except (EOFError, KeyboardInterrupt):
                break
            if label.lower() in {"q", "quit", "exit"}:
                break
            if label:
                last = label
            self.capture(last)

    def run_timed(self, interval: float, limit: int = 0, label: str = "auto"):
        print(f"Recording every {interval}s. Ctrl-C to stop.\n")
        try:
            while not limit or self.count < limit:
                self.capture(label)
                time.sleep(interval)
        except KeyboardInterrupt:
            print("\nstopped")

    def close(self):
        self.backend.close()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default="tours", help="output directory")
    ap.add_argument("--window", default="IsekaiWaifuOverlord")
    ap.add_argument("--timed", type=float, metavar="SECONDS", help="grab every N seconds instead of interactively")
    ap.add_argument("--limit", type=int, default=0, help="max frames in timed mode (0 = unlimited)")
    ap.add_argument("--label", default="auto", help="label for timed-mode frames")
    ap.add_argument("--ocr", action="store_true", help="OCR each frame on save to help label it later")
    args = ap.parse_args()

    ocr = Ocr() if args.ocr else None
    tour = Tour(Path(args.out), args.window, ocr)
    try:
        if args.timed:
            tour.run_timed(args.timed, args.limit, args.label)
        else:
            tour.run_interactive()
    finally:
        tour.close()

    print(f"\n{tour.count} frames in {tour.out}")
    print(f"manifest: {tour.manifest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
