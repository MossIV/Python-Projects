"""Village economy model: which upgrade is worth buying right now.

Deliberately pure — no screenshots, no clicking, no I/O.  Every rule here is
unit-testable, which matters because *this* is the part that decides how the
bot spends your money.  The vision layer finds the numbers; this layer decides.

The model
---------
An idle economy gives you one real choice: given limited coins, which purchase
maximises future income fastest?  For each candidate we compute the **marginal
income** it buys and its **ROI** (marginal income per coin spent):

    marginal = income * (income_growth - 1)
    roi      = marginal / cost
    payback  = cost / marginal          # seconds to earn the cost back

Greedy-by-ROI is optimal enough here and, crucially, *explainable* — you can
read the plan and see why each pick was made.  Payback time is the number that
actually matters early on: anything under a few minutes is an easy yes.
"""

from __future__ import annotations

from dataclasses import dataclass, replace


@dataclass
class Building:
    """One upgradeable income source."""

    name: str
    level: int = 1
    income: float = 0.0  # coins per second at the current level
    upgrade_cost: float = 0.0  # coins to reach the next level
    cost_growth: float = 1.55  # cost multiplier per level
    income_growth: float = 1.5  # income multiplier per level

    def marginal_income(self) -> float:
        return self.income * (self.income_growth - 1.0)

    def roi(self) -> float:
        """Marginal income gained per coin spent.  0 when unpriced/unaffordable."""
        if self.upgrade_cost <= 0:
            return 0.0
        return self.marginal_income() / self.upgrade_cost

    def payback_seconds(self) -> float:
        """Seconds of income needed to earn back the upgrade cost."""
        if self.upgrade_cost <= 0:
            return float("inf")  # unpriced: payback is meaningless, not zero
        m = self.marginal_income()
        return float("inf") if m <= 0 else self.upgrade_cost / m

    def after_upgrade(self) -> "Building":
        return replace(
            self,
            level=self.level + 1,
            income=self.income * self.income_growth,
            upgrade_cost=self.upgrade_cost * self.cost_growth,
        )


@dataclass
class Purchase:
    name: str
    cost: float
    income_gain: float
    roi: float
    payback_seconds: float
    level_from: int
    level_to: int

    def describe(self) -> str:
        pb = "∞" if self.payback_seconds == float("inf") else f"{self.payback_seconds:.0f}s"
        return (
            f"{self.name} L{self.level_from}->L{self.level_to} "
            f"cost={self.cost:,.0f} +{self.income_gain:,.1f}/s roi={self.roi:.3e} payback={pb}"
        )


def plan_upgrades(
    buildings: list[Building],
    coins: float,
    max_purchases: int = 10,
    reserve: float = 0.0,
    min_roi: float = 0.0,
    max_payback_seconds: float | None = None,
) -> list[Purchase]:
    """Greedily pick the best upgrades affordable with ``coins``.

    ``reserve`` keeps a floor of coins untouched (useful when saving for a big
    unlock).  Upgrades are re-priced as they're taken, so the plan can't spend
    the same coin twice or assume a cost that's already grown.

    Returns purchases in the order they should be made — each one is affordable
    at the point it's taken, given the coins the earlier ones leave behind.
    """
    remaining = coins - reserve
    working = [replace(b) for b in buildings]  # don't mutate the caller's list
    plan: list[Purchase] = []

    for _ in range(max(0, max_purchases)):
        candidates = [b for b in working if b.upgrade_cost > 0 and b.upgrade_cost <= remaining]

        if max_payback_seconds is not None:
            candidates = [b for b in candidates if b.payback_seconds() <= max_payback_seconds]
        if min_roi:
            candidates = [b for b in candidates if b.roi() >= min_roi]
        if not candidates:
            break

        # Rank by ROI; break ties by the biggest absolute gain (spend the coin
        # on something substantial rather than a rounding-error upgrade).
        best = max(candidates, key=lambda b: (b.roi(), b.marginal_income()))
        if best.roi() <= 0:
            break

        plan.append(
            Purchase(
                name=best.name,
                cost=best.upgrade_cost,
                income_gain=best.marginal_income(),
                roi=best.roi(),
                payback_seconds=best.payback_seconds(),
                level_from=best.level,
                level_to=best.level + 1,
            )
        )
        remaining -= best.upgrade_cost
        idx = next(i for i, b in enumerate(working) if b.name == best.name)
        working[idx] = best.after_upgrade()

    return plan


def income_per_second(buildings: list[Building]) -> float:
    return sum(b.income for b in buildings)


def project_income(buildings: list[Building], purchases: list[Purchase]) -> float:
    """Total income/sec after applying ``purchases``, in order."""
    working = [replace(b) for b in buildings]
    for p in purchases:
        idx = next((i for i, b in enumerate(working) if b.name == p.name), None)
        if idx is None:
            continue
        working[idx] = working[idx].after_upgrade()
    return income_per_second(working)
