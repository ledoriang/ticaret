# Implementation Phases

## Phase 1 — Foundation & Backtesting (2-3 weeks)

**Goal:** Run a backtested SMA crossover strategy on BTC/USDT historical data with a full metrics report. Prove the data pipeline, model layer, and backtesting engine work end-to-end. **Backtesting must reflect realistic trading conditions** — brokerage fees and slippage are applied so that a profitable backtest is meaningful, not just a paper win.

| Step | Deliverable | Key Details |
|---|---|---|
| 1.1 | Project scaffolding | `pyproject.toml` (uv, ruff, mypy strict), Docker Compose (Redis, TimescaleDB, Grafana, Prometheus) |
| 1.2 | `core/enums.py` + `core/models.py` | `AssetClass`, `Side`, `OrderType`, `OrderStatus` enums. Pydantic v2 models for `Bar`, `Order`, `Position`, `Portfolio`, `AccountInfo` |
| 1.3 | `core/events.py` | `SignalEvent`, `OrderEvent`, `FillEvent`, `SentimentEvent` — all carry `source`, `timestamp`, `asset_class` |
| 1.4 | `core/config.py` | Pydantic Settings from YAML + env vars. `brokers:` section with `active` list per asset class |
| 1.5 | `core/market_hours.py` | Market hours calendar — crypto returns always-open, equity respects NYSE calendar |
| 1.6 | `execution/gateway.py` + `execution/adapters/base.py` | `BrokerProtocol` definition, `AbstractBrokerAdapter` base class, adapter registry |
| 1.7 | `execution/adapters/binance.py` | Binance REST historical bars, account info, order submission. Testnet-ready |
| 1.8 | `execution/paper.py` | Dry-run adapter — logs orders to DB, simulates fills at last known price, tracks virtual positions |
| 1.9 | `data/ingestion.py` + `data/repository.py` | Historical bar fetching via adapter, TimescaleDB hypertable storage |
| 1.10 | `data/indicators.py` | pandas-ta + TA-Lib wrappers, vectorized computation |
| 1.11 | `strategy/base.py` + `strategy/registry.py` + `strategy/sma_crossover.py` | Strategy plugin system, first strategy |
| 1.12 | `backtest/runner.py` + `backtest/metrics.py` | Vectorbt engine, Sharpe/drawdown/PnL/Sortino/win rate |
| 1.13 | `backtest/brokerage.py` | **Brokerage cost model** — configurable per-broker fee schedule (e.g. Binance 0.1% maker/taker, Alpaca $0 commission). Applied to every fill in the backtest. Estimated effort: ~0.5 day. Fee structure can be a simple dict in config: `{maker: 0.001, taker: 0.001}` |
| 1.14 | `backtest/slippage.py` | **Slippage model** — configurable slippage per asset class and order type. Defaults: crypto 0.05%-0.1% (varies by liquidity), equity 0.02%-0.05%. Applied as adverse price movement on each fill. Estimated effort: ~0.5 day. Can start with a fixed-basis-point model and later add volume-based slippage |
| 1.15 | `backtest/trade_journal.py` | **Detailed trade log per fill** — records entry/exit timestamp, price, quantity, slippage, brokerage cost, strategy signal source, and the raw indicator values that triggered the trade. Enables manual chart review of every trade to spot false positives that passed code filters but aren't valid setups to a human eye. Estimated effort: ~1 day |
| 1.16 | `rust_kernel/` scaffold | `Cargo.toml`, `lib.rs` stub, `maturin` config. Compiles, importable from Python, does nothing yet |
| 1.17 | Full test suite | Unit tests for models, events, adapters (mocked HTTP), risk rules, strategies, brokerage/slippage cost calculations |
| 1.18 | Docker Compose validation | `docker-compose up` starts Redis, TimescaleDB, Grafana, Prometheus. Health checks pass |
| 1.19 | Dev tooling scripts | `scripts/ticaret.sh` CLI shorthand (up/down/lint/test/check/seed/db/backtest/setup) + standalone `docker.sh`, `lint.sh`, `test.sh`, `db.sh`. Python utilities moved to `scripts/py/` |

