import asyncio
from typing import Any

import structlog

from trading.core.config import SentimentProviderConfig
from trading.data.news.base import NewsProvider, RateLimitError
from trading.data.news.registry import NEWS_PROVIDER_REGISTRY
from trading.data.sentiment_repository import SentimentRepository
from trading.orchestration.bus import EventBus

logger = structlog.get_logger(__name__)


class SentimentIngester:
    def __init__(
        self,
        config: SentimentProviderConfig,
        event_bus: EventBus | None = None,
        repository: SentimentRepository | None = None,
    ) -> None:
        self._config = config
        self._event_bus = event_bus
        self._repository = repository
        self._provider: NewsProvider | None = None
        self._running = False

    async def start(self) -> None:
        provider_cls = NEWS_PROVIDER_REGISTRY.get(self._config.provider)
        if provider_cls is None:
            logger.error("sentiment_provider_not_found", provider=self._config.provider)
            return

        provider_kwargs: dict[str, Any] = {}
        if self._config.provider == "alpha_vantage":
            provider_kwargs["api_key"] = self._config.alpha_vantage_api_key or ""
        elif self._config.provider == "marketaux":
            provider_kwargs["api_token"] = self._config.marketaux_api_token or ""
        elif self._config.provider == "finnhub":
            provider_kwargs["api_key"] = self._config.finnhub_api_key or ""
        elif self._config.provider == "stockgeist":
            provider_kwargs["api_key"] = self._config.stockgeist_api_key or ""
        elif self._config.provider == "cached":
            provider_kwargs["fixture_path"] = self._config.cached_fixture_path or ""

        self._provider = provider_cls(**provider_kwargs)
        self._running = True
        logger.info(
            "sentiment_ingester_started",
            provider=self._config.provider,
            symbols=self._config.symbols,
            poll_interval=self._config.poll_interval_seconds,
        )

    async def run_forever(self) -> None:
        if not self._running or self._provider is None:
            await self.start()

        provider = self._provider
        assert provider is not None

        while self._running:
            for symbol in self._config.symbols:
                try:
                    event = await provider.get_sentiment(symbol)
                except RateLimitError:
                    logger.warning("sentiment_rate_limit", provider=self._config.provider)
                    await self._sleep_interruptible(self._config.poll_interval_seconds)
                    continue
                except Exception:
                    logger.exception(
                        "sentiment_poll_failed",
                        provider=self._config.provider,
                        symbol=symbol,
                    )
                    continue

                if event is None:
                    continue

                if self._event_bus:
                    await self._event_bus.publish(f"sentiment:{symbol}", event)

                if self._repository:
                    try:
                        await self._repository.insert(event)
                    except Exception:
                        logger.exception(
                            "sentiment_insert_failed", symbol=symbol, source=event.source
                        )

            await self._sleep_interruptible(self._config.poll_interval_seconds)

    async def _sleep_interruptible(self, seconds: int) -> None:
        for _ in range(seconds):
            if not self._running:
                return
            await asyncio.sleep(1)

    async def stop(self) -> None:
        self._running = False
        if self._provider is not None:
            await self._provider.close()
        logger.info("sentiment_ingester_stopped")
