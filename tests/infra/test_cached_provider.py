import pytest

from trading.data.news.cached import CachedNewsProvider


@pytest.mark.asyncio
class TestCachedNewsProvider:
    async def test_get_sentiment_returns_event(self) -> None:
        provider = CachedNewsProvider()
        event = await provider.get_sentiment("BTC/USDT")
        assert event is not None
        assert event.symbol == "BTC/USDT"
        assert -1.0 <= event.score <= 1.0
        assert event.source == "cached"
        await provider.close()

    async def test_get_sentiment_no_fixture(self) -> None:
        provider = CachedNewsProvider()
        event = await provider.get_sentiment("UNKNOWN/PAIR")
        assert event is None
        await provider.close()

    async def test_get_sentiment_multiple_calls(self) -> None:
        provider = CachedNewsProvider()
        scores = set()
        for _ in range(20):
            event = await provider.get_sentiment("BTC/USDT")
            assert event is not None
            scores.add(round(event.score, 1))
        assert len(scores) > 1
        await provider.close()

    async def test_get_sentiment_eth(self) -> None:
        provider = CachedNewsProvider()
        event = await provider.get_sentiment("ETH/USDT")
        assert event is not None
        assert event.symbol == "ETH/USDT"
        assert event.source == "cached"
        await provider.close()

    async def test_rate_limit_config(self) -> None:
        assert CachedNewsProvider.rate_limit.capacity == 1000
