"""Assemble and render congressional trading reports."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import date, datetime, timezone

from .analytics import ContestedRow, FilerRow, SectorRow, contested_names, filer_leaderboard, sector_rotation
from .config import Reference
from .models import Universe
from .normalize import window
from .signals import TickerSignal, score


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
    generated_at: datetime | None = None,
    asof: date | None = None,
    lookback: int = 60,
    min_members: int = 3,
    midpoint: str = "geometric",
    source: str = "live",
) -> ReportData:
    """Assemble report data by delegating analysis to the engine modules."""
    reference = reference or Reference.load()
    asof = asof or (max((trade.transaction_date for trade in universe.trades), default=date.today()))
    considered = window(universe, lookback=lookback, asof=asof)

    return ReportData(
        generated_at=generated_at or datetime.now(timezone.utc),
        asof=asof,
        lookback=lookback,
        min_members=min_members,
        midpoint=midpoint,
        source=source,
        signals=score(
            considered,
            reference=reference,
            min_members=min_members,
            midpoint=midpoint,
            lookback=lookback,
            asof=asof,
        ),
        sectors=sector_rotation(
            considered,
            reference=reference,
            midpoint=midpoint,
            lookback=lookback,
            asof=asof,
        ),
        contested=contested_names(
            considered,
            reference=reference,
            midpoint=midpoint,
            min_members=min_members,
        ),
        filers=filer_leaderboard(considered, reference=reference, midpoint=midpoint),
        dropped=dict(universe.dropped),
        n_trades_considered=len(considered),
        has_parties=reference.has_parties,
    )


def _ascii(text: object) -> str:
    return str(text).encode("ascii", "replace").decode("ascii")


def _clip(text: object, width: int) -> str:
    rendered = _ascii(text)
    if len(rendered) <= width:
        return rendered
    if width <= 3:
        return rendered[:width]
    return rendered[: width - 3] + "..."


def _fmt_dollars(value: float) -> str:
    sign = "-" if value < 0 else ""
    absolute = abs(value)
    if absolute >= 1_000_000:
        return f"{sign}${absolute / 1_000_000:.1f}M"
    if absolute >= 10_000:
        return f"{sign}${absolute / 1_000:.0f}k"
    return f"{sign}${absolute:,.0f}"


def _fmt_lag(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.1f}d"


def _section(lines: list[str], title: str, width: int) -> None:
    if lines:
        lines.append("")
    lines.append(_clip(title, width))
    lines.append("-" * min(width, len(title)))


def render_text(data: ReportData, *, top: int = 25, width: int = 96) -> str:
    """Render a bounded-width ASCII report suitable for terminals and files."""
    width = max(24, width)
    lines: list[str] = []

    _section(lines, "CONGRESS TRADER", width)
    lines.append(
        _clip(
            f"Source: {data.source} | As of: {data.asof.isoformat()} | Window: {data.lookback} days | "
            f"Min members: {data.min_members} | Midpoint: {data.midpoint}",
            width,
        )
    )
    lines.append(_clip(f"Trades considered: {data.n_trades_considered}", width))

    _section(lines, "TOP NAMES", width)
    if not data.signals or top <= 0:
        lines.append("No qualifying names.")
    else:
        lines.append(_clip(" # TICKER   SCORE MEM  B/S       NET SECTOR             LAG", width))
        for rank, item in enumerate(data.signals[:top], start=1):
            lines.append(
                _clip(
                    f"{rank:>2} {item.ticker:<8} {item.score:+6.2f} {item.n_members:>3} "
                    f"{item.n_buyers:>2}/{item.n_sellers:<2} {_fmt_dollars(item.net_dollars):>9} "
                    f"{item.sector:<18} {_fmt_lag(item.median_lag_days):>6}",
                    width,
                )
            )
            abbreviations = {
                "breadth": "br",
                "net_flow": "nf",
                "acceleration": "ac",
                "cluster": "cl",
                "freshness": "fr",
                "bipartisan": "bp",
            }
            components = " ".join(
                f"{abbreviations.get(name, name[:2])}={value:+.2f}" for name, value in item.components.items()
            )
            lines.append(_clip(f"   components: {components}", width))

    _section(lines, "SECTOR ROTATION", width)
    if not data.sectors:
        lines.append("No sector activity.")
    else:
        lines.append(_clip("SECTOR                       NET     RECENT      PRIOR MOMENTUM MEM TRADES", width))
        for item in data.sectors:
            lines.append(
                _clip(
                    f"{item.sector:<24} {_fmt_dollars(item.net_dollars):>9} "
                    f"{_fmt_dollars(item.recent_net):>10} {_fmt_dollars(item.prior_net):>10} "
                    f"{item.momentum:+8.2f} {item.n_members:>3} {item.n_trades:>6}",
                    width,
                )
            )

    _section(lines, "CONTESTED NAMES", width)
    if not data.contested:
        lines.append("No names with members on both sides.")
    else:
        lines.append(_clip("TICKER  DISAGREE       BUY      SELL  B/S MEMBERS", width))
        for item in data.contested:
            members = f"buy: {', '.join(item.buyers)}; sell: {', '.join(item.sellers)}"
            lines.append(
                _clip(
                    f"{item.ticker:<7} {item.disagreement:>8.2f} {_fmt_dollars(item.buy_dollars):>9} "
                    f"{_fmt_dollars(item.sell_dollars):>9} {len(item.buyers):>2}/{len(item.sellers):<2} {members}",
                    width,
                )
            )

    _section(lines, "FILER LEADERBOARD", width)
    if not data.filers:
        lines.append("No filers meet the trade minimum.")
    else:
        lines.append(_clip("MEMBER                       CHAMBER PARTY TRADES TICKERS MEDIAN  MEAN FASTEST      GROSS", width))
        for item in data.filers:
            fastest = "n/a" if item.fastest_lag_days is None else f"{item.fastest_lag_days}d"
            lines.append(
                _clip(
                    f"{item.member:<28} {item.chamber:<7} {(item.party or '-'):>5} {item.n_trades:>6} "
                    f"{item.n_tickers:>7} {_fmt_lag(item.median_lag_days):>6} {_fmt_lag(item.mean_lag_days):>6} "
                    f"{fastest:>7} {_fmt_dollars(item.gross_dollars):>10}",
                    width,
                )
            )

    _section(lines, "DROPS", width)
    if data.dropped:
        for reason, count in sorted(data.dropped.items()):
            lines.append(_clip(f"{reason}: {count}", width))
    else:
        lines.append("None.")
    if not data.has_parties:
        lines.append(_clip("Bipartisan component is off: no party reference map loaded.", width))

    return "\n".join(lines) + "\n"


def _signal_json(item: TickerSignal) -> dict[str, object]:
    return {
        "ticker": item.ticker,
        "sector": item.sector,
        "score": item.score,
        "components": item.components,
        "raw": item.raw,
        "n_members": item.n_members,
        "n_buyers": item.n_buyers,
        "n_sellers": item.n_sellers,
        "net_dollars": item.net_dollars,
        "gross_dollars": item.gross_dollars,
        "n_trades": item.n_trades,
        "buyers": item.buyers,
        "sellers": item.sellers,
        "parties": item.parties,
        "first_date": item.first_date.isoformat() if item.first_date else None,
        "last_date": item.last_date.isoformat() if item.last_date else None,
        "median_lag_days": item.median_lag_days,
        "contested": item.contested,
        "direction": item.direction.value,
    }


def render_json(data: ReportData) -> str:
    """Render the stable schema consumed by the macOS client."""
    payload = {
        "schema_version": 1,
        "generated_at": data.generated_at.isoformat(),
        "asof": data.asof.isoformat(),
        "lookback": data.lookback,
        "min_members": data.min_members,
        "midpoint": data.midpoint,
        "source": data.source,
        "has_parties": data.has_parties,
        "n_trades_considered": data.n_trades_considered,
        "dropped": data.dropped,
        "signals": [_signal_json(item) for item in data.signals],
        "sectors": [asdict(item) for item in data.sectors],
        "contested": [asdict(item) for item in data.contested],
        "filers": [asdict(item) for item in data.filers],
    }
    return json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
