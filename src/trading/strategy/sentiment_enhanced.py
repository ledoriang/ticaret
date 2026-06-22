import pandas as pd

from trading.core.enums import Side
from trading.core.events import SentimentEvent, SignalEvent
from trading.strategy.base import Strategy, StrategyResult
from trading.strategy.registry import StrategyRegistry


def _sma(series: pd.Series, length: int) -> pd.Series:
    return series.rolling(window=length).mean()


def _atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    high = df.get("high", df["close"])
    low = df.get("low", df["close"])
    close = df["close"]
    tr = pd.concat(
        [
            high - low,
            (high - close.shift(1)).abs(),
            (low - close.shift(1)).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return tr.rolling(window=period).mean()


@StrategyRegistry.register
class SentimentEnhancedStrategy(Strategy):
    name = "sentiment_enhanced"

    def __init__(
        self,
        fast_period: int = 20,
        slow_period: int = 50,
        atr_period: int = 14,
        atr_multiplier: float = 2.0,
        rr_ratio: float = 2.0,
        min_sentiment: float = -0.2,
        min_confidence: float = 0.6,
    ) -> None:
        self.fast_period = fast_period
        self.slow_period = slow_period
        self.atr_period = atr_period
        self.atr_multiplier = atr_multiplier
        self.rr_ratio = rr_ratio
        self.min_sentiment = min_sentiment
        self.min_confidence = min_confidence

    async def initialize(self) -> None:
        pass

    async def on_data(
        self, df: pd.DataFrame, sentiment: SentimentEvent | None = None
    ) -> StrategyResult:
        signal = self._compute_sma_signal(df)
        if signal is None:
            return StrategyResult()

        if self._is_suppressed_by_sentiment(sentiment):
            return StrategyResult()

        return StrategyResult(signal)

    def _compute_sma_signal(self, df: pd.DataFrame) -> SignalEvent | None:
        fast_sma = _sma(df["close"], length=self.fast_period)
        slow_sma = _sma(df["close"], length=self.slow_period)

        if len(fast_sma) < 2 or len(slow_sma) < 2:
            return None

        prev_fast = fast_sma.iloc[-2]
        curr_fast = fast_sma.iloc[-1]
        prev_slow = slow_sma.iloc[-2]
        curr_slow = slow_sma.iloc[-1]

        symbol = ""
        if "symbol" in df.columns:
            symbol = str(df["symbol"].iloc[-1])

        if pd.isna(prev_fast) or pd.isna(curr_fast) or pd.isna(prev_slow) or pd.isna(curr_slow):
            return None

        entry_price = float(df["close"].iloc[-1])
        atr_series = _atr(df, period=self.atr_period)
        if len(atr_series) < 2:
            return None
        atr_value = float(atr_series.iloc[-1])
        if pd.isna(atr_value) or atr_value <= 0:
            return None
        stop_distance = atr_value * self.atr_multiplier

        if prev_fast <= prev_slow and curr_fast > curr_slow:
            return SignalEvent(
                symbol=symbol,
                side=Side.BUY,
                confidence=0.7,
                strategy_name=self.name,
                source=self.name,
                entry_price=entry_price,
                stop_loss_price=entry_price - stop_distance,
                take_profit_price=entry_price + stop_distance * self.rr_ratio,
            )

        if prev_fast >= prev_slow and curr_fast < curr_slow:
            return SignalEvent(
                symbol=symbol,
                side=Side.SELL,
                confidence=0.7,
                strategy_name=self.name,
                source=self.name,
                entry_price=entry_price,
                stop_loss_price=entry_price + stop_distance,
                take_profit_price=entry_price - stop_distance * self.rr_ratio,
            )

        return None

    def _is_suppressed_by_sentiment(
        self, sentiment: SentimentEvent | None
    ) -> bool:
        if sentiment is None:
            return False
        if sentiment.score >= self.min_sentiment:
            return False
        return sentiment.confidence < self.min_confidence
