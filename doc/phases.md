# Implementation Phases

## Phase 1 — Foundation & Backtesting (close gaps)

**Goal:** Run a backtested SMA crossover strategy on BTC/USDT historical data with a full metrics report. Prove the data pipeline, model layer, and backtesting engine work end-to-end. Backtesting must reflect realistic trading conditions — brokerage fees and slippage are applied so that a profitable backtest is meaningful, not just a paper win.

Mostly **DONE**. Remaining gaps before re-baselining on Phase 2:

| # | Item | Status | Remaining work |
|---|---|---|---|
| 1.G1 | Models, events, enums, config | ✅ | — |
| 1.G2 | Risk rules + manager | ✅ | — |
| 1.G3 | Paper adapter (slippage + commission) | ✅ | — |
| 1.G4 | Backtest brokerage/slippage/journal/metrics | ✅ | — |
| 1.G5 | `BacktestRunner.run()` | ✅ | Real bars from adapter, parametrized by strategy_name |
| 1.G6 | `TimescaleRepository.bulk_insert_bars()` | ✅ | asyncpg copy_records_to_table |
| 1.G7 | `BinanceAdapter.get_positions()` | ✅ | Single ticker price call, filters stablecoins |
| 1.G8 | Test coverage | ✅ | 57 tests (dispatcher, risk rules, paper adapter, binance adapter) |

**Exit criteria:**
- Run `./scripts/ticaret.sh backtest --strategy sma_crossover --symbol BTC/USDT --start 2020-01-01 --end 2025-01-01` and get a full metrics report with equity curve
- Backtest metrics include brokerage fees and slippage deducted from PnL
- Trade journal exported with per-trade details for manual chart verification
- Binance adapter fetches real data from API (REST path)
- Paper adapter simulates fills correctly
- All tests pass. `./scripts/ticaret.sh lint` and `./scripts/ticaret.sh check` pass

---

## Phase 2 — Event-Driven Live Pipeline + Multi-Provider Sentiment + 3 Strategies + Backtest Infra + Containerized Tests

**Goal:** The trading engine becomes a proper event-driven system. It subscribes to live WebSocket market data, maintains rolling bar buffers so strategies can compute indicators, listens on Redis Pub/Sub for signals and commands from other services, and can change symbols/strategies at runtime without restart. A pluggable multi-provider news/sentiment pipeline publishes `SentimentEvent`s through the event bus. Three strategies run live: SMA crossover, RSI mean-reversion, and sentiment-enhanced SMA. All runtime services and tests run in containers.

**Key architectural decisions:**
- **EventBus is the central nervous system** — the Orchestrator communicates entirely through Redis Pub/Sub topics. No direct method calls across modules
- **BarBuffer per symbol** — rolling `deque` per symbol, sized to max `lookback` across all loaded strategies. Cold-start fetches historical bars via adapter REST before live streaming begins
- **Runtime dynamic control** — external services (or a CLI) publish `CommandEvent`s to `commands:*` to add/remove symbols and strategies without restarting
- **Pluggable news/sentiment providers** — `NewsProvider` protocol with registry. Alpha Vantage, Marketaux, Finnhub, StockGeist implementations. Swap providers via config flag. CachedNewsProvider for dev/backtest
- **All code runs in containers** — `docker compose up` runs the full system. `docker compose --profile test up` runs the test container. No mock-services containers; tests use in-process mocks (fakeredis, respx, mock WS fixtures)
- **Two distinct test suites** — `tests/infra/` (pipeline plumbing: bus, adapters, repository, news providers) and `tests/trading/` (strategy correctness, paper-trade simulation, backtest engine). Both run in a `Dockerfile.test` container

**Time estimate:** ~60h total (expanded from ~44h to include stop losses, quality filters, regime detection, exit management, and rigorous backtesting). Accepts it slips past a single weekend into weekday evenings. No scope cut.

### 2.A — EventBus hardening ✅

