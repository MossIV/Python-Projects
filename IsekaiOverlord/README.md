# Isekai Waifu Overlord — computer-vision bot

A CV bot that plays *Isekai: Waifu Overlord* by **looking at the screen** and
clicking, rather than reading the game's memory or injecting into its process.

```
┌─ perceive ──────────────┐   ┌─ decide ────────┐   ┌─ act ───────────────┐
│ capture (PrintWindow)   │   │ screen ID       │   │ click / drag / key  │
│ OCR (RapidOCR, regions) │──▶│ routine         │──▶│ dry-run by default  │
│ template match (cv2)    │   │ economy planner │   │ budget + kill switch│
└─────────────────────────┘   └─────────────────┘   └─────────────────────┘
                                       │
                                journal (JSONL) ──▶ every action verified
```

## Status

| Piece | State |
|---|---|
| Capture (Windows `PrintWindow`) | ✅ verified on the live Steam build |
| OCR (RapidOCR + onnxruntime) | ✅ verified, coordinates match the UI |
| Screen classifier | ✅ 4 screens mapped, all classify ≥0.86 |
| Actuators (dry-run / PostMessage / SendInput) | ✅ implemented and unit-tested |
| Brain loop, verification, budgets, kill switch | ✅ implemented and unit-tested |
| Economy upgrade planner | ✅ implemented, unit-tested |
| Village screen (7 buildings) | ✅ calibrated |
| Building panel (upgrade + workers) | ✅ calibrated, `upgrade_btn` reads `UPGRADE 1.13T` |
| Village routine | ✅ opens each building's panel in turn |
| Building panel routine | ✅ assigns workers, then upgrades within budget |
| Tests | ✅ 116 passing, 1 xfailed |

**Honest summary:** the whole loop runs end to end on real screens — capture →
recognise → decide → click → verify — with the two routines chained: the village
screen opens a building's panel, the panel routine assigns free workers and then
upgrades if the cost is affordable and inside the run budget, then leaves.

The routines have **not yet been run armed against the live game** — that needs
your go-ahead, and `tools/run.py` stays in dry-run until you pass `--arm`.

### What the UI actually does (established by experiment, not assumption)

A before/after capture of a real click settled this, and it contradicted the
original design:

* The gold diamond button on a village building card **opens a management panel**.
  It is not an upgrade button, and the top number on the card is not income.
* The panel is where the real **`UPGRADE`** button lives, showing its gold cost
  (`1.13T` for `Hot Spring Lvl 25` in the captured frame).
* The panel also holds the **worker** system: `Current workers 2/5`,
  `Available workers 9`, worker cards with bonuses like `Works on Farm +75%`, and
  an **`ADD THE BEST WORKERS`** auto-assign button. That button is free, so the
  routine spends it first — best return on screen, zero risk.

One known weakness is tracked rather than hidden: OCR reads `b2_income` as
`1.151` instead of `1.15T` (the suffix misreads as a digit). A misread suffix
changes a value by 10⁹ — this is exactly why `T` missing from the magnitude map
was caught by tests rather than in your economy. See the xfail in
`tests/test_screens.py`.

## Quick start

```bash
python -m pip install -r requirements.txt

python tools/run.py --check     # what screen is the bot looking at?
python tools/run.py             # dry run: decide + log, click nothing
```

Nothing is ever clicked without `--arm`:

```bash
python tools/run.py --arm --actuator sendinput --steps 200 --max-gold 50000
```

## Tools

| Tool | Purpose |
|---|---|
| `tools/run.py` | the bot. `--check` to classify once, `--arm` to actually play |
| `tools/probe.py` | OCR a live screen, print coordinates in fractions, draw an overlay |
| `tools/tour.py` | record labelled frames while you click through the UI |
| `tools/before_after.py` | snapshot, let a human act, snapshot again, diff it |
| `tools/verify_regions.py` | calibrate region boxes against values you know are on screen |
| `tools/snap_buttons.py` | locate action buttons by local template search, with deltas |
| `tools/grab.py` | minimal single-frame capture probe |

