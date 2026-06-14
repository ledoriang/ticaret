import asyncio
from datetime import datetime

import structlog
import typer

from trading.backtest.runner import BacktestRunner
from trading.core.config import load_config
from trading.core.logging import configure_logging
from trading.execution.adapters.base import AbstractBrokerAdapter
from trading.execution.dispatcher import Dispatcher
from trading.execution.paper import PaperAdapter
from trading.monitoring.alerts import AlertMessage, DiscordAlert
from trading.monitoring.metrics import (
    buying_power,
    cash_balance,
    connection_status,
    open_positions,
    portfolio_value,
    start_metrics_server,
)
from trading.orchestration.orchestrator import Orchestrator
from trading.risk.manager import RiskManager
from trading.risk.rules import MaxDailyTradesRule, MaxDrawdownRule, MaxExposureRule

configure_logging()
logger = structlog.get_logger(__name__)

app = typer.Typer()


@app.command()
def backtest(
    symbol: str = "BTC/USDT",
    start: str = "2020-01-01",
    end: str = "2025-01-01",
    config: str = "configs/development.yaml",
    initial_cash: float = 10_000.0,
) -> None:
    """Run a backtest for the given symbol."""
    cfg = load_config(config)
    runner = BacktestRunner(cfg)

    async def _run() -> None:
        metrics = await runner.run(
            symbol=symbol,
            start=start,
            end=end,
            initial_cash=initial_cash,
        )
        typer.echo("\n=== Backtest Results ===")
        for key, value in metrics.summary().items():
            typer.echo(f"  {key}: {value}")

    asyncio.run(_run())


@app.command()
def paper_trade(
    strategy: str = "sma_crossover",
    symbols: str = "BTC/USDT",
    config: str = "configs/development.yaml",
) -> None:
    """Paper-trade a strategy using the paper adapter."""
    cfg = load_config(config)
    paper = PaperAdapter(
        simulated_slippage=cfg.brokers.paper.get("simulated_slippage", 0.001),
        simulated_fee_rate=cfg.brokers.paper.get("simulated_fee_rate", 0.001),
    )
    adapters: dict[str, AbstractBrokerAdapter] = {"paper": paper}
    dispatcher = Dispatcher(adapters, cfg.brokers)
    risk_mgr = RiskManager(
        [
            MaxDrawdownRule(max_drawdown_pct=0.20),
            MaxExposureRule(max_exposure_pct=0.30),
            MaxDailyTradesRule(max_trades=10),
        ]
    )
    orchestrator = Orchestrator(cfg, dispatcher, risk_mgr)
    orchestrator.load_strategy(strategy)

    metrics_port = cfg.monitoring.prometheus_port
    start_metrics_server(metrics_port)

    alert = DiscordAlert(cfg.monitoring.alerts)

    async def _run() -> None:
        typer.echo(f"Paper-trading {symbols} with strategy '{strategy}' on port {metrics_port}")
        symbol_list = [s.strip() for s in symbols.split(",")]
        for _sym in symbol_list:
            connection_status.labels(broker="paper").set(1)
            acc = await paper.get_account()
            portfolio_value.set(acc.total_equity)
            cash_balance.set(acc.cash)
            buying_power.set(acc.buying_power)
            open_positions.set(len(await paper.get_positions()))
            if cfg.monitoring.alerts.discord_webhook_url:
                await alert.send(
                    AlertMessage(
                        title="Paper Trade Started",
                        description=f"Strategy: {strategy}, Symbols: {symbols}",
                        severity="info",
                        timestamp=datetime.now().isoformat(),
                    )
                )
        await orchestrator.start()

        stop_event = asyncio.Event()
        try:
            await stop_event.wait()
        except asyncio.CancelledError:
            pass
        finally:
            await orchestrator.stop()

    try:
        asyncio.run(_run())
    except KeyboardInterrupt:
        typer.echo("\nShutting down...")


@app.command()
def list_strategies() -> None:
    """List all registered strategies."""
    from trading.strategy.registry import StrategyRegistry

    strategies = StrategyRegistry.list_strategies()
    typer.echo("Registered strategies:")
    for s in strategies:
        typer.echo(f"  - {s}")


if __name__ == "__main__":
    app()
