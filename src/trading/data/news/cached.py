import random
from pathlib import Path
from typing import Any

import structlog
import yaml

from trading.core.enums import AssetClass
from trading.core.events import SentimentEvent
from trading.data.news.base import TokenBucket
from trading.data.news.registry import register_provider

logger = structlog.get_logger(__name__)


@register_provider
class CachedNewsProvider:
    name = "cached"
    asset_classes: list[AssetClass] = [AssetClass.CRYPTO, AssetClass.EQUITY]
    rate_limit = TokenBucket(capacity=1000, refill_seconds=1)

    def __init__(self, fixture_path: str = "") -> None:
        self._fixture_path = fixture_path
        self._fixtures: dict[str, list[dict[str, Any]]] = {}
        self._loaded = False

    def _load(self) -> None:
        if self._loaded:
            return
        self._loaded = True

        if self._fixture_path and Path(self._fixture_path).exists():
            raw = yaml.safe_load(Path(self._fixture_path).read_text())
            if isinstance(raw, dict):
                self._fixtures = raw
                logger.info("cached_news_loaded", path=self._fixture_path, symbols=list(raw))
                return

        self._fixtures = {
            "BTC/USDT": [
                {"score": 0.65, "summary": "Bitcoin ETF inflows surge"},
                {"score": -0.30, "summary": "Regulatory concerns weigh on BTC"},
                {"score": 0.50, "summary": "Institutional adoption grows"},
            ],
            "ETH/USDT": [
                {"score": 0.55, "summary": "Ethereum 2.0 staking reaches new high"},
                {"score": -0.20, "summary": "Gas fees spike on network congestion"},
            ],
        }

    async def get_sentiment(self, symbol: str) -> SentimentEvent | None:
        self._load()
        entries = self._fixtures.get(symbol)
        if not entries:
            logger.warning("cached_news_no_fixture", symbol=symbol)
            return None

        entry = random.choice(entries)
        jitter = random.uniform(-0.15, 0.15)
        score = max(-1.0, min(1.0, entry["score"] + jitter))

        return SentimentEvent(
            symbol=symbol,
            score=score,
            confidence=random.uniform(0.5, 1.0),
            source="cached",
            summary=entry.get("summary", "Cached news sentiment"),
        )

    async def close(self) -> None:
        pass
