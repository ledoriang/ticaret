import pandas as pd
import pytest

from trading.strategy.sma_crossover import SMACrossoverStrategy


def _ohlc(close: float) -> dict[str, float]:
    return {"open": close - 0.5, "high": close + 1.0, "low": close - 1.0, "close": close}


@pytest.mark.asyncio
class TestSMACrossoverStrategy:
    async def test_no_signal_when_insufficient_data(self) -> None:
        strat = SMACrossoverStrategy(fast_period=20, slow_period=50)
        rows = [_ohlc(100.0) for _ in range(10)]
        df = pd.DataFrame(rows)
        result = await strat.on_data(df)
        assert result.signal is None

    async def test_no_signal_when_no_cross(self) -> None:
        strat = SMACrossoverStrategy(fast_period=2, slow_period=5)
        data = [100.0, 101.0, 102.0, 103.0, 104.0, 105.0]
        rows = [_ohlc(v) for v in data]
        df = pd.DataFrame(rows)
        result = await strat.on_data(df)
        assert result.signal is None

    async def test_buy_signal_on_golden_cross(self) -> None:
        strat = SMACrossoverStrategy(fast_period=3, slow_period=5, atr_period=3, atr_multiplier=2.0)
        data = [100, 100, 100, 100, 100, 100, 100, 100, 100, 100, 100, 200]
        rows = [_ohlc(v) for v in data]
        df = pd.DataFrame(rows)
        result = await strat.on_data(df)
        assert result.signal is not None
        assert result.signal.side.value == "buy"
        assert result.signal.entry_price == 200.0
        assert result.signal.stop_loss_price is not None
        assert result.signal.stop_loss_price < 200.0  # stop below entry for BUY

    async def test_sell_signal_on_death_cross(self) -> None:
        strat = SMACrossoverStrategy(fast_period=3, slow_period=5, atr_period=3, atr_multiplier=2.0)
        data = [200, 200, 200, 200, 200, 200, 200, 200, 200, 200, 200, 100]
        rows = [_ohlc(v) for v in data]
        df = pd.DataFrame(rows)
        result = await strat.on_data(df)
        assert result.signal is not None
        assert result.signal.side.value == "sell"
        assert result.signal.entry_price == 100.0
        assert result.signal.stop_loss_price is not None
        assert result.signal.stop_loss_price > 100.0  # stop above entry for SELL

    async def test_signal_carries_atr_based_stop(self) -> None:
        strat = SMACrossoverStrategy(fast_period=3, slow_period=5, atr_period=3, atr_multiplier=2.0)
        # Stable prices then jump: ATR includes the jump
        data = [50, 50, 50, 50, 50, 50, 50, 50, 50, 50, 50, 60]
        rows = [_ohlc(v) for v in data]
        df = pd.DataFrame(rows)
        result = await strat.on_data(df)
        assert result.signal is not None
        assert result.signal.entry_price == 60.0
        # ATR(3) at bar 11: last 3 TR = [2, 2, 11] = 5.0 avg
        # stop_distance = 5.0 * 2.0 = 10.0
        # stop_loss = 60 - 10 = 50
        assert result.signal.stop_loss_price == 50.0
        assert result.signal.take_profit_price == 80.0  # 60 + 10 * 2.0
