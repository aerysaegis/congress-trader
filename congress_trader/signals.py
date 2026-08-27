"""The scoring engine.

One member's trade is noise. Agreement between independent members is the
thing worth measuring. Six components, each z-scored across the universe of
qualifying names and blended with configurable weights.

This module is the frozen contract every other module consumes. Changing the
shape of `TickerSignal` or the keys of `DEFAULT_WEIGHTS` breaks report.py,
strategy.py and the macOS client at once -- treat it as an API.
"""
from __future__ import annotations

import math
import statistics
from dataclasses import dataclass, field
from datetime import date

from .config import Reference
from .models import Side, Trade

# Blend weights. Before changing these, run `report --lookback 120` and
# `--lookback 30` and check whether the top names survive both. A signal that
# only exists at one window length isn't a signal.
DEFAULT_WEIGHTS: dict[str, float] = {
    "breadth": 1.00,
    "net_flow": 0.80,
    "acceleration": 0.60,
    "cluster": 0.50,
    "freshness": 0.40,
    "bipartisan": 0.30,
}

COMPONENTS = tuple(DEFAULT_WEIGHTS)

# Time constant for the cluster kernel, in days. A group of buyers loses about
# 63% of its cluster credit for every CLUSTER_TAU days it spreads out over.
CLUSTER_TAU = 7.0


@dataclass(frozen=True, slots=True)
class TickerSignal:
    """Everything the report and the strategy need about one name."""

    ticker: str
    sector: str
    score: float
    components: dict[str, float]          # z-scored, post-weight-eligible
    raw: dict[str, float]                 # pre-z, for debugging and display
    n_members: int
    n_buyers: int
    n_sellers: int
    net_dollars: float
    gross_dollars: float
    n_trades: int
    buyers: list[str]
    sellers: list[str]
    parties: dict[str, int] = field(default_factory=dict)
    first_date: date | None = None
    last_date: date | None = None
    median_lag_days: float | None = None

    @property
    def contested(self) -> bool:
        """Members on both sides of the same name."""
        return self.n_buyers > 0 and self.n_sellers > 0

    @property
    def direction(self) -> Side:
        return Side.BUY if self.net_dollars >= 0 else Side.SELL


# --- component math --------------------------------------------------------


# Dollar unit the log flow is measured in. Anchoring at $1k (rather than $1)
# is what makes $15M score ~2x $150k instead of ~1.4x -- below this unit a
# trade contributes essentially nothing, which is the intent of --min-dollars.
FLOW_UNIT = 1_000.0


def _log_flow(dollars: float) -> float:
    """Signed log-scale dollars, so $15M is ~2x $150k rather than 100x."""
    return math.copysign(math.log10(1.0 + abs(dollars) / FLOW_UNIT), dollars)


def _cluster_density(days: list[int]) -> float:
    """Tightest grouping of buy dates: 5 members inside 6 days != 5 across 45.

    For every contiguous run of k>=2 distinct buy dates we score
    `k * exp(-span / CLUSTER_TAU)` and keep the best. More members raises it
    linearly; spreading them out decays it exponentially.
    """
    if len(days) < 2:
        return 0.0
    ordered = sorted(days)
    best = 0.0
    for i in range(len(ordered)):
        for j in range(i + 1, len(ordered)):
            k = j - i + 1
            span = ordered[j] - ordered[i]
            best = max(best, k * math.exp(-span / CLUSTER_TAU))
    return best


def _zscore(values: list[float]) -> list[float]:
    """Population z-score. A degenerate spread scores every name flat at zero."""
    if not values:
        return []
    mean = statistics.fmean(values)
    if len(values) < 2:
        return [0.0 for _ in values]
    spread = statistics.pstdev(values)
    if spread <= 1e-12:
        return [0.0 for _ in values]
    return [(v - mean) / spread for v in values]