| Step | Deliverable | Key Details |
|---|---|---|
| 2.A.1 | SentimentEvent + CommandEvent in bus deser map | Confirm `SentimentEvent` in `bus.py` deserialization map; add `CommandEvent` type. Topic conventions: `bars:{symbol}`, `signals:{symbol}`, `orders:{symbol}`, `fills:{symbol}`, `sentiment:{symbol}`, `commands:*`, `risk_block:{symbol}` |
| 2.A.2 | Correlation IDs on all events | All events carry `correlation_id` (add envelope if missing) |
| 2.A.3 | Event schema versioning | Add `_event_schema_version: int = 1` to `BaseEvent` (forward-compat for sentiment V2) |
| 2.A.4 | Infra tests for EventBus | `tests/infra/test_bus.py` — pub/sub round-trip per event type, dead-letter on bad payload, schema-version mismatch handling |

### 2.B — BarBuffer & cold-start ✅

| Step | Deliverable | Key Details |
|---|---|---|
| 2.B.1 | `orchestration/bar_buffer.py` | New component — rolling `deque` per symbol, max-size = max(strategy.lookback) across loaded strategies. `add(symbol, bar) -> pd.DataFrame` returns full window |
| 2.B.2 | Cold-start hook | Empty buffer → fetch N historical bars via `adapter.get_bars()` before live stream begins |
| 2.B.3 | Infra tests | `tests/infra/test_bar_buffer.py` — fill/eviction, DataFrame shape, cold-start fetch mocked |

### 2.C — Commands & runtime control ✅

| Step | Deliverable | Key Details |
|---|---|---|
| 2.C.1 | `orchestration/commands.py` | New component — `CommandEvent` model + handlers: `add_symbol`, `remove_symbol`, `add_strategy`, `remove_strategy`, `update_risk_rule` |
| 2.C.2 | Orchestrator subscribes to `commands:*` | Dispatches runtime control actions. Risk rules accept runtime parameter updates via `update_risk_rule` |
| 2.C.3 | Infra tests | `tests/infra/test_commands.py` — publish `add_symbol` over fakeredis → orchestrator state changes |

### 2.D — Orchestrator rewrite (bus-driven) ✅

| Step | Deliverable | Key Details |
|---|---|---|
| 2.D.1 | Subscribe to `bars:{symbol}` | `BarBuffer.add()` → full-history DataFrame per strategy |
| 2.D.2 | Subscribe to `sentiment:{symbol}` | Passes `sentiment: SentimentEvent \| None` into `strategy.on_data()` (signature change in 2.E.1) |
| 2.D.3 | Publish signals/orders | `SignalEvent` → `signals:{symbol}`; risk pass → `OrderEvent` → `orders:{symbol}`; risk block → `RiskBlockEvent` → `risk_block:{symbol}` |
| 2.D.4 | Subscribe to `fills:{symbol}` | Reconcile positions against `PaperAdapter` |
| 2.D.5 | Trading tests | `tests/trading/test_orchestrator.py` — replay synthetic bars → assert signal/order/fill sequence with deterministic strategies |

### 2.E — Stop losses, position sizing & strategy signature change (~5h)

**Goal:** Every signal carries a stop loss. Position size is risk-based, not confidence-based. The strategy signature is updated to accept sentiment. The SMA crossover strategy is enhanced with ATR-based stops. This is the foundation of quality-over-quantity trading.

| Step | Deliverable | Key Details |
|---|---|---|
| 2.E.1 | Add stop-loss fields to `SignalEvent` | `stop_loss_price: float`, `entry_price: float`, `take_profit_price: float \| None = None`. All three are set by the strategy at signal generation time. A signal without `stop_loss_price` is rejected by the risk manager. |
| 2.E.2 | Risk-based position sizing in orchestrator | Replace `quantity = max(1.0, confidence * 100)` with `qty = (portfolio_value * risk_per_trade) / abs(entry_price - stop_loss_price)`. Default `risk_per_trade = 0.01` (1% of portfolio). Config-driven. |
| 2.E.3 | New `Strategy.on_data()` signature | `on_data(self, bars: pd.DataFrame, sentiment: SentimentEvent \| None) -> SignalEvent \| None` |
| 2.E.4 | Update `sma_crossover.py` | Accept new signature. Compute ATR(14) on the bar history. Set `stop_loss_price = entry_price - 2 * ATR` for BUY signals (mirror for SELL). Set `take_profit_price = entry_price + 4 * ATR` (2:1 R:R). Ignore sentiment for now. |
| 2.E.5 | Stop-loss validation risk rule | New `StopLossValidationRule`: rejects any SignalEvent where `stop_loss_price` is missing, NaN, or on the wrong side of `entry_price`. This is a hard rule — no signal reaches execution without a valid stop. |
| 2.E.6 | Trading tests | `tests/trading/test_strategy_sma.py` — assert SignalEvent has `stop_loss_price` set, stop is below entry for BUY, stop is above entry for SELL, ATR-based stop distance is reasonable. `tests/trading/test_position_sizing.py` — assert qty is calculated from risk amount and stop distance, not from confidence. |

