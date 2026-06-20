from datetime import datetime
from unittest.mock import AsyncMock

import pandas as pd
import pytest

from trading.core.enums import AssetClass
from trading.core.models import Bar
from trading.orchestration.bar_buffer import BarBuffer


def _make_bar(symbol: str, close: float, dt: datetime | None = None) -> Bar:
    return Bar(
        symbol=symbol,
        asset_class=AssetClass.CRYPTO,
        timeframe="1d",
        open=close - 1.0,
        high=close + 1.0,
        low=close - 2.0,
        close=close,
        volume=100.0,
        timestamp=dt or datetime.now(),
    )


@pytest.fixture
def buffer() -> BarBuffer:
    return BarBuffer(max_size=5)


class TestBarBuffer:
    def test_add_returns_dataframe_with_correct_shape(self, buffer: BarBuffer) -> None:
        df = buffer.add("BTC/USDT", _make_bar("BTC/USDT", 50000.0))
        assert isinstance(df, pd.DataFrame)
        assert list(df.columns) == ["open", "high", "low", "close", "volume", "symbol"]
        assert len(df) == 1
        assert df["close"].iloc[-1] == 50000.0

    def test_add_multiple_bars_increases_length(self, buffer: BarBuffer) -> None:
        for i in range(3):
            buffer.add("BTC/USDT", _make_bar("BTC/USDT", float(50000 + i * 100)))
        df = buffer.get("BTC/USDT")
        assert len(df) == 3
        assert df["close"].iloc[-1] == 50200.0

    def test_eviction_oldest_bar(self, buffer: BarBuffer) -> None:
        for i in range(6):
            buffer.add("BTC/USDT", _make_bar("BTC/USDT", float(50000 + i * 100)))
        df = buffer.get("BTC/USDT")
        assert len(df) == 5  # max_size
        assert df["close"].iloc[0] == 50100.0  # oldest retained, not 50000.0

    def test_size_method(self, buffer: BarBuffer) -> None:
        assert buffer.size("BTC/USDT") == 0
        buffer.add("BTC/USDT", _make_bar("BTC/USDT", 50000.0))
        assert buffer.size("BTC/USDT") == 1

    def test_get_returns_empty_dataframe_for_unknown_symbol(self, buffer: BarBuffer) -> None:
        df = buffer.get("UNKNOWN")
        assert isinstance(df, pd.DataFrame)
        assert df.empty

    def test_symbols_isolated(self, buffer: BarBuffer) -> None:
        buffer.add("BTC/USDT", _make_bar("BTC/USDT", 50000.0))
        buffer.add("ETH/USDT", _make_bar("ETH/USDT", 3000.0))
        assert buffer.size("BTC/USDT") == 1
        assert buffer.size("ETH/USDT") == 1
        assert buffer.get("ETH/USDT")["close"].iloc[-1] == 3000.0

    def test_dataframe_is_sorted_by_timestamp(self, buffer: BarBuffer) -> None:
        from datetime import timedelta

        now = datetime.now()
        buffer.add("BTC/USDT", _make_bar("BTC/USDT", 51000.0, dt=now + timedelta(minutes=2)))
        buffer.add("BTC/USDT", _make_bar("BTC/USDT", 50000.0, dt=now))
        buffer.add("BTC/USDT", _make_bar("BTC/USDT", 50500.0, dt=now + timedelta(minutes=1)))
        df = buffer.get("BTC/USDT")
        assert list(df["close"]) == [50000.0, 50500.0, 51000.0]

    def test_clear_symbol(self, buffer: BarBuffer) -> None:
        buffer.add("BTC/USDT", _make_bar("BTC/USDT", 50000.0))
        buffer.add("ETH/USDT", _make_bar("ETH/USDT", 3000.0))
        buffer.clear("BTC/USDT")
        assert buffer.size("BTC/USDT") == 0
        assert buffer.size("ETH/USDT") == 1

    def test_clear_all(self, buffer: BarBuffer) -> None:
        buffer.add("BTC/USDT", _make_bar("BTC/USDT", 50000.0))
        buffer.add("ETH/USDT", _make_bar("ETH/USDT", 3000.0))
        buffer.clear()
        assert buffer.size("BTC/USDT") == 0
        assert buffer.size("ETH/USDT") == 0


@pytest.mark.asyncio
class TestBarBufferColdStart:
    async def test_cold_start_populates_buffer(self, buffer: BarBuffer) -> None:
        mock_adapter = AsyncMock()
        mock_adapter.get_bars.return_value = [
            _make_bar("BTC/USDT", 50000.0),
            _make_bar("BTC/USDT", 51000.0),
            _make_bar("BTC/USDT", 52000.0),
        ]
        count = await buffer.cold_start(
            symbol="BTC/USDT",
            adapter=mock_adapter,
            timeframe="1d",
            start=datetime(2024, 1, 1),
            end=datetime(2024, 1, 10),
        )
        assert count == 3
        assert buffer.size("BTC/USDT") == 3
        mock_adapter.get_bars.assert_awaited_once_with(
            "BTC/USDT", "1d", datetime(2024, 1, 1), datetime(2024, 1, 10)
        )

    async def test_cold_start_empty_response(self, buffer: BarBuffer) -> None:
        mock_adapter = AsyncMock()
        mock_adapter.get_bars.return_value = []
        count = await buffer.cold_start(
            symbol="BTC/USDT",
            adapter=mock_adapter,
            timeframe="1d",
            start=datetime(2024, 1, 1),
            end=datetime(2024, 1, 2),
        )
        assert count == 0
        assert buffer.size("BTC/USDT") == 0

    async def test_cold_start_does_not_exceed_max_size(self, buffer: BarBuffer) -> None:
        mock_adapter = AsyncMock()
        mock_adapter.get_bars.return_value = [
            _make_bar("BTC/USDT", float(i)) for i in range(10)
        ]
        await buffer.cold_start(
            symbol="BTC/USDT",
            adapter=mock_adapter,
            timeframe="1d",
            start=datetime(2024, 1, 1),
            end=datetime(2024, 1, 10),
        )
        assert buffer.size("BTC/USDT") == 5  # max_size

