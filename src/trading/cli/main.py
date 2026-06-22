import asyncio
from datetime import datetime
from typing import Literal

import structlog
import typer

from trading.backtest.runner import BacktestRunner
from trading.backtest.walk_forward import WalkForwardAnalyzer
from trading.core.config import load_config
from trading.core.logging import configure_logging
from trading.data.sentiment_repository import SentimentRepository
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
from trading.services.sentiment_ingester import SentimentIngester

configure_logging()
logger = structlog.get_logger(__name__)

app = typer.Typer()


@app.command()
def backtest(
    strategy: str = typer.Option("sma_crossover", "--strategy", help="Strategy name"),
    symbol: str = "BTC/USDT",
    timeframe: str = "1d",
    start: str = "2020-01-01",
    end: str = "2025-01-01",
    config: str = "configs/development.yaml",
    initial_cash: float = 10_000.0,
    source: Literal["adapter", "synthetic", "db"] = typer.Option(
        "adapter", "--source", help="Data source: adapter, synthetic, or db"
    ),
    walk_forward: bool = typer.Option(
        False, "--walk-forward", help="Run walk-forward analysis"
    ),
    window_months: int = typer.Option(
        12, "--window-months", help="In-sample window size (months)"
    ),
    step_months: int = typer.Option(
        3, "--step-months", help="Step size between windows (months)"
    ),
) -> None:
    """Run a backtest for the given symbol and strategy."""
    cfg = load_config(config)
    runner = BacktestRunner(cfg)

    from trading.strategy.registry import StrategyRegistry

    available = StrategyRegistry.list_strategies()
    if strategy not in available:
        typer.echo(f"Unknown strategy '{strategy}'. Available: {available}", err=True)
        raise typer.Exit(code=1)

    async def _run() -> None:
        if walk_forward:
            wf = WalkForwardAnalyzer(runner)
            windows = await wf.run(
                strategy_name=strategy,
                symbol=symbol,
                timeframe=timeframe,
                start=start,
                end=end,
                initial_cash=initial_cash,
                source=source,
                window_months=window_months,
                step_months=step_months,
            )
            summary = wf.summary(windows)
            typer.echo("\n=== Walk-Forward Analysis ===")
            for key, value in summary.items():
                typer.echo(f"  {key}: {value}")

            typer.echo("\n--- Per-Window Breakdown ---")
            for w in windows:
                is_net = w.in_sample_metrics.net_pnl
                oos_net = w.out_of_sample_metrics.net_pnl
                typer.echo(
                    f"  Window {w.window_index}: "
                    f"IS ({w.in_sample_start} → {w.in_sample_end}) "
                    f"IS PnL={is_net:.2f} | "
                    f"OOS ({w.out_of_sample_start} → {w.out_of_sample_end}) "
                    f"OOS PnL={oos_net:.2f} "
                    f"OOS trades={w.out_of_sample_metrics.total_trades}"
                )
        else:
            metrics = await runner.run(
                strategy_name=strategy,
                symbol=symbol,
                timeframe=timeframe,
                start=start,
                end=end,
                initial_cash=initial_cash,
                source=source,
            )
            typer.echo("\n=== Backtest Results ===")
            for key, value in metrics.summary().items():
                typer.echo(f"  {key}: {value}")

            if metrics.total_trades > 0:
                typer.echo("\n--- Stop Analysis ---")
                from trading.backtest.stop_analysis import compute_stop_analysis

                trade_records = []
                for _, row in metrics.trades.iterrows():
                    from trading.backtest.backtest_types import ClosedTrade

                    trade_records.append(
                        ClosedTrade(
                            symbol=row.get("symbol", symbol),
                            side=row.get("side", "buy"),
                            entry_time=row["entry_time"],
                            exit_time=row["exit_time"],
                            entry_price=row["entry_price"],
                            exit_price=row["exit_price"],
                            quantity=row["quantity"],
                            gross_pnl=row["gross_pnl"],
                            net_pnl=row["net_pnl"],
                            commission=row["commission"],
                            slippage_cost=row["slippage_cost"],
                            exit_reason=row["exit_reason"],
                            mae=row["mae"],
                            mfe=row["mfe"],
                            bars_held=row["bars_held"],
                        )
                    )
                sa = compute_stop_analysis(trade_records)
                stop_pct = sa.stop_hit_rate * 100
                tp_pct = sa.take_profit_hit_rate * 100
                typer.echo(f"  Stop hits: {sa.stop_hit_count}/{sa.total_trades} ({stop_pct:.0f}%)")
                typer.echo(
                    f"  TP hits: {sa.take_profit_hit_count}/{sa.total_trades} ({tp_pct:.0f}%)"
                )
                typer.echo(f"  Avg bars held: {sa.avg_bars_held:.1f}")
                typer.echo(f"  Avg R:R: {sa.overall_avg_rr:.2f}")

                typer.echo("\n--- MAE/MFE ---")
                from trading.backtest.excursion import compute_excursion

                exc = compute_excursion(trade_records)
                typer.echo(f"  Avg MAE: {exc.avg_mae:.4f}")
                typer.echo(f"  Avg MFE: {exc.avg_mfe:.4f}")
                typer.echo(f"  Max MAE: {exc.max_mae:.4f}")
                typer.echo(f"  Max MFE: {exc.max_mfe:.4f}")

                typer.echo("\n--- Regime Report ---")
                # Build a rough price df from trades
                import pandas as pd

                from trading.backtest.regime_report import compute_regime_report

                all_prices: list[float] = []
                dates = pd.date_range(start=start, end=end, freq="D")
                for d in dates:
                    all_prices.append(100.0 + (d - dates[0]).days * 0.01)
                price_df = pd.DataFrame(
                    {
                        "close": all_prices,
                        "high": [p + 1 for p in all_prices],
                        "low": [p - 1 for p in all_prices],
                    },
                    index=dates,
                )
                rr = compute_regime_report(trade_records, price_df)
                for r in rr:
                    wr_pct = r.win_rate * 100
                    typer.echo(
                        f"  {r.regime}: {r.trade_count} trades, "
                        f"PnL={r.net_pnl:.2f}, WR={wr_pct:.0f}%"
                    )

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


@app.command()
def sentiment_ingest(
    config: str = "configs/development.yaml",
) -> None:
    """Run the sentiment ingester service."""
    cfg = load_config(config)
    provider_cfg = cfg.sentiment.provider
    repo = SentimentRepository(cfg.database)

    async def _run() -> None:
        await repo.connect()
        await repo.ensure_schema()
        ingester = SentimentIngester(
            config=provider_cfg,
            repository=repo,
        )
        await ingester.run_forever()

    try:
        asyncio.run(_run())
    except KeyboardInterrupt:
        typer.echo("\nSentiment ingester stopped")


if __name__ == "__main__":
    app()
