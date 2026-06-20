# Architecture

## System Overview

The trading stack is structured as three distinct layers communicating through an asynchronous event bus. No layer directly calls another — all communication is through structured events.

```
+------------------------------------------------------------+
|                  1. Data & Identification                  |
|  (Technical Indicators, News Providers, Sentiment Scores)  |
+-----------------------------+------------------------------+
                              |
                              v  [Emits BarEvent + SentimentEvent]
+------------------------------------------------------------+
|                  2. Strategy Orchestration                 |
|   (Evaluators, Position Sizing, Rule-Engine, Risk Manager) |
+-----------------------------+------------------------------+
                              |
                              v  [Emits OrderEvent (if risk passes)]
+------------------------------------------------------------+
|                  3. Execution & Gateway                    |
|          (Broker API Wrappers, Live State Tracking)        |
+------------------------------------------------------------+
```

## Event Flow

```
                    ┌───────────────────┐
                    │   Redis Pub/Sub   │
                    │    Event Bus      │
                    │                   │
                    │  bars:*   signals:*│
                    │  orders:*  fills:* │
                    │sentiment:*commands:*│
                    │  risk_block:*      │
                    └──────┬────────────┘
                           │
         ┌─────────────────┼──────────────────┐
         │                 │                  │
         v                 v                  v
   ┌──────────┐    ┌──────────────┐    ┌───────────┐
   │ Live     │    │ Orchestrator │    │ Sentiment  │
   │ Stream   │    │              │    │ Ingester   │
   │ (WS)     │    │ ┌──────────┐ │    │ (service)  │
   └────┬─────┘    │ │ BarBuffer│ │    └─────┬─────┘
        │          │ │ (deque)  │ │          │
        │ bars:*   │ └──────────┘ │          │sentiment:*
        │          │      │       │          │
        │          │ ┌────┴─────┐ │          │
        │          │ │ Strat(s) │ │          │
        │          │ └────┬─────┘ │          │
        │          │ ┌────┴─────┐ │          │
        │          │ │  Risk    │ │          │
        │          │ └────┬─────┘ │          │
        │          └──────┼──────┘          │
        │                 │                 │
        │        signals:*│ orders:*        │
        └───────┐         │                 │
                │         v                 │
                │ ┌──────────────┐           │
                │ │  Dispatcher  │           │
                │ │ (routes by   │           │
                │ │  asset_class)│           │
                │ └──────┬───────┘           │
                │        │                   │
                │       fills:*              │
                │        │                   │
        ┌───────┼────────┼──────────┐        │
        v       v        v          v        v
   ┌────────┐┌────────┐┌────────┐┌──────────┐│
   │Binance ││ Paper  ││ Alpaca ││(future)  ││
   │Adapter ││Adapter ││Adapter ││ adapters ││
   │(REST+WS)││       ││(Ph. 3) ││         ││
   └────────┘└────────┘└────────┘└──────────┘│
                                             │
                    ┌─────────────────────────┘
                    │
              ┌─────┴──────────────┐
              │ News Providers      │
              │ ┌───────────────┐   │
              │ │Alpha Vantage   │  │
              │ │Marketaux       │  │
              │ │Finnhub         │  │
              │ │StockGeist      │  │
              │ │CachedProvider  │  │
              │ └───────────────┘   │
              └────────────────────┘
```

## Event Types

All events are typed Pydantic models carrying a correlation ID and schema version for end-to-end tracing and forward compatibility.

| Event | Emitter | Consumer | Payload |
|---|---|---|---|
| `BarEvent` | LiveStream (WebSocket) | Orchestrator → BarBuffer → Strategy | symbol, timeframe, OHLCV, timestamp |
| `SignalEvent` | Strategy (via Orchestrator) | Risk Manager | symbol, side, confidence, strategy_name, asset_class |
| `SentimentEvent` | Sentiment Ingester (NewsProvider) | Orchestrator → Strategy | symbol, score (-1 to 1), confidence, source, provider_name |
| `OrderEvent` | Risk Manager (approved) | Dispatcher/Execution | symbol, side, quantity, order_type, broker |
| `FillEvent` | Broker Adapter | Portfolio, Risk, Monitoring | symbol, side, fill_price, quantity, fees, timestamp |
| `RiskBlockEvent` | Risk Manager (rejected) | Monitoring, Alerts | original_signal, reason, rule_that_blocked |
| `CommandEvent` | CLI or external service | Orchestrator (Command Handler) | command: str (add_symbol, remove_symbol, add_strategy, remove_strategy, update_risk_rule), payload: dict |