**Exit Criteria:**
- Run `./scripts/ticaret.sh backtest --symbol BTC/USDT --start 2020-01-01 --end 2025-01-01` and get a full metrics report with equity curve
- Backtest metrics include brokerage fees and slippage deducted from PnL
- Trade journal exported with per-trade details for manual chart verification
- Binance adapter fetches real data from API
- Paper adapter simulates fills correctly
- `import rust_kernel` succeeds (returns stub)
- All tests pass. `./scripts/ticaret.sh lint` and `./scripts/ticaret.sh check` pass

---

## Phase 2 — Orchestration, Risk & Paper Trading (2-3 weeks)

**Goal:** Paper-trade on Binance testnet for a full week with zero manual intervention. System survives network drops, restarts cleanly, and logs all decisions. Grafana shows live dashboards.

| Step | Deliverable | Key Details |
|---|---|---|
| 2.1 | `orchestration/bus.py` | Redis Pub/Sub event bus — `publish(event)`, `subscribe(topic, handler)` |
| 2.2 | `orchestration/orchestrator.py` | Subscribes to data events, feeds strategy, routes to risk → execution. The central coordinator |
| 2.3 | `risk/manager.py` + `risk/rules.py` | Modular risk rules: `MaxDrawdownRule`, `MaxExposureRule`, `CorrelationRule`, `MaxDailyTradesRule`. Each returns pass/fail + reason |
| 2.4 | `execution/dispatcher.py` | Routes `OrderEvent` to correct broker adapter based on `asset_class` and config. Supports multiple active brokers |
| 2.5 | `data/live_stream.py` | WebSocket streaming via broker adapter — real-time bars and fills |
| 2.6 | `monitoring/metrics.py` | Prometheus counters: orders placed, fills received, strategy signals, risk blocks. Gauges: portfolio value, open positions, drawdown |
| 2.7 | `monitoring/grafana/` + provisioning | Pre-built dashboards: trading overview (PnL, positions, orders), risk metrics (drawdown, exposure, blocked orders) |
| 2.8 | `monitoring/alerts.py` | Discord webhooks on: max drawdown breach, order failure, system health — multi-channel routing |
| 2.9 | `cli/main.py` | `trading paper-trade --strategy sma_crossover --symbols BTC/USDT,ETH/USDT --broker binance-testnet` |
| 2.10 | Integration tests | Full pipeline: data → strategy → risk → paper adapter → DB. Mock broker failures (500s, timeouts, rate limits). Test dead-letter handling |
| 2.11 | Structured logging | `structlog` JSON logging throughout. Correlation IDs on every event |

**Exit Criteria:**
- Paper-trade on Binance testnet unattended for 1 week
- Grafana shows live PnL curve, drawdown gauge, order flow
- Risk manager blocks trades that violate limits
- System recovers from network drops
- All events logged with correlation IDs
- Discord alerts fire on risk breaches and system errors

---

## Phase 3 — Sentiment & Alternative Data (2-4 weeks)

**Goal:** Sentiment scores flow through the event bus and influence strategy decisions. LLM outputs are always structured JSON. All sentiment data is traceable and logged.

| Step | Deliverable | Key Details |
|---|---|---|
| 3.1 | `data/sentiment.py` | Ollama client: takes raw text, returns structured `SentimentEvent` with `score`, `confidence`, `source` |
| 3.2 | `data/scrapers/crypto_news.py` | CryptoPanic API, CoinTelegraph RSS — emits raw news text to sentiment pipeline |
| 3.3 | `data/scrapers/social.py` | Reddit (r/cryptocurrency) trending tickers, X sentiment — emits to sentiment pipeline |
| 3.4 | `SentimentEvent` integration | Sentiment events flow through bus, orchestrator passes them to strategy alongside TA signals |
| 3.5 | `strategy/sentiment_enhanced.py` | TA signals filtered/boosted by sentiment. LLM never decides to trade — only produces data that informs strategy |
| 3.6 | Backtest sentiment-enhanced strategy | Re-run Phase 1 backtest with sentiment pipeline validated end-to-end |

