import pytest

from trading.data.news.stockgeist import StockGeistProvider


@pytest.mark.asyncio
class TestStockGeistProvider:
    async def test_get_sentiment_returns_none(self) -> None:
        provider = StockGeistProvider(api_key="test-key")
        event = await provider.get_sentiment("AAPL")
        assert event is None
        await provider.close()

    async def test_rate_limit_config(self) -> None:
        assert StockGeistProvider.rate_limit.capacity == 10
