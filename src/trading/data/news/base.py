import asyncio
import time
from typing import Protocol

import structlog

from trading.core.events import SentimentEvent

logger = structlog.get_logger(__name__)


class RateLimitError(Exception):
    pass


class TokenBucket:
    def __init__(self, capacity: int, refill_seconds: int) -> None:
        self.capacity = capacity
        self._tokens = float(capacity)
        self._refill_rate = capacity / refill_seconds
        self._last_refill = time.monotonic()

    def _refill(self) -> None:
        now = time.monotonic()
        elapsed = now - self._last_refill
        self._tokens = min(self.capacity, self._tokens + elapsed * self._refill_rate)
        self._last_refill = now

    def try_consume(self) -> bool:
        self._refill()
        if self._tokens >= 1:
            self._tokens -= 1
            return True
        return False

    async def wait_and_consume(self) -> None:
        while not self.try_consume():
            wait = 1.0 / self._refill_rate if self._refill_rate > 0 else self.capacity
            await asyncio.sleep(min(wait, 5.0))


class NewsProvider(Protocol):
    name: str
    rate_limit: TokenBucket

    async def get_sentiment(self, symbol: str) -> SentimentEvent | None: ...

    async def close(self) -> None: ...
