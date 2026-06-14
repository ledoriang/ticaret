from dataclasses import dataclass, field
from datetime import datetime

import pandas as pd

from trading.core.enums import Side


@dataclass
class TradeRecord:
    symbol: str
    side: Side
    entry_time: datetime
    exit_time: datetime
    entry_price: float
    exit_price: float
    quantity: float
    gross_pnl: float
    commission: float
    slippage_cost: float
    net_pnl: float
    strategy: str = ""
    indicator_values: dict[str, float] = field(default_factory=dict)


class TradeJournal:
    def __init__(self) -> None:
        self.trades: list[TradeRecord] = []

    def add(self, trade: TradeRecord) -> None:
        self.trades.append(trade)

    def to_dataframe(self) -> pd.DataFrame:
        rows = []
        for t in self.trades:
            row = {
                "symbol": t.symbol,
                "side": t.side.value,
                "entry_time": t.entry_time,
                "exit_time": t.exit_time,
                "entry_price": t.entry_price,
                "exit_price": t.exit_price,
                "quantity": t.quantity,
                "gross_pnl": t.gross_pnl,
                "commission": t.commission,
                "slippage_cost": t.slippage_cost,
                "net_pnl": t.net_pnl,
                "strategy": t.strategy,
                **{f"ind_{k}": v for k, v in t.indicator_values.items()},
            }
            rows.append(row)
        return pd.DataFrame(rows)

    def to_csv(self, path: str) -> None:
        self.to_dataframe().to_csv(path, index=False)

    @property
    def total_commission(self) -> float:
        return sum(t.commission for t in self.trades)

    @property
    def total_slippage_cost(self) -> float:
        return sum(t.slippage_cost for t in self.trades)
