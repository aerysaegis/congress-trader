"""Core record types. Everything downstream speaks Trade."""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date
from enum import Enum


class Side(str, Enum):
    BUY = "buy"
    SELL = "sell"
    EXCHANGE = "exchange"
    UNKNOWN = "unknown"

    @property
    def sign(self) -> int:
        return {Side.BUY: 1, Side.SELL: -1}.get(self, 0)


class Chamber(str, Enum):
    HOUSE = "house"
    SENATE = "senate"


@dataclass(frozen=True, slots=True)
class Trade:
    """One disclosed transaction, already normalized.

    Filings give dollar *ranges*, never exact amounts, so `amount_low` and
    `amount_high` are the truth and every point estimate derives from them.
    """

    member: str
    chamber: Chamber
    ticker: str
    side: Side
    transaction_date: date
    disclosure_date: date | None
    amount_low: float
    amount_high: float
    asset_description: str = ""
    asset_type: str = ""
    owner: str = ""
    raw_amount: str = ""
    party: str | None = None
    source: str = ""

    @property
    def filing_lag_days(self) -> int | None:
        """Days between the trade and its disclosure. None if undisclosed."""
        if self.disclosure_date is None:
            return None
        return (self.disclosure_date - self.transaction_date).days

    def midpoint(self, method: str = "geometric") -> float:
        """Point estimate of the trade size.

        Geometric by default: sqrt(low * high). The arithmetic mean badly
        overweights the top buckets -- $5M-$25M becomes $15M instead of ~$11M.
        """
        lo, hi = self.amount_low, self.amount_high
        if hi <= 0:
            return 0.0
        if lo <= 0:
            # Open-ended low bucket; geometric mean is undefined at zero.
            lo = min(1.0, hi)
        if method == "arithmetic":
            return (lo + hi) / 2.0
        return math.sqrt(lo * hi)

    def signed_dollars(self, method: str = "geometric") -> float:
        return self.side.sign * self.midpoint(method)


@dataclass(slots=True)
class Universe:
    """A filtered, normalized set of trades plus what got dropped and why."""

    trades: list[Trade] = field(default_factory=list)
    dropped: dict[str, int] = field(default_factory=dict)

    def __len__(self) -> int:
        return len(self.trades)

    def drop(self, reason: str, n: int = 1) -> None:
        self.dropped[reason] = self.dropped.get(reason, 0) + n
