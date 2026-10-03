"""The control loop: perceive -> decide -> act -> verify.

Design rules that came out of what actually breaks game bots:

* **Verify, never assume.**  After an action the brain re-grabs and measures how
  much the screen moved.  An action that produced no change is a *miss*, and
  consecutive misses abort the run — this is what stops a bot from sitting in a
  corner spinning at 30 clicks/second.
* **Fail loud on the unknown.**  An unrecognised screen halts and reports, it
  does not guess.
* **Money is guarded, not trusted.**  Routines *report* what they spent; the
  brain keeps the ledger and aborts the run when a cap is crossed.  A routine
  cannot spend past its budget by lying about it.
* **Real-money purchases are structurally impossible.**  Any screen matching the
  forbidden list aborts the run before a routine is ever dispatched.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Protocol

from .actuator import Aborted, Actuator
from .capture import Frame
from .journal import Journal, NullJournal
from .ocr import Ocr
from .screens import Classification, ScreenClassifier
from .vision import diff_ratio


# --------------------------------------------------------------------------- #
# config & context
# --------------------------------------------------------------------------- #


@dataclass
class BrainConfig:
    step_delay: float = 0.6  # idle between successful steps
    settle_time: float = 0.9  # wait for the game to react before verifying
    max_steps: int = 0  # 0 = unlimited
    max_runtime: float = 0.0  # seconds, 0 = unlimited
    max_consecutive_misses: int = 3
    min_screen_change: float = 0.002  # fraction of pixels that must change
    forbidden_screens: tuple[str, ...] = (
        "store",
        "shop",
        "purchase",
        "checkout",
        "payment",
        "topup",
    )
    max_gems_spent: int = 0  # 0 = never spend gems
    max_gold_spent: int = 0  # 0 = never spend gold


@dataclass
class Budget:
    """Ledger for in-game currency.  Real money is out of scope entirely."""

    max_gems: int = 0
    max_gold: int = 0
    spent_gems: int = 0
    spent_gold: int = 0
    log: list[str] = field(default_factory=list)

    def can_spend(self, gems: int = 0, gold: int = 0) -> bool:
        return (self.spent_gems + gems <= self.max_gems) and (self.spent_gold + gold <= self.max_gold)

    def spend(self, gems: int = 0, gold: int = 0, reason: str = "") -> bool:
        if not self.can_spend(gems, gold):
            return False
        self.spent_gems += gems
        self.spent_gold += gold
        if reason:
            self.log.append(f"spend {gems}gems/{gold}gold: {reason}")
        return True

    def remaining(self) -> tuple[int, int]:
        return (self.max_gems - self.spent_gems, self.max_gold - self.spent_gold)


@dataclass
class Context:
    """Everything a routine is allowed to use."""

    frame: Frame
    classification: Classification
    ocr: Ocr
    actuator: Actuator
    journal: Journal
    budget: Budget
    config: BrainConfig

    @property
    def screen(self) -> str:
        return self.classification.name

    def text_in(self, region: str) -> str:
        return self.classification.text_in(region)

    def find_in(self, region: str, needle: str):
        return self.classification.find_in(region, needle)


# --------------------------------------------------------------------------- #
# routines
# --------------------------------------------------------------------------- #


class RoutineOutcome:
    DONE = "done"
    CONTINUE = "continue"
    BLOCKED = "blocked"
    ABORT = "abort"

    def __init__(self, status: str, detail: str = "", spent: dict[str, int] | None = None):
        self.status = status
        self.detail = detail
        self.spent = spent or {}


class Routine(Protocol):
    """Structural type a routine must satisfy.  Not dataclassed on purpose —
    routines are duck-typed, so ``VillageRoutine`` need not inherit from this."""

    name: str
    screens: tuple[str, ...]

    def run(self, ctx: Context) -> RoutineOutcome: ...

# --------------------------------------------------------------------------- #
# run report
# --------------------------------------------------------------------------- #


@dataclass
class RunReport:
    steps: int = 0
    actions: int = 0
    misses: int = 0
    stopped_because: str = "max steps reached"
    duration: float = 0.0
    budget: Budget | None = None

    def summary(self) -> str:
        spent = ""
        if self.budget:
            spent = f" | spent {self.budget.spent_gems} gems, {self.budget.spent_gold} gold"
        return (
            f"{self.steps} steps, {self.actions} actions, {self.misses} misses, "
            f"{self.duration:.1f}s | {self.stopped_because}{spent}"
        )


# --------------------------------------------------------------------------- #
# brain
# --------------------------------------------------------------------------- #


class Brain:
    def __init__(
        self,
        capture,
        ocr: Ocr,
        actuator: Actuator,
        classifier: ScreenClassifier,
        routines: list[Routine] | None = None,
        journal: Journal | None = None,
        config: BrainConfig | None = None,
        should_stop=None,
    ):
        self.capture = capture
        self.ocr = ocr
        self.actuator = actuator
        self.classifier = classifier
        self.routines = list(routines or [])
        self.journal = journal or NullJournal()
        self.config = config or BrainConfig()
        self.should_stop = should_stop or (lambda: False)
        self.budget = Budget(max_gems=self.config.max_gems_spent, max_gold=self.config.max_gold_spent)

    # -- helpers ---------------------------------------------------------- #

    def register(self, routine: Routine) -> None:
        self.routines.append(routine)

    def routine_for(self, screen: str) -> Routine | None:
        """First routine declaring this screen.  Order of registration wins."""
        for routine in self.routines:
            if screen in routine.screens:
                return routine
        return None

    def _grab(self) -> Frame:
        return self.capture.grab()

    def _is_forbidden(self, screen: str) -> bool:
        return any(bad in screen.lower() for bad in self.config.forbidden_screens)

    # -- main loop -------------------------------------------------------- #

    def run(self, max_steps: int | None = None) -> RunReport:
        cfg = self.config
        limit = cfg.max_steps if max_steps is None else max_steps
        report = RunReport(budget=self.budget)
        started = time.time()
        consecutive_misses = 0

        self.journal.event(
            "run_start",
            detail=f"actuator={self.actuator.name} dry_run={self.actuator.dry_run} steps={limit or 'inf'}",
        )

        try:
            while True:
                if self.should_stop():
                    report.stopped_because = "kill switch"
                    break
                if limit and report.steps >= limit:
                    report.stopped_because = "max steps reached"
                    break
                if cfg.max_runtime and (time.time() - started) >= cfg.max_runtime:
                    report.stopped_because = "max runtime reached"
                    break

                frame = self._grab()
                report.steps += 1
                cls = self.classifier.classify(frame)
                self.journal.event(
                    "observe", screen=cls.name, confidence=cls.confidence, detail=cls.evidence
                )

                # -- safety gate, before any routine is consulted ------------- #
                if self._is_forbidden(cls.name):
                    report.stopped_because = f"forbidden screen: {cls.name}"
                    self.journal.event("abort", ok=False, detail=report.stopped_because)
                    break

                if not cls.known:
                    report.stopped_because = f"unknown screen ({cls.evidence})"
                    self.journal.save_frame(frame, "unknown")
                    self.journal.event("unknown_screen", ok=False, detail=cls.evidence)
                    break

                routine = self.routine_for(cls.name)
                if routine is None:
                    report.stopped_because = f"no routine for screen {cls.name}"
                    self.journal.event("no_routine", ok=False, detail=cls.name)
                    break

                g_rem, gold_rem = self.budget.remaining()
                self.journal.event(
                    "dispatch",
                    screen=cls.name,
                    action=routine.name,
                    detail=f"budget remaining gems={g_rem} gold={gold_rem}",
                )

                ctx = Context(frame, cls, self.ocr, self.actuator, self.journal, self.budget, cfg)
                before = frame
                try:
                    outcome = routine.run(ctx)
                except Aborted:
                    report.stopped_because = "kill switch (during action)"
                    break

                if outcome.status == RoutineOutcome.ABORT:
                    report.stopped_because = outcome.detail or "routine requested abort"
                    self.journal.event("abort", ok=False, detail=report.stopped_because)
                    break

                # -- apply reported spending against the ledger -------------- #
                if outcome.spent:
                    gems = int(outcome.spent.get("gems", 0))
                    gold = int(outcome.spent.get("gold", 0))
                    if not self.budget.spend(gems, gold, reason=f"{routine.name} on {cls.name}"):
                        report.stopped_because = (
                            f"budget exceeded by {routine.name}: "
                            f"wanted {gems} gems/{gold} gold, {self.budget.remaining()} left"
                        )
                        self.journal.event("budget_abort", ok=False, detail=report.stopped_because)
                        break
                    report.actions += 1

                # -- verify the action actually did something ---------------- #
                if outcome.status in (RoutineOutcome.DONE, RoutineOutcome.CONTINUE) and outcome.spent:
                    time.sleep(cfg.settle_time)
                    after = self._grab()
                    changed = diff_ratio(before, after)
                    moved = changed >= cfg.min_screen_change
                    self.journal.event(
                        "verify",
                        screen=cls.name,
                        action=routine.name,
                        detail=f"{outcome.detail} ({'moved' if moved else 'no change'})",
                        ok=moved,
                        changed=changed,
                    )
                    if not moved:
                        consecutive_misses += 1
                        report.misses += 1
                        if consecutive_misses >= cfg.max_consecutive_misses:
                            report.stopped_because = (
                                f"{consecutive_misses} consecutive actions had no visible effect"
                            )
                            self.journal.save_frame(after, "stalled")
                            break
                    else:
                        consecutive_misses = 0

                if outcome.status == RoutineOutcome.BLOCKED:
                    report.stopped_because = f"{routine.name} blocked: {outcome.detail}"
                    self.journal.event("blocked", ok=False, detail=outcome.detail)
                    break

                time.sleep(cfg.step_delay)

        finally:
            report.duration = time.time() - started
            self.journal.event("run_end", detail=report.summary())

        return report

    def close(self):
        try:
            self.actuator.close()
        finally:
            try:
                self.capture.close()
            finally:
                self.journal.close()