### 2.F — Quality filters & market regime filter (~5h)

**Goal:** Strategies don't fire on every signal — they fire only when quality conditions are met. A market regime filter halts all new entries during extreme volatility or deep drawdowns. "No trade on a bloodbath day" is enforced in code.

| Step | Deliverable | Key Details |
|---|---|---|
| 2.F.1 | `strategy/filters.py` | Post-signal filter framework. Chainable filters that each return pass/fail. A signal that fails any filter is suppressed (never published to `signals:*`). Filters are strategy-agnostic and composable. |
| 2.F.2 | `TrendAlignmentFilter` | Only allow BUY signals when price is above a higher-timeframe SMA (e.g., 200 SMA). Only allow SELL signals when below. Prevents counter-trend entries. |
| 2.F.3 | `VolumeConfirmationFilter` | Require signal bar volume > N-day average volume (e.g., 1.5x 20-day average). Filters out low-conviction signals. |
| 2.F.4 | `CongestionZoneFilter` | Skip signals when recent bars are in a tight sideways range (e.g., ATR/close < 1%). Breakouts from congestion are allowed; signals inside congestion are suppressed. |
| 2.F.5 | `MinCandleBodyFilter` | Require the signal candle to have a minimum body size relative to its range (e.g., body > 50% of range). Filters out doji/inside bars. |
| 2.F.6 | `risk/regime_filter.py` | Market regime filter that runs before risk rules. Uses ATR% and ADX to classify market state. If ATR/close > threshold (e.g., 5%), suppress all new entries. If ADX < 20, suppress trend-following strategies. Configurable per strategy. |
| 2.F.7 | `DailyDrawdownCircuitBreaker` | Risk rule that tracks intraday portfolio drawdown. If drawdown exceeds daily limit (e.g., -2%), halt all new entries for the rest of the day. Existing positions are still managed by the exit manager (stops still execute). Resets at market open (crypto: UTC midnight). |
| 2.F.8 | Wire filters into orchestrator | Orchestrator runs quality filters after strategy returns a signal. If any filter fails, signal is suppressed (not published). If filters pass, signal is published to `signals:{symbol}` and then checked by risk manager (which includes regime filter + circuit breaker). |
| 2.F.9 | Trading tests | `tests/trading/test_filters.py` — each filter tested independently with synthetic data. `tests/trading/test_regime_filter.py` — high-volatility regime suppresses entries, low-volatility allows. `tests/trading/test_circuit_breaker.py` — drawdown > limit halts new entries, stops still execute. |

### 2.G — Exit management: trailing stops, take-profit, time-based exits (~4h)

**Goal:** Once a position is open, the exit manager monitors every bar and mechanically executes exits. No strategy involvement — exits are non-negotiable. This is the other half of quality trading: entries are rare, exits are disciplined.

| Step | Deliverable | Key Details |
|---|---|---|
| 2.G.1 | `orchestration/exit_manager.py` | New component. Subscribes to `bars:{symbol}` and `fills:{symbol}`. Maintains a registry of open positions with their stop/take-profit/trailing parameters. On each bar, checks if any position's exit conditions are met. |
| 2.G.2 | Stop-loss execution | If price breaches `stop_loss_price`, immediately emit SELL `OrderEvent` to `orders:{symbol}`. No strategy consultation — mechanical execution. |
| 2.G.3 | Trailing stop | As price moves in favor, ratchet the stop tighter. Configurable method: ATR-based (`stop = price - N * ATR`) or percentage-based (`stop = price * (1 - trail_pct)`). Only ratchets in the favorable direction — never loosens the stop. |
| 2.G.4 | Take-profit execution | If price reaches `take_profit_price`, emit SELL `OrderEvent`. |
| 2.G.5 | Time-based exit | If a position has been open for N bars (configurable, e.g., 20 bars) without hitting stop or take-profit, close it. Prevents dead capital in stagnant positions. |
| 2.G.6 | Wire into orchestrator | Orchestrator creates the ExitManager on start. When a FillEvent arrives (from `fills:{symbol}`), the exit manager registers the position. On each BarEvent, the exit manager checks all open positions. |
| 2.G.7 | Trading tests | `tests/trading/test_exit_manager.py` — stop-loss hit → SELL order emitted. Trailing stop ratchets correctly. Take-profit hit → SELL order emitted. Time-based exit after N bars. Stop never loosens. |

