import httpx
import structlog

from trading.core.enums import AssetClass
from trading.core.events import SentimentEvent
from trading.data.news.base import RateLimitError, TokenBucket
from trading.data.news.registry import register_provider

logger = structlog.get_logger(__name__)

BASE_URL = "https://www.alphavantage.co/query"


@register_provider
class AlphaVantageProvider:
    name = "alpha_vantage"
    asset_classes: list[AssetClass] = [AssetClass.CRYPTO, AssetClass.EQUITY]
    rate_limit = TokenBucket(capacity=25, refill_seconds=86400)

    def __init__(self, api_key: str = "") -> None:
        self._api_key = api_key
        self._client = httpx.AsyncClient(timeout=httpx.Timeout(30.0))

    async def get_sentiment(self, symbol: str) -> SentimentEvent | None:
        if not self.rate_limit.try_consume():
            raise RateLimitError("Alpha Vantage daily quota (25 req) exhausted")

        params: dict[str, str] = {
            "function": "NEWS_SENTIMENT",
            "tickers": _map_symbol(symbol),
            "apikey": self._api_key,
        }

        try:
            resp = await self._client.get(BASE_URL, params=params)
            resp.raise_for_status()
            data = resp.json()
        except Exception:
            logger.exception("alpha_vantage_request_failed", symbol=symbol)
            return None

        if "feed" not in data or not data["feed"]:
            logger.warning("alpha_vantage_no_feed", symbol=symbol)
            return None

        scores: list[float] = []
        summaries: list[str] = []

        for article in data["feed"][:5]:
            overall = article.get("overall_sentiment_score")
            if isinstance(overall, (int, float)):
                scores.append(float(overall))
            summary = article.get("summary", "")
            if summary:
                summaries.append(summary[:200])

            ticker_sentiments = article.get("ticker_sentiment", [])
            for ts in ticker_sentiments:
                if isinstance(ts, dict) and ts.get("ticker", "").upper() == _map_symbol(symbol):
                    ts_score = ts.get("ticker_sentiment_score")
                    if isinstance(ts_score, (int, float)):
                        scores.append(float(ts_score))

        if not scores:
            return None

        avg_score = sum(scores) / len(scores)
        combined = " | ".join(summaries[:3]) if summaries else ""

        return SentimentEvent(
            symbol=symbol,
            score=max(-1.0, min(1.0, avg_score)),
            confidence=min(1.0, len(scores) / 10.0),
            source="alpha_vantage",
            summary=combined or "Alpha Vantage sentiment score",
        )

    async def close(self) -> None:
        await self._client.aclose()


def _map_symbol(symbol: str) -> str:
    symbol = symbol.upper()
    symbol = symbol.replace("/", "")
    return symbol
