# Trading Stack — Project Overview

## What

A programmatic, hands-off, event-driven trading infrastructure that removes emotional decision-making from trading. Not a get-rich-quick scheme — a software engineering project focused on robust execution, modular design, and systematic strategy evaluation.

## Why

Retail algorithmic traders fail most often from poor execution infrastructure, bad data, overfitting in backtesting, or unexpected API rate limits — not necessarily bad strategies. This project treats the trading stack as a core infrastructure project with the same rigor applied to production software systems.

## Core Principles

1. **Quality over quantity.** No trade is better than a bad trade. The system is designed to sit idle for days if market conditions don't warrant a trade. A "bloodbath day" with zero trades is a successful day if the alternative was losing capital. Every signal must pass through quality filters, regime checks, and risk management before it becomes an order.
2. **Every trade has a stop loss.** No signal reaches execution without a defined stop-loss price. Stop losses are not optional — they are set at signal generation time, enforced by the risk manager, and monitored by the orchestrator. A trade without a stop is a bug.
3. **Risk-based position sizing.** Position size is calculated from portfolio risk and stop distance, not from signal confidence. `qty = (portfolio_value * risk_per_trade) / (entry_price - stop_loss_price)`. Default risk per trade: 1% of portfolio.
4. **Modular and event-driven.** Every component communicates through asynchronous events over Redis Pub/Sub. No direct coupling between data ingestion, strategy logic, and execution. The Orchestrator subscribes to bar/sentiment events, publishes signals/orders through the bus.
5. **Broker-agnostic.** A `BrokerProtocol` defines the interface. Swapping Binance for Alpaca is a config change, not a code change. Adding a new exchange is creating one adapter file.
6. **Risk management is non-negotiable.** The Risk Manager sits between every strategy signal and the broker. No signal reaches execution without passing hardcoded risk rules. The risk manager also enforces stop-loss discipline and daily loss limits.
7. **News/sentiment produces data, not decisions.** News APIs that already include sentiment values (Alpha Vantage, Marketaux, Finnhub, StockGeist) are consumed via a pluggable `NewsProvider` protocol. Only the Strategy + Risk Manager produce orders.
8. **Typed and strict.** `mypy --strict`, Pydantic v2 models, typed event dataclasses. Everything at a boundary is validated.
9. **Bar buffer for strategy lookback.** Each strategy declares how many historical bars it needs. The engine maintains rolling windows per symbol so strategies receive meaningful history for indicator computation.
10. **Runtime dynamic control.** Symbols and strategies can be added/removed at runtime via Redis `CommandEvent`s — no restart required.
11. **Test before money.** Phase progression: backtest (with walk-forward + out-of-sample) → paper trade → micro-live → expand. Capital enters only after infrastructure and strategies are proven across multiple market regimes.
12. **Observe everything.** Prometheus metrics, Grafana dashboards, structured JSON logging with correlation IDs, Discord alerts across dedicated channels.
13. **Everything runs in containers.** Runtime services (trading engine, sentiment ingester, Redis, TimescaleDB, Grafana, Prometheus) run in Docker Compose. Tests run in a dedicated `Dockerfile.test` container with in-process mocks (fakeredis, respx, mock WS fixtures). No code runs directly on the host for production or CI.

## Tech Stack

