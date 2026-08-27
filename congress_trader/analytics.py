"""The three tables that sit alongside the ranked names.

Derived from the same windowed trades as `signals.score`, but answering
different questions: where is money rotating, where do members disagree, and
who files fast enough for their disclosures to still be worth reading.
"""
from __future__ import annotations

import statistics
from dataclasses import dataclass
from datetime import date

from .config import Reference
from .models import Side, Trade
from .signals import _log_flow, window_midline


@dataclass(frozen=True, slots=True)
class SectorRow:
    sector: str
    net_dollars: float
    gross_dollars: float
    n_members: int
    n_trades: int
    recent_net: float
    prior_net: float
    momentum: float


@dataclass(frozen=True, slots=True)
class ContestedRow:
    ticker: str
    sector: str
    buyers: list[str]
    sellers: list[str]
    buy_dollars: float
    sell_dollars: float
    disagreement: float

    @property
    def n_buyers(self) -> int:
        return len(self.buyers)

    @property
    def n_sellers(self) -> int:
        return len(self.sellers)


@dataclass(frozen=True, slots=True)
class FilerRow:
    member: str
    chamber: str
    party: str | None
    n_trades: int
    n_tickers: int
    median_lag_days: float | None
    mean_lag_days: float | None
    fastest_lag_days: int | None
    gross_dollars: float


def _midline(trades: list[Trade], lookback: int, asof: date | None) -> float:
    """The recent/prior split point. Delegates so it cannot drift from signals."""
    asof = asof or max(t.transaction_date for t in trades)
    return window_midline(asof, lookback)


def sector_rotation(
    trades: list[Trade],
    *,
    reference: Reference | None = None,
    midpoint: str = "geometric",
    lookback: int = 60,
    asof: date | None = None,
) -> list[SectorRow]:
    """Net flow by sector, with recent-vs-prior momentum.

    Unmapped tickers bucket into "Unmapped" rather than vanishing, so a gap in
    sectors.json shows up as a row you can see instead of missing dollars.
    """
    if not trades:
        return []

    split = _midline(trades, lookback, asof)
    reference = reference or Reference.load()

    buckets: dict[str, list[Trade]] = {}
    for trade in trades:
        buckets.setdefault(reference.sector_of(trade.ticker), []).append(trade)

    rows: list[SectorRow] = []
    for sector, rows_in in buckets.items():
        recent = sum(t.signed_dollars(midpoint) for t in rows_in if t.transaction_date.toordinal() > split)
        prior = sum(t.signed_dollars(midpoint) for t in rows_in if t.transaction_date.toordinal() <= split)
        rows.append(
            SectorRow(
                sector=sector,
                net_dollars=sum(t.signed_dollars(midpoint) for t in rows_in),
                gross_dollars=sum(t.midpoint(midpoint) for t in rows_in),
                n_members=len({t.member for t in rows_in}),
                n_trades=len(rows_in),
                recent_net=recent,
                prior_net=prior,
                momentum=_log_flow(recent) - _log_flow(prior),
            )
        )

    rows.sort(key=lambda r: r.momentum, reverse=True)
    return rows


def contested_names(
    trades: list[Trade],
    *,
    reference: Reference | None = None,
    midpoint: str = "geometric",
    min_members: int = 3,
) -> list[ContestedRow]:
    """Names where members are on both sides.

    Disagreement is measured in *people*, not dollars, for the same reason
    breadth is: a lone large seller isn't a disagreement, it's one opinion.
    """
    if not trades:
        return []
    reference = reference or Reference.load()

    by_ticker: dict[str, list[Trade]] = {}
    for trade in trades:
        by_ticker.setdefault(trade.ticker, []).append(trade)

    rows: list[ContestedRow] = []
    for ticker, rows_in in by_ticker.items():
        if len({t.member for t in rows_in}) < min_members:
            continue
        buys = [t for t in rows_in if t.side is Side.BUY]
        sells = [t for t in rows_in if t.side is Side.SELL]
        buyers = sorted({t.member for t in buys})
        sellers = sorted({t.member for t in sells})
        if not buyers or not sellers:
            continue

        rows.append(
            ContestedRow(
                ticker=ticker,
                sector=reference.sector_of(ticker),
                buyers=buyers,
                sellers=sellers,
                buy_dollars=sum(t.midpoint(midpoint) for t in buys),
                sell_dollars=sum(t.midpoint(midpoint) for t in sells),
                disagreement=min(len(buyers), len(sellers)) / max(len(buyers), len(sellers)),
            )
        )

    rows.sort(key=lambda r: (r.disagreement, r.buy_dollars + r.sell_dollars), reverse=True)
    return rows


def filer_leaderboard(
    trades: list[Trade],
    *,
    reference: Reference | None = None,
    midpoint: str = "geometric",
    min_trades: int = 3,
) -> list[FilerRow]:
    """Who files fast. Fast filers produce fresher, more tradeable signal.

    Members whose filings carry no disclosure date sort last: an unknown lag is
    not evidence of a short one.
    """
    if not trades:
        return []
    reference = reference or Reference.load()

    by_member: dict[str, list[Trade]] = {}
    for trade in trades:
        by_member.setdefault(trade.member, []).append(trade)

    rows: list[FilerRow] = []
    for member, rows_in in by_member.items():
        if len(rows_in) < min_trades:
            continue
        lags = [lag for t in rows_in if (lag := t.filing_lag_days) is not None and lag >= 0]
        rows.append(
            FilerRow(
                member=member,
                chamber=rows_in[0].chamber.value,
                party=reference.party_of(member),
                n_trades=len(rows_in),
                n_tickers=len({t.ticker for t in rows_in}),
                median_lag_days=statistics.median(lags) if lags else None,
                mean_lag_days=statistics.fmean(lags) if lags else None,
                fastest_lag_days=min(lags) if lags else None,
                gross_dollars=sum(t.midpoint(midpoint) for t in rows_in),
            )
        )

    # None lags sort last; ties broken by the larger book first.
    rows.sort(key=lambda r: (r.median_lag_days is None, r.median_lag_days or 0.0, -r.gross_dollars))
    return rows
