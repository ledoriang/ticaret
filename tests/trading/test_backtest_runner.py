import pytest

from trading.backtest.runner import BacktestRunner
from trading.core.config import TradingConfig


def _config() -> TradingConfig:
    return TradingConfig()


@pytest.mark.asyncio
class TestBacktestRunner:
    async def test_synthetic_sma_crossover_produces_trades(self) -> None:
        runner = BacktestRunner(_config())
        metrics = await runner.run(
            strategy_name="sma_crossover",
            symbol="BTC/USDT",
            timeframe="1d",
            start="2020-01-01",
            end="2022-01-01",
            initial_cash=10_000.0,
            source="synthetic",
        )
        assert metrics.total_trades > 0
        assert metrics.total_return != 0.0
        assert metrics.sharpe_ratio != 0.0
        assert metrics.net_pnl != 0.0
        assert metrics.total_trades == len(metrics.trades)

    async def test_synthetic_rsi_produces_trades(self) -> None:
        runner = BacktestRunner(_config())
        metrics = await runner.run(
            strategy_name="rsi_mean_reversion",
            symbol="BTC/USDT",
            timeframe="1d",
            start="2020-01-01",
            end="2022-01-01",
            initial_cash=10_000.0,
            source="synthetic",
        )
        assert metrics.total_trades > 0

    async def test_synthetic_sentiment_enhanced_produces_trades(self) -> None:
        runner = BacktestRunner(_config())
        metrics = await runner.run(
            strategy_name="sentiment_enhanced",
            symbol="BTC/USDT",
            timeframe="1d",
            start="2020-01-01",
            end="2022-01-01",
            initial_cash=10_000.0,
            source="synthetic",
        )
        assert metrics.total_trades > 0

    async def test_metrics_include_mae_mfe(self) -> None:
        runner = BacktestRunner(_config())
        metrics = await runner.run(
            strategy_name="sma_crossover",
            symbol="BTC/USDT",
            timeframe="1d",
            start="2020-01-01",
            end="2022-01-01",
            initial_cash=10_000.0,
            source="synthetic",
        )
        assert metrics.avg_mae >= 0
        assert metrics.avg_mfe >= 0

    async def test_metrics_include_stop_hit_rate(self) -> None:
        runner = BacktestRunner(_config())
        metrics = await runner.run(
            strategy_name="sma_crossover",
            symbol="BTC/USDT",
            timeframe="1d",
            start="2020-01-01",
            end="2022-01-01",
            initial_cash=10_000.0,
            source="synthetic",
        )
        assert 0.0 <= metrics.stop_hit_rate <= 1.0

    async def test_metrics_include_avg_bars_held(self) -> None:
        runner = BacktestRunner(_config())
        metrics = await runner.run(
            strategy_name="sma_crossover",
            symbol="BTC/USDT",
            timeframe="1d",
            start="2020-01-01",
            end="2022-01-01",
            initial_cash=10_000.0,
            source="synthetic",
        )
        assert metrics.avg_bars_held > 0

    async def test_trade_dataframe_contains_exit_reason(self) -> None:
        runner = BacktestRunner(_config())
        metrics = await runner.run(
            strategy_name="sma_crossover",
            symbol="BTC/USDT",
            timeframe="1d",
            start="2020-01-01",
            end="2022-01-01",
            initial_cash=10_000.0,
            source="synthetic",
        )
        if metrics.total_trades > 0:
            assert "exit_reason" in metrics.trades.columns
            assert "mae" in metrics.trades.columns
            assert "mfe" in metrics.trades.columns
            assert "bars_held" in metrics.trades.columns

    async def test_no_trades_on_short_data(self) -> None:
        runner = BacktestRunner(_config())
        metrics = await runner.run(
            strategy_name="sma_crossover",
            symbol="BTC/USDT",
            timeframe="1d",
            start="2020-01-01",
            end="2020-01-10",
            initial_cash=10_000.0,
            source="synthetic",
        )
        assert metrics.total_trades == 0

    async def test_summary_returns_dict(self) -> None:
        runner = BacktestRunner(_config())
        metrics = await runner.run(
            strategy_name="sma_crossover",
            symbol="BTC/USDT",
            timeframe="1d",
            start="2020-01-01",
            end="2022-01-01",
            initial_cash=10_000.0,
            source="synthetic",
        )
        s = metrics.summary()
        assert isinstance(s, dict)
        assert "total_return_pct" in s
        assert "total_trades" in s
        assert "net_pnl" in s
