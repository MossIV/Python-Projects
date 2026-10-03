"""Run the bot.

Safety defaults, in order of importance:

1. **Dry run is the default.**  Without ``--arm`` the bot makes all of its
   decisions and logs every action it *would* take, but the actuator is inert.
   Run it this way first and read the journal; it will tell you exactly what it
   wanted to click and why.
2. **Spending is capped and defaults to zero.**  ``--max-gold``/``--max-gems``
   default to 0, so the bot cannot buy anything until you say so.
3. **A panic key.**  F12 aborts immediately, as does Ctrl-C.  Both are checked
   between actions, and the kill switch is also consulted mid-drag.
4. Real-money purchase screens abort the run on sight.

Usage
-----
    python tools/run.py                              # dry run, 10 steps
    python tools/run.py --check                      # classify once and exit
    python tools/run.py --steps 50 --keep-frames     # dry run, save frames
    python tools/run.py --arm --actuator sendinput --steps 200 \
        --max-gold 50000 --max-gems 0                # for real
"""

from __future__ import annotations

import argparse
import ctypes
import signal
import sys
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from iwol import (  # noqa: E402
    Brain,
    BrainConfig,
    DryRunActuator,
    Journal,
    Ocr,
    PostMessageActuator,
    PrintWindowBackend,
    ScreenClassifier,
    SendInputActuator,
    SentinelActuator,
    find_windows,
)
from iwol.routines import VillageRoutine  # noqa: E402

VK_F12 = 0x7B


class KillSwitch:
    """Stops the run on Ctrl-C or the F12 panic key."""

    def __init__(self, panic_vk: int | None = VK_F12):
        self.panic_vk = panic_vk
        self._flag = threading.Event()
        self._reason = ""
        signal.signal(signal.SIGINT, self._on_signal)

    def _on_signal(self, *_args):
        self._reason = "Ctrl-C"
        self._flag.set()

    def _panic_pressed(self) -> bool:
        if self.panic_vk is None:
            return False
        # key down and not toggled => currently held
        return bool(ctypes.windll.user32.GetAsyncKeyState(self.panic_vk) & 0x8000)

    def __call__(self) -> bool:
        if self._flag.is_set():
            return True
        if self._panic_pressed():
            self._reason = "F12 panic key"
            self._flag.set()
            return True
        return False

    @property
    def reason(self) -> str:
        return self._reason or "kill switch"


def build_actuator(kind: str, window: str, arm: bool, hwnd: int):
    if not arm:
        return DryRunActuator()

    if kind == "postmessage":
        return PostMessageActuator(hwnd)
    if kind == "sendinput":
        act = SendInputActuator(hwnd)
        if not act.focus():
            print("! could not bring the game to the foreground — input may not land")
        # small grace period so the window is actually ready
        import time

        time.sleep(0.5)
        return act
    raise SystemExit(f"unknown actuator {kind!r}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--window", default="IsekaiWaifuOverlord", help="window title substring")
    ap.add_argument("--specs", default=None, help="path to screens.json")
    ap.add_argument("--check", action="store_true", help="classify the current screen and exit")
    ap.add_argument("--steps", type=int, default=10, help="max steps (0 = unlimited)")
    ap.add_argument("--seconds", type=float, default=0, help="max runtime (0 = unlimited)")
    ap.add_argument("--arm", action="store_true", help="ACTUALLY click. Without this, dry run.")
    ap.add_argument("--actuator", default="sendinput", choices=["sendinput", "postmessage"],
                    help="input backend when armed")
    ap.add_argument("--max-gold", type=int, default=0, help="gold the run may spend (default 0)")
    ap.add_argument("--max-gems", type=int, default=0, help="gems the run may spend (default 0)")
    ap.add_argument("--step-delay", type=float, default=1.2, help="idle between steps")
    ap.add_argument("--settle", type=float, default=1.2, help="wait for the game to react")
    ap.add_argument("--keep-frames", action="store_true", help="save frames alongside the journal")
    ap.add_argument("--journal", default="runs/journal.jsonl")
    ap.add_argument("--no-village", action="store_true", help="don't register the village routine")
    args = ap.parse_args()

    matches = find_windows(args.window)
    if not matches:
        print(f"! no visible window matching {args.window!r}. Is the game running?")
        return 2
    hwnd, title = matches[0]

    ocr = Ocr()
    classifier = ScreenClassifier.from_json(args.specs, ocr) if args.specs else ScreenClassifier.from_json(ocr=ocr)
    capture = PrintWindowBackend(hwnd=hwnd)

    # -- check mode -------------------------------------------------------- #
    if args.check:
        frame = capture.grab()
        cls = classifier.classify(frame)
        print(f"window  : {title!r} hwnd={hwnd}")
        print(f"size    : {frame.size}  blank={frame.is_blank()}")
        print(f"screen  : {cls.name}  (confidence {cls.confidence:.2f})")
        print(f"evidence: {cls.evidence}")
        print(f"specs   : {[s.name for s in classifier.specs]}")
        capture.close()
        return 0

    # -- run --------------------------------------------------------------- #
    kill = KillSwitch()
    actuator = SentinelActuator(build_actuator(args.actuator, args.window, args.arm, hwnd), should_stop=kill)

    config = BrainConfig(
        step_delay=args.step_delay,
        settle_time=args.settle,
        max_steps=args.steps,
        max_runtime=args.seconds,
        max_gems_spent=args.max_gems,
        max_gold_spent=args.max_gold,
    )

    routines = []
    if not args.no_village:
        village = VillageRoutine()
        routines.append(village)
        if village.layout is None:
            print("! village_layout.json not found — the village routine will refuse to act")
            print("  (that is intentional; see the routine's docstring)")

    journal = Journal(args.journal, keep_frames=args.keep_frames)
    brain = Brain(
        capture=capture,
        ocr=ocr,
        actuator=actuator,
        classifier=classifier,
        routines=routines,
        journal=journal,
        config=config,
        should_stop=kill,
    )

    mode = "ARMED — live clicks" if args.arm else "DRY RUN — nothing will be clicked"
    print(f"=== {mode} ===")
    print(f"window   : {title!r} hwnd={hwnd}")
    print(f"actuator : {actuator.inner.name if args.arm else 'dryrun'}")
    print(f"budget   : gold<={args.max_gold} gems<={args.max_gems}")
    print(f"kill     : Ctrl-C or F12")
    print(f"journal  : {journal.path}")
    print()
    if not args.arm:
        print("Re-run with --arm to actually play.\n")

    try:
        report = brain.run()
    except KeyboardInterrupt:
        print("\ninterrupted")
        report = None
    finally:
        journal.prune_frames()
        brain.close()

    if report:
        print(f"\n=== {report.summary()} ===")
        for line in report.budget.log[:20]:
            print(f"  {line}")
    if kill.reason != "kill switch":
        print(f"stopped by: {kill.reason}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
