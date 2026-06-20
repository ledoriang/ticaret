# Implementation Phases

## Phase 1 — Foundation & Backtesting (close gaps)

**Goal:** Run a backtested SMA crossover strategy on BTC/USDT historical data with a full metrics report. Prove the data pipeline, model layer, and backtesting engine work end-to-end. Backtesting must reflect realistic trading conditions — brokerage fees and slippage are applied so that a profitable backtest is meaningful, not just a paper win.

Mostly **DONE**. Remaining gaps before re-baselining on Phase 2:

| # | Item | Status | Remaining work |
|---|---|---|---|
| 1.G1 | Models, events, enums, config | ✅ | — |
| 1.G2 | Risk rules + manager | ✅ | `CorrelationRule` is a stub → implement placeholder (always-pass with TODO) or simple corr guard |
| 1.G3 | Paper adapter (slippage + commission) | ✅ | — |
| 1.G4 | Backtest brokerage/slippage/journal/metrics | ✅ | — |
| 1.G5 | `BacktestRunner.run()` | ⚠️ | Replace synthetic ramp with real bars; parametrize by `strategy_name` |
| 1.G6 | `TimescaleRepository.bulk_insert_bars()` | ⚠️ | Implement — needed for `--source db` backtest path + seeding |
| 1.G7 | `BinanceAdapter.get_positions()` | ⚠️ | Implement (required for P2 fills reconciliation) |
| 1.G8 | Test coverage | ⚠️ | Dispatcher test trivial; no risk-rule / orchestrator / bus / repo tests (these land in P2) |

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

**Time estimate:** ~44h total. May slip past a single weekend into weekday evenings. No scope cut.

### 2.A — EventBus hardening (~2h)

| Step | Deliverable | Key Details |
|---|---|---|
| 2.A.1 | SentimentEvent + CommandEvent in bus deser map | Confirm `SentimentEvent` in `bus.py` deserialization map; add `CommandEvent` type. Topic conventions: `bars:{symbol}`, `signals:{symbol}`, `orders:{symbol}`, `fills:{symbol}`, `sentiment:{symbol}`, `commands:*`, `risk_block:{symbol}` |
| 2.A.2 | Correlation IDs on all events | All events carry `correlation_id` (add envelope if missing) |
| 2.A.3 | Event schema versioning | Add `_event_schema_version: int = 1` to `BaseEvent` (forward-compat for sentiment V2) |
| 2.A.4 | Infra tests for EventBus | `tests/infra/test_bus.py` — pub/sub round-trip per event type, dead-letter on bad payload, schema-version mismatch handling |

### 2.B — BarBuffer & cold-start (~3h)

| Step | Deliverable | Key Details |
|---|---|---|
| 2.B.1 | `orchestration/bar_buffer.py` | New component — rolling `deque` per symbol, max-size = max(strategy.lookback) across loaded strategies. `add(symbol, bar) -> pd.DataFrame` returns full window |
| 2.B.2 | Cold-start hook | Empty buffer → fetch N historical bars via `adapter.get_bars()` before live stream begins |
| 2.B.3 | Infra tests | `tests/infra/test_bar_buffer.py` — fill/eviction, DataFrame shape, cold-start fetch mocked |

### 2.C — Commands & runtime control (~2h)

| Step | Deliverable | Key Details |
|---|---|---|
| 2.C.1 | `orchestration/commands.py` | New component — `CommandEvent` model + handlers: `add_symbol`, `remove_symbol`, `add_strategy`, `remove_strategy`, `update_risk_rule` |
| 2.C.2 | Orchestrator subscribes to `commands:*` | Dispatches runtime control actions. Risk rules accept runtime parameter updates via `update_risk_rule` |
| 2.C.3 | Infra tests | `tests/infra/test_commands.py` — publish `add_symbol` over fakeredis → orchestrator state changes |

### 2.D — Orchestrator rewrite (bus-driven) (~6h)

| Step | Deliverable | Key Details |
|---|---|---|
| 2.D.1 | Subscribe to `bars:{symbol}` | `BarBuffer.add()` → full-history DataFrame per strategy |
| 2.D.2 | Subscribe to `sentiment:{symbol}` | Passes `sentiment: SentimentEvent \| None` into `strategy.on_data()` (signature change in 2.E.1) |
| 2.D.3 | Publish signals/orders | `SignalEvent` → `signals:{symbol}`; risk pass → `OrderEvent` → `orders:{symbol}`; risk block → `RiskBlockEvent` → `risk_block:{symbol}` |
| 2.D.4 | Subscribe to `fills:{symbol}` | Reconcile positions against `PaperAdapter` |
| 2.D.5 | Trading tests | `tests/trading/test_orchestrator.py` — replay synthetic bars → assert signal/order/fill sequence with deterministic strategies |

### 2.E — Strategy signature change + second strategy (~4h)

