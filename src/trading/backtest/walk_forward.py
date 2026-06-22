from dataclasses import dataclass, field

import pandas as pd

from trading.backtest.metrics import BacktestMetrics
from trading.backtest.runner import BacktestRunner


@dataclass
class WalkForwardWindow:
    window_index: int
    in_sample_start: str
    in_sample_end: str
    out_of_sample_start: str
    out_of_sample_end: str
    in_sample_metrics: BacktestMetrics = field(default_factory=BacktestMetrics)
    out_of_sample_metrics: BacktestMetrics = field(default_factory=BacktestMetrics)


class WalkForwardAnalyzer:
    def __init__(self, runner: BacktestRunner) -> None:
        self.runner = runner

    async def run(
        self,
        strategy_name: str = "sma_crossover",
        symbol: str = "BTC/USDT",
        timeframe: str = "1d",
        start: str = "2020-01-01",
        end: str = "2025-01-01",
        initial_cash: float = 10_000.0,
        window_months: int = 12,
        step_months: int = 3,
        source: str = "adapter",
    ) -> list[WalkForwardWindow]:
        windows = _build_windows(start, end, window_months, step_months)
        results: list[WalkForwardWindow] = []

        for i, (is_start, is_end, oos_start, oos_end) in enumerate(windows):
            # In-sample run
            is_metrics = await self.runner.run(
                strategy_name=strategy_name,
                symbol=symbol,
                timeframe=timeframe,
                start=is_start,
                end=is_end,
                initial_cash=initial_cash,
                source=source,
            )

            # Out-of-sample run
            oos_metrics = await self.runner.run(
                strategy_name=strategy_name,
                symbol=symbol,
                timeframe=timeframe,
                start=oos_start,
                end=oos_end,
                initial_cash=initial_cash,
                source=source,
            )

            results.append(
                WalkForwardWindow(
                    window_index=i,
                    in_sample_start=is_start,
                    in_sample_end=is_end,
                    out_of_sample_start=oos_start,
                    out_of_sample_end=oos_end,
                    in_sample_metrics=is_metrics,
                    out_of_sample_metrics=oos_metrics,
                )
            )

        return results

    def summary(self, windows: list[WalkForwardWindow]) -> dict[str, float | int | str]:
        if not windows:
            return {}
        avg_is_sharpe = sum(w.in_sample_metrics.sharpe_ratio for w in windows) / len(windows)
        avg_oos_sharpe = sum(w.out_of_sample_metrics.sharpe_ratio for w in windows) / len(windows)
        avg_oos_return = sum(w.out_of_sample_metrics.total_return for w in windows) / len(windows)
        total_oos_trades = sum(w.out_of_sample_metrics.total_trades for w in windows)
        oos_win_rates = [
            w.out_of_sample_metrics.win_rate
            for w in windows
            if w.out_of_sample_metrics.total_trades > 0
        ]
        avg_oos_win_rate = sum(oos_win_rates) / len(oos_win_rates) if oos_win_rates else 0.0

        consistent_wins = sum(
            1 for w in windows if w.out_of_sample_metrics.net_pnl > 0
        )

        return {
            "num_windows": len(windows),
            "avg_in_sample_sharpe": round(avg_is_sharpe, 3),
            "avg_out_of_sample_sharpe": round(avg_oos_sharpe, 3),
            "avg_out_of_sample_return_pct": round(avg_oos_return * 100, 2),
            "total_out_of_sample_trades": total_oos_trades,
            "avg_out_of_sample_win_rate_pct": round(avg_oos_win_rate * 100, 1),
            "profitable_windows": consistent_wins,
            "pass_rate_pct": round(consistent_wins / len(windows) * 100, 1) if windows else 0.0,
        }


def _build_windows(
    start: str, end: str, window_months: int, step_months: int
) -> list[tuple[str, str, str, str]]:
    full_start = pd.Timestamp(start)
    full_end = pd.Timestamp(end)

    windows: list[tuple[str, str, str, str]] = []
    current = full_start

    while current + pd.DateOffset(months=window_months + step_months) <= full_end:
        is_start = current
        is_end = current + pd.DateOffset(months=window_months)
        oos_start = is_end
        oos_end = min(
            oos_start + pd.DateOffset(months=step_months),
            full_end,
        )

        windows.append(
            (
                is_start.strftime("%Y-%m-%d"),
                is_end.strftime("%Y-%m-%d"),
                oos_start.strftime("%Y-%m-%d"),
                oos_end.strftime("%Y-%m-%d"),
            )
        )

        current += pd.DateOffset(months=step_months)

    return windows