### 2.H — WebSocket feed infrastructure: universal feed + feed handlers (~8h)

**Goal:** Build a modular WebSocket feed connection that can handle any WebSocket data feed — not just Binance. The feed manages connection lifecycle (connect, reconnect, ping/pong, backoff) while feed-specific logic (URL construction, message parsing, subscribe framing) is delegated to pluggable handlers. Adding a new exchange's WebSocket feed = one handler file + one registry entry, same pattern as `BrokerProtocol` and `NewsProvider`.

**Architecture:**
```
LiveStream  →  WebSocketFeed  →  FeedHandler (Protocol)
                                ├── BinanceFeedHandler
                                ├── CoinbaseFeedHandler (future)
                                └── KrakenFeedHandler (future)
```

The feed is universal — it has zero knowledge of any specific exchange. The handler knows the exchange's WS URL format, message structure, and subscription protocol.

| Step | Deliverable | Key Details |
|---|---|---|
| 2.H.1 | `data/feeds/base.py` | `FeedHandler` Protocol: `build_url(symbols, timeframe) -> str`, `parse_message(raw) -> Bar \| None`, `build_subscribe(symbols) -> str \| None`, `build_unsubscribe(symbols) -> str \| None`, `is_closed_message(raw) -> bool`. `FEED_HANDLER_REGISTRY` dict for plugin registration. |
| 2.H.2 | `data/feeds/feed.py` | `WebSocketFeed` — universal async generator. Takes a `FeedHandler`, manages connection via `websockets` library. Exponential backoff (1s → 2s → 4s → … → 60s max). Ping/pong keepalive via `ping_interval=20`. Yields `Bar` objects from `handler.parse_message()`. Zero knowledge of any specific exchange. |
| 2.H.3 | `data/feeds/binance.py` | `BinanceFeedHandler` — implements `FeedHandler`. Builds Binance kline WS URLs (`wss://stream.binance.com:9443/ws/{stream}`), parses kline messages into `Bar` objects, maps Binance symbols (BTCUSDT → BTC/USDT). URL-based subscription (no control frames needed). Registered in `FEED_HANDLER_REGISTRY`. |
| 2.H.4 | `data/feeds/__init__.py` | `FEED_HANDLER_REGISTRY: dict[str, type[FeedHandler]]` — same pattern as `ADAPTER_REGISTRY`. Adding a new feed = one file + one dict entry. |
| 2.H.5 | Refactor `BinanceAdapter.stream_bars()` | Delegate to `WebSocketFeed` with `BinanceFeedHandler`. The adapter no longer contains WS connection logic — it just creates a feed + handler and yields from `feed.stream()`. |
| 2.H.6 | `data/live_stream.py` refactor | `LiveStream` wraps the feed. Async generator iteration with task-based run loop. Emits `BarEvent` → `bars:{symbol}`. Error-tolerant `_run()` with auto-restart. Dynamic `add_symbol()` / `remove_symbol()` (triggers feed resubscription). |
| 2.H.7 | Interface change | `AbstractBrokerAdapter.stream_bars()` and `BrokerProtocol.stream_bars()` changed from sync `Generator` to `AsyncGenerator`. `PaperAdapter` updated. |
| 2.H.8 | Infra tests | `tests/infra/test_binance_ws.py` — mock WS server via `websockets.serve()`, test bar yield, symbol parsing, multiple bars. `tests/infra/test_ws_feed.py` — test feed delegation logic with mock handler, verify handler calls. |

