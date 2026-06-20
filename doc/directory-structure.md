# Directory Structure

```
ticaret/
├── pyproject.toml                      # uv project, dependencies, ruff/mypy/pytest config
├── uv.lock                             # Dependency lock file
├── Dockerfile                          # Runtime image (trading-engine, sentiment-ingester)
├── Dockerfile.test                     # Test image (dev deps, ruff, mypy, pytest)
├── docker-compose.yml                  # All services + test profile
├── .dockerignore                       # Exclude .venv, caches, egg-info
│
├── configs/
│   ├── development.yaml                # Local dev config
│   ├── paper_trading.yaml              # Paper trading config (Binance testnet)
│   ├── live_micro.yaml                 # Micro-live config (tiny capital)
│   └── docker.yaml                     # Container config (references compose service names)
│
├── src/trading/
│   ├── __init__.py
│   │
│   ├── core/                            # Shared models, events, config, enums
│   │   ├── __init__.py
│   │   ├── enums.py                     # Side, OrderType, AssetClass, OrderStatus
│   │   ├── models.py                    # Bar, Order, Position, Portfolio, AccountInfo
│   │   ├── events.py                    # BaseEvent, SignalEvent, OrderEvent, FillEvent, BarEvent,
│   │   │                                #   SentimentEvent, RiskBlockEvent, CommandEvent
│   │   ├── config.py                    # Pydantic Settings from YAML + env vars (includes sentiment: block)
│   │   ├── logging.py                    # structlog setup, correlation ID context
│   │   └── market_hours.py              # Market hours calendar (crypto vs equity)
│   │
│   ├── data/                            # Data ingestion, storage, indicators, sentiment, news
│   │   ├── __init__.py
│   │   ├── ingestion.py                 # Historical bar fetching (delegates to broker adapter)
│   │   ├── live_stream.py               # Async WebSocket streaming (delegates to broker adapter,
│   │   │                                #   auto-reconnect, dynamic symbol subscription)
│   │   ├── indicators.py                # pandas-ta / TA-Lib wrappers
│   │   ├── repository.py                # TimescaleDB async read/write (asyncpg) — bars
│   │   ├── sentiment_repository.py      # TimescaleDB — news_sentiment hypertable (traceability + backtest replay)
│   │   │
│   │   ├── scrapers/                    # RSS / social scrapers (future — raw text to LLM)
│   │   │   ├── __init__.py
│   │   │   ├── crypto_news.py           # CryptoPanic, CoinTelegraph RSS
│   │   │   └── social.py                # Reddit, X trending
│   │   │
│   │   └── news/                        # Pluggable news/sentiment providers
│   │       ├── __init__.py              # PROVIDER_REGISTRY dict
│   │       ├── base.py                  # NewsProvider Protocol + RateLimit dataclass
│   │       ├── registry.py              # Provider registry (plugin pattern, mirrors adapter registry)
│   │       ├── alpha_vantage.py         # Alpha Vantage NEWS_SENTIMENT (25 req/day free, stocks/crypto/forex,
│   │       │                            #   ticker-specific scores -1.0 to 1.0, token-bucket rate limiter)
│   │       ├── marketaux.py             # Marketaux (100 req/day free, global stocks/crypto,
│   │       │                            #   entity-level impact & sentiment ratios)
│   │       ├── finnhub.py               # Finnhub (30 req/min free, US equities,
│   │       │                            #   company buzz & sector trends)
│   │       ├── stockgeist.py            # StockGeist (credit-based, US equities,
│   │       │                            #   real-time news + social sentiment streams)
│   │       └── cached.py                # CachedNewsProvider — YAML fixture with per-poll variation
│   │                                    #   (default for dev/backtest, config flag to switch)
│   │
│   ├── strategy/                        # Strategy plugins
│   │   ├── __init__.py
│   │   ├── base.py                      # Abstract Strategy — on_data(bars, sentiment) -> SignalEvent | None
│   │   ├── registry.py                  # Strategy registry (plugin pattern)
│   │   ├── sma_crossover.py             # SMA crossover (Phase 1 strategy)
│   │   ├── rsi_mean_reversion.py        # RSI mean-reversion (Phase 2 strategy)
│   │   ├── sentiment_enhanced.py        # SMA + sentiment filter (Phase 2 strategy)
│   │   └── filters.py                   # Post-signal filter plugins (Phase 3)
│   │
│   ├── risk/                            # Risk management
│   │   ├── __init__.py
│   │   ├── manager.py                   # RiskManager — evaluates all rules before approving
│   │   └── rules.py                     # Individual risk rule classes
│   │
│   ├── execution/                       # Broker abstraction and adapters
│   │   ├── __init__.py
│   │   ├── gateway.py                   # BrokerProtocol definition
│   │   ├── dispatcher.py                # Routes OrderEvents to correct broker by asset_class
│   │   ├── paper.py                     # Dry-run adapter (logs to DB, no API calls)
│   │   └── adapters/
│   │       ├── __init__.py              # ADAPTER_REGISTRY dict
│   │       ├── base.py                  # AbstractBrokerAdapter (implements BrokerProtocol)
│   │       ├── binance.py               # Binance REST + WS (crypto)
│   │       ├── okx.py                   # OKX (future)
│   │       ├── alpaca.py                # Alpaca (US equities, Phase 3)
│   │       └── ibkr.py                  # IBKR (future)
│   │
│   ├── orchestration/                   # Event bus, central coordinator, runtime control
│   │   ├── __init__.py
│   │   ├── bus.py                       # Redis Pub/Sub event bus (publish/subscribe/topics)
│   │   ├── orchestrator.py              # Central coordinator (air traffic controller)
│   │   ├── bar_buffer.py               # Rolling window per symbol, sized to strategy lookback
│   │   └── commands.py                  # CommandEvent model + runtime command handlers
│   │
│   ├── services/                        # Long-running background services
│   │   ├── __init__.py
│   │   └── sentiment_ingester.py        # Polls NewsProvider on schedule, publishes SentimentEvent to bus
│   │
│   ├── backtest/                        # Backtesting engine
│   │   ├── __init__.py
│   │   ├── runner.py                    # Vectorbt integration — accepts --source adapter|db
│   │   ├── metrics.py                   # Sharpe, drawdown, PnL, Sortino, win rate
│   │   ├── brokerage.py                 # Commission model (per-broker maker/taker rates)
│   │   ├── slippage.py                  # Slippage model (per asset class, basis points)
│   │   └── trade_journal.py             # Detailed trade log per fill
│   │
│   ├── monitoring/                      # Observability
│   │   ├── __init__.py
│   │   ├── metrics.py                   # Prometheus counters, gauges, histograms
│   │   ├── alerts.py                    # Discord webhook alerts (multi-channel)
│   │   └── grafana/
│   │       ├── trading_overview.json
│   │       ├── risk_metrics.json
│   │       └── sentiment.json
│   │
│   ├── rust_kernel/                     # PyO3 boundary (Phase 4, scaffold only initially)
│   │   ├── Cargo.toml
│   │   ├── pyproject.toml               # maturin build config
│   │   └── src/
│   │       └── lib.rs                   # Stub — backtest engine, indicator math
│   │
│   └── cli/
│       ├── __init__.py
│       └── main.py                      # Typer CLI entry point
│
├── tests/                               # Two distinct test suites
│   ├── __init__.py
│   ├── conftest.py                      # Shared fixtures (fakeredis, respx, mock WS, config)
│   │
│   ├── infra/                           # Infrastructure plumbing tests
│   │   ├── __init__.py                  # Tests that buses, adapters, repos, providers work
│   │   ├── conftest.py                  # Infra-specific fixtures (fakeredis pool, respx router)
│   │   ├── test_bus.py                  # EventBus pub/sub round-trip, dead-letter, schema version
│   │   ├── test_bar_buffer.py           # BarBuffer fill/eviction, cold-start fetch
│   │   ├── test_commands.py            # CommandEvent publish → orchestrator state change
│   │   ├── test_dispatcher.py           # Order routing by asset_class
│   │   ├── test_repository.py           # TimescaleRepository CRUD + bulk_insert_bars
│   │   ├── test_sentiment_repository.py # SentimentRepository persistence
│   │   ├── test_binance_ws.py           # Mock WS server fixture, reconnect, dynamic subscribe
│   │   ├── test_binance_adapter.py      # REST calls mocked via respx
│   │   ├── test_paper_adapter.py        # Fill math, slippage, commission, position tracking
│   │   ├── test_alpha_vantage.py        # AV NEWS_SENTIMENT parsing + rate limit (respx)
│   │   ├── test_marketaux.py            # Marketaux parsing + rate limit (respx)
│   │   ├── test_finnhub.py              # Finnhub parsing + rate limit (respx)
│   │   ├── test_stockgeist.py           # StockGeist parsing (respx)
│   │   ├── test_news_registry.py        # Provider registry registration + lookup
│   │   ├── test_cached_provider.py      # CachedNewsProvider fixture loading + variation
│   │   ├── test_market_hours.py         # Crypto always-open, equity NYSE calendar
│   │   ├── test_config.py               # Default config, YAML override, sentiment: block
│   │   ├── test_models.py               # Bar, Order, Position, Portfolio, AccountInfo
│   │   └── test_events.py               # All event types, correlation_id, schema_version
│   │
│   └── trading/                         # Trading activity simulation tests
│       ├── __init__.py                  # Tests that strategies produce correct trades
│       ├── conftest.py                  # Trading-specific fixtures (synthetic bars, price series)
│       ├── test_strategy_sma.py         # SMA crossover signal correctness
│       ├── test_strategy_rsi.py         # RSI mean-reversion signal correctness
│       ├── test_strategy_sentiment.py   # Sentiment-enhanced suppression logic
│       ├── test_orchestrator.py         # Replay bars → assert signal/order/fill sequence
│       ├── test_backtest_runner.py      # Deterministic series → expected trades (adapter + db source)
│       ├── test_paper_trading.py        # Multi-day paper-trade simulation
│       └── test_sentiment_flow.py        # SentimentEvent → orchestrator → strategy receives it
│
├── scripts/
│   ├── ticaret.sh                       # Dev CLI shorthand (up/down/lint/test/check/seed/db/backtest/
│   │                                    #   test-infra/test-trading/add-symbol/remove-symbol)
│   ├── docker.sh                        # Container lifecycle (up/down/restart/logs/status/reset-db)
│   ├── lint.sh                          # ruff check + format check + mypy --strict
│   ├── test.sh                          # pytest runner (forwards args, --cov support)
│   ├── db.sh                            # Database init/seed/backfill shortcuts
│   └── py/                              # Python utility scripts (called via ticaret.sh)
│       ├── db_init.py                   # Create TimescaleDB hypertables (incl news_sentiment)
│       ├── seed_historical_data.py      # Fetch and store historical bars (bulk_insert path)
│       └── backfill_timescaledb.py      # Bulk data import
│
├── grafana/
│   └── provisioning/                    # Auto-provisioned datasources + dashboards
│       ├── datasources/
│       │   └── prometheus.yml
│       └── dashboards/
│           ├── trading_overview.json
│           ├── risk_metrics.json
│           └── sentiment.json
│
└── doc/
    ├── overview.md
    ├── architecture.md
    ├── directory-structure.md
    ├── broker-protocol.md
    ├── phases.md
    ├── monitoring-alerts.md
    └── pyo3-pathway.md
```

