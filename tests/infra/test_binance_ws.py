"""Tests for BinanceFeedHandler and BinanceAdapter.stream_bars()."""

import json
from datetime import datetime

import pytest
import websockets

from trading.core.enums import AssetClass
from trading.core.models import Bar
from trading.data.feeds.binance import BinanceFeedHandler
from trading.execution.adapters.binance import BinanceAdapter


def _kline_msg(symbol: str, close: float, high: float, low: float, is_closed: bool = True) -> str:
    return json.dumps({
        "e": "kline",
        "E": int(datetime.now().timestamp() * 1000),
        "s": symbol,
        "k": {
            "t": int(datetime.now().timestamp() * 1000) - 60000,
            "T": int(datetime.now().timestamp() * 1000),
            "s": symbol,
            "i": "1m",
            "f": 100,
            "L": 200,
            "o": str(close - 1),
            "c": str(close),
            "h": str(high),
            "l": str(low),
            "v": "100.0",
            "n": 10,
            "x": is_closed,
            "q": "5000000",
            "V": "50",
            "Q": "2500000",
            "B": "0",
        },
    })


class TestBinanceFeedHandler:
    """Direct tests for BinanceFeedHandler in isolation."""

    def test_parse_message_returns_bar(self):
        handler = BinanceFeedHandler()
        raw = _kline_msg("BTCUSDT", 50100.0, 50200.0, 49900.0)
        bar = handler.parse_message(raw)
        assert bar is not None
        assert bar.symbol == "BTC/USDT"
        assert bar.close == 50100.0
        assert bar.high == 50200.0
        assert bar.low == 49900.0

    def test_parse_message_returns_none_for_open_candle(self):
        handler = BinanceFeedHandler()
        raw = _kline_msg("BTCUSDT", 50100.0, 50200.0, 49900.0, is_closed=False)
        bar = handler.parse_message(raw)
        assert bar is None

    def test_parse_message_parses_symbol_correctly(self):
        handler = BinanceFeedHandler()
        raw = _kline_msg("ETHUSDT", 3050.0, 3060.0, 2990.0)
        bar = handler.parse_message(raw)
        assert bar.symbol == "ETH/USDT"
        assert bar.asset_class == AssetClass.CRYPTO

    def test_build_url_constructs_correct_stream(self):
        handler = BinanceFeedHandler(ws_url="wss://test:9443/ws")
        url = handler.build_url(["BTC/USDT", "ETH/USDT"], "1m")
        assert "btcusdt@kline_1m" in url
        assert "ethusdt@kline_1m" in url

    def test_build_subscribe_returns_none(self):
        handler = BinanceFeedHandler()
        assert handler.build_subscribe(["BTC/USDT"]) is None

    def test_register_via_registry(self):
        from trading.data.feeds import FEED_HANDLER_REGISTRY

        assert "binance" in FEED_HANDLER_REGISTRY
        assert FEED_HANDLER_REGISTRY["binance"] is BinanceFeedHandler


async def _mock_ws(ws):
    """Send one kline message then close."""
    await ws.send(_kline_msg("BTCUSDT", 50100.0, 50200.0, 49900.0))
    await ws.close()


async def _mock_ws_two_bars(ws):
    """Send two kline messages then close."""
    for i in range(2):
        await ws.send(_kline_msg("BTCUSDT", 50100 + i, 50200 + i, 49900 + i))
    await ws.close()


@pytest.mark.asyncio
class TestBinanceAdapterWithShovel:
    """Integration tests via BinanceAdapter (delegates to shovel)."""

    async def test_stream_bars_yields_bar(self):
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
        adapter = BinanceAdapter(testnet=True)

        async def mock_ws_eth(ws):
            await ws.send(_kline_msg("ETHUSDT", 3050.0, 3060.0, 2990.0))
            await ws.close()

        async with websockets.serve(mock_ws_eth, "localhost", 18766):
            adapter._ws_url = "ws://localhost:18766"
            gen = adapter.stream_bars(["ETH/USDT"], "1m")
            bar = await gen.__anext__()
            assert bar.symbol == "ETH/USDT"
            assert bar.asset_class == AssetClass.CRYPTO

    async def test_stream_bars_yields_multiple_bars(self):
        adapter = BinanceAdapter(testnet=True)
        async with websockets.serve(_mock_ws_two_bars, "localhost", 18767):
            adapter._ws_url = "ws://localhost:18767"
            gen = adapter.stream_bars(["BTC/USDT"], "1m")
            bar1 = await gen.__anext__()
            assert bar1.close == 50100.0
            bar2 = await gen.__anext__()
            assert bar2.close == 50101.0

