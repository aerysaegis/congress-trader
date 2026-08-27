"""Broker adapters. Paper by default, and live is hard to reach by accident.

`alpaca-py` is an optional dependency: importing this module must work without
it, so the analysis path never depends on a broker SDK being installed. The
import happens inside AlpacaBroker, not at module scope.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Protocol

from .strategy import Order


class BrokerError(RuntimeError):
    """Any broker-side failure. Callers never see vendor SDK exceptions."""


@dataclass(frozen=True, slots=True)
class Account:
    equity: float
    cash: float
    buying_power: float
    is_paper: bool

    def __str__(self) -> str:
        mode = "PAPER" if self.is_paper else "LIVE"
        return f"[{mode}] equity ${self.equity:,.2f}  cash ${self.cash:,.2f}"


class Broker(Protocol):
    def account(self) -> Account: ...
    def positions(self) -> dict[str, float]: ...
    def submit(self, order: Order) -> str: ...


class DryRunBroker:
    """Prints what would happen. Never opens a socket, never needs a key.

    Carries a synthetic account so `run --dry-run` produces a realistic plan
    offline -- sizing depends on equity, so a dry run with no account would
    show caps that don't resemble the real ones.
    """

    def __init__(self, *, equity: float = 10_000.0, cash: float = 10_000.0,
                 positions: dict[str, float] | None = None) -> None:
        self._equity = equity
        self._cash = cash
        self._positions = dict(positions or {})
        self.submitted: list[Order] = []

    def account(self) -> Account:
        return Account(equity=self._equity, cash=self._cash,
                       buying_power=self._cash, is_paper=True)

    def positions(self) -> dict[str, float]:
        return dict(self._positions)

    def submit(self, order: Order) -> str:
        self.submitted.append(order)
        return f"dry-run-{len(self.submitted):04d}"


class AlpacaBroker:
    """Wraps alpaca-py. Live trading requires the gate to have been cleared.

    `live_confirmed` is not a convenience flag -- it exists so that no code
    path can construct a live broker without a caller having explicitly said
    the human-facing gate was passed. The CLI owns that gate.
    """

    def __init__(self, *, paper: bool = True, live_confirmed: bool = False) -> None:
        if not paper and not live_confirmed:
            raise BrokerError(
                "refusing to construct a live broker without live_confirmed=True. "
                "Live trading requires --live and --yes-really on the command line."
            )
        key = os.environ.get("ALPACA_API_KEY", "").strip()
        secret = os.environ.get("ALPACA_API_SECRET", "").strip()
        if not key or not secret:
            raise BrokerError(
                "ALPACA_API_KEY and ALPACA_API_SECRET must be set in the environment. "
                "Use --dry-run to plan orders without credentials."
            )

        try:
            from alpaca.trading.client import TradingClient
        except ImportError as exc:
            raise BrokerError("alpaca-py is not installed. Run: pip install alpaca-py") from exc

        self._paper = paper
        try:
            self._client = TradingClient(key, secret, paper=paper)
        except Exception as exc:
            raise BrokerError(f"could not connect to Alpaca: {exc}") from exc

    def __repr__(self) -> str:
        # Deliberately carries no credentials.
        return f"AlpacaBroker(paper={self._paper})"

    def account(self) -> Account:
        try:
            acct = self._client.get_account()
        except Exception as exc:
            raise BrokerError(f"could not read account: {exc}") from exc
        return Account(
            equity=float(acct.equity),
            cash=float(acct.cash),
            buying_power=float(acct.buying_power),
            is_paper=self._paper,
        )

    def positions(self) -> dict[str, float]:
        try:
            held = self._client.get_all_positions()
        except Exception as exc:
            raise BrokerError(f"could not read positions: {exc}") from exc
        return {p.symbol: float(p.market_value) for p in held}

    def submit(self, order: Order) -> str:
        try:
            from alpaca.trading.enums import OrderSide, TimeInForce
            from alpaca.trading.requests import MarketOrderRequest
        except ImportError as exc:
            raise BrokerError("alpaca-py is not installed. Run: pip install alpaca-py") from exc

        side = OrderSide.BUY if order.side == "buy" else OrderSide.SELL

        if order.side == "sell" and order.dollars == 0.0:
            # Full liquidation: notional would need a price we don't have.
            try:
                closed = self._client.close_position(order.symbol)
            except Exception as exc:
                raise BrokerError(f"could not close {order.symbol}: {exc}") from exc
            return str(getattr(closed, "id", f"close-{order.symbol}"))

        request = MarketOrderRequest(
            symbol=order.symbol,
            notional=round(order.dollars, 2),
            side=side,
            time_in_force=TimeInForce.DAY,
        )
        try:
            placed = self._client.submit_order(request)
        except Exception as exc:
            raise BrokerError(f"could not submit {order.side} {order.symbol}: {exc}") from exc
        return str(placed.id)


def get_broker(*, dry_run: bool, paper: bool = True, live_confirmed: bool = False) -> Broker:
    """The only sanctioned way to obtain a broker."""
    if dry_run:
        return DryRunBroker()
    return AlpacaBroker(paper=paper, live_confirmed=live_confirmed)
