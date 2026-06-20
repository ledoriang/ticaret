import asyncio
from collections.abc import Awaitable, Callable
from contextlib import suppress

import structlog

from trading.core.events import BarEvent
from trading.execution.adapters.base import AbstractBrokerAdapter

logger = structlog.get_logger(__name__)

BarHandler = Callable[[BarEvent], Awaitable[None]]


class LiveStream:
    def __init__(
        self, adapter: AbstractBrokerAdapter, symbols: list[str], timeframe: str = "1m"
    ) -> None:
        self._adapter = adapter
        self._symbols = symbols
        self._timeframe = timeframe
        self._running = False
        self._handlers: list[BarHandler] = []
        self._task: asyncio.Task[None] | None = None

    def on_bar(self, handler: BarHandler) -> None:
        self._handlers.append(handler)

    async def start(self) -> None:
        self._running = True
        logger.info("live_stream_started", symbols=self._symbols, timeframe=self._timeframe)
        self._task = asyncio.create_task(self._run())

    async def _run(self) -> None:
        while self._running:
            try:
                gen = self._adapter.stream_bars(self._symbols, self._timeframe)
                async for bar in gen:
                    if not self._running:
                        return
                    event = BarEvent(
                        symbol=bar.symbol,
                        asset_class=bar.asset_class,
                        open=bar.open,
                        high=bar.high,
                        low=bar.low,
                        close=bar.close,
                        volume=bar.volume,
                        timestamp=bar.timestamp,
                        source="live_stream",
                    )
                    for handler in self._handlers:
                        await handler(event)
            except Exception:
                if self._running:
                    logger.exception("live_stream_error")
                    await asyncio.sleep(1)

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            with suppress(asyncio.CancelledError):
                await self._task
        logger.info("live_stream_stopped")

    async def add_symbol(self, symbol: str, timeframe: str | None = None) -> None:
        if symbol not in self._symbols:
            self._symbols.append(symbol)
            if timeframe:
                self._timeframe = timeframe
            logger.info("live_stream_symbol_added", symbol=symbol)

    async def remove_symbol(self, symbol: str) -> None:
        if symbol in self._symbols:
            self._symbols.remove(symbol)
            logger.info("live_stream_symbol_removed", symbol=symbol)