### 2.I — Sentiment pipeline: pluggable multi-provider news (~7h)

**Goal:** Sentiment scores flow through the event bus and influence strategy decisions. News APIs that already include sentiment values are consumed via a pluggable provider protocol. All sentiment data is traceable and logged to TimescaleDB.

**Provider comparison:**

| Provider | Free Tier Limit | Primary Asset Focus | Sentiment Granularity |
|---|---|---|---|
| Alpha Vantage | 25 requests / day | Stocks, Crypto, Forex | Ticker-specific scores (-1.0 to 1.0) |
| Marketaux | 100 requests / day | Global Stocks, Crypto | Entity-level impact & sentiment ratios |
| Finnhub | 30 requests / minute | US Equities | Aggregated company buzz & sector trends |
| StockGeist | Credit-based | US Equities | Real-time news + social sentiment streams |

| Step | Deliverable | Key Details |
|---|---|---|
| 2.G.1 | `data/news/base.py` | `NewsProvider` Protocol: `async get_sentiment(symbol: str) -> SentimentEvent \| None`, `name: str`, `asset_classes: list[AssetClass]`, `rate_limit: RateLimit` |
| 2.G.2 | `data/news/registry.py` | Plugin registry mirroring adapter registry dict. Adding a news API = one file + dict entry |
| 2.G.3 | `data/news/alpha_vantage.py` | AV `NEWS_SENTIMENT` endpoint, ticker-specific score -1.0..1.0, parses `overall_sentiment_score` + `ticker_sentiment[]`. Free tier 25/day → token-bucket rate limiter in code, raises above quota |
| 2.G.4 | `data/news/marketaux.py` | Marketaux free tier 100/day, global stocks/crypto, entity-level impact + sentiment ratios, token-bucket limiter |
| 2.G.5 | `data/news/finnhub.py` | Finnhub free 30/min, US equities, company buzz + sector trends, token-bucket limiter |
| 2.G.6 | `data/news/stockgeist.py` | StockGeist credit-based, US equities news + social sentiment streams. Stub if API shape needs confirmation |
| 2.G.7 | `data/news/cached.py` | `CachedNewsProvider` returns canned `SentimentEvent` from YAML fixture with per-poll variation to mimic live flow. **Default for weekend runs**. Config flag `sentiment.provider: cached \| alpha_vantage \| marketaux \| finnhub \| stockgeist` |
| 2.G.8 | `services/sentiment_ingester.py` | Long-running task calls provider on schedule (cron-style interval per symbol from config) and publishes `SentimentEvent` → `sentiment:{symbol}`. Runs in its own container |
| 2.G.9 | `data/sentiment_repository.py` | Writes every SentimentEvent to `news_sentiment` TimescaleDB hypertable for traceability + backtest replay |
| 2.G.10 | Config: `sentiment:` block | YAML section — `provider`, `poll_interval_seconds`, `symbols`, per-provider api_key env-var refs |
| 2.G.11 | Infra tests | `tests/infra/test_alpha_vantage.py`, `test_marketaux.py`, `test_finnhub.py`, `test_stockgeist.py`, `test_news_registry.py`, `test_sentiment_repository.py`, `test_cached_provider.py` — all real providers use `respx` mocked HTTP; assert payload parsing + rate-limit raising |
| 2.G.12 | Trading tests | `tests/trading/test_sentiment_flow.py` — publish SentimentEvent → orchestrator → sentiment-enhanced strategy receives it |

### 2.J — Second strategy: RSI mean-reversion + third strategy: sentiment-enhanced SMA (~4h)

| Step | Deliverable | Key Details |
|---|---|---|
| 2.J.1 | `strategy/rsi_mean_reversion.py` | RSI <30 buy / >70 sell. `lookback = rsi_period + 5`. Stop loss = recent swing low (for BUY) or swing high (for SELL). Take-profit at 2:1 R:R. Only fires in ranging regime (ADX < 25) — regime filter enforces this. |
| 2.J.2 | `strategy/sentiment_enhanced.py` | SMA crossover core with ATR stops (same as 2.E.4). Signal suppressed when `sentiment.score < min_sentiment` AND `confidence < min_confidence`. Config: `min_confidence = 0.6`, `min_sentiment = -0.2`. All quality filters from 2.F apply. |
| 2.J.3 | Trading tests | `tests/trading/test_strategy_rsi.py` — oversold/overbought/neutral, stop loss set correctly, regime filter suppresses in trending market. `tests/trading/test_strategy_sentiment.py` — buy+bullish passes, buy+bearish-below-threshold suppressed, neutral acts like SMA baseline. |

