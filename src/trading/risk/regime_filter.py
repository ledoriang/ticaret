import pandas as pd

from trading.core.events import SignalEvent


def _atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    high = df.get("high", df["close"])
    low = df.get("low", df["close"])
    close = df["close"]
    tr = pd.concat(
        [
            high - low,
            (high - close.shift(1)).abs(),
            (low - close.shift(1)).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return tr.rolling(window=period).mean()


def _adx(df: pd.DataFrame, period: int = 14) -> float | None:
    high = df.get("high", df["close"])
    low = df.get("low", df["close"])
    close = df["close"]
    if len(close) < period * 2 + 1:
        return None

    plus_dm = high.diff()
    minus_dm = low.diff().abs()
    tr = _atr(df, period=period)

    plus_di = 100 * (plus_dm.rolling(window=period).mean() / tr)
    minus_di = 100 * (minus_dm.rolling(window=period).mean() / tr)
    dx = 100 * ((plus_di - minus_di).abs() / (plus_di + minus_di))
    adx_series = dx.rolling(window=period).mean()

    if pd.isna(adx_series.iloc[-1]):
        return None
    return float(adx_series.iloc[-1])


class RegimeFilter:
    name = "regime_filter"

    def __init__(
        self,
        max_atr_pct: float = 0.05,
        min_adx_trend: float = 20.0,
        max_adx_range: float = 25.0,
    ) -> None:
        self.max_atr_pct = max_atr_pct
        self.min_adx_trend = min_adx_trend
        self.max_adx_range = max_adx_range

    async def check(
        self, df: pd.DataFrame, signal: SignalEvent | None = None
    ) -> tuple[bool, str]:
        close = df["close"]
        if len(close) < 15:
            return True, ""

        current_close = float(close.iloc[-1])
        if current_close <= 0:
            return True, ""

        atr_series = _atr(df, period=14)
        atr_value = float(atr_series.iloc[-1]) if not pd.isna(atr_series.iloc[-1]) else 0.0

        if atr_value > 0:
            atr_pct = atr_value / current_close
            if atr_pct > self.max_atr_pct:
                msg = (
                    f"Volatility too high: ATR/close ({atr_pct:.2%}) "
                    f"exceeds {self.max_atr_pct:.2%}"
                )
                return False, msg

        adx_value = _adx(df, period=14)
        if adx_value is not None and signal is not None:
            from trading.strategy.filters import _sma

            fast_sma = _sma(close, length=20)
            slow_sma = _sma(close, length=50)
            is_trend_strategy = (
                len(fast_sma) >= 2
                and len(slow_sma) >= 2
                and not pd.isna(fast_sma.iloc[-2])
                and not pd.isna(slow_sma.iloc[-2])
            )

            if is_trend_strategy and adx_value < self.min_adx_trend:
                msg = (
                    f"Trend strategy suppressed: ADX ({adx_value:.1f}) "
                    f"below {self.min_adx_trend}"
                )
                return False, msg

            if not is_trend_strategy and adx_value > self.max_adx_range:
                msg = (
                    f"Mean-reversion suppressed: ADX ({adx_value:.1f}) "
                    f"above {self.max_adx_range}"
                )
                return False, msg

        return True, ""
