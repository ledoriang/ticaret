import pytest

from trading.execution.adapters.binance import BinanceAdapter


@pytest.mark.asyncio
class TestBinanceAdapter:
    async def test_interval_mapping(self) -> None:
        assert BinanceAdapter._to_binance_interval("1d") == "1d"
        assert BinanceAdapter._to_binance_interval("1h") == "1h"
        assert BinanceAdapter._to_binance_interval("1m") == "1m"
