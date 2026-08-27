"""Raw feed rows -> Trade records, with every drop counted and reported.

The drop rules are the opinionated part. Each one removes filings that are
technically disclosures but not *decisions* -- automatic reinvestments, asset
transfers, instruments whose size can't be recovered from a range.
"""
from __future__ import annotations

import re
from datetime import date, datetime

from .config import Reference
from .models import Chamber, Side, Trade, Universe

# --- parsing helpers -------------------------------------------------------

_DATE_FORMATS = ("%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y", "%Y/%m/%d", "%d-%b-%Y")
_MONEY = re.compile(r"\$?\s*([\d,]+(?:\.\d+)?)")
_NULLISH = {"", "--", "-", "n/a", "na", "none", "null", "unknown", "?"}

# Options: match option *context*, not any word containing "call" (Callaway).
_OPTION_PATTERNS = re.compile(
    r"\b(call|put)\s+option(s)?\b"
    r"|\boption(s)?\s+(to|on|contract)\b"
    r"|\b(strike|expir\w+)\b"
    r"|\b(call|put)s?\b\s*(@|\$|\d{1,2}/\d{1,2})"
    r"|\bwrit(e|ten|ing)\s+(call|put)",
    re.IGNORECASE,
)

_EQUITY_ASSET_TYPES = re.compile(
    r"\b(stock|common\s+stock|equity|equities|etf|exchange[- ]traded|adr|reit)\b", re.IGNORECASE
)
_NON_EQUITY_ASSET_TYPES = re.compile(
    r"\b(option|bond|note|bill|treasur\w+|municipal|debt|future|crypto|currenc\w+|"
    r"commodit\w+|annuit\w+|insurance|hedge\s+fund|private\s+equity|partnership|"
    r"farm|real\s+estate|property|trust\s+account|deposit|savings|529|"
    r"variable\s+rate|corporate\s+securit\w+|non[- ]public)\b",
    re.IGNORECASE,
)

_REINVEST = re.compile(r"\b(dividend\s+reinvest\w*|reinvest\w*\s+dividend|drip)\b", re.IGNORECASE)
_TRANSFER = re.compile(r"\b(exchange|gift|inherit\w+|transfer|conversion|spin[- ]?off|merger)\b", re.IGNORECASE)

_TICKER_OK = re.compile(r"^[A-Z][A-Z0-9.\-]{0,6}$")


def _clean(value) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    return "" if text.lower() in _NULLISH else text


def parse_date(value) -> date | None:
    text = _clean(value)
    if not text:
        return None
    text = text.split("T")[0].strip()
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def parse_amount(value) -> tuple[float, float]:
    """'$1,001 - $15,000' -> (1001.0, 15000.0). Open-ended buckets extrapolate.

    Returns (0.0, 0.0) when nothing numeric is present.
    """
    text = _clean(value)
    if not text:
        return (0.0, 0.0)
    numbers = [float(m.replace(",", "")) for m in _MONEY.findall(text)]
    if not numbers:
        return (0.0, 0.0)
    if len(numbers) >= 2:
        lo, hi = min(numbers[0], numbers[1]), max(numbers[0], numbers[1])
        return (lo, hi)
    only = numbers[0]
    lowered = text.lower()
    if "over" in lowered or "+" in text or "more than" in lowered or "least" in lowered:
        # Open-ended top bucket: assume one more doubling rather than infinity.
        return (only, only * 2.0)
    if "under" in lowered or "less than" in lowered:
        return (only / 2.0, only)
    return (only, only)


def parse_side(value) -> Side:
    text = _clean(value).lower()
    if not text:
        return Side.UNKNOWN
    if "exchange" in text:
        return Side.EXCHANGE
    if "purchase" in text or text.startswith("buy") or text == "p":
        return Side.BUY
    if "sale" in text or text.startswith("sell") or text.startswith("s"):
        return Side.SELL
    return Side.UNKNOWN


