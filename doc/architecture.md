# Architecture

## System Overview

The trading stack is structured as three distinct layers communicating through an asynchronous event bus. No layer directly calls another — all communication is through structured events.

```
+------------------------------------------------------------+
|                  1. Data & Identification                  |
|  (Technical Indicators, Social Sentiment, News Aggregators) |
+-----------------------------+------------------------------+
                              |
                              v  [Emits SignalEvent + SentimentEvent]
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
                 ┌──────────────────┐
                 │  Redis Pub/Sub   │
                 │   Event Bus      │
                 └──────┬───────────┘
                        │
          ┌─────────────┼─────────────┐
          │             │             │
          v             v             v
    ┌──────────┐  ┌──────────┐  ┌──────────┐
    │  Data    │  │ Strategy │  │   Risk   │
    │ Ingestion│  │   Engine │  │ Manager  │
    └────┬─────┘  └────┬─────┘  └────┬─────┘
         │             │             │
         │  BarEvent    │  SignalEvent│  ApprovedOrderEvent
         │  SentimentEvent          │
         │             │             │
         └─────────────┼─────────────┘
                       │
                       v
                ┌──────────────┐
                │  Dispatcher  │
                │  (routes by  │
                │  asset_class)│
                └──────┬───────┘
                       │
              ┌────────┼────────┐
              v        v        v
         ┌────────┐ ┌────────┐ ┌────────┐
         │Binance │ │ Alpaca │ │ Paper  │
         │Adapter │ │Adapter │ │Adapter │
         └────────┘ └────────┘ └────────┘
```

## Event Types

All events are typed Pydantic models carrying a correlation ID for end-to-end tracing.

| Event | Emitter | Consumer | Payload |
|---|---|---|---|
| `BarEvent` | Data Ingestion | Strategy, Indicators | symbol, timeframe, OHLCV, timestamp |
| `SignalEvent` | Strategy | Risk Manager | symbol, side, confidence, strategy_name, asset_class |
| `SentimentEvent` | Sentiment Pipeline | Strategy | symbol, score (-1 to 1), confidence, source |
| `OrderEvent` | Risk Manager (approved) | Dispatcher/Execution | symbol, side, quantity, order_type, broker |
| `FillEvent` | Broker Adapter | Portfolio, Risk, Monitoring | symbol, side, fill_price, quantity, fees, timestamp |
| `RiskBlockEvent` | Risk Manager (rejected) | Monitoring, Alerts | original_signal, reason, rule_that_blocked |

## Layer 1: Data & Identification

### Technical Analysis
- Use **pandas-ta** or **TA-Lib** (C++ with Python wrappers). Never write indicator math from scratch.
- Indicators are computed on bars fetched from TimescaleDB or streamed via WebSocket.
- Output: vectorized DataFrames consumed by strategy modules.

### Alternative Data & Sentiment
- **News:** RSS feeds, CryptoPanic API, CoinTelegraph — raw text passed to local LLM.
- **Social:** Reddit (r/cryptocurrency), X (Twitter) trending tickers — raw text passed to local LLM.
- **LLM Role:** A locally-running model (Ollama with quantized Llama 3 or Mistral) receives raw text and outputs structured JSON:
  ```json
  {
    "symbol": "BTC",
    "sentiment_score": 0.65,
    "confidence": 0.82,
    "source": "crypto_news",
    "summary": "Bitcoin ETF inflows surge..."
  }
  ```
- The LLM never produces a trade decision. It produces data that a strategy consumes.

## Layer 2: Strategy Orchestration & Evaluation

### The Orchestrator
- Central coordinator ("air traffic controller").
- Subscribes to `BarEvent` and `SentimentEvent` from the bus.
- Routes bars+sentiment to the active strategy.
- Receives `SignalEvent` from strategy, passes to Risk Manager.
- If Risk Manager approves, emits `OrderEvent` to the Dispatcher.
- If Risk Manager rejects, emits `RiskBlockEvent` to monitoring.

### Strategy Modules
- Written as isolated plugins implementing an abstract `Strategy` base class.
- Registered in a strategy registry (`StrategyRegistry`).
- Example: `SMACrossoverStrategy`, `SentimentEnhancedStrategy`.
- Adding a new strategy: create a file, subclass `Strategy`, register it. No other code changes.

### Risk Manager
- Sits between every strategy signal and the execution layer.
- Contains modular, independently-testable risk rules.
- Each rule returns pass/fail + reason.
- Hardcoded rules (not configurable without code review):
  - Maximum drawdown per day
  - Maximum exposure per single asset (e.g., 5% of portfolio)
  - Correlation check (prevent buying 5 highly correlated assets)
  - Maximum daily trades
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
| TimescaleDB (hypertables) | OHLCV bars, tick data, sentiment scores |
| TimescaleDB (standard tables) | Orders, fills, positions, risk blocks, trade journal |
| Redis | Event bus (Pub/Sub), caching, session state |
| Parquet files (local) | Backtest results, exported data snapshots |

## Dry-Run Mode

`execution_mode: dry_run` is a first-class config. When active:
- The `PaperAdapter` intercepts all orders.
- Orders are written to a `paper_orders` table with simulated fill prices.
- No API call reaches any broker.
- All other components (data, strategy, risk) run normally.

This enables full pipeline testing without money at risk.