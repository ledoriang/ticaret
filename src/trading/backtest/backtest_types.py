from dataclasses import dataclass
from datetime import datetime

from trading.core.enums import Side


@dataclass
class OpenTrade:
    symbol: str
    side: Side
    entry_price: float
    quantity: float
    entry_time: datetime
    stop_loss_price: float
    take_profit_price: float | None
    highest_price: float
    lowest_price: float
    bars_held: int = 0


@dataclass
class ClosedTrade:
    symbol: str
    side: Side
    entry_time: datetime
    exit_time: datetime
    entry_price: float
    exit_price: float
    quantity: float
    gross_pnl: float
    net_pnl: float
    commission: float
    slippage_cost: float
    exit_reason: str
    mae: float
    mfe: float
    bars_held: int
