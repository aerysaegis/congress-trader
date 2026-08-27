"""Command line interface.

Exit codes: 0 success, 1 runtime failure, 2 bad usage.

`--json` writes only JSON to stdout so `report --json | jq` works; everything
informational goes to stderr.
"""
from __future__ import annotations

import argparse
import sys
from datetime import date

from . import report as report_module
from . import sources
from .broker import Broker, BrokerError, get_broker
from .config import Reference
from .normalize import normalize
from .risk import Budget, RiskViolation
from .strategy import build_plan

MIDPOINTS = ("geometric", "arithmetic")
SOURCES = ("live", "house", "senate", "sample")


def _note(message: str) -> None:
    """Informational output. Always stderr, so --json stays pipeable.

    stdout is flushed first: when stdout is a pipe it block-buffers while
    stderr does not, so without this the notes arrive before the output they
    are commenting on.
    """
    sys.stdout.flush()
    print(message, file=sys.stderr, flush=True)


def _add_shared(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--lookback", type=int, default=60, metavar="DAYS")
    parser.add_argument("--min-members", type=int, default=3, metavar="N",
                        help="distinct people required before a name is scored")
    parser.add_argument("--min-dollars", type=float, default=1000.0, metavar="USD")
    parser.add_argument("--midpoint", choices=MIDPOINTS, default="geometric")
    parser.add_argument("--source", choices=SOURCES, default="live")
    parser.add_argument("--sample", action="store_true", help="alias for --source sample")
    parser.add_argument("--refresh", action="store_true", help="bypass the cache")
    parser.add_argument("--asof", metavar="YYYY-MM-DD")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="congress-trader",
        description="STOCK Act disclosure clustering signal, with optional Alpaca execution.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    rep = sub.add_parser("report", help="score the current window and print the tables")
    _add_shared(rep)
    rep.add_argument("--top", type=int, default=25, metavar="N")
    rep.add_argument("--json", action="store_true", help="machine-readable output on stdout")

    run = sub.add_parser("run", help="build an order plan and optionally submit it")
    _add_shared(run)
    run.add_argument("--dry-run", action="store_true", help="plan only, no broker, no credentials")
    run.add_argument("--paper", action="store_true", default=True, help="paper trading (default)")
    run.add_argument("--live", action="store_true", help="real money; also requires --yes-really")
    run.add_argument("--yes-really", action="store_true", help="confirm live trading")
    run.add_argument("--min-score", type=float, default=0.5)
    run.add_argument("--exit-score", type=float, default=-0.5)

    return parser


def _resolve_asof(raw: str | None) -> date | None:
    if not raw:
        return None
    try:
        return date.fromisoformat(raw)
    except ValueError:
        raise SystemExit(f"--asof must be YYYY-MM-DD, got {raw!r}") from None


def _load(args) -> tuple[Reference, object, str]:
    source = "sample" if args.sample else args.source
    reference = Reference.load()
    rows = sources.load(source, refresh=args.refresh)
    universe = normalize(rows, reference=reference, min_dollars=args.min_dollars,
                         midpoint=args.midpoint)
    return reference, universe, source


def cmd_report(args) -> int:
    asof = _resolve_asof(args.asof)
    reference, universe, source = _load(args)
    if not args.json:
        _note(f"loaded {len(universe.trades)} usable trades from {source}")

    data = report_module.build(
        universe, reference=reference, lookback=args.lookback,
        min_members=args.min_members, midpoint=args.midpoint, source=source, asof=asof,
    )

    if args.json:
        print(report_module.render_json(data))
    else:
        print(report_module.render_text(data, top=args.top))
    return 0


def cmd_run(args) -> int:
    # The live gate. The message must name --yes-really: CI greps for it, so
    # that this check cannot pass on an unrelated failure.
    if args.live and not args.yes_really:
        _note("refusing to trade live without --yes-really.")
        _note("")
        _note("  --live moves real money. Add --yes-really if that is what you mean:")
        _note("      python3 -m congress_trader run --live --yes-really")
        _note("")
        _note("  No orders were placed.")
        return 1

    asof = _resolve_asof(args.asof)
    reference, universe, source = _load(args)
    _note(f"loaded {len(universe.trades)} usable trades from {source}")

    data = report_module.build(
        universe, reference=reference, lookback=args.lookback,
        min_members=args.min_members, midpoint=args.midpoint, source=source, asof=asof,
    )
    if not data.signals:
        _note(f"nothing cleared the {args.min_members}-member floor; no orders to place")
        return 0

    paper = not args.live
    try:
        broker: Broker = get_broker(dry_run=args.dry_run, paper=paper,
                                    live_confirmed=args.live and args.yes_really)
        account = broker.account()
        positions = broker.positions()
    except BrokerError as exc:
        _note(f"broker unavailable: {exc}")
        return 1

    budget = Budget(equity=account.equity, cash=account.cash,
                    open_positions=len(positions))
    try:
        plan = build_plan(data.signals, budget=budget, positions=positions,
                          min_score=args.min_score, exit_score=args.exit_score,
                          midpoint=args.midpoint)
    except RiskViolation as exc:
        _note(f"plan violated a risk cap and was discarded: {exc}")
        return 1

    mode = "DRY RUN" if args.dry_run else ("LIVE" if args.live else "PAPER")
    print(f"{account}   mode {mode}")
    print(f"cash buffer holds ${budget.untouchable_cash:,.2f} untouched; "
          f"${budget.deployable_cash:,.2f} deployable\n")
    print(plan.describe())

    if args.dry_run:
        _note("\ndry run: nothing was submitted")
        return 0
    if not plan.orders:
        _note("\nnothing to submit")
        return 0

    print()
    submitted = 0
    for order in plan.orders:
        try:
            order_id = broker.submit(order)
        except BrokerError as exc:
            _note(f"FAILED {order.symbol}: {exc}")
            continue
        print(f"  submitted {order.symbol:<6s} {order_id}")
        submitted += 1
    _note(f"\n{submitted} of {len(plan.orders)} orders submitted")
    return 0 if submitted == len(plan.orders) else 1


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "report":
            return cmd_report(args)
        if args.command == "run":
            return cmd_run(args)
    except sources.SourceError as exc:
        _note(f"could not load data: {exc}")
        _note("Try --sample to run against the bundled offline fixture.")
        return 1
    except KeyboardInterrupt:
        _note("interrupted")
        return 1
    parser.error(f"unknown command {args.command!r}")
    return 2


if __name__ == "__main__":
    sys.exit(main())
