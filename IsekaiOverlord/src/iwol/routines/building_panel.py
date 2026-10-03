"""The building management panel — where upgrades and workers actually happen.

Discovered by experiment rather than assumption: the gold diamond button on a
village card does **not** upgrade anything, it opens this panel.  The panel is
where the real `UPGRADE` button lives (and it shows its gold cost), alongside
the worker assignment system.

Priorities, cheapest-and-safest first:

1. **Assign workers** while slots are free.  Free, reversible, and the worker
   bonuses are large (+75% on Farm in the observed capture), so this is the best
   return available and it costs nothing.
2. **Upgrade** if the cost is readable, affordable against the *displayed* gold
   balance, and inside the run's budget.
3. Otherwise **leave** — back to the village so the caller can try another
   building.

Every refusal path reports why.  "Nothing affordable" and "budget exhausted"
look identical on screen but mean very different things to a human reading the
journal.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ..brain import Context, RoutineOutcome
from ..ocr import parse_numbers


@dataclass
class PanelReading:
    building: str = ""
    level: float | None = None
    gold: float | None = None
    cost: float | None = None
    workers_current: int | None = None
    workers_max: int | None = None

    @property
    def slots_free(self) -> int:
        if self.workers_current is None or self.workers_max is None:
            return 0
        return max(0, self.workers_max - self.workers_current)


class BuildingPanelRoutine:
    """Assign workers, then upgrade if it's worth it and allowed."""

    name = "building_panel"
    screens = ("building_panel",)

    def __init__(self, upgrade_cap: float = float("inf")):
        # Guards against a single runaway purchase; the run-wide cap lives in
        # the brain's budget ledger, this is the per-click ceiling.
        self.upgrade_cap = upgrade_cap

    # -- reading ---------------------------------------------------------- #

    def read(self, ctx: Context) -> PanelReading:
        r = PanelReading()
        r.building = ctx.text_in("building_name").replace(" ", " ").strip()

        lvl = ctx.numbers_in("building_level")
        r.level = lvl[-1] if lvl else None

        gold = ctx.numbers_in("gold")
        # The gold region should hold one value; if OCR splits or a neighbouring
        # value bleeds in, the balance is the largest number there.
        r.gold = max(gold) if gold else None

        # upgrade_btn reads e.g. ['UPGRADE', '1.13T'] -- the cost is its number.
        costs = ctx.numbers_in("upgrade_btn")
        r.cost = max(costs) if costs else None

        workers = ctx.numbers_in("workers_header")  # 'Current workers 2/5' -> [2, 5]
        if len(workers) >= 2:
            r.workers_current, r.workers_max = int(workers[0]), int(workers[1])
        return r

    # -- steps ------------------------------------------------------------ #

    def _assign_workers(self, ctx: Context, r: PanelReading) -> RoutineOutcome:
        res = ctx.click_region("add_workers_btn")
        if res is None:
            return RoutineOutcome(RoutineOutcome.BLOCKED, "add_workers_btn region not defined")
        ctx.journal.event(
            "assign_workers", screen=ctx.screen, action="add_best_workers",
            detail=f"{r.workers_current}/{r.workers_max} -> clicked ({res.detail})", ok=res.ok,
        )
        if not res.ok:
            return RoutineOutcome(RoutineOutcome.BLOCKED, f"click refused: {res.detail}")
        return RoutineOutcome(
            RoutineOutcome.DONE,
            f"assigned best workers (was {r.workers_current}/{r.workers_max})",
            acted=True,
        )

    def _upgrade(self, ctx: Context, r: PanelReading) -> RoutineOutcome:
        if r.cost is None:
            return RoutineOutcome(
                RoutineOutcome.BLOCKED,
                "could not read the upgrade cost from the UPGRADE button",
            )
        if r.cost > self.upgrade_cap:
            return RoutineOutcome(
                RoutineOutcome.DONE,
                f"upgrade costs {r.cost:,.0f}, above the per-click cap {self.upgrade_cap:,.0f}",
            )
        if r.gold is None:
            return RoutineOutcome(RoutineOutcome.BLOCKED, "could not read the gold balance")
        if r.cost > r.gold:
            return RoutineOutcome(
                RoutineOutcome.DONE,
                f"cannot afford: {r.building} L{r.level} costs {r.cost:,.0f}, have {r.gold:,.0f}",
            )
        if not ctx.budget.can_spend(gold=int(r.cost)):
            remaining_gold = ctx.budget.remaining()[1]
            return RoutineOutcome(
                RoutineOutcome.DONE,
                f"run budget would be exceeded: cost {r.cost:,.0f}, {remaining_gold:,} left",
            )

        res = ctx.click_region("upgrade_btn")
        if res is None:
            return RoutineOutcome(RoutineOutcome.BLOCKED, "upgrade_btn region not defined")
        ctx.journal.event(
            "upgrade", screen=ctx.screen, action=r.building or "building",
            detail=f"L{r.level} for {r.cost:,.0f} gold ({res.detail})", ok=res.ok,
        )
        if not res.ok:
            return RoutineOutcome(RoutineOutcome.BLOCKED, f"click refused: {res.detail}")
        return RoutineOutcome(
            RoutineOutcome.DONE,
            f"upgraded {r.building} L{r.level} for {r.cost:,.0f} gold",
            spent={"gold": int(r.cost)},
            acted=True,
        )

    def _leave(self, ctx: Context, why: str) -> RoutineOutcome:
        res = ctx.click_region("back_btn")
        if res is None or not res.ok:
            return RoutineOutcome(RoutineOutcome.BLOCKED, f"{why}; and the back button was not clickable")
        ctx.journal.event("leave_panel", screen=ctx.screen, detail=why)
        return RoutineOutcome(RoutineOutcome.DONE, f"{why}; left the panel", acted=True)

    # -- entry point ------------------------------------------------------ #

    def run(self, ctx: Context) -> RoutineOutcome:
        r = self.read(ctx)
        ctx.journal.event(
            "panel_state", screen=ctx.screen, action=r.building,
            detail=(
                f"L{r.level} cost={r.cost if r.cost is None else format(r.cost, ',.0f')} "
                f"gold={r.gold if r.gold is None else format(r.gold, ',.0f')} "
                f"workers={r.workers_current}/{r.workers_max}"
            ),
        )

        if r.slots_free > 0:
            return self._assign_workers(ctx, r)

        outcome = self._upgrade(ctx, r)
        # Anything that means "nothing to do here" should still get us out of
        # the panel, otherwise the loop sits on this screen forever.
        if outcome.status == RoutineOutcome.DONE and not outcome.spent:
            return self._leave(ctx, outcome.detail)
        return outcome
