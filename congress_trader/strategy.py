"""Turn ranked congressional signals into a risk-compliant order plan."""
from __future__ import annotations

from dataclasses import dataclass

from .models import Side
from .risk import LIMITS, Budget, assert_compliant, clamp_order
from .signals import TickerSignal


@dataclass(frozen=True, slots=True)
class Order:
    symbol: str
    side: str
    dollars: float
    reason: str
    score: float | None


@dataclass(frozen=True, slots=True)
class Plan:
    exits: list[Order]
    entries: list[Order]
    skipped: list[tuple[str, str]]
    budget_before: Budget
    budget_after: Budget


def _budget_after_exits(budget: Budget, positions: dict[str, float], exits: list[Order]) -> Budget:
    proceeds = sum(max(0.0, positions.get(order.symbol, 0.0)) for order in exits)
    return Budget(
        equity=budget.equity,
        cash=budget.cash + proceeds,
        spent_this_run=budget.spent_this_run,
        open_positions=max(0, budget.open_positions - len(exits)),
    )


def _desired_dollars(score: float) -> float:
    score_scaled = score * LIMITS.max_dollars_per_trade
    return max(LIMITS.min_dollars_per_trade, min(score_scaled, LIMITS.max_dollars_per_trade))


def build_plan(
    signals: list[TickerSignal],
    *,
    budget: Budget,
    positions: dict[str, float],
    min_score: float = 0.5,
    exit_score: float = -0.5,
    midpoint: str = "geometric",
) -> Plan:
    """Build exits first, then size entries against the resulting budget."""
    del midpoint  # Signals already contain the midpoint-derived score and flow.

    by_symbol = {signal.ticker: signal for signal in signals}
    exits: list[Order] = []
    for symbol in sorted(positions):
        if positions[symbol] <= 0:
            continue
        signal = by_symbol.get(symbol)
        if signal is None:
            exits.append(
                Order(
                    symbol=symbol,
                    side="sell",
                    dollars=0.0,
                    reason="crowd signal disappeared",
                    score=None,
                )
            )
        elif signal.score < exit_score:
            exits.append(
                Order(
                    symbol=symbol,
                    side="sell",
                    dollars=0.0,
                    reason=f"score {signal.score:+.2f} below exit threshold {exit_score:+.2f}",
                    score=signal.score,
                )
            )

    available = _budget_after_exits(budget, positions, exits)
    current = available
    entries: list[Order] = []
    skipped: list[tuple[str, str]] = []

    for signal in sorted(signals, key=lambda item: (-item.score, item.ticker)):
        if signal.direction is not Side.BUY:
            skipped.append((signal.ticker, "signal direction is sell"))
            continue
        if signal.score < min_score:
            skipped.append((signal.ticker, f"score {signal.score:+.2f} below minimum {min_score:+.2f}"))
            continue

        existing = max(0.0, positions.get(signal.ticker, 0.0))
        dollars = clamp_order(
            _desired_dollars(signal.score),
            budget=current,
            existing_position_dollars=existing,
            is_new_position=existing == 0.0,
        )
        if dollars == 0.0:
            skipped.append((signal.ticker, "risk limits leave no compliant order"))
            continue

        entries.append(
            Order(
                symbol=signal.ticker,
                side="buy",
                dollars=dollars,
                reason=f"crowd score {signal.score:+.2f}",
                score=signal.score,
            )
        )
        current = current.after_spending(dollars, new_position=existing == 0.0)

    assert_compliant([(order.symbol, order.dollars) for order in entries], budget=available)
    return Plan(
        exits=exits,
        entries=entries,
        skipped=skipped,
        budget_before=budget,
        budget_after=current,
    )
