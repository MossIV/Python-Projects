"""Brain loop: safety gates, action verification, and the stall detector.

Everything here uses stubs, so these tests are fast and deterministic — they
run with no game, no window and no input injection.
"""

from __future__ import annotations

import numpy as np
import pytest

from iwol.brain import Brain, BrainConfig, Context, RoutineOutcome
from iwol.capture import Frame
from iwol.actuator import DryRunActuator
from iwol.journal import NullJournal
from iwol.screens import Classification, ScreenSpec


# --------------------------------------------------------------------------- #
# stubs
# --------------------------------------------------------------------------- #


class StubCapture:
    """Replays frames in order; repeats the last one forever after."""

    def __init__(self, frames: list[Frame]):
        self.frames = list(frames)
        self.calls = 0

    def grab(self) -> Frame:
        f = self.frames[min(self.calls, len(self.frames) - 1)]
        self.calls += 1
        return f

    def close(self):
        pass


class StubClassifier:
    """Returns preset screen names, one per call."""

    def __init__(self, names: list[str]):
        self.names = list(names)
        self.calls = 0
        self.specs: list[ScreenSpec] = []

    def classify(self, frame, texts=None) -> Classification:
        name = self.names[min(self.calls, len(self.names) - 1)]
        self.calls += 1
        if name in {"unknown", "blank"}:
            return Classification(name, 0.0, "stub: no match", None)
        spec = ScreenSpec(name=name, regions={})
        return Classification(name, 1.0, "stub", spec)


class StubRoutine:
    def __init__(self, name, screens, outcome, calls_until=10**9):
        self.name = name
        self.screens = tuple(screens)
        self.outcome = outcome
        self.calls_until = calls_until
        self.calls = 0
        self.contexts: list[Context] = []

    def run(self, ctx: Context) -> RoutineOutcome:
        self.calls += 1
        self.contexts.append(ctx)
        if self.calls > self.calls_until:
            return RoutineOutcome(RoutineOutcome.BLOCKED, "stub exhausted")
        return self.outcome


def make_frame(value: int = 30) -> Frame:
    return Frame(np.full((60, 80, 3), value, dtype=np.uint8), (0, 0))


def make_brain(capture, classifier, routines, config=None, should_stop=None):
    return Brain(
        capture=capture,
        ocr=None,
        actuator=DryRunActuator(),  # inert; these tests must never inject input
        classifier=classifier,
        routines=routines,
        journal=NullJournal(),
        config=config or BrainConfig(step_delay=0, settle_time=0),
        should_stop=should_stop,
    )


FAST = BrainConfig(step_delay=0, settle_time=0)


# --------------------------------------------------------------------------- #
# safety gates
# --------------------------------------------------------------------------- #


def test_unknown_screen_halts_immediately():
    brain = make_brain(StubCapture([make_frame()]), StubClassifier(["unknown"]), [])
    report = brain.run(max_steps=10)
    assert report.steps == 1
    assert "unknown screen" in report.stopped_because


def test_blank_capture_is_reported_not_crashed():
    brain = make_brain(StubCapture([make_frame()]), StubClassifier(["blank"]), [])
    report = brain.run(max_steps=5)
    assert report.stopped_because == "unknown screen (stub: no match)"


def test_forbidden_screen_aborts_before_any_routine_runs():
    routine = StubRoutine("village", ["store"], RoutineOutcome(RoutineOutcome.DONE, "x"))
    brain = make_brain(StubCapture([make_frame()]), StubClassifier(["store"]), [routine])
    report = brain.run(max_steps=10)
    assert "forbidden screen" in report.stopped_because
    assert routine.calls == 0  # never dispatched


def test_missing_routine_halts():
    brain = make_brain(StubCapture([make_frame()]), StubClassifier(["village"]), [])
    report = brain.run(max_steps=10)
    assert "no routine for screen village" in report.stopped_because


def test_kill_switch_stops_the_loop():
    brain = make_brain(
        StubCapture([make_frame()]),
        StubClassifier(["village"]),
        [],
        should_stop=lambda: True,
    )
    report = brain.run(max_steps=10)
    assert report.stopped_because == "kill switch"
    assert report.steps == 0


def test_max_steps_is_respected():
    routine = StubRoutine("village", ["village"], RoutineOutcome(RoutineOutcome.CONTINUE, "idle"))
    brain = make_brain(StubCapture([make_frame()]), StubClassifier(["village"]), [routine])
    report = brain.run(max_steps=3)
    assert report.steps == 3
    assert report.stopped_because == "max steps reached"
    assert routine.calls == 3


def test_max_runtime_is_respected():
    routine = StubRoutine("village", ["village"], RoutineOutcome(RoutineOutcome.CONTINUE, "idle"))
    cfg = BrainConfig(step_delay=0.05, settle_time=0, max_runtime=0.12)
    brain = make_brain(StubCapture([make_frame()]), StubClassifier(["village"]), [routine], cfg)
    brain.config.max_runtime = 0.12
    report = brain.run()
    assert report.stopped_because == "max runtime reached"