| Step | Deliverable | Key Details |
|---|---|---|
| 2.E.1 | New `Strategy.on_data()` signature | `on_data(self, bars: pd.DataFrame, sentiment: SentimentEvent \| None) -> SignalEvent \| None` |
| 2.E.2 | Update `sma_crossover.py` | Accept new signature (sentiment ignored) |
| 2.E.3 | `strategy/rsi_mean_reversion.py` | RSI <30 buy / >70 sell. `lookback = rsi_period + 5` |
| 2.E.4 | Trading tests | `tests/trading/test_strategy_rsi.py` — oversold / overbought / neutral scenarios |

### 2.F — Binance WebSocket streaming (~6h)

| Step | Deliverable | Key Details |
|---|---|---|
| 2.F.1 | `BinanceAdapter.stream_bars()` | Async generator over Binance kline WS (`wss://stream.binance.com:9443/ws/{symbol}@kline_{interval}`), multi-symbol |
| 2.F.2 | Auto-reconnect | Exponential backoff (1s, 2s, 4s, 8s, …, max 60s); ping/pong keepalive |
| 2.F.3 | Dynamic subscribe/unsubscribe | Runtime `SUBSCRIBE`/`UNSUBSCRIBE` control frames on `add_symbol`/`remove_symbol` |
| 2.F.4 | `BinanceAdapter.get_positions()` | Implement (required for fills reconciliation) |
| 2.F.5 | `data/live_stream.py` refactor | Async generator with reconnect; emits `BarEvent` → `bars:{symbol}` |
| 2.F.6 | Infra tests | `tests/infra/test_binance_ws.py` — mock WS server started in pytest fixture, reconnect, dynamic subscribe |

### 2.G — Sentiment pipeline: pluggable multi-provider news (~7h)

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

### 2.H — Third strategy: sentiment-enhanced SMA (~2h)

| Step | Deliverable | Key Details |
|---|---|---|
| 2.H.1 | `strategy/sentiment_enhanced.py` | SMA crossover core, but signal suppressed when `sentiment.score < min_sentiment` AND `confidence < min_confidence`. Config: `min_confidence = 0.6`, `min_sentiment = -0.2`. LLM never decides to trade — only produces data that informs strategy |
| 2.H.2 | Trading tests | `tests/trading/test_strategy_sentiment.py` — buy+bullish passes, buy+bearish-below-threshold suppressed, neutral acts like SMA baseline |

### 2.I — Backtest infrastructure for strategies (~5h)

| Step | Deliverable | Key Details |
|---|---|---|
| 2.I.1 | Refactor `BacktestRunner` | Accept `(strategy_name, symbol, start, end, source)`. Supports `--source adapter` (REST via `BinanceAdapter.get_bars()`) **and** `--source db` (read from TimescaleDB via repository after seeding) |
| 2.I.2 | Shared contract | Backtest loop honors same `BarBuffer → strategy.on_data()` contract as live — strategies work identically in production |
| 2.I.3 | Sentiment replay | Backtest supports optional `SentimentEvent` replay from `news_sentiment` table so sentiment-enhanced strategy can be backtested |
| 2.I.4 | `seed_historical_data.py` | Updated to use `bulk_insert_bars()` (from 1.G6) for the `--source db` path |
| 2.I.5 | Trading tests | `tests/trading/test_backtest_runner.py` — known price series → expected trade sequence for SMA, RSI, Sentiment-enhanced; both `--source` paths |
| 2.I.6 | CLI | `backtest` command requires `--strategy`; choices: `sma_crossover`, `rsi_mean_reversion`, `sentiment_enhanced`. `--source adapter\|db` (default `adapter`) |

### 2.J — Containerize runtime + test profile (~4h)

| Step | Deliverable | Key Details |
|---|---|---|
| 2.J.1 | `Dockerfile.test` | New — installs `[dependency-groups] dev`, runs `ruff`, `mypy`, then `pytest` |
| 2.J.2 | `sentiment-ingester` service | docker-compose service (image reuse, command override `sentiment-ingest --config ...`), depends on Redis + Timescale |
| 2.J.3 | `test` profile in docker-compose | `test-runner` builds `Dockerfile.test`, mounts source, runs pytest. Depends on Redis + Timescale. In-process mocks only for broker HTTP/WS — no mock-services containers |
| 2.J.4 | `.dockerignore` | Exclude `.venv`, `.mypy_cache`, `.ruff_cache`, `.pytest_cache`, `*.egg-info` |
| 2.J.5 | Test CLI scripts | `scripts/ticaret.sh test-infra` / `test-trading` invoke the test container with the correct `tests/<root>` filter + marker |
| 2.J.6 | Healthcheck | `trading-engine` healthcheck → real `httpx` probe against `/metrics` endpoint (replace `import trading`) |

