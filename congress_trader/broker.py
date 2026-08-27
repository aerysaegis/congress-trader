"""Broker boundary for offline plans and optional Alpaca execution."""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Protocol

from .strategy import Order


class BrokerError(RuntimeError):
    """A safe, vendor-neutral broker failure."""


@dataclass(frozen=True, slots=True)
class Account:
    equity: float
    cash: float
    buying_power: float
    is_paper: bool


class Broker(Protocol):
    def account(self) -> Account: ...

    def positions(self) -> dict[str, float]: ...

    def submit(self, order: Order) -> str: ...


class DryRunBroker:
    """In-memory broker used for offline planning and CLI previews."""

    def __init__(
        self,
        *,
        equity: float = 10_000.0,
        cash: float | None = None,
        positions: dict[str, float] | None = None,
    ) -> None:
        self._equity = float(equity)
        self._cash = float(equity if cash is None else cash)
        self._positions = dict(positions or {})
        self._submitted: list[Order] = []

    def account(self) -> Account:
        return Account(
            equity=self._equity,
            cash=self._cash,
            buying_power=self._cash,
            is_paper=True,
        )

    def positions(self) -> dict[str, float]:
        return dict(self._positions)

    def submit(self, order: Order) -> str:
        if order.side == "buy" and order.dollars > 0:
            self._positions[order.symbol] = self._positions.get(order.symbol, 0.0) + order.dollars
            self._cash -= order.dollars
        elif order.side == "sell" and order.dollars == 0.0:
            self._cash += self._positions.pop(order.symbol, 0.0)
        else:
            raise BrokerError(f"unsupported dry-run order for {order.symbol}")
        self._submitted.append(order)
        return f"dry-run-{len(self._submitted)}"


class AlpacaBroker:
    """Thin Alpaca-py adapter with a second live-trading safety gate."""

    def __init__(self, *, paper: bool = True, live_gate_cleared: bool = False) -> None:
        if not paper and not live_gate_cleared:
            raise BrokerError("live gate has not been cleared")

        api_key = os.environ.get("ALPACA_API_KEY")
        api_secret = os.environ.get("ALPACA_API_SECRET")
        if not api_key or not api_secret:
            raise BrokerError("missing ALPACA_API_KEY or ALPACA_API_SECRET")

        try:
            from alpaca.trading.client import TradingClient
            from alpaca.trading.enums import OrderSide, TimeInForce
            from alpaca.trading.requests import MarketOrderRequest
        except ImportError:
            raise BrokerError('Alpaca trading requires: pip install "alpaca-py>=0.21"') from None

        try:
            client = TradingClient(api_key, api_secret, paper=paper)
        except Exception:
            raise BrokerError("could not initialize Alpaca trading client") from None

        self._client = client
        self._paper = paper
        self._order_side = OrderSide
        self._time_in_force = TimeInForce
        self._market_order_request = MarketOrderRequest

    def account(self) -> Account:
        try:
            raw = self._client.get_account()
            return Account(
                equity=float(raw.equity or 0.0),
                cash=float(raw.cash or 0.0),
                buying_power=float(raw.buying_power or 0.0),
                is_paper=self._paper,
            )
        except Exception:
            raise BrokerError("could not load Alpaca account") from None

    def positions(self) -> dict[str, float]:
        try:
            rows = self._client.get_all_positions()
            return {str(row.symbol): float(row.market_value or 0.0) for row in rows}
        except Exception:
            raise BrokerError("could not load Alpaca positions") from None

    @staticmethod
    def _order_id(response: object) -> str:
        value = response.get("id") if isinstance(response, dict) else getattr(response, "id", None)
        if value is None:
            raise BrokerError("Alpaca did not return an order id")
        return str(value)

    def submit(self, order: Order) -> str:
        if order.side not in {"buy", "sell"}:
            raise BrokerError(f"unsupported order side for {order.symbol}")
        if order.side == "buy" and order.dollars <= 0:
            raise BrokerError(f"buy order for {order.symbol} has no notional")

        try:
            if order.side == "sell" and order.dollars == 0.0:
                return self._order_id(self._client.close_position(order.symbol))

            side = self._order_side.BUY if order.side == "buy" else self._order_side.SELL
            request = self._market_order_request(
                symbol=order.symbol,
                notional=order.dollars,
                side=side,
                time_in_force=self._time_in_force.DAY,
            )
            return self._order_id(self._client.submit_order(order_data=request))
        except BrokerError:
            raise
        except Exception:
            raise BrokerError(f"could not submit Alpaca order for {order.symbol}") from None


def get_broker(
    *,
    dry_run: bool,
    paper: bool = True,
    live_gate_cleared: bool = False,
) -> Broker:
    if dry_run:
        return DryRunBroker()
    return AlpacaBroker(paper=paper, live_gate_cleared=live_gate_cleared)
