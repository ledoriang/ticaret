import pandas as pd
import pytest

from trading.core.enums import Side
from trading.core.events import SentimentEvent
from trading.strategy.sentiment_enhanced import SentimentEnhancedStrategy


def _ohlc(close: float) -> dict[str, float]:
    return {"open": close - 0.5, "high": close + 1.0, "low": close - 1.0, "close": close}


@pytest.mark.asyncio
class TestSentimentEnhancedStrategy:
    async def test_buy_signal_with_bullish_sentiment(self) -> None:
        strat = SentimentEnhancedStrategy(fast_period=3, slow_period=5, atr_period=3)
        data = [100.0] * 10 + [200.0]
        rows = [_ohlc(v) for v in data]
        df = pd.DataFrame(rows)
        sentiment = SentimentEvent(
            symbol="SYM", score=0.5, confidence=0.8, source="test"
        )
        result = await strat.on_data(df, sentiment=sentiment)
        assert result.signal is not None
        assert result.signal.side == Side.BUY

    async def test_buy_signal_with_neutral_sentiment(self) -> None:
        """Neutral sentiment (score >= min_sentiment) should not suppress."""
        strat = SentimentEnhancedStrategy(
            fast_period=3, slow_period=5, atr_period=3, min_sentiment=-0.2
        )
        data = [100.0] * 10 + [200.0]
        rows = [_ohlc(v) for v in data]
        df = pd.DataFrame(rows)
        sentiment = SentimentEvent(
            symbol="SYM", score=0.0, confidence=0.3, source="test"
        )
        result = await strat.on_data(df, sentiment=sentiment)
        assert result.signal is not None
        assert result.signal.side == Side.BUY

    async def test_suppressed_when_bearish_and_low_confidence(self) -> None:
        """Signal suppressed when sentiment.score < min_sentiment AND
        confidence < min_confidence."""
        strat = SentimentEnhancedStrategy(
            fast_period=3, slow_period=5, atr_period=3,
            min_sentiment=-0.2, min_confidence=0.6,
        )
        data = [100.0] * 10 + [200.0]
        rows = [_ohlc(v) for v in data]
        df = pd.DataFrame(rows)
        sentiment = SentimentEvent(
            symbol="SYM", score=-0.5, confidence=0.3, source="test",
        )
        result = await strat.on_data(df, sentiment=sentiment)
        assert result.signal is None

    async def test_not_suppressed_when_bearish_but_high_confidence(self) -> None:
        """Bearish score but high confidence — still fires (only one condition met)."""
        strat = SentimentEnhancedStrategy(
            fast_period=3, slow_period=5, atr_period=3,
            min_sentiment=-0.2, min_confidence=0.6,
        )
        data = [100.0] * 10 + [200.0]
        rows = [_ohlc(v) for v in data]
        df = pd.DataFrame(rows)
        sentiment = SentimentEvent(
            symbol="SYM", score=-0.5, confidence=0.8, source="test",
        )
        result = await strat.on_data(df, sentiment=sentiment)
        assert result.signal is not None
        assert result.signal.side == Side.BUY

    async def test_not_suppressed_when_no_sentiment(self) -> None:
        """No sentiment event — acts like baseline SMA."""
        strat = SentimentEnhancedStrategy(fast_period=3, slow_period=5, atr_period=3)
        data = [100.0] * 10 + [200.0]
        rows = [_ohlc(v) for v in data]
        df = pd.DataFrame(rows)
        result = await strat.on_data(df, sentiment=None)
        assert result.signal is not None
        assert result.signal.side == Side.BUY

    async def test_sell_signal_with_sentiment(self) -> None:
        strat = SentimentEnhancedStrategy(fast_period=3, slow_period=5, atr_period=3)
        data = [200.0] * 10 + [100.0]
        rows = [_ohlc(v) for v in data]
        df = pd.DataFrame(rows)
        sentiment = SentimentEvent(
            symbol="SYM", score=-0.3, confidence=0.7, source="test"
        )
        result = await strat.on_data(df, sentiment=sentiment)
        assert result.signal is not None
        assert result.signal.side == Side.SELL

    async def test_no_cross_no_signal(self) -> None:
        strat = SentimentEnhancedStrategy(fast_period=3, slow_period=5, atr_period=3)
        data = [100.0, 101.0, 102.0, 103.0, 104.0, 105.0]
        rows = [_ohlc(v) for v in data]
        df = pd.DataFrame(rows)
        result = await strat.on_data(df)
        assert result.signal is None

    async def test_suppressed_when_bearish_and_low_confidence_sell(self) -> None:
        """SELL signal should also be suppressible by sentiment."""
        strat = SentimentEnhancedStrategy(
            fast_period=3, slow_period=5, atr_period=3,
            min_sentiment=-0.2, min_confidence=0.6,
        )
        data = [200.0] * 10 + [100.0]
        rows = [_ohlc(v) for v in data]
        df = pd.DataFrame(rows)
        sentiment = SentimentEvent(
            symbol="SYM", score=-0.5, confidence=0.3, source="test",
        )
        result = await strat.on_data(df, sentiment=sentiment)
        assert result.signal is None

    async def test_signal_carries_atr_stop(self) -> None:
        strat = SentimentEnhancedStrategy(fast_period=3, slow_period=5, atr_period=3)
        data = [50.0, 50.0, 50.0, 50.0, 50.0, 50.0, 50.0, 50.0, 50.0, 50.0, 50.0, 60.0]
        rows = [_ohlc(v) for v in data]
        df = pd.DataFrame(rows)
        result = await strat.on_data(df)
        assert result.signal is not None
        assert result.signal.entry_price == 60.0
        assert result.signal.stop_loss_price == 50.0
        assert result.signal.take_profit_price == 80.0

    async def test_configurable_thresholds(self) -> None:
        strat = SentimentEnhancedStrategy(min_sentiment=0.0, min_confidence=0.8)
        assert strat.min_sentiment == 0.0
        assert strat.min_confidence == 0.8