### 2.K — Rigorous backtest infrastructure (~7h)

**Goal:** Backtesting is not a single run — it's a disciplined evaluation across multiple market regimes, time periods, and out-of-sample data. A strategy that looks good on a full-period backtest but fails walk-forward is rejected. No strategy goes to paper trading until it passes all backtest gates.

| Step | Deliverable | Key Details |
|---|---|---|
| 2.K.1 | Refactor `BacktestRunner` | Accept `(strategy_name, symbol, start, end, source)`. Supports `--source adapter` and `--source db`. Uses same `BarBuffer → strategy.on_data()` contract as live. Quality filters and regime filter run during backtest (same as live). Exit manager runs during backtest (stops, trailing, take-profit, time-based). |
| 2.K.2 | Walk-forward analysis | `backtest/walk_forward.py` — splits data into in-sample and out-of-sample windows (e.g., 12 months in-sample, 3 months out-of-sample, rolling). Runs strategy on each window. Reports per-window metrics. A strategy that performs well in-sample but poorly out-of-sample is overfit and rejected. |
| 2.K.3 | Regime-aware evaluation | `backtest/regime_report.py` — classifies each bar into regime (trending/ranging/volatile) and reports strategy performance per regime. A trend-following strategy that loses money in ranging markets is expected; one that loses in trending markets is broken. |
| 2.K.4 | MAE/MFE analysis | `backtest/excursion.py` — Maximum Adverse Excursion (worst drawdown during each trade before exit) and Maximum Favorable Excursion (best profit before exit). Shows whether stops are too tight (MAE > stop distance frequently) or too loose (MAE much larger than final profit). |
| 2.K.5 | Stop-loss hit rate | `backtest/stop_analysis.py` — reports how often stops are hit vs. take-profit, average hold time, distribution of R:R realized. A strategy with 90% stop-hit rate and 10% take-profit is not viable unless the R:R is extreme. |
| 2.K.6 | Sentiment replay | Backtest supports optional `SentimentEvent` replay from `news_sentiment` table so sentiment-enhanced strategy can be backtested. |
| 2.K.7 | `seed_historical_data.py` | Updated to use `bulk_insert_bars()` for the `--source db` path. |
| 2.K.8 | CLI | `backtest` command: `--strategy`, `--source adapter\|db`, `--walk-forward` (runs walk-forward analysis), `--regime-report` (per-regime breakdown). |
| 2.K.9 | Trading tests | `tests/trading/test_backtest_runner.py` — known price series → expected trade sequence for SMA, RSI, Sentiment-enhanced; both `--source` paths. `tests/trading/test_walk_forward.py` — synthetic data split into windows, verify per-window metrics. `tests/trading/test_exit_in_backtest.py` — stop-loss and take-profit execute during backtest. |

### 2.L — Containerize runtime + test profile (~4h)

| Step | Deliverable | Key Details |
|---|---|---|
| 2.L.1 | `Dockerfile.test` | New — installs `[dependency-groups] dev`, runs `ruff`, `mypy`, then `pytest` |
| 2.L.2 | `sentiment-ingester` service | docker-compose service (image reuse, command override `sentiment-ingest --config ...`), depends on Redis + Timescale |
| 2.L.3 | `test` profile in docker-compose | `test-runner` builds `Dockerfile.test`, mounts source, runs pytest. Depends on Redis + Timescale. In-process mocks only for broker HTTP/WS — no mock-services containers |
| 2.L.4 | `.dockerignore` | Exclude `.venv`, `.mypy_cache`, `.ruff_cache`, `.pytest_cache`, `*.egg-info` |
| 2.L.5 | Test CLI scripts | `scripts/ticaret.sh test-infra` / `test-trading` invoke the test container with the correct `tests/<root>` filter + marker |
| 2.L.6 | Healthcheck | `trading-engine` healthcheck → real `httpx` probe against `/metrics` endpoint (replace `import trading`) |

