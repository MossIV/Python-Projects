"""Routine behaviour — the actual automation decisions.

Two layers:

* **Synthetic contexts** (fast): drive the decision logic through every branch —
  affordable, unaffordable, over budget, unreadable — without a game or OCR.
* **Real fixtures** (slow): read the panel screenshot for real and assert the
  routine extracts the right building, level, gold and cost.

The second layer is what proves the region calibration still matches the UI; the
first is what proves the *decision* on top of it is sane.
"""

from __future__ import annotations

import numpy as np
import pytest

from conftest import fixture_image

from iwol import (
    BrainConfig,
    Budget,
    DryRunActuator,
    Frame,
    ImageBackend,
    NullJournal,
    Ocr,
    ScreenClassifier,
)
from iwol.brain import Context, RoutineOutcome
from iwol.ocr import TextLine
from iwol.routines import BuildingPanelRoutine, VillageRoutine
from iwol.screens import Classification, Region, ScreenSpec


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #


# Regions every routine may try to click.  A synthetic context must define them
# or click_region() returns None and the routine correctly reports BLOCKED
# instead of exercising the branch under test.
CLICKABLE = ("add_workers_btn", "upgrade_btn", "back_btn")


def make_ctx(regions: dict[str, str], gold_budget: float = 1e15, screen: str = "building_panel"):
    """A Context whose screen text is whatever we say it is."""
    names = set(regions) | set(CLICKABLE)
    spec = ScreenSpec(name=screen, regions={k: Region(0, 0, 0.2, 0.2) for k in names})
    texts = {k: [TextLine(v, 0.9, (0, 0, 10, 10))] for k, v in regions.items()}
    cls = Classification(screen, 1.0, "synthetic", spec, texts)
    frame = Frame(np.zeros((200, 300, 3), dtype=np.uint8), (0, 0))
    ctx = Context(
        frame=frame,
        classification=cls,
        ocr=None,
        actuator=DryRunActuator(),
        journal=NullJournal(),
        budget=Budget(max_gems=0, max_gold=int(gold_budget)),
        config=BrainConfig(step_delay=0, settle_time=0),
    )
    return ctx


FULL_WORKERS = {"workers_header": "Current workers 5/5"}
FREE_SLOTS = {"workers_header": "Current workers 2/5"}


# --------------------------------------------------------------------------- #
# building panel — decision logic
# --------------------------------------------------------------------------- #


def test_panel_assigns_workers_when_slots_are_free():
    ctx = make_ctx({**FREE_SLOTS, "upgrade_btn": "UPGRADE 1.13T", "gold": "1.20T"})
    out = BuildingPanelRoutine().run(ctx)
    assert out.status == RoutineOutcome.DONE
    assert out.acted
    assert not out.spent  # assigning workers is free
    clicked = [a for a in ctx.actuator.actions if a[0] == "click"]
    assert len(clicked) == 1


def test_panel_upgrades_when_affordable_and_within_budget():
    ctx = make_ctx(
        {**FULL_WORKERS, "upgrade_btn": "UPGRADE 1.13T", "gold": "1.20T",
         "building_name": "Hot Spring", "building_level": "Lvl 25"},
    )
    out = BuildingPanelRoutine().run(ctx)
    assert out.status == RoutineOutcome.DONE
    assert out.acted
    assert out.spent == {"gold": int(1.13e12)}


def test_panel_will_not_upgrade_when_it_cannot_afford_it():
    ctx = make_ctx({**FULL_WORKERS, "upgrade_btn": "UPGRADE 1.13T", "gold": "500B"})
    out = BuildingPanelRoutine().run(ctx)
    assert "cannot afford" in out.detail
    assert not out.spent
    # and it must leave the panel rather than sit there
    clicked = [a for a in ctx.actuator.actions if a[0] == "click"]
    assert len(clicked) == 1


def test_panel_will_not_upgrade_past_the_run_budget():
    ctx = make_ctx(
        {**FULL_WORKERS, "upgrade_btn": "UPGRADE 1.13T", "gold": "1.20T"},
        gold_budget=1e11,  # budget far below the cost
    )
    out = BuildingPanelRoutine().run(ctx)
    assert "budget" in out.detail.lower()
    assert not out.spent
    assert ctx.budget.spent_gold == 0


def test_panel_blocks_when_the_cost_is_unreadable():
    ctx = make_ctx({**FULL_WORKERS, "upgrade_btn": "UPGRADE", "gold": "1.20T"})
    out = BuildingPanelRoutine().run(ctx)
    assert out.status == RoutineOutcome.BLOCKED
    assert "upgrade cost" in out.detail


def test_panel_blocks_when_gold_is_unreadable():
    ctx = make_ctx({**FULL_WORKERS, "upgrade_btn": "UPGRADE 1.13T", "gold": ""})
    out = BuildingPanelRoutine().run(ctx)
    assert out.status == RoutineOutcome.BLOCKED
    assert "gold balance" in out.detail


