from __future__ import annotations

from datetime import date

import pytest

from congress_trader.config import Reference
from congress_trader.models import Chamber, Side, Trade
from congress_trader.signals import TickerSignal


@pytest.fixture
def reference() -> Reference:
    return Reference(
        sectors={"AAA": "Alpha", "BBB": "Beta", "CCC": "Gamma"},
        parties={"alice": "D", "bob": "R", "carol": "D", "dave": "R"},
    )


@pytest.fixture
def trade_factory():
    def make(
        ticker: str = "AAA",
        member: str = "Alice",
        *,
        side: Side = Side.BUY,
        transaction_date: date = date(2025, 1, 20),
        disclosure_date: date | None = date(2025, 1, 30),
        low: float = 1_000.0,
        high: float = 10_000.0,
        chamber: Chamber = Chamber.HOUSE,
    ) -> Trade:
        return Trade(
            member=member,
            chamber=chamber,
            ticker=ticker,
            side=side,
            transaction_date=transaction_date,
            disclosure_date=disclosure_date,
            amount_low=low,
            amount_high=high,
        )

    return make


@pytest.fixture
def signal_factory():
    def make(
        ticker: str = "AAA",
        score: float = 1.0,
        *,
        direction: Side = Side.BUY,
    ) -> TickerSignal:
        buyers = ["Alice", "Bob", "Carol"] if direction is Side.BUY else []
        sellers = [] if direction is Side.BUY else ["Alice", "Bob", "Carol"]
        return TickerSignal(
            ticker=ticker,
            sector="Test",
            score=score,
            components={},
            raw={},
            n_members=3,
            n_buyers=len(buyers),
            n_sellers=len(sellers),
            net_dollars=10_000.0 if direction is Side.BUY else -10_000.0,
            gross_dollars=10_000.0,
            n_trades=3,
            buyers=buyers,
            sellers=sellers,
            first_date=date(2025, 1, 1),
            last_date=date(2025, 1, 3),
        )

    return make
