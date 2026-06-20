import pytest

from trading.core.enums import AssetClass, Side
from trading.core.events import SignalEvent


def _simulate_position_size(
    signal: SignalEvent, portfolio_value: float, risk_per_trade: float
) -> float:
    entry_price = signal.entry_price or 0.0
    stop_price = signal.stop_loss_price
    if entry_price <= 0 or stop_price is None:
        return max(1.0, signal.confidence * 100)
    stop_distance = abs(entry_price - stop_price)
    if stop_distance <= 0:
        return max(1.0, signal.confidence * 100)
    risk_amount = portfolio_value * risk_per_trade
    return risk_amount / stop_distance


class TestPositionSizing:
    def test_risk_based_sizing_larger_stop_gives_smaller_position(self) -> None:
        signal = SignalEvent(
            symbol="BTC/USDT",
            side=Side.BUY,
            confidence=0.7,
            strategy_name="sma_crossover",
            asset_class=AssetClass.CRYPTO,
            source="test",
            entry_price=50000.0,
            stop_loss_price=49500.0,
        )
        portfolio = 100_000.0
        size = _simulate_position_size(signal, portfolio, 0.01)
        # risk_amount = 100_000 * 0.01 = 1000
        # stop_distance = 500
        # size = 1000 / 500 = 2.0
        assert size == pytest.approx(2.0)

    def test_tighter_stop_gives_larger_position(self) -> None:
        signal = SignalEvent(
            symbol="BTC/USDT",
            side=Side.BUY,
            confidence=0.8,
            strategy_name="sma_crossover",
            asset_class=AssetClass.CRYPTO,
            source="test",
            entry_price=50000.0,
            stop_loss_price=49900.0,
        )
        portfolio = 100_000.0
        size = _simulate_position_size(signal, portfolio, 0.01)
        # risk_amount = 1000, stop_distance = 100
        # size = 1000 / 100 = 10.0
        assert size == pytest.approx(10.0)

    def test_larger_portfolio_gives_larger_position(self) -> None:
        signal = SignalEvent(
            symbol="BTC/USDT",
            side=Side.BUY,
            confidence=0.7,
            strategy_name="sma_crossover",
            asset_class=AssetClass.CRYPTO,
            source="test",
            entry_price=50000.0,
            stop_loss_price=49500.0,
        )
        size_small = _simulate_position_size(signal, 100_000.0, 0.01)
        size_large = _simulate_position_size(signal, 200_000.0, 0.01)
        assert size_large == size_small * 2

    def test_falls_back_to_confidence_when_no_stop(self) -> None:
        signal = SignalEvent(
            symbol="BTC/USDT",
            side=Side.BUY,
            confidence=0.7,
            strategy_name="sma_crossover",
            asset_class=AssetClass.CRYPTO,
            source="test",
        )
        size = _simulate_position_size(signal, 100_000.0, 0.01)
        assert size == max(1.0, signal.confidence * 100)
