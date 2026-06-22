import pandas as pd
import pandas_ta as ta

from trading.core.enums import Side
from trading.core.events import SentimentEvent, SignalEvent
from trading.strategy.base import Strategy, StrategyResult
from trading.strategy.registry import StrategyRegistry


@StrategyRegistry.register
class RSIMeanReversionStrategy(Strategy):
    name = "rsi_mean_reversion"

    def __init__(
        self,
        rsi_period: int = 14,
        oversold: float = 30.0,
        overbought: float = 70.0,
        rr_ratio: float = 2.0,
    ) -> None:
        self.rsi_period = rsi_period
        self.oversold = oversold
        self.overbought = overbought
        self.rr_ratio = rr_ratio
        self._lookback = rsi_period + 5

    async def initialize(self) -> None:
        pass

    async def on_data(
        self, df: pd.DataFrame, sentiment: SentimentEvent | None = None  # noqa: ARG002
    ) -> StrategyResult:
        if len(df) < self._lookback + 1:
            return StrategyResult()

        close = df["close"]
        rsi_series = ta.rsi(close, length=self.rsi_period)
        if rsi_series is None or len(rsi_series) < 2:
            return StrategyResult()

        current_rsi = float(rsi_series.iloc[-1])
        prev_rsi = float(rsi_series.iloc[-2])

        if pd.isna(current_rsi) or pd.isna(prev_rsi):
            return StrategyResult()

        symbol = ""
        if "symbol" in df.columns:
            symbol = str(df["symbol"].iloc[-1])

        entry_price = float(close.iloc[-1])
        low = df.get("low", close)
        high = df.get("high", close)

        if prev_rsi > self.oversold and current_rsi <= self.oversold:
            stop_loss = float(low.iloc[-self._lookback:].min())
            stop_distance = entry_price - stop_loss
            if stop_distance <= 0:
                return StrategyResult()
            take_profit = entry_price + stop_distance * self.rr_ratio
            return StrategyResult(
                SignalEvent(
                    symbol=symbol,
                    side=Side.BUY,
                    confidence=0.7,
                    strategy_name=self.name,
                    source=self.name,
                    entry_price=entry_price,
                    stop_loss_price=stop_loss,
                    take_profit_price=take_profit,
                )
            )

        if prev_rsi < self.overbought and current_rsi >= self.overbought:
            stop_loss = float(high.iloc[-self._lookback:].max())
            stop_distance = stop_loss - entry_price
            if stop_distance <= 0:
                return StrategyResult()
            take_profit = entry_price - stop_distance * self.rr_ratio
            return StrategyResult(
                SignalEvent(
                    symbol=symbol,
                    side=Side.SELL,
                    confidence=0.7,
                    strategy_name=self.name,
                    source=self.name,
                    entry_price=entry_price,
                    stop_loss_price=stop_loss,
                    take_profit_price=take_profit,
                )
            )

        return StrategyResult()
