import pandas as pd
import pytest

from trading.strategy.sma_crossover import SMACrossoverStrategy


@pytest.mark.asyncio
class TestSMACrossoverStrategy:
    async def test_no_signal_when_insufficient_data(self) -> None:
        strat = SMACrossoverStrategy(fast_period=20, slow_period=50)
        df = pd.DataFrame({"close": [100.0] * 10})
        result = await strat.on_data(df)
        assert result.signal is None

    async def test_no_signal_when_no_cross(self) -> None:
        strat = SMACrossoverStrategy(fast_period=2, slow_period=5)
        data = [100.0, 101.0, 102.0, 103.0, 104.0, 105.0]
        df = pd.DataFrame({"close": data})
        result = await strat.on_data(df)
        assert result.signal is None

    async def test_buy_signal_on_golden_cross(self) -> None:
        strat = SMACrossoverStrategy(fast_period=3, slow_period=5)
        # Last price jump from 100→200 triggers fast SMA(3) = 133.3 crossing above slow SMA(5) = 120
        data = [100, 100, 100, 100, 100, 100, 100, 100, 100, 100, 100, 200]
        df = pd.DataFrame({"close": data})
        result = await strat.on_data(df)
        assert result.signal is not None
        assert result.signal.side.value == "buy"
