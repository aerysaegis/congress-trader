"""Deterministic offline fixture. `report --sample` must work with no network.

Rows are emitted in the *raw feed shape*, not as Trades, so the sample
exercises the real normalize.py path -- including rows that are meant to be
dropped (options, reinvestments, bonds, sub-threshold trades). If a drop rule
regresses, the sample report's drop counts move.

Dates are generated relative to `anchor` (today by default) so the sample
always looks like a live window. Tests pass a fixed anchor for determinism.
"""
from __future__ import annotations

import random
from datetime import date, timedelta

AMOUNT_BUCKETS = [
    "$1,001 - $15,000",
    "$15,001 - $50,000",
    "$50,001 - $100,000",
    "$100,001 - $250,000",
    "$250,001 - $500,000",
    "$500,001 - $1,000,000",
    "$1,000,001 - $5,000,000",
]

HOUSE_MEMBERS = [
    "Hon. Marjorie Ellery", "Hon. Daniel Okonjo", "Hon. Priya Raghunathan",
    "Hon. Thomas Vance", "Hon. Cecilia Marlowe", "Hon. Robert Iselin",
    "Hon. Amara Nwosu", "Hon. Grace Lindqvist", "Hon. Peter Almeida",
    "Hon. Helen Sorokin", "Hon. Marcus Whitfield", "Hon. Nadia Farouk",
    "Hon. Owen Brackett", "Hon. Sylvia Chen", "Hon. Julian Ferrer",
]

SENATE_MEMBERS = [
    "Katherine Bly", "Arthur Pemberton", "Rosa Villanueva", "Edmund Cray",
    "Ingrid Halvorsen", "Samuel Adeyemi", "Lorraine Deschamps", "Victor Kaplan",
]

# Names the sample deliberately crowds, so the report has something to find.
CROWDED = {
    "NVDA": ("Information Technology", 9, 0.92),
    "AVGO": ("Information Technology", 7, 0.86),
    "LLY":  ("Health Care", 6, 0.83),
    "VST":  ("Utilities", 5, 0.90),
    "GEV":  ("Industrials", 5, 0.78),
    "JPM":  ("Financials", 4, 0.70),
}

# Names with genuine two-sided disagreement.
CONTESTED = {"TSLA": ("Consumer Discretionary", 6, 0.45), "BA": ("Industrials", 5, 0.40)}

# Background churn: enough distinct names that z-scoring has a real universe.
BACKGROUND = {
    "AAPL": "Information Technology", "MSFT": "Information Technology",
    "AMZN": "Consumer Discretionary", "GOOGL": "Communication Services",
    "META": "Communication Services", "UNH": "Health Care",
    "XOM": "Energy", "CVX": "Energy", "PG": "Consumer Staples",
    "KO": "Consumer Staples", "HD": "Consumer Discretionary",
    "CAT": "Industrials", "DE": "Industrials", "PFE": "Health Care",
    "BAC": "Financials", "GS": "Financials", "NEE": "Utilities",
    "LIN": "Materials", "AMT": "Real Estate", "T": "Communication Services",
}


def _row(rng, member, ticker, description, side, txn, discl, amount, chamber, **extra):
    base = {
        "transaction_date": txn.isoformat() if chamber == "house" else txn.strftime("%m/%d/%Y"),
        "disclosure_date": discl.strftime("%m/%d/%Y"),
        "owner": rng.choice(["self", "joint", "spouse", "dependent"]),
        "ticker": ticker,
        "asset_description": description,
        "type": side,
        "amount": amount,
        "_chamber": chamber,
    }
    if chamber == "house":
        base["representative"] = member
        base["district"] = f"{rng.choice(['CA','TX','NY','FL','OH','PA'])}{rng.randint(1,30):02d}"
    else:
        base["senator"] = member
        base["asset_type"] = "Stock"
        base["comment"] = "--"
    base.update(extra)
    return base


def _member_pool(rng, n):
    pool = HOUSE_MEMBERS + SENATE_MEMBERS
    return rng.sample(pool, min(n, len(pool)))


