import pytest
import respx

from trading.data.news.alpha_vantage import AlphaVantageProvider


@pytest.mark.asyncio
class TestAlphaVantageProvider:
    @respx.mock
    async def test_get_sentiment_returns_event(self) -> None:
        provider = AlphaVantageProvider(api_key="test-key")
        url = "https://www.alphavantage.co/query"
        respx.get(url).respond(
            json={
                "feed": [
                    {
                        "overall_sentiment_score": 0.65,
                        "summary": "Bitcoin ETF inflows surge",
                        "ticker_sentiment": [
                            {"ticker": "BTCUSDT", "ticker_sentiment_score": 0.7}
                        ],
                    }
                ]
            }
        )

        event = await provider.get_sentiment("BTC/USDT")
        assert event is not None
        assert event.symbol == "BTC/USDT"
        assert event.score > 0
        assert event.source == "alpha_vantage"
        await provider.close()

    @respx.mock
    async def test_get_sentiment_no_feed(self) -> None:
        provider = AlphaVantageProvider(api_key="test-key")
        url = "https://www.alphavantage.co/query"
        respx.get(url).respond(json={})

        event = await provider.get_sentiment("BTC/USDT")
        assert event is None
        await provider.close()

    @respx.mock
    async def test_raise_when_quota_exhausted(self) -> None:
        provider = AlphaVantageProvider(api_key="test-key")
        for _ in range(25):
            provider.rate_limit.try_consume()

        from trading.data.news.base import RateLimitError

        with pytest.raises(RateLimitError):
            await provider.get_sentiment("BTC/USDT")
        await provider.close()

    async def test_rate_limit_config(self) -> None:
        assert AlphaVantageProvider.rate_limit.capacity == 25

    async def test_symbol_mapping(self) -> None:
        from trading.data.news.alpha_vantage import _map_symbol

        assert _map_symbol("BTC/USDT") == "BTCUSDT"
        assert _map_symbol("eth/usdt") == "ETHUSDT"
        assert _map_symbol("AAPL") == "AAPL"
