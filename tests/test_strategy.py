from __future__ import annotations

from datetime import date

import pytest

from congress_trader.config import Reference
from congress_trader.normalize import normalize, window
from congress_trader.risk import LIMITS, Budget, assert_compliant
from congress_trader.sample_data import build_sample
from congress_trader.signals import score
from congress_trader.strategy import build_plan


def test_exits_free_cash_and_slots_before_entries(signal_factory) -> None:
    plan = build_plan(
        [signal_factory("NEW", 3.0)],
        budget=Budget(equity=10_000.0, cash=2_000.0, open_positions=1),
        positions={"OLD": 1_000.0},
    )

    assert [(order.symbol, order.side, order.dollars) for order in plan.exits] == [("OLD", "sell", 0.0)]
    assert plan.entries and plan.entries[0].symbol == "NEW"
    assert plan.budget_after.cash == 2_500.0
    assert plan.budget_after.spent_this_run == 500.0
    assert plan.budget_after.open_positions == 1


def test_sizing_is_monotonic_with_floor_and_ceiling(signal_factory) -> None:
    plan = build_plan(
        [
            signal_factory("LOW", 0.5),
            signal_factory("MID", 1.5),
            signal_factory("HIGH", 50.0),
        ],
        budget=Budget(equity=100_000.0, cash=100_000.0),
        positions={},
        min_score=0.5,
    )

    dollars = {order.symbol: order.dollars for order in plan.entries}
    assert dollars["LOW"] == LIMITS.min_dollars_per_trade
    assert dollars["LOW"] < dollars["MID"] < dollars["HIGH"]
    assert dollars["HIGH"] == LIMITS.max_dollars_per_trade


@pytest.mark.parametrize(
    ("budget", "positions"),
    [
        (Budget(equity=10_000.0, cash=2_049.0), {}),
        (Budget(equity=10_000.0, cash=10_000.0, spent_this_run=1_951.0), {}),
        (Budget(equity=10_000.0, cash=10_000.0, open_positions=15), {}),
        (Budget(equity=10_000.0, cash=10_000.0, open_positions=1), {"NEW": 751.0}),
    ],
)
def test_each_zero_clamp_is_skipped_with_reason(signal_factory, budget, positions) -> None:
    plan = build_plan([signal_factory("NEW", 50.0)], budget=budget, positions=positions)

    assert plan.entries == []
    assert plan.skipped and plan.skipped[0][0] == "NEW"


def test_sixteenth_new_position_is_refused(signal_factory) -> None:
    held_signals = [signal_factory(f"HELD{i}", 0.0) for i in range(15)]
    plan = build_plan(
        [signal_factory("NEW", 50.0), *held_signals],
        budget=Budget(equity=100_000.0, cash=100_000.0, open_positions=15),
        positions={f"HELD{i}": 100.0 for i in range(15)},
    )

    assert plan.entries == []
    assert any(symbol == "NEW" for symbol, _reason in plan.skipped)


def test_run_cap_binds_across_plan(signal_factory) -> None:
    plan = build_plan(
        [signal_factory(f"S{i}", 50.0) for i in range(5)],
        budget=Budget(equity=100_000.0, cash=100_000.0),
        positions={},
    )

    assert sum(order.dollars for order in plan.entries) == LIMITS.max_dollars_per_run
    assert len(plan.entries) == 4
    assert plan.skipped[0][0] == "S4"


def test_every_threshold_rejection_is_explained(signal_factory) -> None:
    plan = build_plan(
        [signal_factory("LOW", 0.0)],
        budget=Budget(equity=10_000.0, cash=10_000.0),
        positions={},
    )

    assert plan.skipped and plan.skipped[0][0] == "LOW"
    assert "score" in plan.skipped[0][1]


def test_zero_equity_returns_skip_instead_of_crashing(signal_factory) -> None:
    plan = build_plan(
        [signal_factory("ZERO", 1.0)],
        budget=Budget(equity=0.0, cash=1_000.0),
        positions={},
    )

    assert plan.entries == []
    assert plan.skipped and plan.skipped[0][0] == "ZERO"


@pytest.mark.parametrize("min_score", [-1.0, 0.0, 0.5, 1.0])
def test_sample_plans_are_compliant(min_score: float) -> None:
    anchor = date(2025, 1, 31)
    reference = Reference.load()
    universe = normalize(build_sample(anchor=anchor), reference=reference)
    signals = score(
        window(universe, lookback=60, asof=anchor),
        reference=reference,
        lookback=60,
        asof=anchor,
    )

    plan = build_plan(
        signals,
        budget=Budget(equity=25_000.0, cash=10_000.0),
        positions={},
        min_score=min_score,
    )

    assert_compliant([(order.symbol, order.dollars) for order in plan.entries], budget=plan.budget_before)
