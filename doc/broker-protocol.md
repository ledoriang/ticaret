# Broker Protocol & Exchange Adapter Design

## The Problem

Different brokers have different APIs, authentication methods, rate limits, WebSocket formats, and market conventions. If strategy code or orchestration code directly calls a broker API, switching brokers requires rewriting the entire stack.

## The Solution: BrokerProtocol

Every broker adapter implements the same `BrokerProtocol` interface. The rest of the system (orchestrator, risk, strategy) never touches a broker-specific API call.

```python
from trading.core.enums import AssetClass
from trading.core.models import Bar, Order, Position, AccountInfo, FillEvent
from trading.core.events import OrderEvent

class BrokerProtocol(Protocol):
    """Every exchange/broker adapter must implement this interface."""

    name: str
    asset_classes: list[AssetClass]

    async def get_bars(
        self, symbol: str, timeframe: str, start: datetime, end: datetime
    ) -> list[Bar]: ...

    async def get_account(self) -> AccountInfo: ...

    async def get_positions(self) -> list[Position]: ...

    async def submit_order(self, order: OrderEvent) -> FillEvent: ...

    async def cancel_order(self, order_id: str) -> None: ...

    async def stream_bars(
        self, symbols: list[str], timeframe: str
    ) -> AsyncIterator[Bar]: ...

    async def get_market_hours(self, symbol: str) -> MarketHours: ...
```

## Adding a New Exchange

Three steps. No existing code changes required.

### 1. Create the adapter

File: `src/trading/execution/adapters/newexchange.py`

```python
class NewExchangeAdapter(AbstractBrokerAdapter):
    name = "newexchange"
    asset_classes = [AssetClass.CRYPTO]

    async def get_bars(self, symbol, timeframe, start, end) -> list[Bar]:
        # Translate to NewExchange's REST API
        ...

    async def submit_order(self, order: OrderEvent) -> FillEvent:
        # Translate to NewExchange's order format
        ...
```

### 2. Register it

Add to the adapter registry map (a simple dict):

```python
ADAPTER_REGISTRY: dict[str, type[AbstractBrokerAdapter]] = {
    "binance": BinanceAdapter,
    "alpaca": AlpacaAdapter,
    "newexchange": NewExchangeAdapter,
    "paper": PaperAdapter,
}
```

### 3. Configure it

```yaml
brokers:
  newexchange:
    api_key: ${NEWEXCHANGE_KEY}
    api_secret: ${NEWEXCHANGE_SECRET}
    testnet: false
```

Set `brokers.active.crypto: newexchange` and the dispatcher routes all crypto orders to the new adapter. Zero changes to orchestrator, strategy, risk, or monitoring.

## Removing an Exchange

Delete the adapter file, remove it from the registry dict, remove the config section. The system shrinks. No dangling references because no other module imports adapter internals.

## Adapter Implementations

### Binance (Crypto) — Phase 1

- REST: Historical bars, account info, order submission
- WebSocket: Real-time bar streaming
- Testnet support for paper trading
- 24/7 market hours (`get_market_hours` returns always-open)

### Paper (Dry-Run) — Phase 1

- No API calls. Logs orders to `paper_orders` table.
- Simulates fills at last known price.
- Tracks virtual positions and portfolio.
- Used for all backtesting and pipeline validation.

### Alpaca (US Equities) — Phase 4

- REST: Historical bars, account, orders
- WebSocket: Real-time bar streaming
- Paper trading API (`paper: true` in config)
- NYSE market hours: 09:30–16:00 ET, closed weekends and holidays
- Pattern Day Trader (PDT) rule awareness in risk manager

### Future Adapters (Not Yet Implemented)

| Adapter | Asset Classes | Notes |
|---|---|---|
| OKX | Crypto | Similar to Binance, additional derivatives support |
| IBKR | Multi-asset | Gold standard for international access. Complex TWS API gateway |
| Kraken | Crypto | Strong EU regulatory compliance |

## Multi-Broker Routing

The Dispatcher routes `OrderEvent` to the correct adapter based on `asset_class`:

```python
class Dispatcher:
    def __init__(self, adapters: dict[str, AbstractBrokerAdapter]):
        self.adapters = adapters
        self.routing: dict[AssetClass, str] = {}  # loaded from config

    async def dispatch(self, order: OrderEvent) -> FillEvent:
        adapter_name = self.routing[order.asset_class]
        adapter = self.adapters[adapter_name]
        return await adapter.submit_order(order)
```

Config example — running crypto on Binance live and equities on Alpaca paper simultaneously:

```yaml
brokers:
  active:
    crypto: binance
    equity: alpaca
  binance:
    api_key: ${BINANCE_KEY}
    api_secret: ${BINANCE_SECRET}
    testnet: false
  alpaca:
    api_key: ${ALPACA_KEY}
    api_secret: ${ALPACA_SECRET}
    paper: true
```

## Market Hours Handling

Each adapter returns market hours relevant to its asset class:

- **Crypto adapters** return `MarketHours(always_open=True)` — no scheduling constraints.
- **Equity adapters** return `MarketHours(open="09:30", close="16:00", timezone="US/Eastern", holidays=NYSE_CALENDAR)` — the orchestrator suppresses order generation outside market hours.

This means the orchestrator and risk manager don't need to know whether it's a crypto or equity trade. The adapter handles it.