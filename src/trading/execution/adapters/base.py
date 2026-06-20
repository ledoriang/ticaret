from abc import ABC, abstractmethod
from collections.abc import AsyncGenerator
from datetime import datetime

from trading.core.enums import AssetClass
from trading.core.events import FillEvent, OrderEvent
from trading.core.market_hours import MarketHours
from trading.core.models import AccountInfo, Bar, Position


class AbstractBrokerAdapter(ABC):
    name: str = ""
    asset_classes: list[AssetClass] = []

    @abstractmethod
    async def get_bars(
        self, symbol: str, timeframe: str, start: datetime, end: datetime
    ) -> list[Bar]: ...

    @abstractmethod
    async def get_account(self) -> AccountInfo: ...

    @abstractmethod
    async def get_positions(self) -> list[Position]: ...

    @abstractmethod
    async def submit_order(self, order: OrderEvent) -> FillEvent: ...

    @abstractmethod
    async def cancel_order(self, order_id: str) -> None: ...

    @abstractmethod
    def stream_bars(
        self, symbols: list[str], timeframe: str
    ) -> AsyncGenerator[Bar, None]: ...

    @abstractmethod
    async def get_market_hours(self, symbol: str) -> MarketHours: ...
