from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
from typing import TYPE_CHECKING

import structlog
import websockets

from trading.core.models import Bar

if TYPE_CHECKING:
    from trading.data.feeds.base import FeedHandler

logger = structlog.get_logger(__name__)


class WebSocketShovel:
    """Universal WebSocket connection manager.

    The shovel handles connection lifecycle: connect, reconnect with
    exponential backoff, ping/pong keepalive, and message dispatch.
    It has zero knowledge of any specific exchange — all exchange-specific
    logic is delegated to a FeedHandler.

    Usage:
        shovel = WebSocketShovel(handler)
        async for bar in shovel.stream(["BTC/USDT"], "1m"):
            process(bar)
    """

    def __init__(
        self,
        handler: FeedHandler,
        max_retry_delay: float = 60.0,
        ping_interval: int = 20,
    ) -> None:
        self._handler = handler
        self._max_retry_delay = max_retry_delay
        self._ping_interval = ping_interval
        self._retry_delay = 1.0

    async def stream(
        self, symbols: list[str], timeframe: str
    ) -> AsyncGenerator[Bar, None]:
        url = self._handler.build_url(symbols, timeframe)
        self._retry_delay = 1.0

        while True:
            try:
                async with websockets.connect(url, ping_interval=self._ping_interval) as ws:
                    self._retry_delay = 1.0

                    sub_msg = self._handler.build_subscribe(symbols)
                    if sub_msg:
                        await ws.send(sub_msg)

                    async for raw in ws:
                        text = raw if isinstance(raw, str) else raw.decode("utf-8")

                        if self._handler.is_closed_message(text):
                            return

                        bar = self._handler.parse_message(text)
                        if bar is not None:
                            yield bar

            except websockets.ConnectionClosed:
                logger.warning("shovel_disconnected", delay=self._retry_delay)
            except asyncio.CancelledError:
                raise
            except GeneratorExit:
                raise
            except Exception:
                logger.exception("shovel_error", delay=self._retry_delay)
            else:
                return

            await asyncio.sleep(self._retry_delay)
            self._retry_delay = min(self._retry_delay * 2, self._max_retry_delay)