## Design Rationale

### Single Repo

Everything lives in one repository because:

- The system is an event-driven Python monolith, not deployed microservices
- The `BrokerProtocol` interface, risk rules, and strategy plugins all import from `core/`
- Refactoring the protocol instantly propagates to all adapters
- One `pyproject.toml`, one `uv.lock`, one CI pipeline, one `docker-compose.yml`
- The `rust_kernel/` lives alongside Python since it's imported as a Python module via `maturin`

### Modularity via Package Structure

Removing an exchange = deleting one file from `adapters/`. Adding a strategy = adding one file to `strategy/`. Adding a news API = adding one file to `data/news/` + one dict entry in `PROVIDER_REGISTRY`. No repo-level surgery. Pure package-level isolation enforced by import boundaries.

### Two Distinct Test Suites

`tests/infra/` and `tests/trading/` are structurally separated because they test fundamentally different things:

- **Infra tests** verify that the plumbing works — events flow through the bus, adapters route correctly, repositories persist and retrieve, news providers parse API responses, rate limiters enforce quotas. They use `fakeredis` for Redis and `respx` for HTTP mocking. They are mostly stateless and fast.
- **Trading tests** verify that trading activity is correct — strategies fire the right signals on the right bar sequences, the orchestrator produces expected order/fill chains, the backtest engine reproduces known trade sequences on deterministic data, and a multi-day paper trade simulation produces realistic portfolio state. They use synthetic price series and in-process mocks.

Both suites run inside the same `Dockerfile.test` container, but each can be invoked selectively via `pytest -m infra` or `pytest -m trading`. The container depends on Redis and TimescaleDB services from docker-compose.

### In-Process Mocks Only

No separate mock-services containers. Broker HTTP is mocked via `respx`. Redis is mocked via `fakeredis`. Binance WebSocket is mocked via a tiny `aiohttp` WS server started in a pytest fixture. This keeps the test profile simple — one test container + Redis + Timescale, nothing else.

### Rust Kernel as Sibling, Not a Separate Repo

`rust_kernel/` is compiled by `maturin` into a native Python module. Importing it is `import rust_kernel`. It shares the same repo because:

- It depends on the same Pydantic models for input/output serialization
- The config toggle (`use_rust_backtester: true`) lives in the same YAML
- Integration tests need both Python and Rust in the same test run