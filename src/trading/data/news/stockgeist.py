import structlog

from trading.core.enums import AssetClass
from trading.core.events import SentimentEvent
from trading.data.news.base import TokenBucket
from trading.data.news.registry import register_provider

logger = structlog.get_logger(__name__)


@register_provider
class StockGeistProvider:
    name = "stockgeist"
    asset_classes: list[AssetClass] = [AssetClass.EQUITY]
    rate_limit = TokenBucket(capacity=10, refill_seconds=3600)

    def __init__(self, api_key: str = "") -> None:
        self._api_key = api_key
        if not api_key:
            logger.warning("stockgeist_no_api_key")

    async def get_sentiment(self, symbol: str) -> SentimentEvent | None:
        logger.warning("stockgeist_not_implemented", symbol=symbol)
        return None

    async def close(self) -> None:
        pass
