"""The village economy routine — collect income, then buy the best upgrades.

Kept honest about its own limits: the *layout* (which pixel is the Market's
upgrade button) is data, not code, and lives in ``village_layout.json``.  Until
that file exists the routine refuses to act rather than clicking blind — which
is the whole point, because a blind click here spends your coins.

Who decides what
----------------
``economy.plan_upgrades`` decides *what* to buy (pure logic, unit-tested).
This module only decides *where to click* to buy it.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path

from ..brain import Context, RoutineOutcome
from ..economy import Building, plan_upgrades, project_income
from ..ocr import parse_number

DEFAULT_LAYOUT = Path(__file__).with_name("village_layout.json")


@dataclass
class TileLayout:
    """Where one building's numbers live and how to upgrade it."""

    name: str
    level_region: str = ""
    cost_region: str = ""
    income_region: str = ""
    upgrade_region: str = ""
    cost_growth: float = 1.55
    income_growth: float = 1.5


@dataclass
class VillageLayout:
    screen: str = "village"
    coins_region: str = "coins"
    income_region: str = "income_total"
    collect_regions: list[str] = field(default_factory=list)
    tiles: list[TileLayout] = field(default_factory=list)
    max_purchases: int = 5
    reserve: float = 0.0
    max_payback_seconds: float | None = 900.0
    settle: float = 0.9

    @classmethod
    def load(cls, path: str | Path = DEFAULT_LAYOUT) -> "VillageLayout | None":
        path = Path(path)
        if not path.exists():
            return None
        raw = json.loads(path.read_text(encoding="utf-8"))
        return cls(
            screen=raw.get("screen", "village"),
            coins_region=raw.get("coins_region", "coins"),
            income_region=raw.get("income_region", "income_total"),
            collect_regions=list(raw.get("collect_regions", [])),
            tiles=[TileLayout(**t) for t in raw.get("tiles", [])],
            max_purchases=raw.get("max_purchases", 5),
            reserve=raw.get("reserve", 0.0),
            max_payback_seconds=raw.get("max_payback_seconds", 900.0),
            settle=raw.get("settle", 0.9),
        )


def read_buildings(ctx: Context, layout: VillageLayout) -> list[Building]:
    """Turn the on-screen numbers into :class:`Building` objects.

    Unreadable tiles are skipped rather than guessed at — a guessed cost turns
    into a real purchase.
    """
    buildings: list[Building] = []
    for tile in layout.tiles:
        cost = level = None
        if tile.cost_region:
            cost = parse_number(ctx.text_in(tile.cost_region))
        if tile.level_region:
            level = parse_number(ctx.text_in(tile.level_region))
        income = parse_number(ctx.text_in(tile.income_region)) if tile.income_region else None
        if cost is None or cost <= 0:
            ctx.journal.event("tile_unreadable", screen=ctx.screen, action=tile.name,
                              detail=f"cost region {tile.cost_region!r} unreadable", ok=False)
            continue
        buildings.append(
            Building(
                name=tile.name,
                level=int(level or 1),
                income=float(income or 0.0),
                upgrade_cost=float(cost),
                cost_growth=tile.cost_growth,
                income_growth=tile.income_growth,
            )
        )
    return buildings


class VillageRoutine:
    """Collect, then upgrade by ROI.  Never spends more than the brain allows."""

    def __init__(self, layout: VillageLayout | None = None, layout_path: str | Path = DEFAULT_LAYOUT):
        self.layout = layout or VillageLayout.load(layout_path)
        self.name = "village"
        self.screens = (self.layout.screen,) if self.layout else ("village",)

    # -- steps ------------------------------------------------------------ #

    def _collect(self, ctx: Context) -> int:
        """Tap every configured collect point.  Returns how many were clicked."""
        clicked = 0
        for region in self.layout.collect_regions:
            box = ctx.classification.spec.region_px(ctx.frame.size).get(region) if ctx.classification.spec else None
            if box is None:
                continue
            x, y, w, h = box
            res = ctx.actuator.click(ctx.frame.to_screen(x + w // 2, y + h // 2)[0],
                                     ctx.frame.to_screen(x + w // 2, y + h // 2)[1])
            ctx.journal.event("collect", screen=ctx.screen, action=region,
                              detail=res.detail, ok=res.ok)
            clicked += 1 if res.ok else 0
        return clicked

    def _upgrade(self, ctx: Context) -> RoutineOutcome:
        assert self.layout is not None
        coins = parse_number(ctx.text_in(self.layout.coins_region))
        if coins is None:
            return RoutineOutcome(
                RoutineOutcome.BLOCKED,
                f"could not read coin balance from region {self.layout.coins_region!r}",
            )

        buildings = read_buildings(ctx, self.layout)
        if not buildings:
            return RoutineOutcome(
                RoutineOutcome.BLOCKED,
                "no building tiles readable — check village_layout.json regions",
            )

        plan = plan_upgrades(
            buildings,
            coins=coins,
            max_purchases=self.layout.max_purchases,
            reserve=self.layout.reserve,
            max_payback_seconds=self.layout.max_payback_seconds,
        )
        if not plan:
            ctx.journal.event("no_upgrade", screen=ctx.screen,
                              detail=f"nothing affordable/useful with {coins:,.0f} coins")
            return RoutineOutcome(RoutineOutcome.DONE, f"no worthwhile upgrade at {coins:,.0f} coins")

        before = sum(b.income for b in buildings)
        after = project_income(buildings, plan)
        ctx.journal.event(
            "plan", screen=ctx.screen,
            detail=f"{len(plan)} upgrades, income {before:,.0f}->{after:,.0f}/s; "
                   + " | ".join(p.describe() for p in plan),
        )

        by_name = {t.name: t for t in self.layout.tiles}
        spent = 0
        bought = 0
        for purchase in plan:
            tile = by_name.get(purchase.name)
            if tile is None or not tile.upgrade_region:
                continue
            spec = ctx.classification.spec
            box = spec.region_px(ctx.frame.size).get(tile.upgrade_region) if spec else None
            if box is None:
                ctx.journal.event("upgrade_region_missing", screen=ctx.screen,
                                  action=purchase.name, detail=tile.upgrade_region, ok=False)
                continue
            x, y, w, h = box
            sx, sy = ctx.frame.to_screen(x + w // 2, y + h // 2)
            res = ctx.actuator.click(sx, sy)
            ctx.journal.event("upgrade", screen=ctx.screen, action=purchase.name,
                              detail=f"{purchase.describe()} -> {res.detail}", ok=res.ok)
            if res.ok:
                spent += int(purchase.cost)
                bought += 1
            time.sleep(self.layout.settle)

        if not bought:
            return RoutineOutcome(RoutineOutcome.BLOCKED, "plan was non-empty but no upgrade button was clickable")
        return RoutineOutcome(
            RoutineOutcome.DONE,
            f"bought {bought}/{len(plan)} upgrades for {spent:,} gold",
            spent={"gold": spent},
        )

    # -- entry point ------------------------------------------------------ #

    def run(self, ctx: Context) -> RoutineOutcome:
        if self.layout is None:
            return RoutineOutcome(
                RoutineOutcome.BLOCKED,
                f"{DEFAULT_LAYOUT.name} not found — record the village screen with "
                f"tools/tour.py, then fill in the regions. Refusing to click blind.",
            )

        collected = self._collect(ctx)
        if collected:
            ctx.journal.event("collected", screen=ctx.screen, detail=f"{collected} collect points")
            return RoutineOutcome(RoutineOutcome.CONTINUE, f"collected {collected} point(s)")

        return self._upgrade(ctx)
