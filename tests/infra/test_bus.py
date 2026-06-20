import pytest

from trading.core.enums import Side
from trading.core.events import (
    BarEvent,
    CommandEvent,
    FillEvent,
    OrderEvent,
    RiskBlockEvent,
    SentimentEvent,
    SignalEvent,
)


@pytest.mark.asyncio
class TestEventBus:
    async def test_signal_event_round_trip(self, bus, sample_signal) -> None:
        received = []
        bus.subscribe("signals:BTC/USDT", lambda e: received.append(e))
        await bus.start()
        await bus.publish("signals:BTC/USDT", sample_signal)
        await bus._redis.ping()
        await bus._redis.time()
        await bus._pubsub.get_message(timeout=2.0) if bus._pubsub else None
        import asyncio

        await asyncio.sleep(0.2)
        assert len(received) == 1
        ev = received[0]
        assert isinstance(ev, SignalEvent)
        assert ev.symbol == "BTC/USDT"
        assert ev.side == Side.BUY
        assert ev.confidence == 0.8
        assert ev.strategy_name == "sma_crossover"

    async def test_order_event_round_trip(self, bus, sample_order) -> None:
        received = []
        bus.subscribe("orders:BTC/USDT", lambda e: received.append(e))
        await bus.start()
        await bus.publish("orders:BTC/USDT", sample_order)
        import asyncio

        await asyncio.sleep(0.2)
        assert len(received) == 1
        ev = received[0]
        assert isinstance(ev, OrderEvent)
        assert ev.quantity == 1.0

    async def test_fill_event_round_trip(self, bus, sample_fill) -> None:
        received = []
        bus.subscribe("fills:BTC/USDT", lambda e: received.append(e))
        await bus.start()
        await bus.publish("fills:BTC/USDT", sample_fill)
        import asyncio

        await asyncio.sleep(0.2)
        assert len(received) == 1
        ev = received[0]
        assert isinstance(ev, FillEvent)
        assert ev.fill_price == 50000.0

    async def test_bar_event_round_trip(self, bus, sample_bar) -> None:
        received = []
        bus.subscribe("bars:BTC/USDT", lambda e: received.append(e))
        await bus.start()
        await bus.publish("bars:BTC/USDT", sample_bar)
        import asyncio

        await asyncio.sleep(0.2)
        assert len(received) == 1
        ev = received[0]
        assert isinstance(ev, BarEvent)
        assert ev.close == 50500.0

    async def test_sentiment_event_round_trip(self, bus, sample_sentiment) -> None:
        received = []
        bus.subscribe("sentiment:BTC/USDT", lambda e: received.append(e))
        await bus.start()
        await bus.publish("sentiment:BTC/USDT", sample_sentiment)
        import asyncio

        await asyncio.sleep(0.2)
        assert len(received) == 1
        ev = received[0]
        assert isinstance(ev, SentimentEvent)
        assert ev.score == 0.65
        assert ev.source == "alpha_vantage"

    async def test_command_event_round_trip(self, bus, sample_command) -> None:
        received = []
        bus.subscribe("commands:*", lambda e: received.append(e))
        await bus.start()
        await bus.publish("commands:*", sample_command)
        import asyncio

        await asyncio.sleep(0.2)
        assert len(received) == 1
        ev = received[0]
        assert isinstance(ev, CommandEvent)
        assert ev.command == "add_symbol"
        assert ev.payload == {"symbol": "ETH/USDT", "timeframe": "1d"}

    async def test_risk_block_event_round_trip(self, bus, sample_risk_block) -> None:
        received = []
        bus.subscribe("risk_block:BTC/USDT", lambda e: received.append(e))
        await bus.start()
        await bus.publish("risk_block:BTC/USDT", sample_risk_block)
        import asyncio

        await asyncio.sleep(0.2)
        assert len(received) == 1
        ev = received[0]
        assert isinstance(ev, RiskBlockEvent)
        assert ev.reason == "Max drawdown exceeded"
        assert ev.rule_that_blocked == "max_drawdown"

    async def test_schema_version_present(self, sample_signal) -> None:
        assert sample_signal.event_schema_version == 1
        payload = sample_signal.model_dump_json()
        restored = SignalEvent.model_validate_json(payload)
        assert restored.event_schema_version == 1

    async def test_event_carries_correlation_id(self, bus, sample_signal) -> None:
        sample_signal.correlation_id = "test-corr-123"
        received = []
        bus.subscribe("signals:BTC/USDT", lambda e: received.append(e))
        await bus.start()
        await bus.publish("signals:BTC/USDT", sample_signal)
        import asyncio

        await asyncio.sleep(0.2)
        assert len(received) == 1
        assert received[0].correlation_id == "test-corr-123"

    async def test_dead_letter_bad_payload(self, bus) -> None:
        received = []
        bus.subscribe("signals:BTC/USDT", lambda e: received.append(e))
        await bus.start()
        # Publish invalid JSON — system should not crash
        await bus._redis.publish("signals:BTC/USDT", "not valid json{{{")
        import asyncio

        await asyncio.sleep(0.2)
        # Handler should not have been called
        assert len(received) == 0

    async def test_dead_letter_unknown_topic(self, bus) -> None:
        received = []
        bus.subscribe("signals:BTC/USDT", lambda e: received.append(e))
        await bus.start()
        # Publish on a topic with no handler — silently dropped
        await bus.publish(
            "unknown:test",
            SignalEvent(
                symbol="BTC/USDT",
                side=Side.BUY,
                confidence=0.7,
                strategy_name="test",
                source="test",
            ),
        )
        import asyncio

        await asyncio.sleep(0.2)
        # Handler for signals should not have been called
        assert len(received) == 0

    async def test_multiple_handlers_on_same_topic(self, bus, sample_signal) -> None:
        received1 = []
        received2 = []
        bus.subscribe("signals:BTC/USDT", lambda e: received1.append(e))
        bus.subscribe("signals:BTC/USDT", lambda e: received2.append(e))
        # Directly test _process_message dispatch logic (circumvents fakeredis
        # pubsub multi-delivery limitation in in-process mode)
        payload = sample_signal.model_dump_json()
        await bus._process_message("signals:BTC/USDT", payload)
        assert len(received1) == 1
        assert len(received2) == 1

    async def test_events_isolated_by_topic(self, bus, sample_bar) -> None:
        signal_received = []
        bar_received = []
        bus.subscribe("signals:BTC/USDT", lambda e: signal_received.append(e))
        bus.subscribe("bars:BTC/USDT", lambda e: bar_received.append(e))
        await bus.start()
        await bus.publish("bars:BTC/USDT", sample_bar)
        import asyncio

        await asyncio.sleep(0.2)
        assert len(signal_received) == 0
        assert len(bar_received) == 1