def test_panel_respects_a_per_click_cap():
    ctx = make_ctx({**FULL_WORKERS, "upgrade_btn": "UPGRADE 1.13T", "gold": "1.20T"})
    out = BuildingPanelRoutine(upgrade_cap=1e9).run(ctx)
    assert not out.spent
    assert "cap" in out.detail


# --------------------------------------------------------------------------- #
# village — cycling through buildings
# --------------------------------------------------------------------------- #


def test_village_opens_a_building_panel():
    regions = {f"b{i}_btn": "x" for i in range(1, 8)}
    ctx = make_ctx(regions, screen="village")
    routine = VillageRoutine()
    out = routine.run(ctx)
    assert out.status == RoutineOutcome.DONE
    assert out.acted
    assert len([a for a in ctx.actuator.actions if a[0] == "click"]) == 1


def test_village_cycles_through_every_building():
    regions = {f"b{i}_btn": "x" for i in range(1, 8)}
    routine = VillageRoutine()
    seen = []
    for _ in range(7):
        ctx = make_ctx(regions, screen="village")
        routine.run(ctx)
        seen.append(routine._index % len(routine.buttons))
    assert sorted(seen) == list(range(7))  # no repeats, none skipped


def test_village_blocks_when_no_buttons_are_defined():
    ctx = make_ctx({"gold": "1T"}, screen="village")
    out = VillageRoutine().run(ctx)
    assert out.status == RoutineOutcome.BLOCKED


# --------------------------------------------------------------------------- #
# real fixtures — proves the region calibration still matches the UI
# --------------------------------------------------------------------------- #


@pytest.fixture(scope="session")
def classifier(ocr_engine):
    return ScreenClassifier.from_json(ocr=ocr_engine)


@pytest.mark.slow
def test_panel_reading_from_the_real_screenshot(ocr_engine, classifier):
    path = fixture_image("building_panel")
    if not path.exists():
        pytest.skip("fixture not present")
    frame = ImageBackend(str(path)).grab()
    cls = classifier.classify(frame)
    assert cls.name == "building_panel"

    ctx = Context(
        frame=frame,
        classification=cls,
        ocr=ocr_engine,
        actuator=DryRunActuator(),
        journal=NullJournal(),
        budget=Budget(max_gems=0, max_gold=int(1e15)),
        config=BrainConfig(step_delay=0, settle_time=0),
    )
    r = BuildingPanelRoutine().read(ctx)

    assert "Spring" in r.building or "Hot" in r.building
    assert r.level == 25
    assert r.workers_current == 2
    assert r.workers_max == 5
    assert r.slots_free == 3
    # gold 1.20T and cost 1.13T as they appear on that screen
    assert r.gold == pytest.approx(1.20e12, rel=0.02)
    assert r.cost == pytest.approx(1.13e12, rel=0.02)
    assert r.cost < r.gold  # so this building should be upgradeable


@pytest.mark.slow
def test_panel_routine_assigns_workers_on_the_real_screenshot(ocr_engine, classifier):
    """The captured screen shows 2/5 workers, so the routine must assign first."""
    path = fixture_image("building_panel")
    if not path.exists():
        pytest.skip("fixture not present")
    frame = ImageBackend(str(path)).grab()
    cls = classifier.classify(frame)
    ctx = Context(
        frame=frame, classification=cls, ocr=ocr_engine,
        actuator=DryRunActuator(), journal=NullJournal(),
        budget=Budget(max_gems=0, max_gold=int(1e15)),
        config=BrainConfig(step_delay=0, settle_time=0),
    )
    out = BuildingPanelRoutine().run(ctx)
    assert out.status == RoutineOutcome.DONE
    assert "workers" in out.detail.lower()
    assert not out.spent


@pytest.mark.slow
def test_village_routine_clicks_a_real_building_button(ocr_engine, classifier):
    path = fixture_image("village")
    if not path.exists():
        pytest.skip("fixture not present")
    frame = ImageBackend(str(path)).grab()
    cls = classifier.classify(frame)
    assert cls.name == "village"
    ctx = Context(
        frame=frame, classification=cls, ocr=ocr_engine,
        actuator=DryRunActuator(), journal=NullJournal(),
        budget=Budget(max_gems=0, max_gold=int(1e15)),
        config=BrainConfig(step_delay=0, settle_time=0),
    )
    out = VillageRoutine().run(ctx)
    assert out.status == RoutineOutcome.DONE
    action, args = ctx.actuator.actions[0]
    assert action == "click"
    # the click must land inside the 2560x1440 frame
    assert 0 <= args[0] < 2560 and 0 <= args[1] < 1440
