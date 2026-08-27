from __future__ import annotations

import math
from datetime import date

from congress_trader.analytics import sector_rotation
from congress_trader.config import Reference
from congress_trader.models import Side
from congress_trader.signals import score

ASOF = date(2025, 1, 31)


def test_geometric_and_arithmetic_midpoints_flow_through_signal_totals(trade_factory, reference) -> None:
    trades = [
        trade_factory("AAA", member, low=1_000.0, high=9_000.0)
        for member in ("Alice", "Bob", "Carol")
    ] + [
        trade_factory("BBB", member, low=1_000.0, high=4_000.0)
        for member in ("Alice", "Bob", "Carol")
    ]

    geometric = {item.ticker: item for item in score(trades, reference=reference, asof=ASOF)}
    arithmetic = {
        item.ticker: item for item in score(trades, reference=reference, midpoint="arithmetic", asof=ASOF)
    }

    assert geometric["AAA"].gross_dollars == 9_000.0
    assert arithmetic["AAA"].gross_dollars == 15_000.0
    assert geometric["AAA"].net_dollars < arithmetic["AAA"].net_dollars


def test_member_floor_excludes_one_whale(trade_factory, reference) -> None:
    trades = [trade_factory("WHAL", "Alice", low=50_000_000.0, high=100_000_000.0)]
    trades += [trade_factory("AAA", member) for member in ("Alice", "Bob", "Carol")]

    ranked = score(trades, reference=reference, min_members=3, asof=ASOF)

    assert [item.ticker for item in ranked] == ["AAA"]


def test_tight_cluster_outranks_same_members_spread_across_window(trade_factory, reference) -> None:
    tight_days = [date(2025, 1, 27), date(2025, 1, 28), date(2025, 1, 29)]
    spread_days = [date(2024, 12, 5), date(2024, 12, 25), date(2025, 1, 29)]
    members = ["Alice", "Bob", "Carol"]
    trades = [
        trade_factory("AAA", member, transaction_date=day)
        for member, day in zip(members, tight_days, strict=True)
    ] + [
        trade_factory("BBB", member, transaction_date=day)
        for member, day in zip(members, spread_days, strict=True)
    ]

    ranked = score(trades, reference=reference, weights={"cluster": 1.0}, asof=ASOF, lookback=60)

    assert [item.ticker for item in ranked] == ["AAA", "BBB"]
    assert ranked[0].raw["cluster"] > ranked[1].raw["cluster"]


def test_bipartisan_component_is_absent_without_party_map(trade_factory) -> None:
    trades = [trade_factory("AAA", member) for member in ("Alice", "Bob", "Carol")]

    ranked = score(trades, reference=Reference(sectors={"AAA": "Alpha"}), asof=ASOF)

    assert "bipartisan" not in ranked[0].components
    assert "bipartisan" in ranked[0].raw


def test_min_members_gate_is_configurable(trade_factory, reference) -> None:
    trades = [trade_factory("AAA", member) for member in ("Alice", "Bob")]

    assert score(trades, reference=reference, min_members=3, asof=ASOF) == []
    assert score(trades, reference=reference, min_members=2, asof=ASOF)


def test_sector_momentum_uses_same_midline_as_signal_acceleration(trade_factory) -> None:
    reference = Reference(sectors={"AAA": "Alpha"})
    trades = [
        trade_factory("AAA", "Alice", transaction_date=date(2025, 1, 25), side=Side.BUY),
        trade_factory("AAA", "Bob", transaction_date=date(2025, 1, 15), side=Side.BUY),
        trade_factory("AAA", "Carol", transaction_date=date(2024, 12, 20), side=Side.SELL),
    ]

    signal = score(trades, reference=reference, asof=ASOF, lookback=60)[0]
    sector = sector_rotation(trades, reference=reference, asof=ASOF, lookback=60)[0]

    assert math.isclose(signal.raw["acceleration"], sector.momentum)
