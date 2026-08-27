from __future__ import annotations

from datetime import date

from congress_trader.analytics import contested_names, filer_leaderboard, sector_rotation
from congress_trader.models import Side

ASOF = date(2025, 1, 31)


def test_sector_rotation_orders_by_momentum_and_keeps_unmapped(trade_factory, reference) -> None:
    trades = [
        trade_factory("AAA", "Alice", transaction_date=date(2025, 1, 28)),
        trade_factory("AAA", "Bob", transaction_date=date(2025, 1, 27)),
        trade_factory("BBB", "Carol", transaction_date=date(2024, 12, 10)),
        trade_factory("ZZZ", "Dave", transaction_date=date(2025, 1, 29), low=1_000_000, high=5_000_000),
    ]

    rows = sector_rotation(trades, reference=reference, lookback=60, asof=ASOF)

    assert rows == sorted(rows, key=lambda item: item.momentum, reverse=True)
    assert any(item.sector == "Unmapped" and item.gross_dollars > 2_000_000 for item in rows)


def test_contested_orders_by_disagreement_then_gross_dollars(trade_factory, reference) -> None:
    trades = [
        trade_factory("AAA", "Alice"),
        trade_factory("AAA", "Bob", side=Side.SELL),
        trade_factory("AAA", "Carol", low=100_000, high=100_000),
        trade_factory("BBB", "Alice"),
        trade_factory("BBB", "Bob", side=Side.SELL),
        trade_factory("BBB", "Carol", low=1_000, high=1_000),
        trade_factory("CCC", "Alice"),
        trade_factory("CCC", "Bob"),
        trade_factory("CCC", "Carol", side=Side.SELL),
        trade_factory("CCC", "Dave", side=Side.SELL),
    ]

    rows = contested_names(trades, reference=reference, min_members=3)

    assert [item.ticker for item in rows] == ["CCC", "AAA", "BBB"]
    assert rows[0].disagreement == 1.0
    assert rows[1].disagreement == rows[2].disagreement == 0.5


def test_filers_sort_unknown_lags_last(trade_factory, reference) -> None:
    trades = []
    for member, lag_date in (("Alice", date(2025, 1, 21)), ("Bob", date(2025, 1, 30))):
        trades.extend(
            trade_factory("AAA", member, disclosure_date=lag_date)
            for _ in range(3)
        )
    trades.extend(trade_factory("BBB", "Carol", disclosure_date=None) for _ in range(3))

    rows = filer_leaderboard(trades, reference=reference, min_trades=3)

    assert [item.member for item in rows] == ["Alice", "Bob", "Carol"]
    assert rows[-1].median_lag_days is None


def test_empty_analytics_inputs_return_empty(reference) -> None:
    assert sector_rotation([], reference=reference, asof=ASOF) == []
    assert contested_names([], reference=reference) == []
    assert filer_leaderboard([], reference=reference) == []