def _raw_components(
    trades: list[Trade],
    *,
    reference: Reference,
    midpoint: str,
    asof: date,
    lookback: int,
) -> dict[str, float]:
    """Pre-z component values for a single ticker."""
    buys = [t for t in trades if t.side is Side.BUY]
    sells = [t for t in trades if t.side is Side.SELL]

    # breadth counts *people*, not dollars, so one $15M whale can't dominate.
    buyers = {t.member for t in buys}
    sellers = {t.member for t in sells}
    breadth = sum(reference.weight_of(m) for m in buyers) - sum(reference.weight_of(m) for m in sellers)

    net = sum(t.signed_dollars(midpoint) * reference.weight_of(t.member) for t in trades)
    net_flow = _log_flow(net)

    # acceleration: recent half of the window against the older half.
    midline = asof.toordinal() - lookback / 2.0
    recent = sum(t.signed_dollars(midpoint) for t in trades if t.transaction_date.toordinal() > midline)
    older = sum(t.signed_dollars(midpoint) for t in trades if t.transaction_date.toordinal() <= midline)
    acceleration = _log_flow(recent) - _log_flow(older)

    cluster = _cluster_density([t.transaction_date.toordinal() for t in buys])

    # freshness: a 44-day-old filing is stale on arrival, so slow filers get
    # penalised. Undisclosed rows are treated as the statutory 45-day ceiling.
    lags = [t.filing_lag_days if t.filing_lag_days is not None else 45 for t in trades]
    freshness = -statistics.fmean([max(0, lag) for lag in lags]) if lags else 0.0

    # bipartisan: a bonus when buyers span both parties. Silently zero without
    # a parties.json, and the component is dropped from the blend entirely.
    bipartisan = 0.0
    if reference.has_parties:
        by_party: dict[str, set[str]] = {}
        for t in buys:
            party = reference.party_of(t.member)
            if party:
                by_party.setdefault(party, set()).add(t.member)
        if len(by_party) >= 2:
            sizes = sorted((len(v) for v in by_party.values()), reverse=True)
            bipartisan = float(min(sizes[0], sizes[1]))

    return {
        "breadth": breadth,
        "net_flow": net_flow,
        "acceleration": acceleration,
        "cluster": cluster,
        "freshness": freshness,
        "bipartisan": bipartisan,
    }


# --- public entry point ----------------------------------------------------


def score(
    trades: list[Trade],
    *,
    reference: Reference | None = None,
    weights: dict[str, float] | None = None,
    min_members: int = 3,
    midpoint: str = "geometric",
    lookback: int = 60,
    asof: date | None = None,
) -> list[TickerSignal]:
    """Score every ticker that clears the `min_members` floor.

    That floor is what separates this from a Pelosi tracker: nothing is scored
    until at least `min_members` distinct people have traded it.

    Returns signals sorted by score, highest first.
    """
    reference = reference or Reference.load()
    weights = dict(weights or DEFAULT_WEIGHTS)
    if not reference.has_parties:
        weights.pop("bipartisan", None)

    if not trades:
        return []
    asof = asof or max(t.transaction_date for t in trades)

    by_ticker: dict[str, list[Trade]] = {}
    for trade in trades:
        by_ticker.setdefault(trade.ticker, []).append(trade)

    qualifying = {
        ticker: rows
        for ticker, rows in by_ticker.items()
        if len({t.member for t in rows}) >= min_members
    }
    if not qualifying:
        return []

    tickers = sorted(qualifying)
    raw_by_ticker = {
        ticker: _raw_components(
            qualifying[ticker],
            reference=reference,
            midpoint=midpoint,
            asof=asof,
            lookback=lookback,
        )
        for ticker in tickers
    }

    # Z-score each component across the universe, then blend.
    zs: dict[str, list[float]] = {
        component: _zscore([raw_by_ticker[t][component] for t in tickers]) for component in COMPONENTS
    }

    signals: list[TickerSignal] = []
    for index, ticker in enumerate(tickers):
        rows = qualifying[ticker]
        components = {c: zs[c][index] for c in COMPONENTS if c in weights}
        total = sum(weights[c] * components[c] for c in components)

        buys = [t for t in rows if t.side is Side.BUY]
        sells = [t for t in rows if t.side is Side.SELL]
        lags = [t.filing_lag_days for t in rows if t.filing_lag_days is not None]
        parties: dict[str, int] = {}
        for member in {t.member for t in rows}:
            party = reference.party_of(member)
            if party:
                parties[party] = parties.get(party, 0) + 1

        signals.append(
            TickerSignal(
                ticker=ticker,
                sector=reference.sector_of(ticker),
                score=total,
                components=components,
                raw=raw_by_ticker[ticker],
                n_members=len({t.member for t in rows}),
                n_buyers=len({t.member for t in buys}),
                n_sellers=len({t.member for t in sells}),
                net_dollars=sum(t.signed_dollars(midpoint) for t in rows),
                gross_dollars=sum(t.midpoint(midpoint) for t in rows),
                n_trades=len(rows),
                buyers=sorted({t.member for t in buys}),
                sellers=sorted({t.member for t in sells}),
                parties=parties,
                first_date=min(t.transaction_date for t in rows),
                last_date=max(t.transaction_date for t in rows),
                median_lag_days=statistics.median(lags) if lags else None,
            )
        )

    signals.sort(key=lambda s: s.score, reverse=True)
    return signals
