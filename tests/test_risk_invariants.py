"""The guardrail test. If this fails, a risk limit moved -- find out why.

These assertions duplicate the values in congress_trader/risk.py on purpose.
Duplication is the point: an agent editing one file cannot quietly change the
system's risk posture, because the other file still says what it used to be.
"""
from __future__ import annotations

import pytest

from congress_trader.risk import LIMITS, Budget, RiskViolation, assert_compliant, clamp_order


def test_documented_limits_have_not_drifted():
    assert LIMITS.max_positions == 15
    assert LIMITS.max_dollars_per_trade == 500.0
    assert LIMITS.max_dollars_per_run == 2000.0
    assert LIMITS.max_equity_fraction_per_name == 0.08
    assert LIMITS.cash_buffer_fraction == 0.20


def test_cash_buffer_is_never_deployable():
    budget = Budget(equity=10_000.0, cash=10_000.0)
    assert budget.untouchable_cash == 2_000.0
    assert budget.deployable_cash == 8_000.0


def test_clamp_respects_per_trade_cap():
    assert clamp_order(5_000.0, budget=Budget(equity=100_000.0, cash=100_000.0)) == 500.0


def test_clamp_respects_run_budget():
    budget = Budget(equity=100_000.0, cash=100_000.0, spent_this_run=1_800.0)
    assert clamp_order(500.0, budget=budget) == 200.0


def test_clamp_respects_eight_percent_per_name():
    budget = Budget(equity=5_000.0, cash=5_000.0)
    # 8% of $5k is $400, and $350 is already held, so only $50 of headroom.
    assert clamp_order(500.0, budget=budget, existing_position_dollars=350.0) == 50.0


def test_clamp_skips_rather_than_sending_a_dust_ticket():
    budget = Budget(equity=5_000.0, cash=5_000.0)
    assert clamp_order(500.0, budget=budget, existing_position_dollars=399.0) == 0.0


def test_clamp_refuses_new_position_beyond_max_positions():
    budget = Budget(equity=100_000.0, cash=100_000.0, open_positions=15)
    assert clamp_order(500.0, budget=budget, is_new_position=True) == 0.0
    # An add to an existing name is still allowed at the cap.
    assert clamp_order(500.0, budget=budget, is_new_position=False) == 500.0


def test_clamp_never_dips_into_the_buffer():
    budget = Budget(equity=10_000.0, cash=2_100.0)
    assert clamp_order(500.0, budget=budget) == 100.0


@pytest.mark.parametrize(
    "orders, message",
    [
        ([("AAA", 600.0)], "per-trade"),
        ([(f"T{i}", 500.0) for i in range(5)], "run total"),
    ],
)
def test_assert_compliant_rejects_bypassed_plans(orders, message):
    with pytest.raises(RiskViolation, match=message):
        assert_compliant(orders, budget=Budget(equity=100_000.0, cash=100_000.0))


def test_assert_compliant_accepts_a_clean_plan():
    assert_compliant([("AAA", 500.0), ("BBB", 300.0)], budget=Budget(equity=100_000.0, cash=100_000.0))