All events carry `_event_schema_version: int` (currently `1`) for forward compatibility.

## Layer 1: Data & Identification

### Technical Analysis
- Use **pandas-ta** or **TA-Lib** (C++ with Python wrappers). Never write indicator math from scratch.
- Indicators are computed on bars fetched from TimescaleDB (historical) or streamed via Binance WebSocket kline streams (live).
- **Live streaming:** BinanceAdapter implements `stream_bars()` as an **async generator** over Binance WebSocket `wss://stream.binance.com:9443/ws/{symbol}@kline_{interval}`. Multi-symbol subscription, auto-reconnect with exponential backoff, ping/pong keepalive.
- Bars emitted by the WebSocket stream are published to `bars:{symbol}` topics on the EventBus.
- Output: vectorized DataFrames consumed by strategy modules.

### News & Sentiment Providers

The system consumes news APIs that already include sentiment values — no self-hosted LLM inference required for the base pipeline. A `NewsProvider` protocol defines the interface, and a pluggable registry (mirroring the broker adapter pattern) allows adding new providers with one file + one dict entry.

```python
from trading.core.enums import AssetClass
from trading.core.events import SentimentEvent

class NewsProvider(Protocol):
    """Every news/sentiment API adapter must implement this interface."""

    name: str
    asset_classes: list[AssetClass]
    rate_limit: RateLimit  # requests/day or requests/min

    async def get_sentiment(self, symbol: str) -> SentimentEvent | None: ...
```

**Provider implementations:**

| Provider | Free Tier | Asset Focus | Sentiment Output |
|---|---|---|---|
| Alpha Vantage | 25 req/day | Stocks, Crypto, Forex | Ticker-specific scores -1.0 to 1.0 via `NEWS_SENTIMENT` endpoint |
| Marketaux | 100 req/day | Global Stocks, Crypto | Entity-level impact & sentiment ratios |
| Finnhub | 30 req/min | US Equities | Company buzz & sector trends |
| StockGeist | Credit-based | US Equities | Real-time news + social sentiment streams |
| CachedNewsProvider | Unlimited | All | Canned payloads from YAML fixture (dev/backtest) |

Each real provider enforces its rate limit in code via a token-bucket limiter. The `CachedNewsProvider` is the default for development and backtesting — it returns canned `SentimentEvent` payloads from a YAML fixture with per-poll variation to mimic live flow. Config flag `sentiment.provider` switches between `cached` and any real provider.

**Sentiment Ingester service** (`services/sentiment_ingester.py`) is a long-running background task that:
1. Reads the active provider and symbol list from config
2. Polls the provider on a configurable schedule (cron-style interval per symbol)
3. Publishes `SentimentEvent` → `sentiment:{symbol}` topic on the EventBus
4. Persists every SentimentEvent to the `news_sentiment` TimescaleDB hypertable for traceability and backtest replay

The sentiment provider never produces a trade decision. It produces data that a strategy consumes.

## Layer 2: Strategy Orchestration & Evaluation

### The Orchestrator
- Central coordinator ("air traffic controller"). Communicates entirely through the EventBus — no direct method calls across modules.
- **Subscribes to:** `bars:{symbol}` (from LiveStream), `sentiment:{symbol}` (from Sentiment Ingester), `commands:*` (runtime control from CLI/external services), `fills:{symbol}` (from broker adapters for position reconciliation).
- **Publishes to:** `signals:{symbol}` (strategy output → risk), `orders:{symbol}` (approved orders → dispatcher), `risk_block:{symbol}` (blocked signals → monitoring).
- **BarBuffer:** maintains a rolling `deque` of recent bars per symbol, sized to max `lookback` across all loaded strategies. On cold start, fetches historical bars via adapter REST API to fill the buffer before live streaming begins. Strategies receive a full-history DataFrame (not a single row).
- Routes bars + sentiment to each loaded strategy via the bar buffer.
- Receives `SignalEvent` from strategy, passes to Risk Manager.
- If Risk Manager approves, emits `OrderEvent` to the Dispatcher.
- If Risk Manager rejects, emits `RiskBlockEvent` to monitoring.
- **Runtime control:** subscribes to `commands:*` topic. Handles `add_symbol`, `remove_symbol`, `add_strategy`, `remove_strategy`, `update_risk_rule` commands without restart.

