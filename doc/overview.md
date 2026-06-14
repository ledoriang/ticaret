# Trading Stack — Project Overview

## What

A programmatic, hands-off, event-driven trading infrastructure that removes emotional decision-making from trading. Not a get-rich-quick scheme — a software engineering project focused on robust execution, modular design, and systematic strategy evaluation.

## Why

Retail algorithmic traders fail most often from poor execution infrastructure, bad data, overfitting in backtesting, or unexpected API rate limits — not necessarily bad strategies. This project treats the trading stack as a core infrastructure project with the same rigor applied to production software systems.

## Core Principles

1. **Modular and event-driven.** Every component communicates through asynchronous events. No direct coupling between data ingestion, strategy logic, and execution.
2. **Broker-agnostic.** A `BrokerProtocol` defines the interface. Swapping Binance for Alpaca is a config change, not a code change. Adding a new exchange is creating one adapter file.
3. **Risk management is non-negotiable.** The Risk Manager sits between every strategy signal and the broker. No signal reaches execution without passing hardcoded risk rules.
4. **LLMs produce data, not decisions.** Language models output structured sentiment scores. Only the Strategy + Risk Manager produce orders.
5. **Typed and strict.** `mypy --strict`, Pydantic v2 models, typed event dataclasses. Everything at a boundary is validated.
6. **Test before money.** Phase progression: backtest → paper trade → micro-live → expand. Capital enters only after infrastructure is proven.
7. **Observe everything.** Prometheus metrics, Grafana dashboards, structured JSON logging with correlation IDs, Discord alerts across dedicated channels.

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
| Sentiment | Ollama (local LLM), structured JSON output |
| PyO3 | Scaffolded in Phase 1, implemented in Phase 5 (conditional) |
| Linting/formatting | Ruff |
| Type checking | mypy (strict) |
| Testing | pytest + pytest-asyncio |
| Logging | structlog (JSON, correlation IDs) |
| CLI | Typer |
| Async HTTP | httpx |
| Async DB | asyncpg |

## Asset Classes

| Asset Class | Phase Introduced | Market Hours | First Broker |
|---|---|---|---|
| Crypto | Phase 1 | 24/7 | Binance |
| US Equities | Phase 4 | NYSE calendar (09:30–16:00 ET) | Alpaca (paper → live) |

## Regional Considerations

- Based in Europe or South Africa
- SARB foreign capital allowance limits: R1M single discretionary, R10M foreign investment
- Alpaca International available for EU residents
- IBKR fully available in both EU and ZA
- Crypto exchanges generally available subject to local country restrictions

## Related Docs

- [Architecture](architecture.md) — Event-driven layers, data flow
- [Directory Structure](directory-structure.md) — Project layout
- [Broker Protocol](broker-protocol.md) — Adapter interface design
- [Phases](phases.md) — Implementation checklist
- [Monitoring & Alerts](monitoring-alerts.md) — Grafana, Prometheus, Discord
- [PyO3 Pathway](pyo3-pathway.md) — Hybrid Rust kernel plan