from datetime import datetime

from pydantic import BaseModel, Field

from trading.core.enums import AssetClass, OrderStatus, OrderType, Side, TimeInForce


class Bar(BaseModel):
    symbol: str
    asset_class: AssetClass
    timeframe: str
    open: float
    high: float
    low: float
    close: float
    volume: float
    timestamp: datetime


class Order(BaseModel):
    id: str
    symbol: str
    asset_class: AssetClass
    side: Side
    order_type: OrderType
    quantity: float
    price: float | None = None
    stop_price: float | None = None
    time_in_force: TimeInForce = TimeInForce.GTC
    status: OrderStatus = OrderStatus.PENDING
    filled_quantity: float = 0.0
    avg_fill_price: float | None = None
    created_at: datetime
    updated_at: datetime | None = None
    broker: str = "paper"
    client_order_id: str | None = None


class Position(BaseModel):
    symbol: str
    asset_class: AssetClass
    quantity: float
    avg_entry_price: float
    current_price: float
    unrealized_pnl: float = 0.0
    realized_pnl: float = 0.0
    timestamp: datetime
    broker: str = "paper"

    def model_post_init(self, __context: object) -> None:
        self.unrealized_pnl = (self.current_price - self.avg_entry_price) * self.quantity


class AccountInfo(BaseModel):
    broker: str
    total_equity: float
    cash: float
    buying_power: float
    timestamp: datetime


class Portfolio(BaseModel):
    positions: list[Position] = Field(default_factory=list)
    account: AccountInfo | None = None
    total_value: float = 0.0
    cash: float = 0.0
    timestamp: datetime = Field(default_factory=datetime.now)