### 2.K — Test suite split + tests written (~7h)

Two distinct test suites with clearly separated concerns:

- **`tests/infra/`** — tests the infrastructure plumbing: event bus, bar buffer, commands, dispatcher routing, repository, news providers (mocked HTTP), paper adapter fill math, binance WS fixture. Uses `fakeredis` and `respx`.
- **`tests/trading/`** — tests trading activity simulation: strategy correctness, orchestrator replay → expected fills, backtest engine on deterministic series, paper-trade multi-day simulation. Strategies run against synthetic price data and assert expected trade sequences.

| Step | Deliverable | Key Details |
|---|---|---|
| 2.K.1 | Reorganize existing tests | Move into `tests/infra/` (config, models, events, market_hours, dispatcher, adapter plumbing, repository, news providers) and `tests/trading/` (strategy behavior, paper fill sim, signal accuracy, orchestrator replay, backtest engine, paper-trade multi-day simulation) |
| 2.K.2 | `tests/infra/` suite | Bus, bar_buffer, commands, dispatcher routing, repository (incl `bulk_insert_bars`), alpha_vantage/marketaux/finnhub/stockgeist (respx-mocked HTTP), news_registry, sentiment_repository, cached_provider, paper_adapter fill math, binance WS fixture |
| 2.K.3 | `tests/trading/` suite | Strategy correctness (SMA/RSI/Sentiment), orchestrator replay → expected fills, backtest engine on deterministic series (both sources), paper-trade multi-day simulation |
| 2.K.4 | Pytest markers | `pyproject.toml` `pytest.ini_options`: `markers = ["infra", "trading"]`; each test decorated so `pytest -m infra` / `pytest -m trading` selects cleanly inside one container invocation |

**Exit criteria:**
- `docker compose --profile test up --abort-on-container-exit` passes `tests/infra` + `tests/trading` inside the test container (in-process mocks only — no mock-services containers)
- `docker compose up` runs: `trading-engine` (orchestrator + live_stream + paper), `sentiment-ingester` (CachedNewsProvider on schedule, real providers ready to flip), Redis, Timescale, Prometheus, Grafana
- 3 strategies loaded; `./scripts/ticaret.sh add-symbol ETH/USDT` adds at runtime via Redis command
- `SentimentEvent` visible on `sentiment:BTC/USDT` topic (from CachedNewsProvider during weekend); sentiment-enhanced strategy suppresses trades per threshold
- Grafana shows PnL, drawdown, order flow, sentiment panels
- Backtest runs for all 3 strategies via `--source adapter` (default) and `--source db` (after seed)
- Config flag `sentiment.provider` flips to real `alpha_vantage` / `marketaux` / `finnhub` / `stockgeist` for post-weekend debug; quota/rate-limits enforced in code per provider
- Paper-trade on Binance testnet with dynamic symbol/strategy changes via Redis commands
- System recovers from network drops and WebSocket disconnections
- All events logged with correlation IDs
- Discord alerts fire on risk breaches and system errors

---

## Phase 3 — Live Micro-Trading, Alpaca & Hardening (ongoing)

**Goal:** System trades live with real money (tiny position sizes) on Binance. Alpaca adapter enables simultaneous equity paper trading. System runs unattended for weeks. Slippage and fees match paper trading within tolerance.

| Step | Deliverable | Key Details |
|---|---|---|
| 3.1 | Binance adapter → live mode | Config change: `mode: live`, `paper: false`. Tiny capital ($50-100) |
| 3.2 | `execution/adapters/alpaca.py` | Alpaca REST + WebSocket adapter. Paper trading first. NYSE market hours. PDT rule awareness |
| 3.3 | Health monitoring & self-healing | Auto-reconnect on WebSocket drops. Stale data detection (no bar for > 60s triggers alert) |
| 3.4 | Dead-letter queue | Failed orders land in `failed_orders` table. Manual review or automatic retry |
| 3.5 | Position reconciliation | On startup, sync local state with broker state. Detect drift |
| 3.6 | Slippage & fee tracking | Real vs. expected fill comparison. Alert if slippage exceeds threshold. Validates that the brokerage/slippage models from Phase 1 match real execution within 5% |
| 3.7 | Win/loss trade journal | Every trade logged: strategy name, signal source, sentiment at entry, risk rule verdicts, entry/exit price, slippage, brokerage cost |
| 3.8 | Trade quality review pipeline | Manual chart review of trade journal exports from backtests and paper trading. Identify trades that passed code filters but are not valid setups on the chart → add new filter rules to `strategy/filters.py`. ~2-3 days per strategy |
| 3.9 | `strategy/filters.py` | Post-signal filter plugins: minimum trend alignment, congestion zone exclusion, news blackout windows, volume confirmation thresholds. Strategy-agnostic and chainable. ~1 day for framework, ~0.5 day per filter rule |

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