import pytest
import respx

from trading.execution.adapters.binance import BinanceAdapter


@pytest.mark.asyncio
class TestBinanceAdapter:
    async def test_interval_mapping(self) -> None:
        assert BinanceAdapter._to_binance_interval("1d") == "1d"
        assert BinanceAdapter._to_binance_interval("1h") == "1h"
        assert BinanceAdapter._to_binance_interval("1m") == "1m"
        assert BinanceAdapter._to_binance_interval("5m") == "5m"
        assert BinanceAdapter._to_binance_interval("1w") == "1w"
        assert BinanceAdapter._to_binance_interval("unknown") == "1d"

    async def test_get_account_mocked(self) -> None:
        adapter = BinanceAdapter(api_key="test_key", api_secret="test_secret", testnet=True)
        with respx.mock:
            respx.get("https://testnet.binance.vision/api/v3/account").respond(
                json={
                    "balances": [
                        {"asset": "BTC", "free": "0.5", "locked": "0.0"},
                        {"asset": "USDT", "free": "50000.0", "locked": "0.0"},
                    ]
                }
            )
            acc = await adapter.get_account()
            assert acc.cash == 50000.0
            assert acc.total_equity == 50000.5  # BTC 0.5 + USDT 50000
            assert acc.broker == "binance"
        await adapter.close()

    async def test_get_positions_mocked(self) -> None:
        adapter = BinanceAdapter(api_key="test_key", api_secret="test_secret", testnet=True)
        with respx.mock:
            respx.get("https://testnet.binance.vision/api/v3/account").respond(
                json={
                    "balances": [
                        {"asset": "BTC", "free": "0.5", "locked": "0.0"},
                        {"asset": "ETH", "free": "2.0", "locked": "0.5"},
                        {"asset": "USDT", "free": "50000.0", "locked": "0.0"},
                        {"asset": "BUSD", "free": "100.0", "locked": "0.0"},
                    ]
                }
            )
            respx.get("https://testnet.binance.vision/api/v3/ticker/price").respond(
                json=[
                    {"symbol": "BTCUSDT", "price": "65000.00"},
                    {"symbol": "ETHUSDT", "price": "3500.00"},
                    {"symbol": "BNBUSDT", "price": "300.00"},
                ]
            )

            positions = await adapter.get_positions()
            assert len(positions) == 2

            btc = [p for p in positions if p.symbol == "BTC/USDT"][0]
            assert btc.quantity == 0.5
            assert btc.current_price == 65000.0

            eth = [p for p in positions if p.symbol == "ETH/USDT"][0]
            assert eth.quantity == 2.5  # 2.0 free + 0.5 locked
            assert eth.current_price == 3500.0
        await adapter.close()

    async def test_get_positions_skips_zero_balances(self) -> None:
        adapter = BinanceAdapter(api_key="test_key", api_secret="test_secret", testnet=True)
        with respx.mock:
            respx.get("https://testnet.binance.vision/api/v3/account").respond(
                json={
                    "balances": [
                        {"asset": "BTC", "free": "0.0", "locked": "0.0"},
                        {"asset": "USDT", "free": "50000.0", "locked": "0.0"},
                    ]
                }
            )
            positions = await adapter.get_positions()
            assert len(positions) == 0
        await adapter.close()

    async def test_get_bars_mocked(self) -> None:
        from datetime import datetime

        adapter = BinanceAdapter(testnet=True)
        with respx.mock:
            respx.get("https://testnet.binance.vision/api/v3/klines").respond(
                json=[
                    [1609459200000, "29000.0", "29500.0", "28800.0", "29200.0", "100.0"],
                    [1609545600000, "29200.0", "29800.0", "29100.0", "29600.0", "150.0"],
                ]
            )
            bars = await adapter.get_bars(
                "BTC/USDT",
                "1d",
                datetime(2021, 1, 1),
                datetime(2021, 1, 3),
            )
            assert len(bars) == 2
            assert bars[0].symbol == "BTC/USDT"
            assert bars[0].close == 29200.0
            assert bars[1].close == 29600.0
        await adapter.close()