### 2.M — Test suite split + tests written (~7h)

Two distinct test suites with clearly separated concerns:

- **`tests/infra/`** — tests the infrastructure plumbing: event bus, bar buffer, commands, dispatcher routing, repository, news providers (mocked HTTP), paper adapter fill math, binance WS fixture. Uses `fakeredis` and `respx`.
- **`tests/trading/`** — tests trading activity simulation: strategy correctness, orchestrator replay → expected fills, backtest engine on deterministic series, paper-trade multi-day simulation. Strategies run against synthetic price data and assert expected trade sequences.

| Step | Deliverable | Key Details |
|---|---|---|
| 2.M.1 | Reorganize existing tests | Move into `tests/infra/` (config, models, events, market_hours, dispatcher, adapter plumbing, repository, news providers) and `tests/trading/` (strategy behavior, paper fill sim, signal accuracy, orchestrator replay, backtest engine, paper-trade multi-day simulation, exit management, regime filter, walk-forward) |
| 2.M.2 | `tests/infra/` suite | Bus, bar_buffer, commands, dispatcher routing, repository (incl `bulk_insert_bars`), alpha_vantage/marketaux/finnhub/stockgeist (respx-mocked HTTP), news_registry, sentiment_repository, cached_provider, paper_adapter fill math, binance WS fixture |
| 2.M.3 | `tests/trading/` suite | Strategy correctness (SMA/RSI/Sentiment) with stop losses, quality filters, orchestrator replay → expected fills, exit manager (stop/trailing/take-profit/time), regime filter, circuit breaker, backtest engine on deterministic series (both sources), walk-forward analysis, MAE/MFE analysis |
| 2.M.4 | Pytest markers | `pyproject.toml` `pytest.ini_options`: `markers = ["infra", "trading"]`; each test decorated so `pytest -m infra` / `pytest -m trading` selects cleanly inside one container invocation |

**Exit criteria:**
- `docker compose --profile test up --abort-on-container-exit` passes `tests/infra` + `tests/trading` inside the test container (in-process mocks only — no mock-services containers)
- `docker compose up` runs: `trading-engine` (orchestrator + live_stream + paper + exit_manager), `sentiment-ingester` (CachedNewsProvider on schedule, real providers ready to flip), Redis, Timescale, Prometheus, Grafana
- 3 strategies loaded; `./scripts/ticaret.sh add-symbol ETH/USDT` adds at runtime via Redis command
- **Every SignalEvent carries `stop_loss_price` and `entry_price`** — no signal without a stop reaches execution
- **Position sizing is risk-based** — every trade risks the same dollar amount (default 1% of portfolio)
- **Quality filters active** — trend alignment, volume confirmation, congestion exclusion, candle body filter all chainable and enforced
- **Market regime filter active** — high-volatility periods suppress new entries; daily drawdown circuit breaker halts trading on bad days
- **Exit manager active** — stop losses, trailing stops, take-profit, and time-based exits all execute mechanically on every bar
- `SentimentEvent` visible on `sentiment:BTC/USDT` topic; sentiment-enhanced strategy suppresses trades per threshold
- Grafana shows PnL, drawdown, order flow, sentiment panels, **stop-loss hit rate**, **regime classification**
- **Backtest with walk-forward analysis passes** for all 3 strategies — no strategy goes to paper trading unless out-of-sample performance is acceptable
- **MAE/MFE analysis available** — stop placement validated against actual adverse/favorable excursion
- Config flag `sentiment.provider` flips to real `alpha_vantage` / `marketaux` / `finnhub` / `stockgeist` for post-weekend debug; quota/rate-limits enforced in code per provider
- Paper-trade on Binance testnet with dynamic symbol/strategy changes via Redis commands
- System recovers from network drops and WebSocket disconnections
- All events logged with correlation IDs
- Discord alerts fire on risk breaches, stop-loss executions, and system errors

---

## Phase 3 — Live Micro-Trading, Alpaca & Hardening (ongoing)

**Goal:** System trades live with real money (tiny position sizes) on Binance. Alpaca adapter enables simultaneous equity paper trading. System runs unattended for weeks. Slippage and fees match paper trading within tolerance. Quality filters, stop losses, and regime detection from Phase 2 are active — this phase adds real-money execution and the human review loop.

