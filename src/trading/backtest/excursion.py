from dataclasses import dataclass

from trading.backtest.backtest_types import ClosedTrade


@dataclass
class ExcursionMetrics:
    total_trades: int = 0
    avg_mae: float = 0.0
    avg_mfe: float = 0.0
    median_mae: float = 0.0
    median_mfe: float = 0.0
    max_mae: float = 0.0
    max_mfe: float = 0.0
    stops_too_tight: float = 0.0
    stops_too_loose: float = 0.0


def compute_excursion(
    trades: list[ClosedTrade], stop_distance_pct: float = 0.02
) -> ExcursionMetrics:
    if not trades:
        return ExcursionMetrics()

    mae_values = [abs(t.mae) for t in trades]
    mfe_values = [abs(t.mfe) for t in trades]
    sorted_mae = sorted(mae_values)
    sorted_mfe = sorted(mfe_values)
    n = len(sorted_mae)

    # stops_too_tight: MAE exceeds typical stop distance frequently
    tight_count = sum(1 for m in mae_values if m > stop_distance_pct * 100)
    # stops_too_loose: MAE much larger than final profit (ratio > 3)
    loose_count = sum(
        1 for t in trades
        if abs(t.mae) > 0 and abs(t.net_pnl) > 0
        and abs(t.mae) > abs(t.net_pnl) * 3
    )

    return ExcursionMetrics(
        total_trades=n,
        avg_mae=sum(mae_values) / n,
        avg_mfe=sum(mfe_values) / n,
        median_mae=sorted_mae[n // 2] if n > 0 else 0.0,
        median_mfe=sorted_mfe[n // 2] if n > 0 else 0.0,
        max_mae=max(mae_values),
        max_mfe=max(mfe_values),
        stops_too_tight=tight_count / n if n > 0 else 0.0,
        stops_too_loose=loose_count / n if n > 0 else 0.0,
    )
