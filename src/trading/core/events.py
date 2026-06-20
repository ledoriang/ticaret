from datetime import datetime
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field

from trading.core.enums import AssetClass, OrderType, Side


class BaseEvent(BaseModel):
    event_id: str = Field(default_factory=lambda: uuid4().hex)
    correlation_id: str = ""
    source: str = ""
    timestamp: datetime = Field(default_factory=datetime.now)
    asset_class: AssetClass = AssetClass.CRYPTO
    event_schema_version: int = 1


class SignalEvent(BaseEvent):
    symbol: str
    side: Side
    confidence: float = Field(ge=0.0, le=1.0)
    strategy_name: str
    price: float | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class OrderEvent(BaseEvent):
    symbol: str
    side: Side
    order_type: OrderType
    quantity: float = Field(gt=0.0)
    price: float | None = None
    stop_price: float | None = None
    broker: str = "paper"
    strategy_name: str = ""


class FillEvent(BaseEvent):
    symbol: str
    side: Side
    quantity: float = Field(gt=0.0)
    fill_price: float = Field(gt=0.0)
    commission: float = 0.0
    realized_pnl: float | None = None
    order_id: str = ""
    broker: str = "paper"


class BarEvent(BaseEvent):
    symbol: str
    open: float = 0.0
    high: float = 0.0
    low: float = 0.0
    close: float = 0.0
    volume: float = 0.0


class SentimentEvent(BaseEvent):
    symbol: str
    score: float = Field(default=0.0, ge=-1.0, le=1.0)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    source: str = ""
    summary: str = ""


class CommandEvent(BaseEvent):
    command: str
    payload: dict[str, Any] = Field(default_factory=dict)


class RiskBlockEvent(BaseEvent):
    original_signal: SignalEvent
    reason: str
    rule_that_blocked: str
