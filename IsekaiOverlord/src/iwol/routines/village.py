"""The village screen — the hub of the economy loop.

Its job is small on purpose: pick a building and open its management panel.
The actual spending happens in :mod:`iwol.routines.building_panel`, behind the
real UPGRADE button, where the cost and the gold balance are both on screen.

Why this file was rewritten
---------------------------
It originally assumed the gold diamond button on each card *was* the upgrade
button, and read a per-card "income" to rank by ROI.  A before/after capture of
a real click showed that assumption was wrong: the button opens a panel, and the
top number on the card is the next upgrade's gold cost, not income.  So the ROI
planner could not be fed from this screen at all.

Rather than guess a replacement, the loop now visits every building in turn and
lets the panel routine decide, reporting what it finds.  Once a full sweep of
panel readings is recorded, the existing economy planner can be fed real
numbers -- that is the next step, not this one.
"""

from __future__ import annotations

from ..brain import Context, RoutineOutcome

DEFAULT_BUTTONS = tuple(f"b{i}_btn" for i in range(1, 8))


class VillageRoutine:
    """Open the next building's panel, cycling through all of them."""

    name = "village"
    screens = ("village",)

    def __init__(self, buttons: tuple[str, ...] = DEFAULT_BUTTONS):
        self.buttons = tuple(buttons)
        self._index = 0
        self._visited = 0

    def run(self, ctx: Context) -> RoutineOutcome:
        spec = ctx.classification.spec
        if spec is None:
            return RoutineOutcome(RoutineOutcome.BLOCKED, "no screen spec for the village screen")

        available = [b for b in self.buttons if b in spec.regions]
        if not available:
            return RoutineOutcome(
                RoutineOutcome.BLOCKED,
                "no building buttons defined on this screen — check screens.json",
            )

        # Try each button once, so one stale/misplaced region can't wedge the loop.
        for _ in range(len(available)):
            name = available[self._index % len(available)]
            self._index += 1
            point = ctx.region_center(name)
            if point is None:
                continue
            res = ctx.actuator.click(point[0], point[1])
            if res.ok:
                self._visited += 1
                ctx.journal.event(
                    "open_building", screen=ctx.screen, action=name,
                    detail=f"clicked ({point[0]},{point[1]}) after {self._visited} buildings visited",
                    ok=True,
                )
                return RoutineOutcome(
                    RoutineOutcome.DONE, f"opened {name} at ({point[0]},{point[1]})", acted=True
                )
            ctx.journal.event(
                "open_building", screen=ctx.screen, action=name, detail=res.detail, ok=False
            )

        return RoutineOutcome(RoutineOutcome.BLOCKED, "no building button could be clicked")
