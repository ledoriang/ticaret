import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from trading.core.config import SentimentProviderConfig
from trading.data.sentiment_repository import SentimentRepository
from trading.orchestration.bus import EventBus
from trading.services.sentiment_ingester import SentimentIngester


@pytest.mark.asyncio
class TestSentimentFlow:
    async def test_ingester_publishes_to_bus(self) -> None:
        config = SentimentProviderConfig(
            provider="cached", symbols=["BTC/USDT"], poll_interval_seconds=1
        )
        bus = MagicMock(spec=EventBus)
        bus.publish = AsyncMock()

        ingester = SentimentIngester(config=config, event_bus=bus)
        await ingester.start()
        task = asyncio.create_task(ingester.run_forever())
        await asyncio.sleep(0.3)
        await ingester.stop()
        await task

        assert bus.publish.called
        topic = bus.publish.call_args[0][0]
        assert topic == "sentiment:BTC/USDT"

    async def test_ingester_writes_to_repository(self) -> None:
        config = SentimentProviderConfig(
            provider="cached", symbols=["BTC/USDT"], poll_interval_seconds=1
        )
        repo = MagicMock(spec=SentimentRepository)
        repo.insert = AsyncMock()

        ingester = SentimentIngester(config=config, repository=repo)
        await ingester.start()
        task = asyncio.create_task(ingester.run_forever())
        await asyncio.sleep(0.3)
        await ingester.stop()
        await task

        assert repo.insert.called

    async def test_ingester_start_gracefully_no_provider(self) -> None:
        config = SentimentProviderConfig(provider="nonexistent", symbols=["BTC/USDT"])
        ingester = SentimentIngester(config=config)
        await ingester.start()
        await ingester.stop()

    async def test_ingester_multiple_symbols(self) -> None:
        config = SentimentProviderConfig(
            provider="cached",
            symbols=["BTC/USDT", "ETH/USDT"],
            poll_interval_seconds=1,
        )
        bus = MagicMock(spec=EventBus)
        bus.publish = AsyncMock()

        ingester = SentimentIngester(config=config, event_bus=bus)
        await ingester.start()
        task = asyncio.create_task(ingester.run_forever())
        await asyncio.sleep(0.3)
        await ingester.stop()
        await task

        topics = {call[0][0] for call in bus.publish.call_args_list}
        assert "sentiment:BTC/USDT" in topics
        assert "sentiment:ETH/USDT" in topics
