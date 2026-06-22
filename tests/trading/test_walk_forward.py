import pytest

from trading.backtest.runner import BacktestRunner
from trading.backtest.walk_forward import WalkForwardAnalyzer, _build_windows
from trading.core.config import TradingConfig


def _config() -> TradingConfig:
    return TradingConfig()


class TestBuildWindows:
    def test_build_windows_returns_list(self) -> None:
        windows = _build_windows("2020-01-01", "2022-01-01", 12, 3)
        assert len(windows) > 0

    def test_each_window_has_four_dates(self) -> None:
        windows = _build_windows("2020-01-01", "2022-01-01", 12, 3)
        for w in windows:
            assert len(w) == 4
            assert w[0] < w[1]
            assert w[1] <= w[2]
            assert w[2] < w[3]

    def test_no_windows_if_range_too_short(self) -> None:
        windows = _build_windows("2020-01-01", "2020-06-01", 12, 3)
        assert len(windows) == 0

    def test_windows_dont_exceed_end_date(self) -> None:
        windows = _build_windows("2020-01-01", "2021-06-01", 12, 3)
        for w in windows:
            assert w[3] <= "2021-06-01"


@pytest.mark.asyncio
class TestWalkForwardAnalyzer:
    async def test_run_returns_windows(self) -> None:
        runner = BacktestRunner(_config())
        wf = WalkForwardAnalyzer(runner)
        windows = await wf.run(
            strategy_name="sma_crossover",
            symbol="BTC/USDT",
            timeframe="1d",
            start="2020-01-01",
            end="2022-01-01",
            initial_cash=10_000.0,
            source="synthetic",
            window_months=12,
            step_months=3,
        )
        assert len(windows) > 0

    async def test_each_window_has_metrics(self) -> None:
        runner = BacktestRunner(_config())
        wf = WalkForwardAnalyzer(runner)
        windows = await wf.run(
            strategy_name="sma_crossover",
            symbol="BTC/USDT",
            timeframe="1d",
            start="2020-01-01",
            end="2022-01-01",
            initial_cash=10_000.0,
            source="synthetic",
            window_months=12,
            step_months=3,
        )
        for w in windows:
            assert w.in_sample_metrics is not None
            assert w.out_of_sample_metrics is not None

    async def test_summary_returns_dict(self) -> None:
        runner = BacktestRunner(_config())
        wf = WalkForwardAnalyzer(runner)
        windows = await wf.run(
            strategy_name="sma_crossover",
            symbol="BTC/USDT",
            timeframe="1d",
            start="2020-01-01",
            end="2022-01-01",
            initial_cash=10_000.0,
            source="synthetic",
            window_months=12,
            step_months=3,
        )
        s = wf.summary(windows)
        assert isinstance(s, dict)
        assert "num_windows" in s
        assert "avg_in_sample_sharpe" in s
        assert "avg_out_of_sample_sharpe" in s
