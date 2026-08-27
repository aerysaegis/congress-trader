from __future__ import annotations

import os
import subprocess
import sys
from types import ModuleType, SimpleNamespace

import pytest

from congress_trader.broker import AlpacaBroker, BrokerError, DryRunBroker, get_broker
from congress_trader.strategy import Order


def test_module_imports_without_alpaca_dependency() -> None:
    environment = dict(os.environ)
    environment.pop("ALPACA_API_KEY", None)
    environment.pop("ALPACA_API_SECRET", None)

    result = subprocess.run(
        [sys.executable, "-c", "import congress_trader.broker"],
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr


def test_dry_run_needs_no_credentials(monkeypatch) -> None:
    monkeypatch.delenv("ALPACA_API_KEY", raising=False)
    monkeypatch.delenv("ALPACA_API_SECRET", raising=False)

    broker = get_broker(dry_run=True)

    assert isinstance(broker, DryRunBroker)
    assert broker.account().equity == 10_000.0
    assert broker.account().is_paper is True
    assert broker.positions() == {}


def test_live_construction_refuses_without_gate() -> None:
    with pytest.raises(BrokerError, match="live"):
        AlpacaBroker(paper=False)


def test_missing_optional_dependency_has_install_hint(monkeypatch) -> None:
    monkeypatch.setenv("ALPACA_API_KEY", "paper-key")
    monkeypatch.setenv("ALPACA_API_SECRET", "paper-secret")
    monkeypatch.setitem(sys.modules, "alpaca", None)

    with pytest.raises(BrokerError, match=r"pip install.*alpaca-py"):
        AlpacaBroker()


def install_fake_alpaca(monkeypatch, *, constructor_error: bool = False):
    alpaca = ModuleType("alpaca")
    alpaca.__path__ = []
    trading = ModuleType("alpaca.trading")
    trading.__path__ = []
    client_module = ModuleType("alpaca.trading.client")
    enums_module = ModuleType("alpaca.trading.enums")
    requests_module = ModuleType("alpaca.trading.requests")

    class FakeRequest:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

    class FakeClient:
        last = None

        def __init__(self, key, secret, *, paper):
            if constructor_error:
                raise RuntimeError(f"vendor echoed {key} and {secret}")
            self.requests = []
            self.closed = []
            FakeClient.last = self

        def get_account(self):
            return SimpleNamespace(equity="12500.50", cash="4000", buying_power="8000")

        def get_all_positions(self):
            return [SimpleNamespace(symbol="NVDA", market_value="725.25")]

        def submit_order(self, request):
            self.requests.append(request)
            return SimpleNamespace(id="buy-id")

        def close_position(self, symbol):
            self.closed.append(symbol)
            return SimpleNamespace(id="sell-id")

    client_module.TradingClient = FakeClient
    enums_module.OrderSide = SimpleNamespace(BUY="buy", SELL="sell")
    enums_module.TimeInForce = SimpleNamespace(DAY="day")
    requests_module.MarketOrderRequest = FakeRequest
    for name, module in {
        "alpaca": alpaca,
        "alpaca.trading": trading,
        "alpaca.trading.client": client_module,
        "alpaca.trading.enums": enums_module,
        "alpaca.trading.requests": requests_module,
    }.items():
        monkeypatch.setitem(sys.modules, name, module)
    return FakeClient


def test_alpaca_maps_account_positions_and_orders(monkeypatch) -> None:
    fake = install_fake_alpaca(monkeypatch)
    monkeypatch.setenv("ALPACA_API_KEY", "paper-key")
    monkeypatch.setenv("ALPACA_API_SECRET", "paper-secret")
    broker = AlpacaBroker()

    assert broker.account().equity == 12_500.50
    assert broker.positions() == {"NVDA": 725.25}
    assert broker.submit(Order("AVGO", "buy", 300.0, "test", 1.0)) == "buy-id"
    assert fake.last.requests[0].notional == 300.0
    assert broker.submit(Order("NVDA", "sell", 0.0, "exit", None)) == "sell-id"
    assert fake.last.closed == ["NVDA"]


def test_vendor_exception_cannot_leak_credentials(monkeypatch) -> None:
    install_fake_alpaca(monkeypatch, constructor_error=True)
    monkeypatch.setenv("ALPACA_API_KEY", "TOPSECRETKEY")
    monkeypatch.setenv("ALPACA_API_SECRET", "TOPSECRETSECRET")

    with pytest.raises(BrokerError) as caught:
        AlpacaBroker()

    rendered = str(caught.value)
    assert "TOPSECRETKEY" not in rendered
    assert "TOPSECRETSECRET" not in rendered
    assert caught.value.__cause__ is None
