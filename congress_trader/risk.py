"""Hard risk caps. The signal engine cannot override these.

PROTECTED FILE. Agents must not change the numbers in `LIMITS` or weaken
`clamp_order`. `tests/test_risk_invariants.py` asserts every value here as a
literal and CI fails on any drift -- that test is the guardrail, not a
suggestion. If a limit genuinely needs to move, the human changes both this
file and the test in the same commit, deliberately.

Every order in the system routes through `clamp_order`. There is no other
sanctioned path to a submitted order.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Limits:
    max_positions: int = 15
    max_dollars_per_trade: float = 500.0
    max_dollars_per_run: float = 2000.0
    max_equity_fraction_per_name: float = 0.08
    cash_buffer_fraction: float = 0.20
    min_dollars_per_trade: float = 50.0


LIMITS = Limits()


class RiskViolation(RuntimeError):
    """Raised when an order cannot be made compliant, so it must not be sent."""


@dataclass(frozen=True, slots=True)
class Budget:
    """Mutable-by-replacement view of what is still spendable this run."""

    equity: float
    cash: float
    spent_this_run: float = 0.0
    open_positions: int = 0

    @property
    def untouchable_cash(self) -> float:
        """The 20% buffer is never spent, on any run, for any signal."""
        return self.equity * LIMITS.cash_buffer_fraction

    @property
    def deployable_cash(self) -> float:
        return max(0.0, self.cash - self.untouchable_cash)

    @property
    def remaining_run_budget(self) -> float:
        return max(0.0, LIMITS.max_dollars_per_run - self.spent_this_run)

    def after_spending(self, dollars: float, *, new_position: bool) -> Budget:
        return Budget(
            equity=self.equity,
            cash=self.cash - dollars,
            spent_this_run=self.spent_this_run + dollars,
            open_positions=self.open_positions + (1 if new_position else 0),
        )


def clamp_order(
    desired_dollars: float,
    *,
    budget: Budget,
    existing_position_dollars: float = 0.0,
    is_new_position: bool = False,
) -> float:
    """Reduce a desired buy to the largest compliant size, or 0 to skip it.

    Never raises for an ordinary "too big" order -- it shrinks it. Returns 0.0
    when no compliant size exists, which the caller must treat as "skip", not
    as "send something smaller anyway".
    """
    if desired_dollars <= 0:
        return 0.0
    if is_new_position and budget.open_positions >= LIMITS.max_positions:
        return 0.0

    allowed = min(
        desired_dollars,
        LIMITS.max_dollars_per_trade,
        budget.remaining_run_budget,
        budget.deployable_cash,
    )

    # 8% of equity per name, counting what is already held in that name.
    name_headroom = LIMITS.max_equity_fraction_per_name * budget.equity - existing_position_dollars
    allowed = min(allowed, name_headroom)

    if allowed < LIMITS.min_dollars_per_trade:
        return 0.0
    return float(allowed)


def assert_compliant(orders: list[tuple[str, float]], *, budget: Budget) -> None:
    """Belt-and-braces check on a finished plan, before anything is submitted.

    `orders` is [(symbol, dollars)] for buys only. Raises RiskViolation rather
    than silently trimming, because reaching here means clamp_order was bypassed.
    """
    total = sum(d for _s, d in orders)
    if total > LIMITS.max_dollars_per_run + 1e-6:
        raise RiskViolation(f"run total ${total:,.2f} exceeds cap ${LIMITS.max_dollars_per_run:,.2f}")
    if total > budget.deployable_cash + 1e-6:
        raise RiskViolation(f"run total ${total:,.2f} breaches the {LIMITS.cash_buffer_fraction:.0%} cash buffer")
    for symbol, dollars in orders:
        if dollars > LIMITS.max_dollars_per_trade + 1e-6:
            raise RiskViolation(f"{symbol}: ${dollars:,.2f} exceeds per-trade cap")
        if 0 < dollars < LIMITS.min_dollars_per_trade:
            raise RiskViolation(f"{symbol}: ${dollars:,.2f} is below the minimum ticket")
        if dollars > LIMITS.max_equity_fraction_per_name * budget.equity + 1e-6:
            raise RiskViolation(f"{symbol}: ${dollars:,.2f} exceeds 8% of equity")
    if len(orders) > LIMITS.max_positions:
        raise RiskViolation(f"{len(orders)} orders exceeds max_positions {LIMITS.max_positions}")
