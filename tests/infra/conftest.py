from unittest.mock import patch

import fakeredis.aioredis
import pytest

from trading.core.config import RedisConfig
from trading.core.enums import AssetClass, OrderType, Side
from trading.core.events import (
    BarEvent,
    CommandEvent,
    FillEvent,
    OrderEvent,
    RiskBlockEvent,
    SentimentEvent,
    SignalEvent,
)
from trading.orchestration.bus import EventBus


@pytest.fixture
def redis_config() -> RedisConfig:
    return RedisConfig(host="localhost", port=6379)


@pytest.fixture
def fake_redis_patch() -> None:
    pass


@pytest.fixture
async def bus(redis_config: RedisConfig) -> EventBus:
    with patch("trading.orchestration.bus.aioredis.Redis", fakeredis.aioredis.FakeRedis):
        eb = EventBus(redis_config)
        yield eb
        await eb.stop()


@pytest.fixture
def sample_signal() -> SignalEvent:
    return SignalEvent(
        symbol="BTC/USDT",
        side=Side.BUY,
        confidence=0.8,
        strategy_name="sma_crossover",
        asset_class=AssetClass.CRYPTO,
        source="test",
    )


@pytest.fixture
def sample_order() -> OrderEvent:
    return OrderEvent(
        symbol="BTC/USDT",
        side=Side.BUY,
        order_type=OrderType.MARKET,
        quantity=1.0,
        price=50000.0,
        asset_class=AssetClass.CRYPTO,
        source="test",
    )


@pytest.fixture
def sample_fill() -> FillEvent:
    return FillEvent(
        symbol="BTC/USDT",
        side=Side.BUY,
        quantity=1.0,
        fill_price=50000.0,
        commission=50.0,
        asset_class=AssetClass.CRYPTO,
        source="test",
    )


@pytest.fixture
def sample_bar() -> BarEvent:
    return BarEvent(
        symbol="BTC/USDT",
        open=49000.0,
        high=51000.0,
        low=48500.0,
        close=50500.0,
        volume=1000.0,
        asset_class=AssetClass.CRYPTO,
        source="test",
    )


@pytest.fixture
def sample_sentiment() -> SentimentEvent:
    return SentimentEvent(
        symbol="BTC/USDT",
        score=0.65,
        confidence=0.8,
        source="alpha_vantage",
        summary="Bitcoin ETF inflows surge",
        asset_class=AssetClass.CRYPTO,
    )


@pytest.fixture
def sample_command() -> CommandEvent:
    return CommandEvent(
        command="add_symbol",
        payload={"symbol": "ETH/USDT", "timeframe": "1d"},
        source="test",
    )


@pytest.fixture
def sample_risk_block() -> RiskBlockEvent:
    return RiskBlockEvent(
        original_signal=SignalEvent(
            symbol="BTC/USDT",
            side=Side.BUY,
            confidence=0.8,
            strategy_name="sma_crossover",
            asset_class=AssetClass.CRYPTO,
            source="test",
        ),
        reason="Max drawdown exceeded",
        rule_that_blocked="max_drawdown",
        source="test",
    )
