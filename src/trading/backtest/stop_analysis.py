from dataclasses import dataclass
from statistics import median

from trading.backtest.backtest_types import ClosedTrade


@dataclass
class StopAnalysis:
    total_trades: int = 0
    stop_hit_count: int = 0
    take_profit_hit_count: int = 0
    signal_exit_count: int = 0
    time_exit_count: int = 0
    stop_hit_rate: float = 0.0
    take_profit_hit_rate: float = 0.0
    signal_exit_rate: float = 0.0
    time_exit_rate: float = 0.0
    avg_bars_held: float = 0.0
    median_bars_held: float = 0.0
    avg_rr_stop_hits: float = 0.0
    avg_rr_tp_hits: float = 0.0
    overall_avg_rr: float = 0.0


def compute_stop_analysis(trades: list[ClosedTrade]) -> StopAnalysis:
    if not trades:
        return StopAnalysis()

    total = len(trades)
    stop_hits = [t for t in trades if t.exit_reason == "stop_loss"]
    tp_hits = [t for t in trades if t.exit_reason == "take_profit"]
    signal_exits = [t for t in trades if t.exit_reason == "signal"]
    time_exits = [t for t in trades if t.exit_reason == "time_exit"]

    bars_held_list = [t.bars_held for t in trades]

    def _avg_rr(group: list[ClosedTrade]) -> float:
        vals: list[float] = []
        for t in group:
            denom = abs(t.entry_price - t.exit_price)
            val = abs(t.net_pnl) / denom if denom > 0 else 0.0
            vals.append(val)
        vals = [v for v in vals if v > 0]
        return sum(vals) / len(vals) if vals else 0.0

    overall_rr = _avg_rr(trades)

    return StopAnalysis(
        total_trades=total,
        stop_hit_count=len(stop_hits),
        take_profit_hit_count=len(tp_hits),
        signal_exit_count=len(signal_exits),
        time_exit_count=len(time_exits),
        stop_hit_rate=len(stop_hits) / total,
        take_profit_hit_rate=len(tp_hits) / total,
        signal_exit_rate=len(signal_exits) / total,
        time_exit_rate=len(time_exits) / total,
        avg_bars_held=sum(bars_held_list) / total,
        median_bars_held=float(median(bars_held_list)) if bars_held_list else 0.0,
        avg_rr_stop_hits=_avg_rr(stop_hits),
        avg_rr_tp_hits=_avg_rr(tp_hits),
        overall_avg_rr=overall_rr,
    )