def parse_ticker(value) -> str:
    text = _clean(value).upper()
    if not text:
        return ""
    text = text.split()[0].strip(".,;:")
    return text if _TICKER_OK.match(text) else ""


# --- the pipeline ----------------------------------------------------------


def normalize(
    rows: list[dict],
    *,
    reference: Reference | None = None,
    min_dollars: float = 1000.0,
    midpoint: str = "geometric",
    keep_sells: bool = True,
) -> Universe:
    """Turn raw feed rows into a Universe, counting each drop reason."""
    reference = reference or Reference.load()
    universe = Universe()

    for row in rows:
        chamber_raw = _clean(row.get("_chamber")) or ("senate" if "senator" in row else "house")
        member = _clean(row.get("representative") or row.get("senator") or row.get("member"))
        if not member:
            universe.drop("no member name")
            continue
        member = _strip_honorific(member)

        asset_type = _clean(row.get("asset_type"))
        description = _clean(row.get("asset_description") or row.get("asset_name"))
        comment = _clean(row.get("comment"))
        haystack = f"{asset_type} {description} {comment}"

        if _OPTION_PATTERNS.search(haystack) or "option" in asset_type.lower():
            universe.drop("options")
            continue
        if _REINVEST.search(haystack):
            universe.drop("dividend reinvestment")
            continue
        if asset_type and not _EQUITY_ASSET_TYPES.search(asset_type) and _NON_EQUITY_ASSET_TYPES.search(asset_type):
            universe.drop("non-equity asset")
            continue

        side = parse_side(row.get("type") or row.get("transaction_type"))
        if side is Side.EXCHANGE or _TRANSFER.search(_clean(row.get("type"))):
            universe.drop("exchange or gift")
            continue
        if side is Side.UNKNOWN:
            universe.drop("unrecognized transaction type")
            continue
        if side is Side.SELL and not keep_sells:
            universe.drop("sells excluded")
            continue

        ticker = parse_ticker(row.get("ticker"))
        if not ticker:
            universe.drop("no ticker")
            continue

        transaction_date = parse_date(row.get("transaction_date"))
        if transaction_date is None:
            universe.drop("unparseable transaction date")
            continue
        disclosure_date = parse_date(row.get("disclosure_date"))

        low, high = parse_amount(row.get("amount"))
        if high <= 0:
            universe.drop("no amount range")
            continue

        trade = Trade(
            member=member,
            chamber=Chamber.SENATE if chamber_raw == "senate" else Chamber.HOUSE,
            ticker=ticker,
            side=side,
            transaction_date=transaction_date,
            disclosure_date=disclosure_date,
            amount_low=low,
            amount_high=high,
            asset_description=description,
            asset_type=asset_type,
            owner=_clean(row.get("owner")),
            raw_amount=_clean(row.get("amount")),
            party=reference.party_of(member),
            source=chamber_raw,
        )

        if trade.midpoint(midpoint) < min_dollars:
            universe.drop("below min dollars")
            continue

        universe.trades.append(trade)

    universe.trades.sort(key=lambda t: t.transaction_date)
    return universe


_HONORIFICS = re.compile(r"^(hon\.?|mr\.?|mrs\.?|ms\.?|dr\.?|rep\.?|sen\.?)\s+", re.IGNORECASE)


def _strip_honorific(name: str) -> str:
    previous = None
    while previous != name:
        previous = name
        name = _HONORIFICS.sub("", name).strip()
    return " ".join(name.split())


def window(universe: Universe, *, lookback: int, asof: date | None = None) -> list[Trade]:
    """Trades whose transaction date falls in the last `lookback` days."""
    if not universe.trades:
        return []
    asof = asof or max(t.transaction_date for t in universe.trades)
    cutoff = asof.toordinal() - lookback
    return [t for t in universe.trades if t.transaction_date.toordinal() > cutoff and t.transaction_date <= asof]
