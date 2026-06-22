import httpx
import structlog

from trading.core.enums import AssetClass
from trading.core.events import SentimentEvent
from trading.data.news.base import RateLimitError, TokenBucket
from trading.data.news.registry import register_provider

logger = structlog.get_logger(__name__)

BASE_URL = "https://finnhub.io/api/v1/news-sentiment"


@register_provider
class FinnhubProvider:
    name = "finnhub"
    asset_classes: list[AssetClass] = [AssetClass.EQUITY]
    rate_limit = TokenBucket(capacity=30, refill_seconds=60)

    def __init__(self, api_key: str = "") -> None:
        self._api_key = api_key
        self._client = httpx.AsyncClient(timeout=httpx.Timeout(30.0))

    async def get_sentiment(self, symbol: str) -> SentimentEvent | None:
        if not self.rate_limit.try_consume():
            raise RateLimitError("Finnhub rate limit (30 req/min) exhausted")

        params: dict[str, str] = {
            "symbol": _map_symbol(symbol),
            "token": self._api_key,
        }

        try:
            resp = await self._client.get(BASE_URL, params=params)
            resp.raise_for_status()
            data = resp.json()
        except Exception:
            logger.exception("finnhub_request_failed", symbol=symbol)
            return None

        buzz = data.get("buzz", {})
        company_score = data.get("companyNewsScore")
        sector_score = data.get("sectorAverageBullishPercent")

        if company_score is None and sector_score is None:
            logger.warning("finnhub_no_sentiment_data", symbol=symbol)
            return None

        score = float(company_score or 0.0)
        if sector_score is not None:
            score = (score + float(sector_score) / 100.0) / 2.0

        buzz_words = buzz.get("articlesInLastWeek", 0)
        confidence = min(1.0, buzz_words / 50.0)

        summary_parts: list[str] = []
        weekly_buzz = buzz.get("weeklyAverage", 0.0)
        if weekly_buzz:
            summary_parts.append(f"Weekly avg buzz: {weekly_buzz:.2f}")
        if company_score is not None:
            summary_parts.append(f"Company score: {company_score:.3f}")
        if buzz_words:
            summary_parts.append(f"{buzz_words} articles last week")

        return SentimentEvent(
            symbol=symbol,
            score=max(-1.0, min(1.0, score)),
            confidence=confidence,
            source="finnhub",
            summary=" | ".join(summary_parts) if summary_parts else "Finnhub sentiment",
        )

    async def close(self) -> None:
        await self._client.aclose()


def _map_symbol(symbol: str) -> str:
    symbol = symbol.upper()
    symbol = symbol.replace("/USDT", "").replace("/USD", "").replace("/", "")
    return symbol
