from collections import deque
from datetime import datetime

import pandas as pd

from trading.core.models import Bar
from trading.execution.adapters.base import AbstractBrokerAdapter


class BarBuffer:
    def __init__(self, max_size: int = 100) -> None:
        self.max_size = max_size
        self._buffers: dict[str, deque[Bar]] = {}

    def _ensure_symbol(self, symbol: str) -> deque[Bar]:
        if symbol not in self._buffers:
            self._buffers[symbol] = deque[Bar](maxlen=self.max_size)
        return self._buffers[symbol]

    def add(self, symbol: str, bar: Bar) -> pd.DataFrame:
        buf = self._ensure_symbol(symbol)
        buf.append(bar)
        return self._to_df(symbol)

    def _to_df(self, symbol: str) -> pd.DataFrame:
        buf = self._buffers.get(symbol)
        if not buf:
            return pd.DataFrame()
        rows = [
            {
                "open": b.open,
                "high": b.high,
                "low": b.low,
                "close": b.close,
                "volume": b.volume,
                "symbol": b.symbol,
                "timestamp": b.timestamp,
            }
            for b in buf
        ]
        df = pd.DataFrame(rows)
        df = df.set_index("timestamp").sort_index()
        df.index = pd.DatetimeIndex(df.index)
        numeric_cols = ["open", "high", "low", "close", "volume"]
        df[numeric_cols] = df[numeric_cols].apply(pd.to_numeric, errors="coerce")
        return df

    def get(self, symbol: str) -> pd.DataFrame:
        return self._to_df(symbol)

    def size(self, symbol: str) -> int:
        buf = self._buffers.get(symbol)
        return len(buf) if buf else 0

    def clear(self, symbol: str | None = None) -> None:
        if symbol:
            self._buffers.pop(symbol, None)
        else:
            self._buffers.clear()

    async def cold_start(
        self,
        symbol: str,
        adapter: AbstractBrokerAdapter,
        timeframe: str,
        start: datetime,
        end: datetime,
    ) -> int:
        bars = await adapter.get_bars(symbol, timeframe, start, end)
        count = 0
        for bar in bars:
            self.add(symbol, bar)
            count += 1
        return count
