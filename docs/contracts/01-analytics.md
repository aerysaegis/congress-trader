# 01 — Secondary analytics

Owner: **Codex**. Branch: `codex/01-analytics`. Owns exactly: `congress_trader/analytics.py`.
Consumes: `00-interfaces`. Blocks: 02, 06.

The README promises three tables beyond the ranked names. They are derived from
the same windowed trades, so they live together, separate from rendering.

## Required API

```python
@dataclass(frozen=True)
class SectorRow:
    sector: str
    net_dollars: float
    gross_dollars: float
    n_members: int
    n_trades: int
    recent_net: float      # newer half of the window
    prior_net: float       # older half
    momentum: float        # log-scaled recent vs prior, same treatment as signals._log_flow

@dataclass(frozen=True)
class ContestedRow:
    ticker: str; sector: str
    buyers: list[str]; sellers: list[str]
    buy_dollars: float; sell_dollars: float
    disagreement: float    # 0..1, 1.0 == perfectly split by member count

@dataclass(frozen=True)
class FilerRow:
    member: str; chamber: str; party: str | None
    n_trades: int; n_tickers: int
    median_lag_days: float | None
    mean_lag_days: float | None
    fastest_lag_days: int | None
    gross_dollars: float

def sector_rotation(trades, *, reference, midpoint="geometric", lookback=60, asof=None) -> list[SectorRow]
def contested_names(trades, *, reference, midpoint="geometric", min_members=3) -> list[ContestedRow]
def filer_leaderboard(trades, *, reference, midpoint="geometric", min_trades=3) -> list[FilerRow]
```

## Rules

- Sort: sectors by `momentum` desc; contested by `disagreement` desc then gross
  dollars desc; filers by `median_lag_days` asc (fast filers first, since they
  produce fresher and more tradeable signal), `None` lags sort last.
- Unmapped tickers go to the `"Unmapped"` sector row. Do not drop them.
- `disagreement = min(nb, ns) / max(nb, ns)` over distinct member counts.
- Reuse the window-halving rule from `signals._raw_components`: the midline is
  `asof.toordinal() - lookback / 2.0`. Import the helper rather than
  reimplementing the log scaling — `from .signals import _log_flow` is fine.
- Empty input returns `[]` everywhere. No exceptions for empty windows.

## Done when

`pytest` green, `ruff check` clean, and all three functions return sensible
non-empty output on `sources.load("sample")` at `lookback=60`.
