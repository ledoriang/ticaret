from datetime import datetime

from trading.backtest.backtest_types import ClosedTrade
from trading.backtest.excursion import compute_excursion
from trading.backtest.stop_analysis import compute_stop_analysis
from trading.core.enums import Side


def _make_trade(
    exit_reason: str,
    entry_price: float = 100.0,
    exit_price: float = 95.0,
    mae: float = -8.0,
    mfe: float = 5.0,
    bars_held: int = 5,
    net_pnl: float = -5.0,
) -> ClosedTrade:
    return ClosedTrade(
        symbol="BTC/USDT",
        side=Side.BUY,
        entry_time=datetime(2024, 1, 1),
        exit_time=datetime(2024, 1, 10),
        entry_price=entry_price,
        exit_price=exit_price,
        quantity=1.0,
        gross_pnl=exit_price - entry_price,
        net_pnl=net_pnl,
        commission=0.5,
        slippage_cost=0.5,
        exit_reason=exit_reason,
        mae=mae,
        mfe=mfe,
        bars_held=bars_held,
    )


class TestStopAnalysis:
    def test_all_stop_hits(self) -> None:
        trades = [_make_trade("stop_loss") for _ in range(10)]
        sa = compute_stop_analysis(trades)
        assert sa.stop_hit_rate == 1.0
        assert sa.take_profit_hit_rate == 0.0
        assert sa.total_trades == 10

    def test_all_tp_hits(self) -> None:
        trades = [_make_trade("take_profit", net_pnl=10.0) for _ in range(5)]
        sa = compute_stop_analysis(trades)
        assert sa.take_profit_hit_rate == 1.0
        assert sa.stop_hit_rate == 0.0

    def test_mixed_exits(self) -> None:
        trades = [_make_trade("stop_loss") for _ in range(3)]
        trades += [_make_trade("take_profit", net_pnl=10.0) for _ in range(2)]
        sa = compute_stop_analysis(trades)
        assert sa.stop_hit_rate == 0.6
        assert sa.take_profit_hit_rate == 0.4

    def test_signal_exits(self) -> None:
        trades = [_make_trade("signal") for _ in range(4)]
        sa = compute_stop_analysis(trades)
        assert sa.signal_exit_rate == 1.0

    def test_time_exits(self) -> None:
        trades = [_make_trade("time_exit") for _ in range(3)]
        sa = compute_stop_analysis(trades)
        assert sa.time_exit_rate == 1.0

    def test_empty_list(self) -> None:
        sa = compute_stop_analysis([])
        assert sa.total_trades == 0
        assert sa.stop_hit_rate == 0.0

    def test_avg_bars_held(self) -> None:
        trades = [
            _make_trade("stop_loss", bars_held=3),
            _make_trade("stop_loss", bars_held=7),
        ]
        sa = compute_stop_analysis(trades)
        assert sa.avg_bars_held == 5.0
        assert sa.median_bars_held == 5.0

    def test_overall_rr(self) -> None:
        trades = [
            _make_trade("stop_loss", entry_price=100, exit_price=90, net_pnl=-10.0),
            _make_trade("take_profit", entry_price=100, exit_price=120, net_pnl=20.0),
        ]
        sa = compute_stop_analysis(trades)
        assert sa.overall_avg_rr > 0


class TestExcursionAnalysis:
    def test_avg_mae_mfe(self) -> None:
        trades = [
            _make_trade("stop_loss", mae=-5.0, mfe=2.0),
            _make_trade("take_profit", mae=-3.0, mfe=8.0),
        ]
        exc = compute_excursion(trades)
        assert exc.avg_mae == 4.0
        assert exc.avg_mfe == 5.0

    def test_max_mae_mfe(self) -> None:
        trades = [
            _make_trade("stop_loss", mae=-2.0, mfe=1.0),
            _make_trade("stop_loss", mae=-10.0, mfe=3.0),
            _make_trade("take_profit", mae=-5.0, mfe=15.0),
        ]
        exc = compute_excursion(trades)
        assert exc.max_mae == 10.0
        assert exc.max_mfe == 15.0

    def test_empty_list(self) -> None:
        exc = compute_excursion([])
        assert exc.total_trades == 0

    def test_median_values(self) -> None:
        trades = [
            _make_trade("stop_loss", mae=-1.0, mfe=1.0),
            _make_trade("stop_loss", mae=-5.0, mfe=3.0),
            _make_trade("take_profit", mae=-2.0, mfe=8.0),
        ]
        exc = compute_excursion(trades)
        assert exc.median_mae == 2.0
        assert exc.median_mfe == 3.0