## Safety rails

These aren't decoration — each one maps to a way game bots go wrong.

* **Dry run is the default.** No `--arm`, no clicks.
* **Spending defaults to zero.** `--max-gold` / `--max-gems` are 0 unless set.
* **Real-money screens abort the run** on sight (`store`, `shop`, `purchase`,
  `checkout`, `payment`, `topup`). Automated spending of real money is out of
  scope for this project entirely.
* **Unknown screens halt** rather than guess. Guessing means clicking blind.
* **Actions are verified.** After anything that spends, the screen is re-grabbed
  and compared; `max_consecutive_misses` (default 3) aborts the run. This is what
  stops a bot sitting in a corner spinning.
* **Clicks are bounded to the game window**, so a stale coordinate can't hit your
  desktop.
* **Panic key F12**, plus Ctrl-C. Checked between actions *and* mid-drag.

## Design notes

**Capture works while the game is unfocused.** `PrintWindow` with
`PW_RENDERFULLCONTENT` returns a clean 2560×1440 frame even when the Unity
window is behind something else. Only *clicking* may require focus.

**Region OCR, not full-frame OCR.** A full 2560×1440 frame costs ~2.4 s in
RapidOCR, almost all of it detection. Screens declare the regions they care
about, and each crop costs ~50 ms.

**Wide UI strips must be padded before OCR.** RapidOCR's detector silently
returns *zero* boxes for very wide, short crops. A 921×79 nav bar (aspect
11.7:1) reads as empty; the same bar padded to aspect 4:1 reads all five
labels. Upscaling doesn't help — only padding does. See `ocr.pad_for_ocr`.
This bug made an entire screen classify as `unknown`.

**Screen definitions are data.** `src/iwol/screens.json` holds regions as
*fractions* of the frame, so one definition works at any resolution. Adding a
screen doesn't require touching Python.

**Routine vs. brain split.** Routines are short and dumb: read the screen, act,
report what was spent. All waiting, verifying and stopping lives in `brain.py`,
so every action is verified the same way and no routine needs its own timing
hacks.

## Adding a new screen

The bot only recognises screens it has seen. To teach it one:

```bash
# 1. navigate to the screen in-game, then record it
python tools/tour.py --out tours/village --ocr
#    (Enter captures, 'q' quits)

# 2. read the coordinates
python tools/probe.py --image tours/village/0001-village.png --full
#    prints every string with px= and frac= positions

# 3. add the region fractions + required keywords to src/iwol/screens.json
# 4. verify
python tools/probe.py --save overlay.png     # cyan boxes = regions, banner = verdict
python -m pytest -m slow
```

`probe.py --save` is the fast feedback loop: cyan rectangles are the defined
regions, green boxes are OCR hits, and the banner shows the classifier's verdict.

## Layout

```
src/iwol/
  capture.py    PrintWindow + mss backends, Frame coordinate maths
  ocr.py        RapidOCR wrapper, wide-crop padding, number parsing
  vision.py     template matching, phash, colour profiles, change detection
  screens.py    screen specs + classifier
  economy.py    which upgrade to buy (pure, unit-tested)
  actuator.py   dry-run / PostMessage / SendInput + kill switch
  journal.py    JSONL audit trail
  brain.py      the loop, verification, budgets, safety gates
  routines/     one handler per screen
  screens.json  screen definitions (data)
tools/          run.py, probe.py, tour.py, grab.py
tests/          90 tests; `-m live` needs the game open, `-m slow` loads OCR
```

## Requirements

Python 3.14 (tested), `numpy`, `opencv-python-headless`, `Pillow`, `mss`,
`rapidocr-onnxruntime`, `pytest`. No separate OCR binary and no GPU — RapidOCR
bundles its models and runs on onnxruntime.

Windows-only as written (the capture and `SendInput` backends are Win32). The
`mss` backend and the `ImageBackend` are portable, so a Linux/browser backend
would slot into `capture.py` without touching the brain.
