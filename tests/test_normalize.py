from __future__ import annotations

from datetime import date

import pytest

from congress_trader.models import Side
from congress_trader.normalize import normalize, parse_amount, parse_date, parse_side


def row(**changes) -> dict:
    base = {
        "representative": "Hon. Dr. Alice Example",
        "_chamber": "house",
        "ticker": "AAA",
        "asset_description": "AAA Inc. Common Stock",
        "asset_type": "Stock",
        "type": "Purchase",
        "transaction_date": "2025-01-20",
        "disclosure_date": "01/30/2025",
        "amount": "$1,001 - $15,000",
    }
    base.update(changes)
    return base


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("$1,001 - $15,000", (1_001.0, 15_000.0)),
        ("$1,000,001 - $5,000,000", (1_000_001.0, 5_000_000.0)),
        ("Over $50,000,000", (50_000_000.0, 100_000_000.0)),
        ("Under $1,000", (500.0, 1_000.0)),
        ("$25,000", (25_000.0, 25_000.0)),
        ("--", (0.0, 0.0)),
    ],
)
def test_amount_bucket_shapes(raw: str, expected: tuple[float, float]) -> None:
    assert parse_amount(raw) == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("2025-01-20", date(2025, 1, 20)), ("01/20/2025", date(2025, 1, 20))],
)
def test_two_feed_date_formats(raw: str, expected: date) -> None:
    assert parse_date(raw) == expected


@pytest.mark.parametrize("raw", ["Sale (Full)", "Sale (Partial)"])
def test_sale_variants_are_sells(raw: str) -> None:
    assert parse_side(raw) is Side.SELL


def test_honorifics_are_stripped_repeatedly() -> None:
    universe = normalize([row()])

    assert universe.trades[0].member == "Alice Example"


def test_every_drop_rule_is_counted() -> None:
    rows = [
        row(representative=""),
        row(asset_type="Stock Option"),
        row(comment="Dividend reinvestment"),
        row(asset_type="Corporate Bond"),
        row(type="Gift"),
        row(type="Mystery"),
        row(ticker=""),
        row(transaction_date="not-a-date"),
        row(amount="--"),
        row(amount="$1 - $500"),
        row(type="Sale (Full)"),
    ]

    universe = normalize(rows, min_dollars=1_000.0, keep_sells=False)

    assert universe.trades == []
    assert universe.dropped == {
        "no member name": 1,
        "options": 1,
        "dividend reinvestment": 1,
        "non-equity asset": 1,
        "exchange or gift": 1,
        "unrecognized transaction type": 1,
        "no ticker": 1,
        "unparseable transaction date": 1,
        "no amount range": 1,
        "below min dollars": 1,
        "sells excluded": 1,
    }