| Component | Choice |
|---|---|
| Language | Python 3.12+ (typed, strict mypy) |
| Package manager | uv |
| Message broker | Redis Pub/Sub |
| Database | PostgreSQL + TimescaleDB |
| Monitoring | Grafana + Prometheus |
| Alerting | Discord webhooks (multi-channel) |
| Backtesting | Vectorbt + pandas-ta |
| Initial broker | Binance (crypto) |
| Second broker | Alpaca (US equities) |
| Broker abstraction | `BrokerProtocol` — pluggable, config-driven |
| News/sentiment providers | Pluggable `NewsProvider` protocol — Alpha Vantage, Marketaux, Finnhub, StockGeist, CachedNewsProvider |
| News abstraction | `NewsProvider` — pluggable, config-driven, same pattern as `BrokerProtocol` |
| PyO3 | Scaffolded in Phase 1, implemented in Phase 4 (conditional) |
| Linting/formatting | Ruff |
| Type checking | mypy (strict) |
| Testing | pytest + pytest-asyncio — `tests/infra/` (plumbing) and `tests/trading/` (strategy simulation) |
| Containerization | Docker Compose (runtime) + `Dockerfile.test` (test container) |
| Mocking (test) | fakeredis (Redis), respx (HTTP), in-fixture mock WS server |
| Logging | structlog (JSON, correlation IDs) |
| CLI | Typer |
| Async HTTP | httpx |
| Async DB | asyncpg |

## Asset Classes

| Asset Class | Phase Introduced | Market Hours | First Broker |
|---|---|---|---|
| Crypto | Phase 1 | 24/7 | Binance |
| US Equities | Phase 3 | NYSE calendar (09:30–16:00 ET) | Alpaca (paper → live) |

## Regional Considerations

- Based in Europe or South Africa
- SARB foreign capital allowance limits: R1M single discretionary, R10M foreign investment
- Alpaca International available for EU residents
- IBKR fully available in both EU and ZA
- Crypto exchanges generally available subject to local country restrictions

## News / Sentiment Providers

The system consumes news APIs that already include sentiment values — no self-hosted LLM inference required for the base pipeline. Providers are pluggable via a `NewsProvider` protocol (same pattern as `BrokerProtocol` for brokers). Adding a new news API = one file + one dict entry.

| Provider | Free Tier Limit | Primary Asset Focus | Sentiment Granularity |
|---|---|---|---|
| Alpha Vantage | 25 requests / day | Stocks, Crypto, Forex | Ticker-specific scores (-1.0 to 1.0) |
| Marketaux | 100 requests / day | Global Stocks, Crypto | Entity-level impact & sentiment ratios |
| Finnhub | 30 requests / minute | US Equities | Aggregated company buzz & sector trends |
| StockGeist | Credit-based | US Equities | Real-time news + social sentiment streams |

All providers enforce their rate limits in code via token-bucket limiters. A `CachedNewsProvider` returns canned payloads from a YAML fixture for development and backtesting — zero API quota burn. Config flag `sentiment.provider` flips between `cached` and any real provider.

Sentiment events flow through the same EventBus as bars and signals. Every SentimentEvent is persisted to TimescaleDB (`news_sentiment` hypertable) for traceability and backtest replay.

## Containerization

All runtime code runs in Docker containers via `docker-compose.yml`:

| Container | Image | Purpose |
|---|---|---|
| `trading-engine` | `Dockerfile` (app) | Orchestrator + live stream + paper adapter |
| `sentiment-ingester` | `Dockerfile` (app, command override) | Polls news provider, publishes SentimentEvents |
| `redis` | `redis:7-alpine` | Event bus (Pub/Sub) |
| `timescaledb` | `timescale/timescaledb` | OHLCV bars, sentiment, orders, fills |
| `prometheus` | `prom/prometheus` | Metrics scraping |
| `grafana` | `grafana/grafana` | Dashboards |
| `test-runner` | `Dockerfile.test` | Runs `tests/infra/` and `tests/trading/` suites |

Tests run in a dedicated `Dockerfile.test` container that installs dev dependencies, runs `ruff`, `mypy`, then `pytest`. No separate mock-services containers — all mocks are in-process (fakeredis, respx, mock WS fixtures).

## Related Docs

- [Architecture](architecture.md) — Event-driven layers, data flow
- [Directory Structure](directory-structure.md) — Project layout
- [Broker Protocol](broker-protocol.md) — Adapter interface design
- [Phases](phases.md) — Implementation checklist
- [Monitoring & Alerts](monitoring-alerts.md) — Grafana, Prometheus, Discord
- [PyO3 Pathway](pyo3-pathway.md) — Hybrid Rust kernel plan