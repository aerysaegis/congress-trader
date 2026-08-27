"""Rendering only. No scoring, no filtering, no loading.

If a number isn't here, it belongs in signals.py or analytics.py -- this module
is deliberately incapable of computing anything the engine didn't hand it.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime, timezone

from .analytics import ContestedRow, FilerRow, SectorRow, contested_names, filer_leaderboard, sector_rotation
from .config import Reference
from .models import Universe
from .signals import TickerSignal, score

SCHEMA_VERSION = 1


@dataclass(frozen=True, slots=True)
class ReportData:
    generated_at: datetime
    asof: date
    lookback: int
    min_members: int
    midpoint: str
    source: str
    signals: list[TickerSignal]
    sectors: list[SectorRow]
    contested: list[ContestedRow]
    filers: list[FilerRow]
    dropped: dict[str, int]
    n_trades_considered: int
    has_parties: bool


def build(
    universe: Universe,
    *,
    reference: Reference | None = None,
    lookback: int = 60,
    min_members: int = 3,
    midpoint: str = "geometric",
    source: str = "live",
    asof: date | None = None,
    weights: dict[str, float] | None = None,
) -> ReportData:
    """Run the engine over a normalized universe and collect every table."""
    from .normalize import window

    reference = reference or Reference.load()
    trades = window(universe, lookback=lookback, asof=asof)
    resolved_asof = asof or (max(t.transaction_date for t in trades) if trades else date.today())

    return ReportData(
        generated_at=datetime.now(timezone.utc),
        asof=resolved_asof,
        lookback=lookback,
        min_members=min_members,
        midpoint=midpoint,
        source=source,
        signals=score(trades, reference=reference, weights=weights, min_members=min_members,
                      midpoint=midpoint, lookback=lookback, asof=resolved_asof),
        sectors=sector_rotation(trades, reference=reference, midpoint=midpoint,
                                lookback=lookback, asof=resolved_asof),
        contested=contested_names(trades, reference=reference, midpoint=midpoint,
                                  min_members=min_members),
        filers=filer_leaderboard(trades, reference=reference, midpoint=midpoint),
        dropped=dict(universe.dropped),
        n_trades_considered=len(trades),
        has_parties=reference.has_parties,
    )


# --- formatting helpers ----------------------------------------------------


def money(value: float) -> str:
    """$1.2M / $150k / $1,001, with a sign only when negative."""
    sign = "-" if value < 0 else ""
    v = abs(value)
    if v >= 1_000_000:
        return f"{sign}${v / 1_000_000:.1f}M"
    if v >= 10_000:
        return f"{sign}${v / 1_000:.0f}k"
    return f"{sign}${v:,.0f}"


def _lag(value: float | None) -> str:
    return "-" if value is None else f"{value:.0f}d"


def _rule(char: str, width: int) -> str:
    return char * width


def _section(title: str, width: int) -> str:
    return f"\n{title}\n{_rule('-', width)}"


# --- text ------------------------------------------------------------------


def render_text(data: ReportData, *, top: int = 25, width: int = 96) -> str:
    out: list[str] = []
    out.append(_rule("=", width))
    out.append("CONGRESS-TRADER  ·  disclosure clustering signal")
    out.append(_rule("=", width))
    out.append(
        f"source {data.source}   as of {data.asof}   window {data.lookback}d   "
        f"floor {data.min_members} members   {data.midpoint} midpoint"
    )
    out.append(
        f"{data.n_trades_considered} trades in window   "
        f"{len(data.signals)} names cleared the floor   "
        f"generated {data.generated_at:%Y-%m-%d %H:%M}Z"
    )

    # 1. Top names
    out.append(_section(f"TOP NAMES (by blended score, showing {min(top, len(data.signals))})", width))
    if not data.signals:
        out.append(f"  Nothing cleared the {data.min_members}-member floor in this window.")
        out.append("  Try a longer --lookback, or lower --min-members if you accept thinner agreement.")
    else:
        out.append(f"  {'#':>2}  {'TICKER':<7}{'SCORE':>7}  {'MEM':>3} {'B/S':>6}  "
                   f"{'NET $':>9}  {'LAG':>4}  SECTOR")
        for rank, sig in enumerate(data.signals[:top], 1):
            out.append(
                f"  {rank:>2}  {sig.ticker:<7}{sig.score:>+7.2f}  {sig.n_members:>3} "
                f"{f'{sig.n_buyers}/{sig.n_sellers}':>6}  {money(sig.net_dollars):>9}  "
                f"{_lag(sig.median_lag_days):>4}  {sig.sector}"
            )
            parts = " ".join(f"{name[:5]}{value:+.1f}" for name, value in sig.components.items())
            out.append(f"      {parts}")

    # 2. Sector rotation
    out.append(_section("SECTOR ROTATION (recent half of window vs older half)", width))
    if not data.sectors:
        out.append("  No trades in window.")
    else:
        out.append(f"  {'SECTOR':<26}{'MOMENTUM':>9}  {'NET $':>9}  {'RECENT':>9}  {'PRIOR':>9}  {'MEM':>4}")
        for row in data.sectors:
            out.append(
                f"  {row.sector[:26]:<26}{row.momentum:>+9.2f}  {money(row.net_dollars):>9}  "
                f"{money(row.recent_net):>9}  {money(row.prior_net):>9}  {row.n_members:>4}"
            )

    # 3. Contested
    out.append(_section("CONTESTED (members on both sides of the same name)", width))
    if not data.contested:
        out.append("  No name has both buyers and sellers above the member floor.")
    else:
        out.append(f"  {'TICKER':<7}{'SPLIT':>6}  {'B/S':>6}  {'BOUGHT':>9}  {'SOLD':>9}  SECTOR")
        for row in data.contested[:15]:
            out.append(
                f"  {row.ticker:<7}{row.disagreement:>6.2f}  "
                f"{f'{row.n_buyers}/{row.n_sellers}':>6}  {money(row.buy_dollars):>9}  "
                f"{money(row.sell_dollars):>9}  {row.sector}"
            )

    # 4. Filers
    out.append(_section("FILERS (fastest first — fast filers make fresher signal)", width))
    if not data.filers:
        out.append("  No member cleared the minimum trade count.")
    else:
        out.append(f"  {'MEMBER':<26}{'CH':<7}{'P':<3}{'MEDIAN':>7}{'FAST':>6}{'TRADES':>7}{'NAMES':>6}  {'GROSS':>9}")
        for row in data.filers[:15]:
            out.append(
                f"  {row.member[:26]:<26}{row.chamber[:6]:<7}{row.party or '-':<3}"
                f"{_lag(row.median_lag_days):>7}{_lag(row.fastest_lag_days):>6}"
                f"{row.n_trades:>7}{row.n_tickers:>6}  {money(row.gross_dollars):>9}"
            )

    # 5. Footer
    out.append(_section("DROPPED", width))
    if not data.dropped:
        out.append("  Nothing dropped.")
    else:
        for reason, count in sorted(data.dropped.items(), key=lambda kv: -kv[1]):
            out.append(f"  {count:>6}  {reason}")
    if not data.has_parties:
        out.append("\n  No parties.json loaded — the bipartisan component is off.")
    out.append("")
    out.append("  Dollar figures are midpoints of disclosed ranges, not actual amounts.")
    out.append("  Filings lag trades by 30-45 days. Not financial advice.")
    out.append(_rule("=", width))
    return "\n".join(out)


# --- json ------------------------------------------------------------------


def _signal_json(sig: TickerSignal) -> dict:
    return {
        "ticker": sig.ticker,
        "sector": sig.sector,
        "score": round(sig.score, 6),
        "components": {k: round(v, 6) for k, v in sig.components.items()},
        "raw": {k: round(v, 6) for k, v in sig.raw.items()},
        "n_members": sig.n_members,
        "n_buyers": sig.n_buyers,
        "n_sellers": sig.n_sellers,
        "net_dollars": round(sig.net_dollars, 2),
        "gross_dollars": round(sig.gross_dollars, 2),
        "n_trades": sig.n_trades,
        "buyers": sig.buyers,
        "sellers": sig.sellers,
        "parties": sig.parties,
        "first_date": sig.first_date.isoformat() if sig.first_date else None,
        "last_date": sig.last_date.isoformat() if sig.last_date else None,
        "median_lag_days": sig.median_lag_days,
        "contested": sig.contested,
        "direction": sig.direction.value,
    }


def to_dict(data: ReportData) -> dict:
    """The wire format. The macOS client decodes exactly this."""
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": data.generated_at.isoformat(),
        "asof": data.asof.isoformat(),
        "lookback": data.lookback,
        "min_members": data.min_members,
        "midpoint": data.midpoint,
        "source": data.source,
        "has_parties": data.has_parties,
        "n_trades_considered": data.n_trades_considered,
        "dropped": data.dropped,
        "signals": [_signal_json(s) for s in data.signals],
        "sectors": [
            {
                "sector": r.sector,
                "net_dollars": round(r.net_dollars, 2),
                "gross_dollars": round(r.gross_dollars, 2),
                "n_members": r.n_members,
                "n_trades": r.n_trades,
                "recent_net": round(r.recent_net, 2),
                "prior_net": round(r.prior_net, 2),
                "momentum": round(r.momentum, 6),
            }
            for r in data.sectors
        ],
        "contested": [
            {
                "ticker": r.ticker,
                "sector": r.sector,
                "buyers": r.buyers,
                "sellers": r.sellers,
                "buy_dollars": round(r.buy_dollars, 2),
                "sell_dollars": round(r.sell_dollars, 2),
                "disagreement": round(r.disagreement, 6),
            }
            for r in data.contested
        ],
        "filers": [
            {
                "member": r.member,
                "chamber": r.chamber,
                "party": r.party,
                "n_trades": r.n_trades,
                "n_tickers": r.n_tickers,
                "median_lag_days": r.median_lag_days,
                "mean_lag_days": round(r.mean_lag_days, 4) if r.mean_lag_days is not None else None,
                "fastest_lag_days": r.fastest_lag_days,
                "gross_dollars": round(r.gross_dollars, 2),
            }
            for r in data.filers
        ],
    }


def render_json(data: ReportData) -> str:
    return json.dumps(to_dict(data), indent=2)
