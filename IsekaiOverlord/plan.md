# Isekai Waifu Overlord — CV Bot: Plan

## Verified facts (probed, not assumed)

| Item | Result |
|---|---|
| Game process | `IsekaiWaifuOverlord.exe`, PID 43208, running |
| Install path | `G:\SteamLibrary\steamapps\common\IsekaiWaifuOverlord\` (2.3 GB) |
| Engine | **Unity** — `UnityPlayer.dll`, `MonoBleedingEdge/`, `*_Data/`, D3D12 |
| Window | hwnd 658454, `0,0 → 2560,1440` (fullscreen borderless) |
| Capture | `PrintWindow(hwnd, PW_RENDERFULLCONTENT)` → clean 2560×1440 BGR. **Works with the window unfocused.** ✅ |
| OCR | RapidOCR (onnxruntime 1.30) on py3.14 → 20 boxes, ~2.4 s full frame, boxes match UI exactly ✅ |
| Python | 3.14.7; numpy 2.5.3, PIL 12.3, cv2 5.0.0, mss, onnxruntime installed |
| Node | v26.7.0 (available if we want a Playwright route) |

## Architecture

```
┌─ perceive ─────────────┐   ┌─ decide ──────┐   ┌─ act ──────────────┐
│ capture (PrintWindow)  │   │ screen ID     │   │ click(x,y)         │
│ OCR (RapidOCR, crops)  │──▶│ state machine │──▶│ drag / key         │
│ template match (cv2)   │   │ routine lib   │   │ spend guards       │
└────────────────────────┘   └───────────────┘   └────────────────────┘
                                     │
                              journal (JSONL) ──▶ verify each action moved state
```

- **Perception** — capture is cheap and background-safe; OCR is the slow part, so we OCR *only
  named regions* per screen (~50 ms) rather than the full frame.
- **Screen ID** — cheap region fingerprint + OCR keyword vote; confidence logged so we can see
  where it misidentifies.
- **Routines** — one handler per screen: `they recognise → they act → they verify`.
- **Verification** — every action re-checks that the expected UI change happened. A click that
  silently misses is the #1 failure mode of game bots; it must be detected, not assumed.

## The decision that shapes everything: input method

Password: the bot's mouse clicks. This is the real fork.

| Option | Background? | Reliability on Unity/D3D12 | Cost |
|---|---|---|---|
| **A. `SendInput`** (real hardware events) | ❌ game must be foreground | High | PC is locked to the game while bot runs |
| **B. `PostMessage` WM_* to hwnd** | ✅ fully background | **Likely fails** — Unity reads raw input | Free to test |
| **C. Windowed game + SendInput** | ❌ | High | Needs borderless-window setup, saves desktop space |
| **D. Browser build + Playwright/CDP** | ✅ fully background | High — synthetic clicks are native there | Re-login; game runs in Chrome, not Steam |
| **E. BepInEx/MelonLoader mod** | ✅ | Highest (no clicking at all) | Not CV — a different project |

**Recommendation: test B for ~2 minutes; if Unity ignores it, go with A**, and keep the code
`actuator`-pluggable so D or E can slot in later without touching the brain.

> Note: capture already works unfocused, so *watching* costs nothing. It's only the clicking
> that may force the game to the foreground.

## Scope — what the bot should actually do

The game is an idle RPG. Value-ordered automation targets:

1. **Village economy** — collect income, buy/upgrade buildings (largest income driver)
2. **Village orders** — quest board → gold + gems
3. **Farm** — plant / harvest on the crop cycle
4. **Expeditions / auto-battles** — send the squad, time ultimates
5. **Inventory** — sell hammers → XP (dev-confirmed: 10 XP/hammer)
6. **Gacha** — pull summon tickets when a threshold is met
7. **Affinity** — gifts & dates to raise workers
8. **Endless labyrinth** — roguelite runs
9. **Rebirth** — reset for permanent multipliers

**Milestone 1 = screen recogniser + the "collect & upgrade" routine.** It exercises the entire
loop (see → decide → click → verify) on the least destructive screen, and every later routine
reuses the same plumbing.

## Hard safety rules

- **Never automate a real-money purchase.** Gem/gold spending inside the game is fine and
  capped by a configurable budget; opening the store or any payment UI aborts the routine.
- Every click is journalled with before/after frames so a bad action is auditable.
- Global kill switch: a hotkey + a watchdog that stops if 3 consecutive actions fail to verify.

## Layout

```
IsekaiOverlord/
├─ plan.md                  ← this file
├─ requirements.txt
├─ src/iwol/
│  ├─ capture.py            # PrintWindow grabber (verified working)
│  ├─ ocr.py                # RapidOCR wrapper, region-cropped
│  ├─ vision.py             # template match, screen fingerprints
│  ├─ screens.py            # screen classifier + region definitions
│  ├─ actuator.py           # SendInput + PostMessage backends, one interface
│  ├─ routines/             # one module per screen
│  ├─ brain.py              # state machine loop
│  └─ journal.py            # JSONL action log + verification
└─ tools/                   # probes used during development
```
