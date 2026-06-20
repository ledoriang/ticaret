from abc import ABC, abstractmethod

import pandas as pd

from trading.core.events import SignalEvent


def _sma(series: pd.Series, length: int) -> pd.Series:
    return series.rolling(window=length).mean()


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


class SignalFilter(ABC):
    name: str = ""

    @abstractmethod
    async def evaluate(self, df: pd.DataFrame, signal: SignalEvent) -> tuple[bool, str]: ...


class TrendAlignmentFilter(SignalFilter):
    name = "trend_alignment"

    def __init__(self, sma_period: int = 200) -> None:
        self.sma_period = sma_period

    async def evaluate(
        self, df: pd.DataFrame, signal: SignalEvent
    ) -> tuple[bool, str]:
        from trading.core.enums import Side

        close = df["close"]
        if len(close) < self.sma_period + 1:
            return True, ""

        sma = _sma(close, length=self.sma_period)
        current_close = float(close.iloc[-1])
        current_sma = float(sma.iloc[-1])
        if pd.isna(current_sma):
            return True, ""

        if signal.side == Side.BUY and current_close < current_sma:
            msg = (
                f"BUY but close ({current_close:.2f}) below "
                f"{self.sma_period} SMA ({current_sma:.2f})"
            )
            return False, msg
        if signal.side == Side.SELL and current_close > current_sma:
            msg = (
                f"SELL but close ({current_close:.2f}) above "
                f"{self.sma_period} SMA ({current_sma:.2f})"
            )
            return False, msg
        return True, ""


class VolumeConfirmationFilter(SignalFilter):
    name = "volume_confirmation"

    def __init__(self, volume_mult: float = 1.5, avg_period: int = 20) -> None:
        self.volume_mult = volume_mult
        self.avg_period = avg_period

    async def evaluate(
        self, df: pd.DataFrame, _signal: SignalEvent  # noqa: ARG002
    ) -> tuple[bool, str]:
        if "volume" not in df.columns:
            return True, ""

        volume = df["volume"]
        if len(volume) < self.avg_period + 1:
            return True, ""

        avg_volume = float(volume.iloc[-self.avg_period:].mean())
        current_volume = float(volume.iloc[-1])

        if avg_volume <= 0:
            return True, ""

        if current_volume < avg_volume * self.volume_mult:
            msg = (
                f"Volume ({current_volume:.0f}) below "
                f"{self.volume_mult:.1f}x avg ({avg_volume:.0f})"
            )
            return False, msg
        return True, ""


class CongestionZoneFilter(SignalFilter):
    name = "congestion_zone"

    def __init__(self, atr_threshold: float = 0.01, atr_period: int = 14) -> None:
        self.atr_threshold = atr_threshold
        self.atr_period = atr_period

    async def evaluate(
        self, df: pd.DataFrame, _signal: SignalEvent  # noqa: ARG002
    ) -> tuple[bool, str]:
        close = df["close"]
        if len(close) < self.atr_period + 1:
            return True, ""

        atr_series = _atr(df, period=self.atr_period)
        current_atr = float(atr_series.iloc[-1])
        current_close = float(close.iloc[-1])

        if pd.isna(current_atr) or current_close <= 0:
            return True, ""

        atr_pct = current_atr / current_close
        if atr_pct < self.atr_threshold:
            msg = (
                f"ATR/close ({atr_pct:.2%}) below "
                f"congestion threshold ({self.atr_threshold:.2%})"
            )
            return False, msg
        return True, ""


class MinCandleBodyFilter(SignalFilter):
    name = "min_candle_body"

    def __init__(self, min_body_ratio: float = 0.5) -> None:
        self.min_body_ratio = min_body_ratio

    async def evaluate(
        self, df: pd.DataFrame, _signal: SignalEvent  # noqa: ARG002
    ) -> tuple[bool, str]:
        if "open" not in df.columns or "high" not in df.columns or "low" not in df.columns:
            return True, ""

        open_p = float(df["open"].iloc[-1])
        high = float(df["high"].iloc[-1])
        low = float(df["low"].iloc[-1])
        close = float(df["close"].iloc[-1])

        body = abs(close - open_p)
        wick = high - low

        if wick <= 0:
            return True, ""

        body_ratio = body / wick
        if body_ratio < self.min_body_ratio:
            msg = (
                f"Body/range ({body_ratio:.1%}) below "
                f"threshold ({self.min_body_ratio:.0%})"
            )
            return False, msg
        return True, ""
