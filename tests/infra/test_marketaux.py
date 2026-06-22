import pytest
import respx

from trading.data.news.marketaux import MarketauxProvider


@pytest.mark.asyncio
class TestMarketauxProvider:
    @respx.mock
    async def test_get_sentiment_returns_event(self) -> None:
        provider = MarketauxProvider(api_token="test-token")
        url = "https://api.marketaux.com/v1/news/all"
        respx.get(url).respond(
            json={
                "data": [
                    {
                        "title": "Bitcoin rallies on ETF news",
                        "entities": [
                            {
                                "symbol": "BTC",
                                "sentiment_score": 0.75,
                            }
                        ],
                    },
                    {
                        "title": "Crypto market overview",
                        "entities": [
                            {
                                "symbol": "BTC",
                                "sentiment_score": 0.55,
                            }
                        ],
                    },
                ],
                "meta": {"found": 2},
            }
        )

        event = await provider.get_sentiment("BTC/USDT")
        assert event is not None
        assert event.symbol == "BTC/USDT"
        assert event.score > 0
        assert event.source == "marketaux"
        await provider.close()

    @respx.mock
    async def test_get_sentiment_no_data(self) -> None:
        provider = MarketauxProvider(api_token="test-token")
        url = "https://api.marketaux.com/v1/news/all"
        respx.get(url).respond(json={"data": [], "meta": {"found": 0}})

        event = await provider.get_sentiment("BTC/USDT")
        assert event is None
        await provider.close()

    @respx.mock
    async def test_get_sentiment_no_entities(self) -> None:
        provider = MarketauxProvider(api_token="test-token")
        url = "https://api.marketaux.com/v1/news/all"
        respx.get(url).respond(
            json={
                "data": [
                    {
                        "title": "Bitcoin news",
                        "entities": [],
                    }
                ],
                "meta": {"found": 1},
            }
        )

        event = await provider.get_sentiment("BTC/USDT")
        assert event is not None
        assert event.score == 0.0
        await provider.close()

    @respx.mock
    async def test_raise_when_quota_exhausted(self) -> None:
        provider = MarketauxProvider(api_token="test-token")
        for _ in range(100):
            provider.rate_limit.try_consume()

        from trading.data.news.base import RateLimitError

        with pytest.raises(RateLimitError):
            await provider.get_sentiment("BTC/USDT")
        await provider.close()

    async def test_rate_limit_config(self) -> None:
        assert MarketauxProvider.rate_limit.capacity == 100

    async def test_symbol_mapping(self) -> None:
        from trading.data.news.marketaux import _map_symbol

        assert _map_symbol("BTC/USDT") == "BTCUSDT"
        assert _map_symbol("AAPL") == "AAPL"
