import httpx
import structlog

from trading.core.enums import AssetClass
from trading.core.events import SentimentEvent
from trading.data.news.base import RateLimitError, TokenBucket
from trading.data.news.registry import register_provider

logger = structlog.get_logger(__name__)

BASE_URL = "https://api.marketaux.com/v1/news/all"


@register_provider
class MarketauxProvider:
    name = "marketaux"
    asset_classes: list[AssetClass] = [AssetClass.CRYPTO, AssetClass.EQUITY]
    rate_limit = TokenBucket(capacity=100, refill_seconds=86400)

    def __init__(self, api_token: str = "") -> None:
        self._api_token = api_token
        self._client = httpx.AsyncClient(timeout=httpx.Timeout(30.0))

    async def get_sentiment(self, symbol: str) -> SentimentEvent | None:
        if not self.rate_limit.try_consume():
            raise RateLimitError("Marketaux daily quota (100 req) exhausted")

        params: dict[str, str] = {
            "symbols": _map_symbol(symbol),
            "api_token": self._api_token,
            "limit": "10",
            "sort": "published_desc",
        }

        try:
            resp = await self._client.get(BASE_URL, params=params)
            resp.raise_for_status()
            data = resp.json()
        except Exception:
            logger.exception("marketaux_request_failed", symbol=symbol)
            return None

        articles = data.get("data", [])
        if not articles:
            logger.warning("marketaux_no_articles", symbol=symbol)
            return None

        scores: list[float] = []
        summaries: list[str] = []

        for article in articles[:5]:
            entities = article.get("entities", [])
            title = article.get("title", "")
            if title:
                summaries.append(title)

            for entity in entities:
                if not isinstance(entity, dict):
                    continue
                sent = entity.get("sentiment_score")
                if isinstance(sent, (int, float)):
                    scores.append(max(-1.0, min(1.0, float(sent))))

        if not scores:
            confidence = 0.3
            score = 0.0
        else:
            score = sum(scores) / len(scores)
            confidence = min(1.0, len(scores) / 15.0)

        combined = " | ".join(summaries[:3]) if summaries else ""

        return SentimentEvent(
            symbol=symbol,
            score=score,
            confidence=confidence,
            source="marketaux",
            summary=combined or "Marketaux sentiment",
        )

    async def close(self) -> None:
        await self._client.aclose()


def _map_symbol(symbol: str) -> str:
    symbol = symbol.upper()
    symbol = symbol.replace("/", "")
    return symbol
