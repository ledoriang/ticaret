import pandas as pd
import pytest

from trading.core.enums import AssetClass, Side
from trading.core.events import SignalEvent
from trading.strategy.filters import (
    CongestionZoneFilter,
    MinCandleBodyFilter,
    TrendAlignmentFilter,
    VolumeConfirmationFilter,
)


def _signal(
    side: Side = Side.BUY,
    symbol: str = "BTC/USDT",
    entry: float = 100.0,
    stop: float = 95.0,
) -> SignalEvent:
    return SignalEvent(
        symbol=symbol,
        side=side,
        confidence=0.7,
        strategy_name="sma_crossover",
        asset_class=AssetClass.CRYPTO,
        source="test",
        entry_price=entry,
        stop_loss_price=stop,
    )


def _df(close: list[float], volume: list[float] | None = None) -> pd.DataFrame:
    n = len(close)
    data = {
        "open": [c - 1.5 for c in close],
        "high": [c + 1.0 for c in close],
        "low": [c - 1.0 for c in close],
        "close": close,
    }
    if volume:
        data["volume"] = volume
    df = pd.DataFrame(data)
    df.index = pd.date_range("2024-01-01", periods=n, freq="D")
    return df


@pytest.mark.asyncio
class TestTrendAlignmentFilter:
    async def test_passes_when_aligned_with_trend(self) -> None:
        # Strong uptrend: close well above 200 SMA
        close = [100 + i * 0.5 for i in range(250)]
        df = _df(close)
        filt = TrendAlignmentFilter(sma_period=200)
        passed, _reason = await filt.evaluate(df, _signal(Side.BUY))
        assert passed

    async def test_blocks_countertrend_buy(self) -> None:
        close = [100 - i * 0.3 for i in range(250)]  # downtrend
        df = _df(close)
        filt = TrendAlignmentFilter(sma_period=200)
        passed, _reason = await filt.evaluate(df, _signal(Side.BUY))
        assert not passed

    async def test_blocks_countertrend_sell(self) -> None:
        close = [100 + i * 0.3 for i in range(250)]  # uptrend
        df = _df(close)
        filt = TrendAlignmentFilter(sma_period=200)
        passed, _reason = await filt.evaluate(df, _signal(Side.SELL))
        assert not passed

    async def test_passes_when_insufficient_data(self) -> None:
        close = [100.0] * 50
        df = _df(close)
        filt = TrendAlignmentFilter(sma_period=200)
        passed, _reason = await filt.evaluate(df, _signal(Side.BUY))
        assert passed


@pytest.mark.asyncio
class TestVolumeConfirmationFilter:
    async def test_passes_when_volume_sufficient(self) -> None:
        close = [100.0] * 25
        volume = [1000.0] * 20 + [2000.0] * 5  # last 5 bars above avg
        df = _df(close, volume)
        filt = VolumeConfirmationFilter(volume_mult=1.5, avg_period=20)
        passed, _reason = await filt.evaluate(df, _signal())
        assert passed

    async def test_blocks_when_volume_too_low(self) -> None:
        close = [100.0] * 25
        volume = [1000.0] * 20 + [100.0] * 5  # last 5 bars well below avg
        df = _df(close, volume)
        filt = VolumeConfirmationFilter(volume_mult=1.5, avg_period=20)
        passed, _reason = await filt.evaluate(df, _signal())
        assert not passed

    async def test_passes_when_no_volume_data(self) -> None:
        close = [100.0] * 25
        df = _df(close)  # no volume column
        filt = VolumeConfirmationFilter()
        passed, _reason = await filt.evaluate(df, _signal())
        assert passed


@pytest.mark.asyncio
class TestCongestionZoneFilter:
    async def test_passes_in_active_market(self) -> None:
        close = [100.0 + i * 0.5 for i in range(20)]  # trending → high ATR/close
        df = _df(close)
        filt = CongestionZoneFilter(atr_threshold=0.01, atr_period=5)
        passed, _reason = await filt.evaluate(df, _signal())
        assert passed

    async def test_blocks_in_congestion(self) -> None:
        close = [100.0 + i * 0.05 for i in range(20)]  # very tight range → low ATR/close
        df = _df(close)
        filt = CongestionZoneFilter(atr_threshold=0.02, atr_period=5)
        passed, _reason = await filt.evaluate(df, _signal())
        assert not passed

    async def test_passes_when_insufficient_data(self) -> None:
        close = [100.0] * 10
        df = _df(close)
        filt = CongestionZoneFilter(atr_period=14)
        passed, _reason = await filt.evaluate(df, _signal())
        assert passed


@pytest.mark.asyncio
class TestMinCandleBodyFilter:
    async def test_passes_with_large_body(self) -> None:
        close = [100.0, 110.0]  # close >> open
        df = _df(close)
        filt = MinCandleBodyFilter(min_body_ratio=0.5)
        passed, _reason = await filt.evaluate(df, _signal())
        assert passed

    async def test_blocks_doji_candle(self) -> None:
        df = pd.DataFrame(
            {
                "open": [100.0, 100.1],
                "high": [102.0, 102.0],
                "low": [98.0, 98.0],
                "close": [100.0, 100.05],  # tiny body relative to range
            }
        )
        filt = MinCandleBodyFilter(min_body_ratio=0.5)
        passed, _reason = await filt.evaluate(df, _signal())
        assert not passed

    async def test_passes_when_no_ohlc_data(self) -> None:
        df = pd.DataFrame({"close": [100.0]})
        filt = MinCandleBodyFilter()
        passed, _reason = await filt.evaluate(df, _signal())
        assert passed
