from collections.abc import AsyncGenerator
from datetime import datetime
from typing import Protocol

from trading.core.enums import AssetClass
from trading.core.events import FillEvent, OrderEvent
from trading.core.market_hours import MarketHours
from trading.core.models import AccountInfo, Bar, Position


class BrokerProtocol(Protocol):
    name: str
    asset_classes: list[AssetClass]

    async def get_bars(
        self, symbol: str, timeframe: str, start: datetime, end: datetime
    ) -> list[Bar]: ...

    async def get_account(self) -> AccountInfo: ...

    async def get_positions(self) -> list[Position]: ...

    async def submit_order(self, order: OrderEvent) -> FillEvent: ...

    async def cancel_order(self, order_id: str) -> None: ...

    def stream_bars(
        self, symbols: list[str], timeframe: str
    ) -> AsyncGenerator[Bar, None]: ...

    async def get_market_hours(self, symbol: str) -> MarketHours: ...
