from dataclasses import dataclass, field

import pandas as pd

from trading.backtest.backtest_types import ClosedTrade


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
    avg_bars_held: float = 0.0
    stop_hit_rate: float = 0.0
    avg_mae: float = 0.0
    avg_mfe: float = 0.0
    avg_rr_realized: float = 0.0

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
            "avg_bars_held": round(self.avg_bars_held, 1),
            "stop_hit_rate_pct": round(self.stop_hit_rate * 100, 1),
            "avg_mae": round(self.avg_mae, 4),
            "avg_mfe": round(self.avg_mfe, 4),
            "avg_rr_realized": round(self.avg_rr_realized, 2),
        }


def _compute_sharpe(returns: pd.Series) -> float:
    if len(returns) < 2 or returns.std() == 0:
        return 0.0
    return float(returns.mean() / returns.std() * (252**0.5))


def _compute_sortino(returns: pd.Series) -> float:
    downside = returns[returns < 0]
    if len(downside) < 2 or downside.std() == 0:
        return 0.0
    return float(returns.mean() / downside.std() * (252**0.5))


def _compute_max_drawdown(equity: pd.Series) -> float:
    if len(equity) < 2:
        return 0.0
    peak = equity.expanding().max()
    dd = (equity - peak) / peak
    return float(abs(dd.min()))


def compute_metrics_from_trades(
    trades: list[ClosedTrade], initial_cash: float
) -> BacktestMetrics:
    if not trades:
        return BacktestMetrics()

    df = pd.DataFrame(
        [
            {
                "entry_time": t.entry_time,
                "exit_time": t.exit_time,
                "side": t.side.value,
                "entry_price": t.entry_price,
                "exit_price": t.exit_price,
                "quantity": t.quantity,
                "gross_pnl": t.gross_pnl,
                "net_pnl": t.net_pnl,
                "commission": t.commission,
                "slippage_cost": t.slippage_cost,
                "exit_reason": t.exit_reason,
                "mae": t.mae,
                "mfe": t.mfe,
                "bars_held": t.bars_held,
            }
            for t in trades
        ]
    )
    df = df.sort_values("exit_time").reset_index(drop=True)

    total_pnl = sum(t.gross_pnl for t in trades)
    total_commission = sum(t.commission for t in trades)
    total_slippage = sum(t.slippage_cost for t in trades)
    net_pnl = total_pnl - total_commission - total_slippage

    # Build equity curve
    capital = initial_cash
    equity_values: list[float] = [capital]
    for t in trades:
        capital += t.net_pnl
        equity_values.append(capital)
    equity = pd.Series(equity_values)

    returns = equity.pct_change().dropna()

    stop_hits = sum(1 for t in trades if t.exit_reason == "stop_loss")

    wins = [t for t in trades if t.net_pnl > 0]

    rr_values: list[float] = []
    for t in trades:
        stop_dist = abs(
            t.entry_price - (t.exit_price if t.exit_reason == "stop_loss" else t.entry_price)
        )
        if stop_dist > 0 and abs(t.net_pnl) > 0:
            rr = abs(t.net_pnl) / stop_dist if stop_dist > 0 else 0.0
            rr_values.append(rr)

    return BacktestMetrics(
        total_return=net_pnl / initial_cash if initial_cash > 0 else 0.0,
        sharpe_ratio=_compute_sharpe(returns),
        max_drawdown=_compute_max_drawdown(equity),
        sortino_ratio=_compute_sortino(returns),
        total_trades=len(trades),
        win_rate=len(wins) / len(trades) if trades else 0.0,
        total_pnl=total_pnl,
        total_commission=total_commission,
        total_slippage_cost=total_slippage,
        net_pnl=net_pnl,
        equity_curve=equity,
        trades=df,
        avg_bars_held=sum(t.bars_held for t in trades) / len(trades) if trades else 0.0,
        stop_hit_rate=stop_hits / len(trades) if trades else 0.0,
        avg_mae=sum(abs(t.mae) for t in trades) / len(trades) if trades else 0.0,
        avg_mfe=sum(abs(t.mfe) for t in trades) / len(trades) if trades else 0.0,
        avg_rr_realized=sum(rr_values) / len(rr_values) if rr_values else 0.0,
    )