| Step | Deliverable | Key Details |
|---|---|---|
| 3.1 | Binance adapter → live mode | Config change: `mode: live`, `paper: false`. Tiny capital ($50-100) |
| 3.2 | `execution/adapters/alpaca.py` | Alpaca REST + WebSocket adapter. Paper trading first. NYSE market hours. PDT rule awareness |
| 3.3 | Health monitoring & self-healing | Auto-reconnect on WebSocket drops. Stale data detection (no bar for > 60s triggers alert) |
| 3.4 | Dead-letter queue | Failed orders land in `failed_orders` table. Manual review or automatic retry |
| 3.5 | Position reconciliation | On startup, sync local state with broker state. Detect drift |
| 3.6 | Slippage & fee tracking | Real vs. expected fill comparison. Alert if slippage exceeds threshold. Validates that the brokerage/slippage models from Phase 1 match real execution within 5% |
| 3.7 | Win/loss trade journal | Every trade logged: strategy name, signal source, sentiment at entry, risk rule verdicts, entry/exit price, stop price, slippage, brokerage cost, MAE, MFE, hold time, R:R realized |
| 3.8 | Trade quality review pipeline | Manual chart review of trade journal exports from backtests and paper trading. Identify trades that passed code filters but are not valid setups on the chart → add new filter rules to `strategy/filters.py`. ~2-3 days per strategy. Key insight: code doesn't see the chart like a human does — many false positives slip through. Each filter iteration removes bad trades, shrinking the trade set but improving signal quality. The goal is not more trades, it's fewer but better trades |
| 3.9 | Additional quality filters | Post-Phase-2 filter additions based on live observation: news blackout windows refined, volume thresholds tuned, spread/liquidity filters calibrated to real market conditions. ~0.5 day per filter rule |

**Dual-broker flow during Phase 3:**
```
Crypto Signal  → Orchestrator → Risk → Dispatcher → Binance (live, tiny capital)
Equity Signal  → Orchestrator → Risk → Dispatcher → Alpaca (paper)
```

**Exit Criteria:**
- System trades live on Binance with real money, tiny position sizes
- Drawdown stays within hard limits for multiple weeks
- Alpaca paper trading for equities runs simultaneously
- Slippage and fees match paper trading within 5%
- All trades appear in the trade journal with full provenance
- Trade journal reviewed manually — false-positive trades identified and filter rules added
- Strategy backtests re-run with filters show improved win-rate and fewer but higher-quality trades
- Discord alerts work for both crypto and equity channels

---

## Phase 4 — PyO3 Performance Kernel (Conditional)

**Goal:** Only executed if profiling shows Python bottlenecks in backtesting or indicator computation. This phase is triggered, not scheduled.

| Step | Deliverable | Key Details |
|---|---|---|
| 4.1 | Profile hot paths | `py-spy` or `cProfile` to identify bottlenecks. Likely: backtest loop, batch indicator calc, risk VaR |
| 4.2 | `rust_kernel::backtest` | Port backtest simulation core to Rust. Takes numpy arrays via PyO3, returns equity curve. Target: > 10x speedup |
| 4.3 | `rust_kernel::indicators` | Port batch indicator computation to Rust. Same inputs, same outputs, faster execution |
| 4.4 | `rust_kernel::risk` | Port Monte Carlo VaR simulation to Rust (if needed) |
| 4.5 | Config-based toggle | `use_rust_backtester: true` in config → imports from `rust_kernel` instead of Python. Zero code changes elsewhere |
| 4.6 | Benchmark & validate | Rust and Python implementations produce identical results. Fuzz-tested |

**What stays in Python forever:**
- Orchestration, event bus, CLI, all I/O (API calls, WebSocket streaming, DB access)
- Strategy logic (should be quick to write and iterate on)
- Configuration, monitoring, alerting
- Sentiment pipeline (news provider HTTP calls, sentiment parsing)

**Exit Criteria:**
- `rust_kernel` produces identical results to Python implementations
- Backtest runs > 10x faster on large datasets
- All existing tests pass with Rust kernel enabled
- Toggle between Python and Rust via config flag