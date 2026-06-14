from collections.abc import Awaitable, Callable

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

    def on_bar(self, handler: BarHandler) -> None:
        self._handlers.append(handler)

    async def start(self) -> None:
        self._running = True
        logger.info("live_stream_started", symbols=self._symbols, timeframe=self._timeframe)
        for symbol in self._symbols:
            for bar in self._adapter.stream_bars([symbol], self._timeframe):
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

    async def stop(self) -> None:
        self._running = False
        logger.info("live_stream_stopped")
