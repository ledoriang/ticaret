import pandas as pd

from trading.core.enums import Side
from trading.core.events import SignalEvent
from trading.strategy.base import Strategy, StrategyResult
from trading.strategy.registry import StrategyRegistry


def _sma(series: pd.Series, length: int) -> pd.Series:
    return series.rolling(window=length).mean()


@StrategyRegistry.register
class SMACrossoverStrategy(Strategy):
    name = "sma_crossover"

    def __init__(self, fast_period: int = 20, slow_period: int = 50) -> None:
        self.fast_period = fast_period
        self.slow_period = slow_period

    async def initialize(self) -> None:
        pass

    async def on_data(self, df: pd.DataFrame) -> StrategyResult:
        fast_sma = _sma(df["close"], length=self.fast_period)
        slow_sma = _sma(df["close"], length=self.slow_period)

        if len(fast_sma) < 2 or len(slow_sma) < 2:
            return StrategyResult()

        prev_fast = fast_sma.iloc[-2]
        curr_fast = fast_sma.iloc[-1]
        prev_slow = slow_sma.iloc[-2]
        curr_slow = slow_sma.iloc[-1]

        symbol = ""
        if "symbol" in df.columns:
            symbol = str(df["symbol"].iloc[-1])

        if pd.isna(prev_fast) or pd.isna(curr_fast) or pd.isna(prev_slow) or pd.isna(curr_slow):
            return StrategyResult()

        if prev_fast <= prev_slow and curr_fast > curr_slow:
            return StrategyResult(
                SignalEvent(
                    symbol=symbol,
                    side=Side.BUY,
                    confidence=0.7,
                    strategy_name=self.name,
                    source=self.name,
                )
            )

        if prev_fast >= prev_slow and curr_fast < curr_slow:
            return StrategyResult(
                SignalEvent(
                    symbol=symbol,
                    side=Side.SELL,
                    confidence=0.7,
                    strategy_name=self.name,
                    source=self.name,
                )
            )

        return StrategyResult()
