"""Economy logic — the part that decides where your coins go.

Pure functions, so these run instantly and cover the cases that would otherwise
turn into a real in-game mistake.
"""

from __future__ import annotations

import pytest

from iwol.economy import(
    Building,
    income_per_second,
    plan_upgrades,
    project_income,
)


def test_marginal_income_and_roi():
    b = Building(name="Market", level=1, income=200, upgrade_cost=1000,
                 cost_growth=1.5, income_growth=1.5)
    assert b.marginal_income() == pytest.approx(100)  # 200 * (1.5 - 1)
    assert b.roi() == pytest.approx(0.1)
    assert b.payback_seconds() == pytest.approx(10.0)  # 1000 / 100


def test_after_upgrade_compounds_cost_and_income():
    b = Building(name="Market", level=1, income=200, upgrade_cost=1000,
                 cost_growth=1.5, income_growth=1.5)
    nxt = b.after_upgrade()
    assert nxt.level == 2
    assert nxt.income == pytest.approx(300)
    assert nxt.upgrade_cost == pytest.approx(1500)
    # the original must not be mutated
    assert b.level == 1 and b.income == pytest.approx(200)


def test_after_upgrade_uses_class_defaults_when_unspecified():
    b = Building(name="Market", level=1, income=200, upgrade_cost=1000)
    nxt = b.after_upgrade()  # default cost_growth is 1.55
    assert nxt.upgrade_cost == pytest.approx(1550)


def test_unpriced_building_has_no_roi():
    b = Building(name="Free", income=10, upgrade_cost=0)
    assert b.roi() == 0.0
    assert b.payback_seconds() == float("inf")


def test_plan_picks_highest_roi_first():
    a = Building(name="A", income=200, upgrade_cost=1000)   # roi 0.10
    b = Building(name="B", income=10, upgrade_cost=100)     # roi 0.05
    plan = plan_upgrades([b, a], coins=1100, max_purchases=1)
    assert [p.name for p in plan] == ["A"]


def test_plan_spends_each_coin_once():
    a = Building(name="A", income=200, upgrade_cost=1000)  # roi 0.10
    b = Building(name="B", income=10, upgrade_cost=100)    # roi 0.05
    plan = plan_upgrades([a, b], coins=1100, max_purchases=10)
    assert [p.name for p in plan] == ["A", "B"]
    assert sum(p.cost for p in plan) == pytest.approx(1100)
    # A's price rose after buying it, and we could not afford it again
    assert plan[0].level_from == 1 and plan[0].level_to == 2


def test_plan_never_exceeds_coins():
    buildings = [
        Building(name="A", income=500, upgrade_cost=1000),
        Building(name="B", income=400, upgrade_cost=900),
        Building(name="C", income=50, upgrade_cost=100),
    ]
    coins = 2500
    plan = plan_upgrades(buildings, coins=coins, max_purchases=20)
    assert sum(p.cost for p in plan) <= coins


def test_plan_respects_reserve():
    buildings = [Building(name="A", income=200, upgrade_cost=100)]
    coins, reserve = 1000, 400
    plan = plan_upgrades(buildings, coins=coins, max_purchases=20, reserve=reserve)
    assert sum(p.cost for p in plan) <= coins - reserve


def test_plan_respects_max_payback():
    good = Building(name="Good", income=1000, upgrade_cost=100)      # payback 0.2s
    terrible = Building(name="Bad", income=1, upgrade_cost=10_000)   # payback 20000s
    plan = plan_upgrades([good, terrible], coins=20_000, max_purchases=5,
                         max_payback_seconds=60)
    assert plan, "expected at least one Good purchase"
    assert {p.name for p in plan} == {"Good"}  # Bad is never worth it


def test_plan_empty_when_nothing_affordable():
    buildings = [Building(name="A", income=100, upgrade_cost=10_000)]
    assert plan_upgrades(buildings, coins=50) == []


def test_plan_does_not_mutate_caller_buildings():
    buildings = [Building(name="A", income=200, upgrade_cost=100)]
    before = (buildings[0].level, buildings[0].income, buildings[0].upgrade_cost)
    plan_upgrades(buildings, coins=10_000, max_purchases=3)
    assert (buildings[0].level, buildings[0].income, buildings[0].upgrade_cost) == before


def test_project_income_applies_plan():
    buildings = [Building(name="A", income=100, upgrade_cost=10)]
    plan = plan_upgrades(buildings, coins=10, max_purchases=1)
    assert income_per_second(buildings) == pytest.approx(100)
    assert project_income(buildings, plan) == pytest.approx(150)  # 100 * 1.5
