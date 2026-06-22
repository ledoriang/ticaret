import pytest
import respx

from trading.data.news.finnhub import FinnhubProvider


@pytest.mark.asyncio
class TestFinnhubProvider:
    @respx.mock
    async def test_get_sentiment_returns_event(self) -> None:
        provider = FinnhubProvider(api_key="test-key")
        url = "https://finnhub.io/api/v1/news-sentiment"
        respx.get(url).respond(
            json={
                "buzz": {
                    "articlesInLastWeek": 42,
                    "weeklyAverage": 35.5,
                    "buzzScore": 1.2,
                },
                "companyNewsScore": 0.65,
                "sectorAverageBullishPercent": 55.0,
                "sectorAverageNewsScore": 0.5,
            }
        )

        event = await provider.get_sentiment("AAPL")
        assert event is not None
        assert event.symbol == "AAPL"
        assert event.source == "finnhub"
        assert event.confidence > 0
        await provider.close()

    @respx.mock
    async def test_get_sentiment_no_data(self) -> None:
        provider = FinnhubProvider(api_key="test-key")
        url = "https://finnhub.io/api/v1/news-sentiment"
        respx.get(url).respond(json={})

        event = await provider.get_sentiment("AAPL")
        assert event is None
        await provider.close()

    @respx.mock
    async def test_get_sentiment_partial_data(self) -> None:
        provider = FinnhubProvider(api_key="test-key")
        url = "https://finnhub.io/api/v1/news-sentiment"
        respx.get(url).respond(json={"companyNewsScore": 0.42})

        event = await provider.get_sentiment("AAPL")
        assert event is not None
        assert event.score == 0.42
        await provider.close()

    @respx.mock
    async def test_raise_when_quota_exhausted(self) -> None:
        provider = FinnhubProvider(api_key="test-key")
        for _ in range(30):
            provider.rate_limit.try_consume()

        from trading.data.news.base import RateLimitError

        with pytest.raises(RateLimitError):
            await provider.get_sentiment("AAPL")
        await provider.close()

    async def test_rate_limit_config(self) -> None:
        assert FinnhubProvider.rate_limit.capacity == 30

    async def test_symbol_mapping(self) -> None:
        from trading.data.news.finnhub import _map_symbol

        assert _map_symbol("AAPL") == "AAPL"
        assert _map_symbol("BTC/USDT") == "BTC"
        assert _map_symbol("SPY/USD") == "SPY"
