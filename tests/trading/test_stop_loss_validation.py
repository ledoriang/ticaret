import pytest

from trading.core.enums import AssetClass, Side
from trading.core.events import SignalEvent
from trading.risk.rules import StopLossValidationRule


@pytest.fixture
def buy_signal() -> SignalEvent:
    return SignalEvent(
        symbol="BTC/USDT",
        side=Side.BUY,
        confidence=0.7,
        strategy_name="sma_crossover",
        asset_class=AssetClass.CRYPTO,
        source="test",
        entry_price=50000.0,
        stop_loss_price=49500.0,
    )


@pytest.fixture
def sell_signal() -> SignalEvent:
    return SignalEvent(
        symbol="BTC/USDT",
        side=Side.SELL,
        confidence=0.7,
        strategy_name="sma_crossover",
        asset_class=AssetClass.CRYPTO,
        source="test",
        entry_price=50000.0,
        stop_loss_price=50500.0,
    )


@pytest.mark.asyncio
class TestStopLossValidationRule:
    async def test_valid_buy_signal_passes(self, buy_signal: SignalEvent) -> None:
        rule = StopLossValidationRule()
        passed, _reason = await rule.evaluate(buy_signal)
        assert passed

    async def test_valid_sell_signal_passes(self, sell_signal: SignalEvent) -> None:
        rule = StopLossValidationRule()
        passed, _reason = await rule.evaluate(sell_signal)
        assert passed

    async def test_missing_stop_loss(self, buy_signal: SignalEvent) -> None:
        rule = StopLossValidationRule()
        buy_signal.stop_loss_price = None
        passed, reason = await rule.evaluate(buy_signal)
        assert not passed
        assert "missing" in reason.lower()

    async def test_missing_entry_price(self, buy_signal: SignalEvent) -> None:
        rule = StopLossValidationRule()
        buy_signal.entry_price = None
        passed, reason = await rule.evaluate(buy_signal)
        assert not passed
        assert "missing" in reason.lower()

    async def test_stop_above_entry_for_buy(self, buy_signal: SignalEvent) -> None:
        rule = StopLossValidationRule()
        buy_signal.stop_loss_price = 51000.0  # above entry 50000
        passed, reason = await rule.evaluate(buy_signal)
        assert not passed
        assert "below" in reason.lower()

    async def test_stop_below_entry_for_sell(self, sell_signal: SignalEvent) -> None:
        rule = StopLossValidationRule()
        sell_signal.stop_loss_price = 49000.0  # below entry 50000
        passed, reason = await rule.evaluate(sell_signal)
        assert not passed
        assert "above" in reason.lower()

    async def test_zero_stop_loss(self, buy_signal: SignalEvent) -> None:
        rule = StopLossValidationRule()
        buy_signal.stop_loss_price = 0.0
        passed, _reason = await rule.evaluate(buy_signal)
        assert not passed
