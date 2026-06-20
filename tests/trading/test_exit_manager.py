from datetime import datetime

import pytest

from trading.core.enums import AssetClass, Side
from trading.core.events import BarEvent, FillEvent
from trading.orchestration.exit_manager import ExitManager


def _bar(
    symbol: str = "BTC/USDT",
    close: float = 100.0,
    high: float | None = None,
    low: float | None = None,
    dt: datetime | None = None,
) -> BarEvent:
    return BarEvent(
        symbol=symbol,
        open=close,
        high=high if high is not None else close + 1.0,
        low=low if low is not None else close - 1.0,
        close=close,
        volume=100.0,
        timestamp=dt or datetime.now(),
        asset_class=AssetClass.CRYPTO,
        source="test",
    )


def _fill(
    symbol: str = "BTC/USDT",
    side: Side = Side.BUY,
    price: float = 100.0,
    qty: float = 1.0,
) -> FillEvent:
    return FillEvent(
        symbol=symbol,
        side=side,
        quantity=qty,
        fill_price=price,
        asset_class=AssetClass.CRYPTO,
        source="test",
    )


class TestExitManagerRegistration:
    def test_register_position_on_buy_fill(self) -> None:
        em = ExitManager()
        fill = _fill(side=Side.BUY, price=100.0)
        em.on_fill(fill)
        assert "BTC/USDT" in em._positions
        pos = em._positions["BTC/USDT"]
        assert pos.side == Side.BUY
        assert pos.entry_price == 100.0
        assert pos.quantity == 1.0

    def test_remove_position_on_sell_fill(self) -> None:
        em = ExitManager()
        em.on_fill(_fill(side=Side.BUY, price=100.0))
        assert "BTC/USDT" in em._positions
        em.on_fill(_fill(side=Side.SELL, price=110.0))
        assert "BTC/USDT" not in em._positions

    def test_no_position_returns_none(self) -> None:
        em = ExitManager()
        bar = _bar(close=100.0)
        assert em.on_bar(bar) is None


class TestStopLoss:
    def test_stop_loss_hit_emits_sell(self) -> None:
        em = ExitManager()
        em.on_fill(_fill(side=Side.BUY, price=100.0))
        # Price drops below stop (initial stop = entry * 0.95 = 95.0)
        bar = _bar(close=94.0)
        order = em.on_bar(bar)
        assert order is not None
        assert order.side == Side.SELL
        assert order.symbol == "BTC/USDT"
        assert order.quantity == 1.0
        assert "BTC/USDT" not in em._positions  # position removed

    def test_stop_loss_not_hit_above_stop(self) -> None:
        em = ExitManager()
        em.on_fill(_fill(side=Side.BUY, price=100.0))
        bar = _bar(close=96.0)  # above stop at 95.0
        order = em.on_bar(bar)
        assert order is None
        assert "BTC/USDT" in em._positions  # position still open


class TestTakeProfit:
    def test_take_profit_hit_emits_sell(self) -> None:
        em = ExitManager()
        em.on_fill(_fill(side=Side.BUY, price=100.0))
        # Price rises above take-profit (initial TP = entry * 1.10 = 110.0)
        bar = _bar(close=111.0)
        order = em.on_bar(bar)
        assert order is not None
        assert order.side == Side.SELL
        assert "BTC/USDT" not in em._positions

    def test_take_profit_not_hit_below_tp(self) -> None:
        em = ExitManager()
        em.on_fill(_fill(side=Side.BUY, price=100.0))
        bar = _bar(close=109.0)  # below TP at 110.0
        order = em.on_bar(bar)
        assert order is None
        assert "BTC/USDT" in em._positions


class TestTimeBasedExit:
    def test_time_exit_after_max_bars(self) -> None:
        em = ExitManager(max_bars=3)
        em.on_fill(_fill(side=Side.BUY, price=100.0))
        # Bar 1: no exit
        assert em.on_bar(_bar(close=100.0)) is None
        # Bar 2: no exit
        assert em.on_bar(_bar(close=100.0)) is None
        # Bar 3: time exit
        order = em.on_bar(_bar(close=100.0))
        assert order is not None
        assert order.side == Side.SELL
        assert "BTC/USDT" not in em._positions

    def test_no_time_exit_before_max_bars(self) -> None:
        em = ExitManager(max_bars=5)
        em.on_fill(_fill(side=Side.BUY, price=100.0))
        for _ in range(4):
            assert em.on_bar(_bar(close=100.0)) is None
        assert "BTC/USDT" in em._positions


class TestTrailingStop:
    def test_trailing_stop_ratchets_up(self) -> None:
        em = ExitManager(trail_method="pct", trail_pct=0.05, max_bars=100)
        em.register_position(
            symbol="BTC/USDT",
            side=Side.BUY,
            entry_price=100.0,
            quantity=1.0,
            stop_loss_price=95.0,
            take_profit_price=None,  # Disable TP for this test
        )
        initial_stop = em._positions["BTC/USDT"].current_stop

        # Price rises to 120 → trailing stop should ratchet up
        em.on_bar(_bar(close=120.0))
        new_stop = em._positions["BTC/USDT"].current_stop
        assert new_stop > initial_stop
        assert new_stop == pytest.approx(120.0 * 0.95)  # 114.0

    def test_trailing_stop_never_loosens(self) -> None:
        em = ExitManager(trail_method="pct", trail_pct=0.05, max_bars=100)
        em.register_position(
            symbol="BTC/USDT",
            side=Side.BUY,
            entry_price=100.0,
            quantity=1.0,
            stop_loss_price=95.0,
            take_profit_price=None,  # Disable TP for this test
        )

        # Price rises to 120 → stop ratchets to 114.0
        em.on_bar(_bar(close=120.0))
        stop_after_rise = em._positions["BTC/USDT"].current_stop

        # Price drops to 115 → stop should NOT loosen (115 > 114, so no exit)
        em.on_bar(_bar(close=115.0))
        stop_after_drop = em._positions["BTC/USDT"].current_stop
        assert stop_after_drop == stop_after_rise  # unchanged

    def test_trailing_stop_triggers_exit(self) -> None:
        em = ExitManager(trail_method="pct", trail_pct=0.05, max_bars=100)
        em.register_position(
            symbol="BTC/USDT",
            side=Side.BUY,
            entry_price=100.0,
            quantity=1.0,
            stop_loss_price=95.0,
            take_profit_price=None,  # Disable TP for this test
        )

        # Price rises to 120 → stop ratchets to 114.0
        em.on_bar(_bar(close=120.0))

        # Price drops to 113 → below trailing stop at 114.0 → exit
        order = em.on_bar(_bar(close=113.0))
        assert order is not None
        assert order.side == Side.SELL
        assert "BTC/USDT" not in em._positions
