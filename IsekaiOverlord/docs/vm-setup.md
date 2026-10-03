# Running the bot in a VMware Workstation VM

Why a VM at all: `SendInput` only reaches a game that owns the **foreground**, so
running the bot on your desktop means not using your desktop. A VM gives the bot
its own screen and leaves the host alone — and it's Windows, so none of the
capture or input code changes.

## Read this first: the DirectX risk

**Check the game launches before doing anything else.** The build ships a
`D3D12/` folder and a `UnityPlayer.dll` compiled for **DirectX 12**. VMware
Workstation's virtual GPU supports up to **DirectX 11** (and OpenGL 4.3). Many
Unity titles fall back to D3D11 automatically, but not all — and if this one
doesn't, you'll find out in ten seconds instead of after an evening of setup.

```
# in the VM, before installing anything else
# rely on Steam: install the game, launch it, and watch for a black window,
# an immediate exit, or a "failed to initialise graphics" dialog.
```

If it won't run, stop and pick another host:

| Fallback | Cost | Notes |
|---|---|---|
| **Browser build** (`isekai-waifu-overlord.com`) | free | cheapest option; runs anywhere, and CDP clicking works in the **background** — no VM needed at all |
| Second physical machine | — | if you have one, it just works |
| Cloud GPU instance | ~$0.40–1.00/hr | only worth it if you specifically need the Unity build headless |

## VM settings

| Setting | Value | Why |
|---|---|---|
| Guest OS | Windows 11 x64 | the bot is Win32 |
| Memory | 8 GB+ | Steam + Unity + 2.3 GB game |
| Processors | 4+ | OCR is the bottleneck and it's CPU-side |
| **Accelerate 3D graphics** | **on** | without it the game is a slideshow or won't start |
| Graphics memory | max available | |
| Display resolution | **a 16:9 mode** (e.g. 1920×1080) | see below |

**Keep the aspect ratio 16:9.** Screen regions are stored as *fractions* of the
frame, so a 1920×1080 VM works with regions calibrated at 2560×1440 — but only
because both are 16:9. A 16:10 or 4:3 mode shifts everything and the regions will
need re-calibrating.

## Getting the project into the VM

Either works:

```bash
# option A: clone inside the VM
git clone <your-remote> IsekaiOverlord

# option B: share the host folder
#   VM Settings -> Options -> Shared Folders -> add D:\github\Python-Projects
```

Option B also lets you edit on the host and run in the VM, which is the nicer
loop while calibrating regions.

## Installing

```bash
# Python 3.12+ (3.14 is what this was developed on)
python -m pip install -r requirements.txt
```

No GPU, no separate OCR binary, no model downloads — RapidOCR bundles its models
and runs on onnxruntime.

## Verify, in this order

Do these before arming anything. Each one is read-only.

```bash
# 1. can it capture the game window at all?
python tools/grab.py vm-frame.png

# 2. does it recognise the screen?
python tools/run.py --check

# 3. re-check the building regions at the VM's resolution (see below)
python -m pytest -m slow
```

### Step 3 matters

The fractional regions should carry over, but a different resolution means
different pixel rounding, and this game's number crops are fussy. Run:

```bash
python tools/probe.py --save overlay.png
```

Open `overlay.png` and check the cyan region boxes actually sit on the things
they claim to. If they've drifted, the fast fix is to re-run the calibration
against a fresh screenshot:

```bash
python tools/before_after.py before --tag vm-cal
# (navigate as needed — this tool never clicks)
```

If a region is off, edit `src/iwol/screens.json` and re-run `pytest -m slow`.
The slow tests assert exact values (`1.13T`, `100+22`), so they will tell you
precisely which region broke rather than letting it fail mid-run.

## Running it armed

```bash
python tools/run.py --arm --actuator sendinput --steps 50 \
    --max-gold 2000000000000 --max-gems 0 --keep-frames
```

Read that command before running it:

* `--arm` is required to click anything. Without it, dry run.
* `--max-gold` is the **run-wide** ceiling. `--max-gems 0` means never spend gems.
* `--keep-frames` writes before/after frames next to the journal so a bad
  decision can be reviewed.
* **F12 aborts immediately**, as does Ctrl-C. Both are checked mid-drag.

Then read `runs/journal.jsonl` — or just the terminal, which echoes every action.
Every line says what it did *and why*, including the refusals.

## Running it unattended

Start small. A first armed session worth running is a few dozen steps on the
village loop, watching the journal, with a modest `--max-gold`. Only then:

```bash
python tools/run.py --arm --steps 0 --seconds 3600 \
    --max-gold <cap> --max-gems 0
```

`--steps 0` means unlimited; `--seconds` bounds the run regardless. The stall
detector still aborts after three consecutive actions that change nothing, so a
broken region can't spin forever.

## Known rough edges

* **~2.5 s per step**, almost all of it the identification OCR. Fine for an idle
  game; noticeable if you want tight reaction timing.
* **`b2_income` reads `1.151` instead of `1.15T`** on the 2560×1440 capture — a
  misread magnitude suffix, tracked as an `xfail`. Nothing currently consumes
  those village-card numbers, but don't wire the economy planner to them until
  there's a suffix-plausibility check.
* Only `village` and `building_panel` have routines. Any other screen halts with
  `no routine for screen <name>`, by design.
