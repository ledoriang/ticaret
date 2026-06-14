import asyncio

import typer

from trading.backtest.runner import BacktestRunner
from trading.core.config import load_config

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
def list_strategies() -> None:
    """List all registered strategies."""
    from trading.strategy.registry import StrategyRegistry

    strategies = StrategyRegistry.list_strategies()
    typer.echo("Registered strategies:")
    for s in strategies:
        typer.echo(f"  - {s}")


if __name__ == "__main__":
    app()
