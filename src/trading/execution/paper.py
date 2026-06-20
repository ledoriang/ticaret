from collections.abc import AsyncGenerator
from datetime import datetime
from uuid import uuid4

from trading.core.enums import AssetClass, Side
from trading.core.events import FillEvent, OrderEvent
from trading.core.market_hours import MarketHours
from trading.core.models import AccountInfo, Bar, Position
from trading.execution.adapters.base import AbstractBrokerAdapter


class PaperAdapter(AbstractBrokerAdapter):
    name = "paper"
    asset_classes = [AssetClass.CRYPTO, AssetClass.EQUITY]

    def __init__(
        self,
        simulated_slippage: float = 0.001,
        simulated_fee_rate: float = 0.001,
        initial_cash: float = 100_000.0,
    ) -> None:
        self.simulated_slippage = simulated_slippage
        self.simulated_fee_rate = simulated_fee_rate
        self._cash = initial_cash
        self._positions: dict[str, Position] = {}
        self._last_prices: dict[str, float] = {}
        self._orders: list[dict[str, object]] = []

    async def get_bars(
        self, _symbol: str, _timeframe: str, _start: datetime, _end: datetime
    ) -> list[Bar]:
        return []

    async def get_account(self) -> AccountInfo:
        total = self._cash + sum(p.quantity * p.current_price for p in self._positions.values())
        return AccountInfo(
            broker=self.name,
            total_equity=total,
            cash=self._cash,
            buying_power=self._cash,
            timestamp=datetime.now(),
        )

    async def get_positions(self) -> list[Position]:
        return list(self._positions.values())

    async def submit_order(self, order: OrderEvent) -> FillEvent:
        fill_price = order.price or self._last_prices.get(order.symbol, 0.0)
        slippage = fill_price * self.simulated_slippage
        fill_price += slippage if order.side == Side.BUY else -slippage
        commission = fill_price * order.quantity * self.simulated_fee_rate

        fill = FillEvent(
            symbol=order.symbol,
            side=order.side,
            quantity=order.quantity,
            fill_price=round(fill_price, 8),
            commission=round(commission, 8),
            order_id=uuid4().hex[:16],
            broker=self.name,
            source=self.name,
            correlation_id=order.correlation_id,
        )

        if order.side == Side.BUY:
            cost = fill_price * order.quantity + commission
            self._cash -= cost
            if order.symbol in self._positions:
                pos = self._positions[order.symbol]
                total_qty = pos.quantity + order.quantity
                total_cost = pos.avg_entry_price * pos.quantity + fill_price * order.quantity
                pos.avg_entry_price = total_cost / total_qty
                pos.quantity = total_qty
            else:
                self._positions[order.symbol] = Position(
                    symbol=order.symbol,
                    asset_class=order.asset_class,
                    quantity=order.quantity,
                    avg_entry_price=fill_price,
                    current_price=fill_price,
                    timestamp=datetime.now(),
                    broker=self.name,
                )
        else:
            revenue = fill_price * order.quantity - commission
            self._cash += revenue
            stored = self._positions.get(order.symbol)
            if stored is not None:
                pos = stored
                pos.quantity -= order.quantity
                if pos.quantity <= 0:
                    del self._positions[order.symbol]

        self._orders.append(
            {
                "order": order.model_dump(),
                "fill": fill.model_dump(),
            }
        )
        return fill

    async def cancel_order(self, order_id: str) -> None:
        pass

    async def stream_bars(
        self, _symbols: list[str], _timeframe: str
    ) -> AsyncGenerator[Bar, None]:
        yield Bar(
            symbol="",
            asset_class=AssetClass.CRYPTO,
            timeframe="",
            open=0.0,
            high=0.0,
            low=0.0,
            close=0.0,
            volume=0.0,
            timestamp=datetime.now(),
        )
        return

    async def get_market_hours(self, _symbol: str) -> MarketHours:
        return MarketHours(always_open=True)

    def update_last_price(self, symbol: str, price: float) -> None:
        self._last_prices[symbol] = price
        if symbol in self._positions:
            self._positions[symbol].current_price = price
