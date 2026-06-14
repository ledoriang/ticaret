from dataclasses import dataclass, field

import pandas as pd


@dataclass
class BacktestMetrics:
    total_return: float = 0.0
    sharpe_ratio: float = 0.0
    max_drawdown: float = 0.0
    sortino_ratio: float = 0.0
    total_trades: int = 0
    win_rate: float = 0.0
    total_pnl: float = 0.0
    total_commission: float = 0.0
    total_slippage_cost: float = 0.0
    net_pnl: float = 0.0
    equity_curve: pd.Series = field(default_factory=lambda: pd.Series(dtype=float))
    trades: pd.DataFrame = field(default_factory=lambda: pd.DataFrame())

    def summary(self) -> dict[str, float | int | str]:
        return {
            "total_return_pct": round(self.total_return * 100, 2),
            "sharpe_ratio": round(self.sharpe_ratio, 3),
            "max_drawdown_pct": round(self.max_drawdown * 100, 2),
            "sortino_ratio": round(self.sortino_ratio, 3),
            "total_trades": self.total_trades,
            "win_rate_pct": round(self.win_rate * 100, 2),
            "total_pnl": round(self.total_pnl, 2),
            "total_commission": round(self.total_commission, 2),
            "total_slippage_cost": round(self.total_slippage_cost, 2),
            "net_pnl": round(self.net_pnl, 2),
        }
