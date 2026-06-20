import pandas as pd
import pytest

from trading.core.enums import AssetClass, Side
from trading.core.events import SignalEvent
from trading.risk.regime_filter import RegimeFilter


def _signal(
    side: Side = Side.BUY,
) -> SignalEvent:
    return SignalEvent(
        symbol="BTC/USDT",
        side=side,
        confidence=0.7,
        strategy_name="sma_crossover",
        asset_class=AssetClass.CRYPTO,
        source="test",
        entry_price=100.0,
        stop_loss_price=95.0,
    )


def _df(close: list[float]) -> pd.DataFrame:
    data = {
        "open": [c - 0.5 for c in close],
        "high": [c + 1.0 for c in close],
        "low": [c - 1.0 for c in close],
        "close": close,
    }
    df = pd.DataFrame(data)
    df.index = pd.date_range("2024-01-01", periods=len(close), freq="D")
    return df


@pytest.mark.asyncio
class TestRegimeFilter:
    async def test_allows_trade_in_normal_volatility(self) -> None:
        close = [100.0 + i * 0.5 for i in range(50)]
        df = _df(close)
        filt = RegimeFilter(max_atr_pct=0.05)
        passed, _reason = await filt.check(df, _signal())
        assert passed

    async def test_blocks_trade_in_high_volatility(self) -> None:
        close = [100.0 + (i % 5) * 20 for i in range(50)]  # wild swings
        df = _df(close)
        filt = RegimeFilter(max_atr_pct=0.03)
        passed, reason = await filt.check(df, _signal())
        assert not passed
        assert "volatility" in reason.lower()

    async def test_passes_when_insufficient_data(self) -> None:
        close = [100.0] * 10
        df = _df(close)
        filt = RegimeFilter()
        passed, _reason = await filt.check(df, _signal())
        assert passed

    async def test_allows_trend_strategy_in_trending_market(self) -> None:
        # Strong trend (ADX > 20) — trend strategy should pass
        close = [100.0 + i * 2.0 for i in range(50)]
        df = _df(close)
        filt = RegimeFilter(min_adx_trend=20.0)
        signal = _signal(Side.BUY)
        passed, _reason = await filt.check(df, signal)
        assert passed

    async def test_allows_when_no_signal_provided(self) -> None:
        close = [100.0 + i * 0.5 for i in range(50)]
        df = _df(close)
        filt = RegimeFilter()
        passed, _reason = await filt.check(df)
        assert passed
