import pandas as pd
import pytest

from trading.strategy.rsi_mean_reversion import RSIMeanReversionStrategy


def _ohlc(close: float) -> dict[str, float]:
    return {"open": close - 0.5, "high": close + 1.0, "low": close - 1.0, "close": close}


def _build_uptrend(length: int) -> pd.DataFrame:
    data = [100.0 + i * 0.5 for i in range(length)]
    rows = [_ohlc(v) for v in data]
    return pd.DataFrame(rows)


def _build_downtrend(length: int) -> pd.DataFrame:
    data = [100.0 - i * 0.5 for i in range(length)]
    rows = [_ohlc(v) for v in data]
    return pd.DataFrame(rows)


@pytest.mark.asyncio
class TestRSIMeanReversionStrategy:
    async def test_insufficient_data_returns_no_signal(self) -> None:
        strat = RSIMeanReversionStrategy(rsi_period=14)
        df = _build_uptrend(10)
        result = await strat.on_data(df)
        assert result.signal is None

    async def test_no_signal_when_rsi_neutral(self) -> None:
        strat = RSIMeanReversionStrategy(rsi_period=14)
        df = _build_uptrend(30)
        result = await strat.on_data(df)
        assert result.signal is None

    async def test_buy_signal_on_oversold(self) -> None:
        strat = RSIMeanReversionStrategy(rsi_period=3, oversold=30.0, overbought=70.0)
        # 6 up bars (RSI ~100) then 3 down bars (RSI crosses 30 at last bar)
        data = [100.0, 101.0, 102.0, 103.0, 104.0, 105.0, 104.0, 103.0, 102.0]
        rows = [_ohlc(v) for v in data]
        df = pd.DataFrame(rows)
        result = await strat.on_data(df)
        assert result.signal is not None
        assert result.signal.side.value == "buy"
        assert result.signal.stop_loss_price is not None
        assert result.signal.stop_loss_price < result.signal.entry_price
        assert result.signal.take_profit_price is not None
        assert result.signal.take_profit_price > result.signal.entry_price

    async def test_sell_signal_on_overbought(self) -> None:
        strat = RSIMeanReversionStrategy(rsi_period=3, oversold=30.0, overbought=70.0)
        # 6 down bars (RSI ~0) then 3 up bars (RSI crosses 70 at last bar)
        data = [100.0, 99.0, 98.0, 97.0, 96.0, 95.0, 96.0, 97.0, 98.0]
        rows = [_ohlc(v) for v in data]
        df = pd.DataFrame(rows)
        result = await strat.on_data(df)
        assert result.signal is not None
        assert result.signal.side.value == "sell"
        assert result.signal.stop_loss_price is not None
        assert result.signal.stop_loss_price > result.signal.entry_price
        assert result.signal.take_profit_price is not None
        assert result.signal.take_profit_price < result.signal.entry_price

    async def test_stop_loss_is_swing_low_for_buy(self) -> None:
        strat = RSIMeanReversionStrategy(rsi_period=5, oversold=50.0)
        data = [100.0] * 5 + [90.0] * 5 + [85.0, 85.0, 85.0, 85.0, 85.0, 85.0]
        rows = [_ohlc(v) for v in data]
        df = pd.DataFrame(rows)
        result = await strat.on_data(df)
        if result.signal is not None and result.signal.side.value == "buy":
            expected_swing_low = min(
                df["low"].iloc[-(strat._lookback):]
            )
            assert result.signal.stop_loss_price == expected_swing_low

    async def test_stop_loss_is_swing_high_for_sell(self) -> None:
        strat = RSIMeanReversionStrategy(rsi_period=5, overbought=50.0)
        data = [100.0] * 5 + [110.0] * 5 + [115.0, 115.0, 115.0, 115.0, 115.0, 115.0]
        rows = [_ohlc(v) for v in data]
        df = pd.DataFrame(rows)
        result = await strat.on_data(df)
        if result.signal is not None and result.signal.side.value == "sell":
            expected_swing_high = max(
                df["high"].iloc[-(strat._lookback):]
            )
            assert result.signal.stop_loss_price == expected_swing_high

    async def test_take_profit_at_2_to_1_rr(self) -> None:
        strat = RSIMeanReversionStrategy(rsi_period=5, oversold=50.0, rr_ratio=2.0)
        data = [100.0, 99.0, 98.0, 97.0, 96.0, 95.0, 70.0, 70.0, 70.0, 70.0, 70.0]
        rows = [_ohlc(v) for v in data]
        df = pd.DataFrame(rows)
        result = await strat.on_data(df)
        if result.signal is not None and result.signal.side.value == "buy":
            entry = result.signal.entry_price
            stop = result.signal.stop_loss_price
            assert stop is not None
            distance = entry - stop
            tp = result.signal.take_profit_price
            assert tp is not None
            assert tp == pytest.approx(entry + distance * 2.0)

    async def test_does_not_fire_without_cross(self) -> None:
        strat = RSIMeanReversionStrategy(rsi_period=5, oversold=20.0, overbought=80.0)
        # RSI already below oversold — no cross event
        data = [100.0] * 4 + [99.0] * 7
        rows = [_ohlc(v) for v in data]
        df = pd.DataFrame(rows)
        result = await strat.on_data(df)
        assert result.signal is None

    async def test_lookback_equals_rsi_period_plus_5(self) -> None:
        strat = RSIMeanReversionStrategy(rsi_period=14)
        assert strat._lookback == 19
