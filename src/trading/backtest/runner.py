import pandas as pd
import vectorbt as vbt

from trading.backtest.metrics import BacktestMetrics
from trading.core.config import TradingConfig
from trading.strategy.sma_crossover import _sma as compute_sma


class BacktestRunner:
    def __init__(self, config: TradingConfig) -> None:
        self.config = config

    async def run(
        self,
        symbol: str = "BTC/USDT",
        start: str = "2020-01-01",
        end: str = "2025-01-01",
        initial_cash: float = 10_000.0,
    ) -> BacktestMetrics:
        start_dt = pd.Timestamp(start)
        end_dt = pd.Timestamp(end)
        index = pd.date_range(start=start_dt, end=end_dt, freq="D")
        close = pd.Series(100.0 + (index - start_dt).days * 0.01, index=index)

        df = pd.DataFrame({"close": close, "symbol": symbol}, index=index)

        pf = vbt.Portfolio.from_orders(
            close=close,
            size=self._compute_signals(df),
            price=close,
            init_cash=initial_cash,
            freq="D",
        )

        return BacktestMetrics(
            total_return=pf.total_return(),
            sharpe_ratio=pf.sharpe_ratio(),
            max_drawdown=pf.max_drawdown(),
            sortino_ratio=pf.sortino_ratio(),
            total_trades=pf.trades.count(),
            win_rate=pf.trades.win_rate(),
            total_pnl=pf.total_profit(),
            equity_curve=pf.value(),
            trades=pf.trades.records,
        )

    def _compute_signals(self, df: pd.DataFrame) -> pd.Series:
        fast_sma = compute_sma(df, length=20)
        slow_sma = compute_sma(df, length=50)

        entries = (fast_sma > slow_sma) & (fast_sma.shift(1) <= slow_sma.shift(1))
        exits = (fast_sma < slow_sma) & (fast_sma.shift(1) >= slow_sma.shift(1))

        position = pd.Series(0, index=df.index)
        in_position = False
        for i in range(len(df)):
            if not in_position and entries.iloc[i]:
                position.iloc[i] = 1
                in_position = True
            elif in_position and exits.iloc[i]:
                position.iloc[i] = -1
                in_position = False

        return position