def _chamber_of(member):
    return "house" if member in HOUSE_MEMBERS else "senate"


def _side(rng, buy_bias):
    return "Purchase" if rng.random() < buy_bias else rng.choice(["Sale (Full)", "Sale (Partial)"])


def build_sample(anchor: date | None = None, seed: int = 20240917) -> list[dict]:
    """Generate the fixture. Same seed + anchor always yields the same rows."""
    anchor = anchor or date.today()
    rng = random.Random(seed)
    rows: list[dict] = []

    def emit(ticker, name, member, side, days_ago, lag, amount):
        txn = anchor - timedelta(days=days_ago)
        rows.append(
            _row(rng, member, ticker, name, side, txn, txn + timedelta(days=lag),
                 amount, _chamber_of(member))
        )

    # Crowded names: buyers bunched inside a tight window, which is exactly
    # what the cluster and acceleration components are built to notice.
    for ticker, (_sector, n_members, buy_bias) in {**CROWDED, **CONTESTED}.items():
        centre = rng.randint(6, 34)
        for member in _member_pool(rng, n_members):
            emit(ticker, f"{ticker} Inc. Common Stock", member,
                 _side(rng, buy_bias),
                 max(1, centre + rng.randint(-4, 4)),
                 rng.randint(12, 44),
                 rng.choice(AMOUNT_BUCKETS[:5]))

    # Background churn across the rest of the universe.
    for ticker in BACKGROUND:
        for member in _member_pool(rng, rng.randint(1, 5)):
            emit(ticker, f"{ticker} Inc. Common Stock", member,
                 _side(rng, 0.55), rng.randint(1, 58), rng.randint(20, 45),
                 rng.choice(AMOUNT_BUCKETS))

    # One whale, to prove breadth counts people rather than dollars: a single
    # member cannot lift a name into the rankings on size alone.
    emit("WHAL", "Whale Holdings Inc.", HOUSE_MEMBERS[0], "Purchase", 8, 20,
         "$1,000,001 - $5,000,000")

    # Rows that must be dropped. If a drop rule regresses these reappear.
    rows.extend([
        _row(rng, SENATE_MEMBERS[0], "SPY", "SPY Call Option, strike $500, expiring 01/17/26",
             "Purchase", anchor - timedelta(days=10), anchor - timedelta(days=1),
             "$15,001 - $50,000", "senate", asset_type="Stock Option"),
        _row(rng, SENATE_MEMBERS[1], "AAPL", "Apple Inc.", "Purchase",
             anchor - timedelta(days=12), anchor - timedelta(days=2),
             "$1,001 - $15,000", "senate", comment="Dividend reinvestment - automatic"),
        _row(rng, SENATE_MEMBERS[2], "UST", "US Treasury Note 4.25% 2029", "Purchase",
             anchor - timedelta(days=14), anchor - timedelta(days=3),
             "$50,001 - $100,000", "senate", asset_type="Corporate Bond"),
        _row(rng, HOUSE_MEMBERS[1], "MSFT", "Microsoft Corp", "exchange",
             anchor - timedelta(days=9), anchor - timedelta(days=1),
             "$15,001 - $50,000", "house"),
        _row(rng, HOUSE_MEMBERS[2], "KO", "Coca-Cola Co", "Purchase",
             anchor - timedelta(days=7), anchor - timedelta(days=1),
             "$1 - $500", "house"),
        _row(rng, HOUSE_MEMBERS[3], "", "Private LLC membership interest", "Purchase",
             anchor - timedelta(days=11), anchor - timedelta(days=2),
             "$15,001 - $50,000", "house"),
    ])

    rng.shuffle(rows)
    return rows


# Module-level convenience for sources.load_sample().
SAMPLE_ROWS = build_sample()

SAMPLE_SECTORS = {**{t: s for t, (s, _n, _b) in {**CROWDED, **CONTESTED}.items()}, **BACKGROUND}
