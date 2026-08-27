# 00 — Frozen interfaces

Owner: **Claude**. Status: **frozen**. Consumers: every other contract.

Do not change these shapes in a feature branch. If a contract cannot be
implemented without changing one, stop and raise it in the PR.

## `models.Trade`

```python
member: str; chamber: Chamber; ticker: str; side: Side
transaction_date: date; disclosure_date: date | None
amount_low: float; amount_high: float
asset_description: str; asset_type: str; owner: str; raw_amount: str
party: str | None; source: str
filing_lag_days -> int | None          # property
midpoint(method="geometric") -> float  # sqrt(low*high); "arithmetic" also valid
signed_dollars(method) -> float        # midpoint * side.sign (buy +1, sell -1)
```

`Side` is `buy|sell|exchange|unknown`; `Side.sign` is `+1|-1|0|0`.
`Chamber` is `house|senate`.

## `models.Universe`

`trades: list[Trade]`, `dropped: dict[str, int]`. `drop(reason, n=1)` increments.

## `signals.TickerSignal`

```python
ticker: str; sector: str; score: float
components: dict[str, float]   # z-scored, only components actually blended
raw: dict[str, float]          # pre-z values, always all six keys
n_members: int; n_buyers: int; n_sellers: int
net_dollars: float; gross_dollars: float; n_trades: int
buyers: list[str]; sellers: list[str]; parties: dict[str, int]
first_date: date | None; last_date: date | None
median_lag_days: float | None
contested -> bool              # property: buyers and sellers both present
direction -> Side              # property
```

`signals.DEFAULT_WEIGHTS` keys, in blend order:
`breadth, net_flow, acceleration, cluster, freshness, bipartisan`.

`bipartisan` is dropped from `components` entirely when `parties.json` is
absent. **Never assume all six keys are present in `components`** — iterate
what is there. `raw` always has all six.

## `signals.score(...)`

```python
score(trades, *, reference=None, weights=None, min_members=3,
      midpoint="geometric", lookback=60, asof=None) -> list[TickerSignal]
```
Sorted by score descending. Returns `[]` when nothing clears `min_members`.

## `normalize`

```python
normalize(rows, *, reference=None, min_dollars=1000.0,
          midpoint="geometric", keep_sells=True) -> Universe
window(universe, *, lookback, asof=None) -> list[Trade]
```

## `config.Reference`

`Reference.load()`; `sector_of(ticker)`, `party_of(member)`, `weight_of(member)`,
`has_parties`. Unmapped tickers return the string `"Unmapped"` — they bucket,
they never drop.

## `risk` — protected

```python
LIMITS: Limits            # max_positions 15, $500/trade, $2000/run, 8%, 20% buffer
Budget(equity, cash, spent_this_run=0.0, open_positions=0)
  .untouchable_cash .deployable_cash .remaining_run_budget
  .after_spending(dollars, *, new_position) -> Budget
clamp_order(desired, *, budget, existing_position_dollars=0.0,
            is_new_position=False) -> float   # 0.0 means SKIP, not "send less"
assert_compliant(orders: list[tuple[str, float]], *, budget) -> None  # raises
RiskViolation
```

## `sources`

`load(source="live"|"house"|"senate"|"sample", *, refresh=False) -> list[dict]`,
raising `SourceError`. Rows are raw feed dicts; `normalize` consumes them.
