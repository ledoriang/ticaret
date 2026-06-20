# Architecture

## System Overview

The trading stack is structured as four distinct layers communicating through an asynchronous event bus. No layer directly calls another — all communication is through structured events. The system is designed around **quality over quantity**: no trade is better than a bad trade, and the system will sit idle for days rather than trade in unfavorable conditions.

```
+------------------------------------------------------------+
|                  1. Data & Identification                  |
|  (Technical Indicators, News Providers, Sentiment Scores)  |
+-----------------------------+------------------------------+
                              |
                              v  [Emits BarEvent + SentimentEvent]
+------------------------------------------------------------+
|             2. Strategy & Signal Generation                |
|  (Strategies, Quality Filters, Stop-Loss Calculation)      |
+-----------------------------+------------------------------+
                              |
                              v  [Emits SignalEvent with stop_loss_price]
+------------------------------------------------------------+
|             3. Risk & Position Management                  |
|  (Regime Filter, Position Sizing, Risk Rules, Exits)       |
+-----------------------------+------------------------------+
                              |
                              v  [Emits OrderEvent (if risk passes)]
+------------------------------------------------------------+
|                  4. Execution & Gateway                    |
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
| `SignalEvent` | Strategy (via Orchestrator) | Risk Manager | symbol, side, confidence, strategy_name, asset_class, **stop_loss_price**, **take_profit_price**, **entry_price** |
| `SentimentEvent` | Sentiment Ingester (NewsProvider) | Orchestrator → Strategy | symbol, score (-1 to 1), confidence, source, provider_name |
| `OrderEvent` | Risk Manager (approved) | Dispatcher/Execution | symbol, side, quantity, order_type, broker, **stop_price**, **price** |
| `FillEvent` | Broker Adapter | Portfolio, Risk, Monitoring, **Exit Manager** | symbol, side, fill_price, quantity, fees, timestamp |
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
- **Every SignalEvent MUST include `stop_loss_price` and `entry_price`.** A signal without a stop loss is rejected by the risk manager. The strategy computes the stop based on recent volatility (ATR) or structure (recent swing low/high).
- **Optional `take_profit_price`**: strategies may set a take-profit target based on a target risk:reward ratio (default 2:1).
- **Quality filters** (`strategy/filters.py`): each strategy chains quality checks before emitting a signal. A signal that fails any filter is suppressed (not emitted). Filters include:
  - Minimum trend alignment (e.g., only buy when price is above 200 SMA)
  - Volume confirmation (require above-average volume on signal bar)
  - Congestion zone exclusion (skip signals in tight sideways ranges)
  - Minimum candle body size (avoid doji/inside bars)
  - News blackout windows (don't enter within X minutes of scheduled news)
  - Spread/liquidity check (skip illiquid symbols)
- Adding a new strategy: create a file, subclass `Strategy`, declare `lookback`, implement `on_data()`, register it. No other code changes.

### Market Regime Filter
- Sits between the strategy output and the risk manager. Runs BEFORE risk rules are evaluated.
- Checks whether the current market regime is tradeable for the given strategy.
- **Volatility guard**: if ATR% is above a threshold (e.g., ATR/close > 5%), suppress all new entries — market is too chaotic.
- **Drawdown circuit breaker**: if portfolio drawdown exceeds a daily limit (e.g., -2% intraday), halt all new entries for the rest of the day. Existing positions are managed by the exit manager (stop losses still execute).
- **Trend regime detection**: using ADX or higher-timeframe SMA slope, classify the market as trending or ranging. Trend-following strategies (SMA crossover) only fire in trending regimes; mean-reversion strategies (RSI) only fire in ranging regimes.
- The regime filter is strategy-aware: each strategy declares which regimes it trades in.

### Risk Manager
- Sits between every strategy signal and the execution layer.
- Contains modular, independently-testable risk rules.
- Each rule returns pass/fail + reason.
- **Hard rules** (not configurable without code review):
  - Maximum drawdown per day (e.g., -2% intraday → halt new entries)
  - Maximum exposure per single asset (e.g., 5% of portfolio)
  - Correlation check (prevent buying 5 highly correlated assets)
  - Maximum daily trades (low number — e.g., 3 per day, not 30)
  - **Stop-loss validation**: every SignalEvent must have `stop_loss_price` set and it must be on the correct side of `entry_price` (below for longs, above for shorts)
- **Position sizing**: calculated from risk, not from signal confidence:
  ```
  risk_amount = portfolio_value * risk_per_trade  (default 1%)
  stop_distance = abs(entry_price - stop_loss_price)
  quantity = risk_amount / stop_distance
  ```
  This ensures every trade risks the same dollar amount regardless of asset price or volatility.
- Risk rules accept **runtime parameter updates** via `CommandEvent` (`update_risk_rule`) — e.g., change max drawdown threshold without restart.
- If any rule fails, the order is blocked and logged.

### Exit Manager
- Monitors open positions on every incoming `BarEvent`.
- **Stop-loss execution**: if price breaches `stop_loss_price`, immediately emits a SELL `OrderEvent` to `orders:{symbol}`. No strategy involvement — stops are mechanical.
- **Trailing stop**: as price moves in favor, the stop is ratcheted tighter. Configurable trailing method:
  - ATR-based: `stop = current_price - N * ATR` (e.g., 2x ATR trail)
  - Percentage-based: `stop = current_price * (1 - trail_pct)`
- **Take-profit**: if price reaches `take_profit_price`, emits a SELL `OrderEvent`.
- **Time-based exit**: if a position has been open for N bars without hitting stop or take-profit, close it. Prevents dead capital in stagnant positions.
- **Exit events** are published to `fills:{symbol}` after execution, same as normal fills.
- The exit manager subscribes to `bars:{symbol}` and maintains a registry of open positions with their stop/take-profit/trailing parameters.

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