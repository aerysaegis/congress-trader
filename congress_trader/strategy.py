"""Turns scores into a concrete order plan, inside the risk caps.

This module touches money. It consumes `risk` and never edits it: every entry
goes through `risk.clamp_order`, and the finished plan is re-checked with
`risk.assert_compliant` before it is returned. There is no other path to a
submitted order.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .models import Side
from .risk import LIMITS, Budget, assert_compliant, clamp_order
from .signals import TickerSignal

# Score span over which position size ramps from the minimum ticket to the
# per-trade cap. A score `SIZING_SPAN` above `min_score` earns a full ticket;
# anything better is clamped, so a runaway score cannot buy a bigger position.
SIZING_SPAN = 2.0


@dataclass(frozen=True, slots=True)
class Order:
    symbol: str
    side: str
    dollars: float
    reason: str
    score: float | None = None

    def __str__(self) -> str:
        size = "ALL" if self.dollars == 0 and self.side == "sell" else f"${self.dollars:,.2f}"
        return f"{self.side.upper():4s} {self.symbol:<6s} {size:>10s}  {self.reason}"


@dataclass(frozen=True, slots=True)
class Plan:
    exits: list[Order] = field(default_factory=list)
    entries: list[Order] = field(default_factory=list)
    skipped: list[tuple[str, str]] = field(default_factory=list)
    budget_before: Budget | None = None
    budget_after: Budget | None = None

    @property
    def orders(self) -> list[Order]:
        """Exits first. Callers must submit in this order so capital frees up."""
        return [*self.exits, *self.entries]

    @property
    def total_entry_dollars(self) -> float:
        return sum(o.dollars for o in self.entries)

    def describe(self) -> str:
        lines: list[str] = [f"EXITS ({len(self.exits)})"]
        lines += [f"  {o}" for o in self.exits] or ["  none"]
        lines.append(f"\nENTRIES ({len(self.entries)}, {self._dollars()})")
        lines += [f"  {o}" for o in self.entries] or ["  none"]
        lines.append(f"\nSKIPPED ({len(self.skipped)})")
        lines += [f"  {symbol:<6s} {why}" for symbol, why in self.skipped] or ["  none"]
        return "\n".join(lines)

    def _dollars(self) -> str:
        return f"${self.total_entry_dollars:,.2f} of ${LIMITS.max_dollars_per_run:,.0f} run cap"


def size_for_score(score: float, *, min_score: float) -> float:
    """Score-proportional, clamped at both ends.

    A better score buys more, but the best score imaginable still cannot buy
    more than the per-trade cap -- the signal is not allowed to argue its way
    into a larger position.
    """
    fraction = (score - min_score) / SIZING_SPAN
    fraction = max(0.0, min(1.0, fraction))
    floor, ceiling = LIMITS.min_dollars_per_trade, LIMITS.max_dollars_per_trade
    return floor + fraction * (ceiling - floor)


def build_plan(
    signals: list[TickerSignal],
    *,
    budget: Budget,
    positions: dict[str, float],
    min_score: float = 0.5,
    exit_score: float = -0.5,
    midpoint: str = "geometric",
) -> Plan:
    """Build the full order plan. Exits are computed and funded before entries."""
    by_ticker = {s.ticker: s for s in signals}
    skipped: list[tuple[str, str]] = []

    # --- exits first, so their proceeds are available to the entries ---
    exits: list[Order] = []
    proceeds = 0.0
    for symbol, market_value in sorted(positions.items()):
        signal = by_ticker.get(symbol)
        if signal is None:
            reason = "no longer in the signal set - the crowd left"
        elif signal.score < exit_score:
            reason = f"score {signal.score:+.2f} below exit threshold {exit_score:+.2f}"
        else:
            continue
        exits.append(Order(symbol=symbol, side="sell", dollars=0.0, reason=reason,
                           score=signal.score if signal else None))
        proceeds += max(0.0, market_value)

    working = Budget(
        equity=budget.equity,
        cash=budget.cash + proceeds,
        spent_this_run=budget.spent_this_run,
        open_positions=max(0, budget.open_positions - len(exits)),
    )

    exited = {o.symbol for o in exits}
    held = {s: v for s, v in positions.items() if s not in exited}

    # --- entries ---
    entries: list[Order] = []
    for signal in sorted(signals, key=lambda s: s.score, reverse=True):
        if signal.score < min_score:
            continue
        if signal.direction is not Side.BUY:
            skipped.append((signal.ticker, f"net flow is a sell ({signal.net_dollars:+,.0f}); never shorts"))
            continue
        if signal.ticker in exited:
            skipped.append((signal.ticker, "exited this run; not re-entered in the same pass"))
            continue

        existing = held.get(signal.ticker, 0.0)
        desired = size_for_score(signal.score, min_score=min_score)
        allowed = clamp_order(
            desired,
            budget=working,
            existing_position_dollars=existing,
            is_new_position=signal.ticker not in held,
        )

        if allowed <= 0.0:
            skipped.append((signal.ticker, _why_skipped(working, existing, signal.ticker in held)))
            continue

        note = f"score {signal.score:+.2f}, {signal.n_buyers} buyers"
        if allowed < desired - 0.01:
            note += f" (trimmed from ${desired:,.0f} by risk caps)"
        entries.append(Order(symbol=signal.ticker, side="buy", dollars=allowed,
                             reason=note, score=signal.score))
        working = working.after_spending(allowed, new_position=signal.ticker not in held)

    # Belt and braces: reaching a violation here means clamp_order was bypassed.
    # Checked against the post-exit budget, since that is the cash the entries
    # were actually sized against.
    funded = Budget(
        equity=budget.equity,
        cash=budget.cash + proceeds,
        spent_this_run=budget.spent_this_run,
        open_positions=budget.open_positions,
    )
    assert_compliant([(o.symbol, o.dollars) for o in entries], budget=funded)

    return Plan(exits=exits, entries=entries, skipped=skipped,
                budget_before=budget, budget_after=working)


def _why_skipped(budget: Budget, existing: float, is_held: bool) -> str:
    """Explain a zero-size clamp in the terms the operator cares about."""
    if not is_held and budget.open_positions >= LIMITS.max_positions:
        return f"at max_positions ({LIMITS.max_positions})"
    if budget.remaining_run_budget < LIMITS.min_dollars_per_trade:
        return f"run budget exhausted (${budget.remaining_run_budget:,.2f} left)"
    if budget.deployable_cash < LIMITS.min_dollars_per_trade:
        return f"cash buffer reached (${budget.deployable_cash:,.2f} deployable)"
    headroom = LIMITS.max_equity_fraction_per_name * budget.equity - existing
    if headroom < LIMITS.min_dollars_per_trade:
        return (f"already {existing / budget.equity:.1%} of equity in this name; "
                f"${headroom:,.2f} headroom under the 8% cap")
    return "no compliant size available"
