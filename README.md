# congress-trader

Pulls every STOCK Act disclosure from both chambers, finds where members are
crowding into the same names, and optionally trades that signal on Alpaca.
Analysis needs nothing but Python 3.10+. Trading needs an Alpaca key.

```bash
python3 -m congress_trader report --sample      # works offline, proves it runs
python3 -m congress_trader report               # live data
python3 -m congress_trader run --dry-run        # orders it would place
```

There is also a native macOS client in `macapp/` that runs the same engine and
renders the report as real Mac UI. It is an analysis surface only — trading
stays on the CLI, behind the `--yes-really` gate.

---

## The signal

One member's trade is noise. Agreement between independent members is the
thing worth measuring. Six components, each z-scored across the universe and
blended with configurable weights:

| Signal | What it captures |
|---|---|
| **breadth** | distinct buyers minus distinct sellers — counts *people*, so one $15M whale can't dominate |
| **net_flow** | signed dollar flow on a log scale, so $15M is ~2x $150k rather than 100x |
| **acceleration** | recent half of the window vs the older half — catches names being picked up *now* |
| **cluster** | tightest grouping of buyers in time; 5 members inside 6 days ≠ 5 members across 45 |
| **freshness** | penalty for slow filers, since a 44-day-old filing is stale on arrival |
| **bipartisan** | bonus when buyers span both parties (needs `parties.json`, silently off without it) |

Also reported: sector rotation with recent-vs-prior momentum, contested names
where members are on both sides, and a filer leaderboard showing who files
fast (fast filers produce fresher, more tradeable signal).

Nothing is scored until at least `--min-members` distinct people (default 3)
have traded it. That floor is what separates this from a Pelosi tracker.

## Data

Free community S3 dumps of House and Senate disclosures, cached to `.cache/`.
If they go stale, write a loader in `sources.py` returning the same `Trade`
records and point it at a paid feed (Quiver, Unusual Whales, Capitol Trades).

Filings give **dollar ranges, never exact amounts**. Every dollar figure here
is a geometric midpoint — `sqrt(low * high)`. Arithmetic midpoints badly
overweight the top buckets ($5M–$25M becomes $15M instead of ~$11M). Switch
with `--midpoint arithmetic` if you disagree.

Dropped automatically: options and non-equity assets, dividend reinvestments
(automatic, not decisions), exchanges and gifts, trades under `--min-dollars`.
Every drop is counted and printed, so a regression in the filters is visible
rather than silent.

## Trading

```bash
export ALPACA_API_KEY=...
export ALPACA_API_SECRET=...
pip install alpaca-py
python3 -m congress_trader run --paper
```

Paper is the default. `--live` additionally requires `--yes-really`.

Hard caps in `risk.py` that the signal engine cannot override:
`max_positions` 15, `$500` per trade, `$2000` per run, 8% of equity per name,
20% cash buffer always untouched. Exits run before entries so capital frees up
first. Position sizing is score-proportional but clamped at both ends.

Those limits are duplicated as literals in `tests/test_risk_invariants.py` on
purpose: an agent editing one file fails against the other, so the risk posture
cannot drift without a human deliberately changing both.

## Tuning

Extend the reference maps in `reference/` — anything unmapped falls into an
"Unmapped" bucket rather than being dropped:

- `sectors.json` — `{"NVDA": "Information Technology"}`
- `parties.json` — `{"Nancy Pelosi": "D"}`, enables the bipartisan signal
- `member_weights.json` — `{"Some Member": 0.3}`, downweight index-fund churners

Weights live in `signals.DEFAULT_WEIGHTS`. Before changing them, run
`report --lookback 120` and `--lookback 30` and see whether the top names
survive. A signal that only exists at one window length isn't a signal.

## Automating it

Cron, hourly on weekdays:

```
0 10-16 * * 1-5 cd /path/to/congress-trader && /usr/bin/python3 -m congress_trader run --paper >> run.log 2>&1
```

## How this repo is built

Two agents work this repo against written contracts, and GitHub is the shared
record. See [AGENTS.md](AGENTS.md) for the full protocol and
[docs/contracts/](docs/contracts/) for the task briefs.

- **Claude** owns architecture, the scoring engine, risk invariants, and review.
- **Codex** owns implementation against frozen interfaces, tests, and the Swift client.
- Neither agent merges its own PR. CI is the tiebreaker on facts; a judgment
  call goes to the human.

```bash
python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"
.venv/bin/python -m pytest
.venv/bin/python -m ruff check .
```

## What this cannot do

- **The 45-day lag is unfixable.** Members have 30–45 days to file. You are
  reading a delayed tape. Any edge that depends on speed is already gone.
- **Options are excluded.** Filings omit premiums and exact sizing, and a lot
  of the headline congressional activity is long-dated calls. Copying those
  from a range is guesswork, so the bot doesn't try.
- **No backtest is included.** Historical returns from disclosure data are
  very easy to overstate — the filings tell you the range and the date, not
  the fill. Treat any number you compute from them as an upper bound.
- **NANC and KRUZ already exist** as ETFs doing roughly this, and apps like
  Autopilot do the copy-trading. If the goal is exposure rather than building
  something, those are cheaper.

Not financial advice. Run it on paper for a few months and see whether the
signal survives contact with reality before it touches real money.
