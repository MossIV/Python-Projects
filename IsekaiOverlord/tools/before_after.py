"""Capture before/after a single human action and report exactly what changed.

For working out what a button actually does without guessing.  You take a
snapshot, perform the action in-game yourself, then take another snapshot; this
diffs the two frames *and* re-reads every screen region, so you get both "the
screen changed here" and "this number went from X to Y".

Two-phase on purpose, so it works across a chat turn: the human clicks in
between, not the bot.  The tool never sends input.

Usage
-----
    python tools/before_after.py before --tag upgrade1
    #  ... click the button in-game yourself ...
    python tools/before_after.py after  --tag upgrade1
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import cv2  # noqa: E402

from iwol import ImageBackend, Ocr, ScreenClassifier, diff_ratio, find_windows  # noqa: E402
from iwol.capture import PrintWindowBackend  # noqa: E402
from iwol.ocr import parse_number  # noqa: E402

STORE = Path("runs/ab")


def snapshot_path(tag: str, phase: str) -> Path:
    return STORE / f"{tag}_{phase}.png"


def meta_path(tag: str) -> Path:
    return STORE / f"{tag}.json"


def read_regions(ocr, frame, spec):
    regions = spec.region_px(frame.size)
    return {name: ocr.read(frame.crop(box)) for name, box in regions.items()}


def as_text(lines) -> str:
    return " ".join(ln.text for ln in lines).strip()


def do_before(args, backend, ocr, classifier):
    frame = backend.grab()
    cls = classifier.classify(frame)
    if cls.spec is None:
        print(f"! screen is {cls.name!r} — cannot record regions for an unknown screen")
        print("  navigate to a mapped screen (e.g. village) first")
        return 2

    STORE.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(snapshot_path(args.tag, "before")), frame.image)

    texts = read_regions(ocr, frame, cls.spec)
    meta = {
        "tag": args.tag,
        "screen": cls.name,
        "regions": {name: [ln.text for ln in lines] for name, lines in texts.items()},
        "size": list(frame.size),
    }
    meta_path(args.tag).write_text(json.dumps(meta, indent=2), encoding="utf-8")

    print(f"screen   : {cls.name} (confidence {cls.confidence:.2f})")
    print(f"size     : {frame.size}")
    print(f"saved    : {snapshot_path(args.tag, 'before')}")
    print(f"meta     : {meta_path(args.tag)}")
    print(f"regions  : {len(texts)} recorded")
    print("\n--- values now on screen ---")
    for name, lines in sorted(texts.items()):
        text = as_text(lines)
        num = parse_number(text)
        if text:
            extra = f"   parsed={num:,.0f}" if num is not None else ""
            print(f"  {name:14} {text!r}{extra}")
    print("\nNow perform the action in-game, then run:")
    print(f"  python tools/before_after.py after --tag {args.tag}")
    return 0


def do_after(args, backend, ocr, classifier):
    mp = meta_path(args.tag)
    bp = snapshot_path(args.tag, "before")
    if not mp.exists() or not bp.exists():
        print(f"! no 'before' snapshot for tag {args.tag!r} — run the 'before' phase first")
        return 2

    meta = json.loads(mp.read_text(encoding="utf-8"))
    before_img = cv2.imread(str(bp))
    after_frame = backend.grab()

    if before_img.shape != after_frame.image.shape:
        print(f"! frame size changed: {before_img.shape} -> {after_frame.image.shape}")
        return 1

    STORE.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(snapshot_path(args.tag, "after")), after_frame.image)

    # 1) pixel-level change
    ratio = diff_ratio(ImageBackend(str(bp)).grab(), after_frame)
    delta = cv2.absdiff(before_img, after_frame.image).max(axis=2)
    changed_mask = (delta > 18).astype("uint8") * 255
    cv2.imwrite(str(STORE / f"{args.tag}_diff.png"), changed_mask)

    print(f"tag      : {args.tag}   screen recorded as: {meta['screen']}")
    print(f"pixels changed: {ratio:.2%} of the frame\n")

    # 2) which screen regions changed
    spec = classifier.get(meta["screen"])
    if spec is None:
        print("! screen spec no longer defined; cannot compare regions")
        return 1

    after_texts = read_regions(ocr, after_frame, spec)
    print(f"{'region':16} {'before':>22} -> {'after':>22}   change")
    print("-" * 78)
    interesting = []
    for name in sorted(meta["regions"]):
        before_txt = " ".join(meta["regions"][name]).strip()
        after_txt = as_text(after_texts.get(name, []))
        if before_txt == after_txt:
            continue
        print(f"{name:16} {before_txt:>22} -> {after_txt:>22}   CHANGED")
        interesting.append((name, before_txt, after_txt))

    if not interesting:
        print("(no region text changed)")

    # 3) numeric deltas, which is usually the actual answer
    print("\n--- numeric deltas ---")
    found_number = False
    for name, before_txt, after_txt in interesting:
        b, a = parse_number(before_txt), parse_number(after_txt)
        if b is None or a is None:
            continue
        found_number = True
        pct = f"{(a - b) / b:.2%}" if b else "n/a"
        print(f"  {name:16} {b:>18,.0f} -> {a:>18,.0f}   ({a - b:+,.0f}, {pct})")
    if not found_number:
        print("  (no numeric region changed)")

    print(f"\nmask     : {STORE / f'{args.tag}_diff.png'}")
    print(f"after    : {snapshot_path(args.tag, 'after')}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("phase", choices=["before", "after"])
    ap.add_argument("--tag", required=True, help="name for this experiment")
    ap.add_argument("--window", default="IsekaiWaifuOverlord")
    ap.add_argument("--specs", default=None)
    args = ap.parse_args()

    matches = find_windows(args.window)
    if not matches:
        print(f"! no window matching {args.window!r}")
        return 2
    backend = PrintWindowBackend(hwnd=matches[0][0])
    ocr = Ocr()
    classifier = (
        ScreenClassifier.from_json(args.specs, ocr) if args.specs else ScreenClassifier.from_json(ocr=ocr)
    )

    try:
        if args.phase == "before":
            return do_before(args, backend, ocr, classifier)
        return do_after(args, backend, ocr, classifier)
    finally:
        backend.close()


if __name__ == "__main__":
    raise SystemExit(main())