**Exit Criteria:**
- Sentiment flows through the event bus with correlation IDs
- LLM outputs are always structured JSON with confidence scores
- Sentiment can influence but never override TA-based strategy decisions
- Grafana has a sentiment dashboard showing score distributions
- System still paper-trades on Binance testnet, now with sentiment layer active

---

## Phase 4 — Live Micro-Trading, Alpaca & Hardening (ongoing)

**Goal:** System trades live with real money (tiny position sizes) on Binance. Alpaca adapter enables simultaneous equity paper trading. System runs unattended for weeks. Slippage and fees match paper trading within tolerance.

| Step | Deliverable | Key Details |
|---|---|---|
| 4.1 | Binance adapter → live mode | Config change: `mode: live`, `paper: false`. Tiny capital ($50-100) |
| 4.2 | `execution/adapters/alpaca.py` | Alpaca REST + WebSocket adapter. Paper trading first. NYSE market hours. PDT rule awareness |
| 4.3 | Health monitoring & self-healing | Auto-reconnect on WebSocket drops. Stale data detection (no bar for > 60s triggers alert) |
| 4.4 | Dead-letter queue | Failed orders land in `failed_orders` table. Manual review or automatic retry |
| 4.5 | Position reconciliation | On startup, sync local state with broker state. Detect drift |
| 4.6 | Slippage & fee tracking | Real vs. expected fill comparison. Alert if slippage exceeds threshold. Validates that the brokerage/slippage models from Phase 1 match real execution within 5% |
| 4.7 | Win/loss trade journal | Every trade logged: strategy name, signal source, sentiment at entry, risk rule verdicts, entry/exit price, slippage, brokerage cost |
| 4.8 | Trade quality review pipeline | Manual chart review of trade journal exports from backtests and paper trading. Identify trades that passed code filters but are not valid setups on the chart → add new filter rules to `strategy/filters.py`. Estimated effort: ~2-3 days per strategy. Key insight: code doesn't see the chart like a human does — many false positives slip through. Each filter iteration removes bad trades, shrinking the trade set but improving signal quality. The goal is not more trades, it's fewer but better trades |
| 4.9 | `strategy/filters.py` | Post-signal filter plugins: minimum trend alignment, congestion zone exclusion, news blackout windows, volume confirmation thresholds, etc. Filters are strategy-agnostic and chainable. Estimated effort: ~1 day for framework, ~0.5 day per filter rule |

**Dual-broker flow during Phase 4:**
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

## Phase 5 — PyO3 Performance Kernel (Conditional)

**Goal:** Only executed if profiling shows Python bottlenecks in backtesting or indicator computation. This phase is triggered, not scheduled.

| Step | Deliverable | Key Details |
|---|---|---|
| 5.1 | Profile hot paths | `py-spy` or `cProfile` to identify bottlenecks. Likely: backtest loop, batch indicator calc, risk VaR |
| 5.2 | `rust_kernel::backtest` | Port backtest simulation core to Rust. Takes numpy arrays via PyO3, returns equity curve. Target: > 10x speedup |
| 5.3 | `rust_kernel::indicators` | Port batch indicator computation to Rust. Same inputs, same outputs, faster execution |
| 5.4 | `rust_kernel::risk` | Port Monte Carlo VaR simulation to Rust (if needed) |
| 5.5 | Config-based toggle | `use_rust_backtester: true` in config → imports from `rust_kernel` instead of Python. Zero code changes elsewhere |
| 5.6 | Benchmark & validate | Rust and Python implementations produce identical results. Fuzz-tested |

**What stays in Python forever:**
- Orchestration, event bus, CLI, all I/O (API calls, WebSocket streaming, DB access)
- Strategy logic (should be quick to write and iterate on)
- Configuration, monitoring, alerting

**Migration pattern:**
1. Write a Rust implementation of the same function signature
2. Compile with `maturin develop` — becomes `import rust_kernel`
3. Add config flag: `use_rust_backtester: true`
4. Python code imports from `rust_kernel` instead of `backtest.runner` — zero changes to rest of stack

**Exit Criteria:**
- `rust_kernel` produces identical results to Python implementations
- Backtest runs > 10x faster on large datasets
- All existing tests pass with Rust kernel enabled
- Toggle between Python and Rust via config flag