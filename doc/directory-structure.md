# Directory Structure

```
trading-stack/
├── pyproject.toml                 # uv project, dependencies, ruff/mypy config
├── docker-compose.yml             # Redis, TimescaleDB, Grafana, Prometheus
├── configs/
│   ├── development.yaml           # Local dev config
│   ├── paper_trading.yaml         # Paper trading config (Binance testnet)
│   └── live_micro.yaml           # Micro-live config (tiny capital)
├── src/trading/
│   ├── __init__.py
│   │
│   ├── core/                      # Shared models, events, config, enums
│   │   ├── __init__.py
│   │   ├── enums.py               # Side, OrderType, AssetClass, OrderStatus
│   │   ├── models.py              # Bar, Order, Position, Portfolio, AccountInfo
│   │   ├── events.py              # SignalEvent, OrderEvent, FillEvent, SentimentEvent
│   │   ├── config.py              # Pydantic Settings from YAML + env vars
│   │   └── market_hours.py        # Market hours calendar (crypto vs equity)
│   │
│   ├── data/                       # Data ingestion, storage, indicators, sentiment
│   │   ├── __init__.py
│   │   ├── ingestion.py            # Historical bar fetching (delegates to broker adapter)
│   │   ├── live_stream.py          # WebSocket streaming (delegates to broker adapter)
│   │   ├── indicators.py           # pandas-ta / TA-Lib wrappers
│   │   ├── sentiment.py            # Ollama client for local LLM inference
│   │   ├── repository.py           # TimescaleDB async read/write (asyncpg)
│   │   └── scrapers/
│   │       ├── __init__.py
│   │       ├── crypto_news.py      # CryptoPanic, CoinTelegraph RSS
│   │       └── social.py           # Reddit, X trending
│   │
│   ├── strategy/                   # Strategy plugins
│   │   ├── __init__.py
│   │   ├── base.py                 # Abstract Strategy, StrategyResult
│   │   ├── registry.py             # Strategy registry (plugin pattern)
│   │   ├── sma_crossover.py        # SMA crossover (Phase 1 strategy)
│   │   └── sentiment_enhanced.py   # TA + sentiment filter (Phase 3)
│   │
│   ├── risk/                       # Risk management
│   │   ├── __init__.py
│   │   ├── manager.py              # RiskManager — evaluates all rules before approving
│   │   └── rules.py                # Individual risk rule classes
│   │
│   ├── execution/                   # Broker abstraction and adapters
│   │   ├── __init__.py
│   │   ├── gateway.py              # BrokerProtocol definition
│   │   ├── dispatcher.py           # Routes OrderEvents to correct broker by asset_class
│   │   ├── paper.py                # Dry-run adapter (logs to DB, no API calls)
│   │   └── adapters/
│   │       ├── __init__.py         # ADAPTER_REGISTRY dict
│   │       ├── base.py             # AbstractBrokerAdapter (implements BrokerProtocol)
│   │       ├── binance.py          # Binance REST + WS (crypto)
│   │       ├── okx.py              # OKX (future)
│   │       ├── alpaca.py           # Alpaca (US equities, Phase 4)
│   │       └── ibkr.py             # IBKR (future)
│   │
│   ├── orchestration/              # Event bus and central coordinator
│   │   ├── __init__.py
│   │   ├── bus.py                  # Redis Pub/Sub event bus
│   │   └── orchestrator.py         # Central coordinator (air traffic controller)
│   │
│   ├── backtest/                    # Backtesting engine
│   │   ├── __init__.py
│   │   ├── runner.py               # Vectorbt integration
│   │   └── metrics.py              # Sharpe, drawdown, PnL, Sortino, win rate
│   │
│   ├── monitoring/                  # Observability
│   │   ├── __init__.py
│   │   ├── metrics.py              # Prometheus counters, gauges, histograms
│   │   ├── alerts.py                # Discord webhook alerts (multi-channel)
│   │   └── grafana/
│   │       ├── trading_overview.json
│   │       └── risk_metrics.json
│   │
│   ├── rust_kernel/                  # PyO3 boundary (Phase 5, scaffold only initially)
│   │   ├── Cargo.toml
│   │   ├── pyproject.toml            # maturin build config
│   │   └── src/
│   │       └── lib.rs                # Stub — backtest engine, indicator math
│   │
│   └── cli/
│       ├── __init__.py
│       └── main.py                  # Typer CLI entry point
│
├── tests/
│   ├── __init__.py
│   ├── conftest.py                  # Shared fixtures, mock broker, test DB
│   ├── unit/
│   │   ├── test_models.py
│   │   ├── test_events.py
│   │   ├── test_config.py
│   │   ├── test_market_hours.py
│   │   ├── test_indicators.py
│   │   ├── test_risk_rules.py
│   │   ├── test_strategy_sma.py
│   │   └── test_dispatcher.py
│   ├── integration/
│   │   ├── test_full_pipeline.py
│   │   ├── test_broker_failures.py
│   │   └── test_paper_trading.py
│   └── adapters/
│       ├── test_binance_adapter.py
│       ├── test_paper_adapter.py
│       └── test_alpaca_adapter.py     # Phase 4
│
├── scripts/
│   ├── ticaret.sh                   # Dev CLI shorthand (up/down/lint/test/check/seed/db/backtest)
│   ├── docker.sh                     # Container lifecycle (up/down/restart/logs/status/reset-db)
│   ├── lint.sh                       # ruff check + format check + mypy --strict
│   ├── test.sh                       # pytest runner (forwards args, --cov support)
│   ├── db.sh                         # Database init/seed/backfill shortcuts
│   └── py/                            # Python utility scripts (called via ticaret.sh)
│       ├── db_init.py                 # Create TimescaleDB hypertables
│       ├── seed_historical_data.py    # Fetch and store historical bars
│       └── backfill_timescaledb.py    # Bulk data import
│
├── grafana/
│   └── provisioning/                 # Auto-provisioned datasources + dashboards
│       ├── datasources/
│       │   └── prometheus.yml
│       └── dashboards/
│           ├── trading_overview.json
│           └── risk_metrics.json
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

Removing an exchange = deleting one file from `adapters/`. Adding a strategy = adding one file to `strategy/`. No repo-level surgery. Pure package-level isolation enforced by import boundaries.

### Rust Kernel as Sibling, Not a Separate Repo

`rust_kernel/` is compiled by `maturin` into a native Python module. Importing it is `import rust_kernel`. It shares the same repo because:

- It depends on the same Pydantic models for input/output serialization
- The config toggle (`use_rust_backtester: true`) lives in the same YAML
- Integration tests need both Python and Rust in the same test run