# --------------------------------------------------------------------------- #
# budget — money is guarded, not trusted
# --------------------------------------------------------------------------- #


def test_spending_with_no_budget_aborts():
    routine = StubRoutine("village", ["village"],
                          RoutineOutcome(RoutineOutcome.DONE, "bought", spent={"gems": 5}))
    brain = make_brain(StubCapture([make_frame(), make_frame(200)]), StubClassifier(["village"]), [routine])
    report = brain.run(max_steps=5)
    assert "budget exceeded" in report.stopped_because
    assert brain.budget.spent_gems == 0


def test_spending_within_budget_is_allowed():
    routine = StubRoutine("village", ["village"],
                          RoutineOutcome(RoutineOutcome.DONE, "bought", spent={"gems": 5}))
    cfg = BrainConfig(step_delay=0, settle_time=0, max_gems_spent=10)
    brain = make_brain(StubCapture([make_frame(0), make_frame(255)]), StubClassifier(["village"]), [routine], cfg)
    report = brain.run(max_steps=1)
    assert brain.budget.spent_gems == 5
    assert report.actions == 1


def test_routine_abort_stops_the_run():
    routine = StubRoutine("village", ["village"],
                          RoutineOutcome(RoutineOutcome.ABORT, "store opened"))
    brain = make_brain(StubCapture([make_frame()]), StubClassifier(["village"]), [routine])
    report = brain.run(max_steps=5)
    assert report.stopped_because == "store opened"


def test_blocked_routine_stops_the_run():
    routine = StubRoutine("village", ["village"],
                          RoutineOutcome(RoutineOutcome.BLOCKED, "layout missing"))
    brain = make_brain(StubCapture([make_frame()]), StubClassifier(["village"]), [routine])
    report = brain.run(max_steps=5)
    assert "blocked: layout missing" in report.stopped_because


# --------------------------------------------------------------------------- #
# verification — the stall detector
# --------------------------------------------------------------------------- #


def test_unchanged_screen_counts_as_a_miss_and_aborts():
    routine = StubRoutine("village", ["village"],
                          RoutineOutcome(RoutineOutcome.DONE, "clicked", spent={"gold": 1}))
    cfg = BrainConfig(step_delay=0, settle_time=0, max_gold_spent=100, max_consecutive_misses=2)
    # identical frames => the action appears to do nothing
    brain = make_brain(StubCapture([make_frame(50)]), StubClassifier(["village"]), [routine], cfg)
    report = brain.run(max_steps=10)
    assert report.misses == 2
    assert "no visible effect" in report.stopped_because


def test_changed_screen_resets_the_miss_counter():
    class Alternating(StubCapture):
        def grab(self):
            f = make_frame(0 if self.calls % 2 == 0 else 255)
            self.calls += 1
            return f

    routine = StubRoutine("village", ["village"],
                          RoutineOutcome(RoutineOutcome.DONE, "clicked", spent={"gold": 1}))
    cfg = BrainConfig(step_delay=0, settle_time=0, max_gold_spent=1000, max_consecutive_misses=2)
    brain = make_brain(Alternating([make_frame()]), StubClassifier(["village"]), [routine], cfg)
    report = brain.run(max_steps=4)
    assert report.misses == 0
    assert report.stopped_because == "max steps reached"


def test_verification_only_runs_when_something_was_spent():
    routine = StubRoutine("village", ["village"], RoutineOutcome(RoutineOutcome.CONTINUE, "collected"))
    cfg = BrainConfig(step_delay=0, settle_time=0)
    brain = make_brain(StubCapture([make_frame()]), StubClassifier(["village"]), [routine], cfg)
    report = brain.run(max_steps=2)
    assert report.misses == 0


def test_routine_receives_the_live_budget_and_journal():
    routine = StubRoutine("village", ["village"], RoutineOutcome(RoutineOutcome.CONTINUE, "x"))
    cfg = BrainConfig(step_delay=0, settle_time=0, max_gems_spent=42)
    brain = make_brain(StubCapture([make_frame()]), StubClassifier(["village"]), [routine], cfg)
    brain.run(max_steps=1)
    ctx = routine.contexts[0]
    assert ctx.budget.max_gems == 42
    assert ctx.journal is not None
    assert ctx.screen == "village"


def test_routine_lookup_prefers_registration_order():
    first = StubRoutine("first", ["village"], RoutineOutcome(RoutineOutcome.CONTINUE, "a"))
    second = StubRoutine("second", ["village"], RoutineOutcome(RoutineOutcome.CONTINUE, "b"))
    brain = make_brain(StubCapture([make_frame()]), StubClassifier(["village"]), [first, second])
    assert brain.routine_for("village") is first
    assert brain.routine_for("nothing") is None