### Strategy Modules
- Written as isolated plugins implementing an abstract `Strategy` base class.
- Registered in a strategy registry (`StrategyRegistry`).
- Initial strategies: `SMACrossoverStrategy`, `RSIMeanReversionStrategy`, `SentimentEnhancedStrategy`.
- Each strategy declares a **`lookback: int`** — the number of historical bars required to compute indicators. The Orchestrator allocates bar buffers sized to the maximum lookback across all loaded strategies.
- **Strategy signature:** `on_data(self, bars: pd.DataFrame, sentiment: SentimentEvent | None) -> SignalEvent | None` — strategies receive full bar history and the latest sentiment event (if any).
- Adding a new strategy: create a file, subclass `Strategy`, declare `lookback`, implement `on_data()`, register it. No other code changes.

### Risk Manager
- Sits between every strategy signal and the execution layer.
- Contains modular, independently-testable risk rules.
- Each rule returns pass/fail + reason.
- Rules:
  - Maximum drawdown per day
  - Maximum exposure per single asset (e.g., 5% of portfolio)
  - Correlation check (prevent buying 5 highly correlated assets)
  - Maximum daily trades
- Risk rules accept **runtime parameter updates** via `CommandEvent` (`update_risk_rule`) — e.g., change max drawdown threshold without restart.
- If any rule fails, the order is blocked and logged.

## Layer 3: Execution & Gateway

### Broker Protocol
- The rest of the stack never knows which broker it's talking to.
- All communication goes through the `BrokerProtocol` interface.
- Each broker adapter implements: `get_bars`, `get_account`, `get_positions`, `submit_order`, `cancel_order`, `stream_bars`, `get_market_hours`.
- A `PaperAdapter` logs orders to the database instead of calling any API.

### Dispatcher
- Routes `OrderEvent` to the correct broker adapter based on `asset_class` and config.
- Supports multiple active brokers simultaneously (e.g., Binance for crypto + Alpaca for equities).

## Data Storage

| Store | Content |
|---|---|
| TimescaleDB (hypertables) | OHLCV bars, tick data, `news_sentiment` scores |
| TimescaleDB (standard tables) | Orders, fills, positions, paper_orders, risk blocks, trade journal |
| Redis | Event bus (Pub/Sub), caching, session state |
| Parquet files (local) | Backtest results, exported data snapshots |

## Containerization

All runtime services run in Docker containers via `docker-compose.yml`:

| Service | Container | Purpose |
|---|---|---|
| `trading-engine` | App (`Dockerfile`) | Orchestrator + live stream + paper adapter |
| `sentiment-ingester` | App (`Dockerfile`, command override) | Polls NewsProvider, publishes SentimentEvents |
| `redis` | `redis:7-alpine` | Event bus (Pub/Sub) |
| `timescaledb` | `timescale/timescaledb` | OHLCV bars, sentiment, orders, fills |
| `prometheus` | `prom/prometheus` | Metrics scraping |
| `grafana` | `grafana/grafana` | Dashboards |
| `test-runner` (`--profile test`) | `Dockerfile.test` | Runs test suites |

Tests run in a dedicated `Dockerfile.test` container with dev dependencies installed. No separate mock-services containers — all mocks are in-process (fakeredis for Redis, respx for HTTP, mock WS server in pytest fixture).

## Testing Architecture

Two distinct test suites with clearly separated concerns:

- **`tests/infra/`** — Infrastructure plumbing tests. Verifies that events flow through the bus, adapters route correctly, repositories persist and retrieve, news providers parse API responses, rate limiters enforce quotas. Uses `fakeredis` and `respx`.
- **`tests/trading/`** — Trading activity simulation tests. Verifies that strategies fire the right signals on the right bar sequences, the orchestrator produces expected order/fill chains, the backtest engine reproduces known trade sequences on deterministic data, and multi-day paper-trade simulations produce realistic portfolio state. Uses synthetic price series and in-process mocks.

Both suites run inside the same `Dockerfile.test` container. Pytest markers (`@pytest.mark.infra`, `@pytest.mark.trading`) allow selective execution via `pytest -m infra` or `pytest -m trading`.

## Dry-Run Mode

`execution_mode: dry_run` is a first-class config. When active:
- The `PaperAdapter` intercepts all orders.
- Orders are written to a `paper_orders` table with simulated fill prices.
- No API call reaches any broker.
- All other components (data, strategy, risk, sentiment) run normally.

This enables full pipeline testing without money at risk.