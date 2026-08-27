# 04 — Alpaca broker adapter

Owner: **Codex**. Branch: `codex/04-broker`. Owns exactly: `congress_trader/broker.py`.
Consumes: `00-interfaces`, `03-strategy`. Blocks: 05.

## Required API

```python
class BrokerError(RuntimeError): ...

@dataclass(frozen=True)
class Account:
    equity: float; cash: float; buying_power: float; is_paper: bool

class Broker(Protocol):
    def account(self) -> Account: ...
    def positions(self) -> dict[str, float]: ...
    def submit(self, order: Order) -> str: ...     # returns broker order id

class DryRunBroker(Broker):     # never touches the network
class AlpacaBroker(Broker):     # wraps alpaca-py

def get_broker(*, dry_run: bool, paper: bool = True) -> Broker
```

## Rules

- **Paper is the default.** `AlpacaBroker(paper=False)` must refuse to
  construct unless explicitly told the live gate has been cleared. The
  `--yes-really` check belongs in the CLI (contract 05); this module's job is
  to make it impossible to reach live by accident from code.
- `alpaca-py` is an **optional** dependency. Import it lazily inside
  `AlpacaBroker`, and raise `BrokerError` with an install hint if missing.
  `import congress_trader.broker` must work without alpaca-py installed —
  a test asserts this.
- Credentials come from `ALPACA_API_KEY` / `ALPACA_API_SECRET` in the
  environment. Never accept them as CLI arguments, never log them, never
  include them in a repr or an exception message.
- `DryRunBroker` takes a synthetic equity/cash (default $10,000 paper-like) so
  `run --dry-run` works with no keys at all, offline.
- Submit notional market orders, day TIF. Fractional where the venue allows.
- Wrap every alpaca-py exception in `BrokerError`. Callers must not need to
  know the vendor SDK's exception types.

## Done when

`python3 -c "import congress_trader.broker"` succeeds in a clean env with no
alpaca-py, and `run --dry-run` prints a full plan offline with no credentials.
