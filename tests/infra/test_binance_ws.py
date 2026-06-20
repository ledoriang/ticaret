import json
from datetime import datetime

import pytest
import websockets

from trading.core.enums import AssetClass
from trading.core.models import Bar
from trading.execution.adapters.binance import BinanceAdapter


async def _mock_ws(ws):
    """Send one kline message then close."""
    msg = {
        "e": "kline",
        "E": int(datetime.now().timestamp() * 1000),
        "s": "BTCUSDT",
        "k": {
            "t": int(datetime.now().timestamp() * 1000) - 60000,
            "T": int(datetime.now().timestamp() * 1000),
            "s": "BTCUSDT",
            "i": "1m",
            "f": 100,
            "L": 200,
            "o": "50000.0",
            "c": "50100.0",
            "h": "50200.0",
            "l": "49900.0",
            "v": "100.0",
            "n": 10,
            "x": True,
            "q": "5000000",
            "V": "50",
            "Q": "2500000",
            "B": "0",
        },
    }
    await ws.send(json.dumps(msg))
    await ws.close()


async def _mock_ws_two_bars(ws):
    """Send two kline messages then close."""
    for i in range(2):
        msg = {
            "e": "kline",
            "E": int(datetime.now().timestamp() * 1000),
            "s": "BTCUSDT",
            "k": {
                "t": int(datetime.now().timestamp() * 1000) - 60000,
                "T": int(datetime.now().timestamp() * 1000),
                "s": "BTCUSDT",
                "i": "1m",
                "f": 100,
                "L": 200,
                "o": "50000.0",
                "c": f"{50100 + i}.0",
                "h": f"{50200 + i}.0",
                "l": f"{49900 + i}.0",
                "v": "100.0",
                "n": 10,
                "x": True,
                "q": "5000000",
                "V": "50",
                "Q": "2500000",
                "B": "0",
            },
        }
        await ws.send(json.dumps(msg))
    await ws.close()


@pytest.mark.asyncio
class TestBinanceWebSocket:
    async def test_stream_bars_yields_bar(self):
        """Test that stream_bars yields a Bar object from WS data."""
        adapter = BinanceAdapter(testnet=True)
        async with websockets.serve(_mock_ws, "localhost", 18765):
            adapter._ws_url = "ws://localhost:18765"
            gen = adapter.stream_bars(["BTC/USDT"], "1m")
            bar = await gen.__anext__()
            assert isinstance(bar, Bar)
            assert bar.symbol == "BTC/USDT"
            assert bar.close == 50100.0
            assert bar.high == 50200.0
            assert bar.low == 49900.0

    async def test_stream_bars_parses_symbol_correctly(self):
        """Test that the symbol is parsed correctly from Binance format."""
        adapter = BinanceAdapter(testnet=True)

        async def mock_ws_eth(ws):
            msg = {
                "e": "kline",
                "E": int(datetime.now().timestamp() * 1000),
                "s": "ETHUSDT",
                "k": {
                    "t": int(datetime.now().timestamp() * 1000) - 60000,
                    "T": int(datetime.now().timestamp() * 1000),
                    "s": "ETHUSDT",
                    "i": "1m",
                    "f": 100,
                    "L": 200,
                    "o": "3000.0",
                    "c": "3050.0",
                    "h": "3060.0",
                    "l": "2990.0",
                    "v": "500.0",
                    "n": 10,
                    "x": True,
                    "q": "1500000",
                    "V": "250",
                    "Q": "750000",
                    "B": "0",
                },
            }
            await ws.send(json.dumps(msg))
            await ws.close()

        async with websockets.serve(mock_ws_eth, "localhost", 18766):
            adapter._ws_url = "ws://localhost:18766"
            gen = adapter.stream_bars(["ETH/USDT"], "1m")
            bar = await gen.__anext__()
            assert bar.symbol == "ETH/USDT"
            assert bar.asset_class == AssetClass.CRYPTO

    async def test_stream_bars_yields_multiple_bars(self):
        """Test that stream_bars yields multiple bars from one connection."""
        adapter = BinanceAdapter(testnet=True)
        async with websockets.serve(_mock_ws_two_bars, "localhost", 18767):
            adapter._ws_url = "ws://localhost:18767"
            gen = adapter.stream_bars(["BTC/USDT"], "1m")
            bar1 = await gen.__anext__()
            assert bar1.close == 50100.0
            bar2 = await gen.__anext__()
            assert bar2.close == 50101.0
