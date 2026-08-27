# 02 — Report rendering

Owner: **Codex**. Branch: `codex/02-report`. Owns exactly: `congress_trader/report.py`.
Consumes: `00-interfaces`, `01-analytics`. Blocks: 05, 07.

Rendering only. No scoring, no filtering, no data loading — if you need a
number the engine doesn't give you, that's a bug in 01, not work for here.

## Required API

```python
@dataclass(frozen=True)
class ReportData:
    generated_at: datetime
    asof: date
    lookback: int
    min_members: int
    midpoint: str
    source: str
    signals: list[TickerSignal]
    sectors: list[SectorRow]
    contested: list[ContestedRow]
    filers: list[FilerRow]
    dropped: dict[str, int]
    n_trades_considered: int
    has_parties: bool

def build(...) -> ReportData          # assemble from a Universe + Reference
def render_text(data: ReportData, *, top: int = 25, width: int = 96) -> str
def render_json(data: ReportData) -> str
```

## Text output

Plain ASCII, no colour, no third-party table library. Must stay readable when
piped to a file. Sections in order:

1. Header — source, as-of date, window, `min_members` floor, midpoint method.
2. **Top names** — rank, ticker, score, members, buyers/sellers, net $, sector,
   median filing lag, and a compact component breakdown.
3. **Sector rotation** — with recent-vs-prior momentum.
4. **Contested names** — members on both sides.
5. **Filer leaderboard** — fastest filers first.
6. Footer — drop counts by reason, and a one-line note when `has_parties` is
   False saying the bipartisan component is off.

Format dollars as `$1.2M` / `$150k` / `$1,001`. Scores to 2 decimals with sign.

## JSON output

Stable schema — the macOS client in contract 07 decodes exactly this. Keys are
`snake_case`, dates are ISO-8601 strings, `null` for missing. Top level:

```json
{
  "schema_version": 1,
  "generated_at": "...", "asof": "...", "lookback": 60, "min_members": 3,
  "midpoint": "geometric", "source": "sample", "has_parties": true,
  "n_trades_considered": 115,
  "dropped": {"options": 1},
  "signals": [{"ticker":"NVDA","sector":"...","score":6.49,"components":{...},
               "raw":{...},"n_members":9,"n_buyers":9,"n_sellers":0,
               "net_dollars":413136.0,"gross_dollars":...,"n_trades":9,
               "buyers":[...],"sellers":[],"parties":{"D":5,"R":4},
               "first_date":"...","last_date":"...","median_lag_days":28.0,
               "contested":false,"direction":"buy"}],
  "sectors": [...], "contested": [...], "filers": [...]
}
```

**Bump `schema_version` if you change any key.** Contract 07 pins it.

## Done when

`report --sample` prints all six sections; `render_json` round-trips through
`json.loads` and every `signals[]` entry carries all listed keys.
