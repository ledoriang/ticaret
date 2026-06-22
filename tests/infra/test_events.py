from trading.core.enums import Side
from trading.core.events import (
    BaseEvent,
    RiskBlockEvent,
    SentimentEvent,
    SignalEvent,
)


class TestBaseEvent:
    def test_event_id_generated(self) -> None:
        e = BaseEvent()
        assert len(e.event_id) == 32
        assert e.event_id is not None

    def test_correlation_id_default(self) -> None:
        e = BaseEvent()
        assert e.correlation_id == ""


class TestSentimentEvent:
    def test_sentiment_defaults(self) -> None:
        e = SentimentEvent(symbol="BTC")
        assert e.score == 0.0
        assert e.confidence == 0.0

    def test_sentiment_validation(self) -> None:
        e = SentimentEvent(symbol="BTC", score=0.8, confidence=0.9)
        assert e.score == 0.8
        assert e.confidence == 0.9


class TestRiskBlockEvent:
    def test_risk_block(self) -> None:
        signal = SignalEvent(symbol="BTC/USDT", side=Side.BUY, confidence=0.8, strategy_name="test")
        block = RiskBlockEvent(
            original_signal=signal,
            reason="Max drawdown exceeded",
            rule_that_blocked="MaxDrawdownRule",
        )
        assert block.reason == "Max drawdown exceeded"
