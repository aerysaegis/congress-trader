# 03 — Strategy and position sizing

Owner: **Codex**. Branch: `codex/03-strategy`. Owns exactly: `congress_trader/strategy.py`.
Consumes: `00-interfaces` (especially the protected `risk` module). Blocks: 05, 06.

**Read the non-negotiable rules in AGENTS.md before starting.** This contract
touches money. `risk.py` is protected — you consume it, you never edit it.

## Required API

```python
@dataclass(frozen=True)
class Order:
    symbol: str
    side: str            # "buy" | "sell"
    dollars: float       # notional; 0.0 for full-liquidation sells
    reason: str          # human-readable, shown in --dry-run
    score: float | None

@dataclass(frozen=True)
class Plan:
    exits: list[Order]
    entries: list[Order]
    skipped: list[tuple[str, str]]   # (symbol, why) — every rejection explained
    budget_before: Budget
    budget_after: Budget

def build_plan(signals, *, budget, positions, min_score=0.5,
               exit_score=-0.5, midpoint="geometric") -> Plan
```

`positions` is `{symbol: market_value_dollars}` for what is currently held.

## Rules

- **Exits run before entries** so capital frees up first. Build the exit list,
  apply its proceeds to the budget, then size entries.
- Exit a held name when its score drops below `exit_score`, or when it no
  longer appears in the signal set at all (the crowd left).
- **Every entry goes through `risk.clamp_order`.** A return of `0.0` means the
  name is skipped and appended to `skipped` with a reason — never round it up.
- Sizing is score-proportional but clamped at both ends: map score to a
  fraction of `LIMITS.max_dollars_per_trade`, floor at
  `LIMITS.min_dollars_per_trade`, ceiling at the per-trade cap. A better score
  buys more, but the best possible score cannot buy more than $500.
- Only names with `direction == Side.BUY` and `score >= min_score` are entry
  candidates. Never open a short.
- Thread the budget through `Budget.after_spending` as you go, so the run cap
  and cash buffer bind across the whole plan, not per order.
- Call `risk.assert_compliant` on the finished entry list before returning.
  If it raises, that is a bug in this file — do not catch and continue.

## Done when

Tests prove each cap binds independently, that a 16th new position is refused,
that exits are ordered before entries in the plan, and that `assert_compliant`
passes on plans built from the sample data at several `min_score` values.
