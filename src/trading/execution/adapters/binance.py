from collections.abc import Generator
from datetime import datetime

import httpx

from trading.core.enums import AssetClass
from trading.core.events import FillEvent, OrderEvent
from trading.core.market_hours import MarketHours
from trading.core.models import AccountInfo, Bar, Position
from trading.execution.adapters.base import AbstractBrokerAdapter


class BinanceAdapter(AbstractBrokerAdapter):
    name = "binance"
    asset_classes = [AssetClass.CRYPTO]

    BASE_URL = "https://api.binance.com"
    TESTNET_URL = "https://testnet.binance.vision"

    def __init__(self, api_key: str = "", api_secret: str = "", testnet: bool = True) -> None:
        self.api_key = api_key
        self.api_secret = api_secret
        self._base_url = self.TESTNET_URL if testnet else self.BASE_URL
        self._client = httpx.AsyncClient(base_url=self._base_url, headers=self._headers())

    def _headers(self) -> dict[str, str]:
        headers: dict[str, str] = {}
        if self.api_key:
            headers["X-MBX-APIKEY"] = self.api_key
        return headers

    async def get_bars(
        self, symbol: str, timeframe: str, start: datetime, end: datetime
    ) -> list[Bar]:
        interval = self._to_binance_interval(timeframe)
        params = {
            "symbol": symbol.replace("/", ""),
            "interval": interval,
            "startTime": int(start.timestamp() * 1000),
            "endTime": int(end.timestamp() * 1000),
            "limit": 1000,
        }
        str_params: dict[str, str] = {k: str(v) for k, v in params.items()}
        resp = await self._client.get("/api/v3/klines", params=str_params)
        resp.raise_for_status()
        bars: list[Bar] = []
        for k in resp.json():
            bars.append(
                Bar(
                    symbol=symbol,
                    asset_class=AssetClass.CRYPTO,
                    timeframe=timeframe,
                    open=float(k[1]),
                    high=float(k[2]),
                    low=float(k[3]),
                    close=float(k[4]),
                    volume=float(k[5]),
                    timestamp=datetime.fromtimestamp(k[0] / 1000),
                )
            )
        return bars

    async def get_account(self) -> AccountInfo:
        resp = await self._client.get("/api/v3/account")
        resp.raise_for_status()
        data = resp.json()
        balances = {b["asset"]: float(b["free"]) + float(b["locked"]) for b in data["balances"]}
        total = sum(balances.values())
        return AccountInfo(
            broker=self.name,
            total_equity=total,
            cash=balances.get("USDT", 0.0),
            buying_power=total,
            timestamp=datetime.now(),
        )

    async def get_positions(self) -> list[Position]:
        return []

    async def submit_order(self, order: OrderEvent) -> FillEvent:
        params = {
            "symbol": order.symbol.replace("/", ""),
            "side": order.side.value.upper(),
            "type": order.order_type.value.upper(),
            "quantity": str(order.quantity),
        }
        if order.price:
            params["price"] = str(order.price)
        resp = await self._client.post("/api/v3/order", params=params)
        resp.raise_for_status()
        data = resp.json()
        return FillEvent(
            symbol=order.symbol,
            side=order.side,
            quantity=float(data.get("executedQty", order.quantity)),
            fill_price=(
                float(data.get("fills", [{}])[0].get("price", 0.0))
                if data.get("fills")
                else order.price or 0.0
            ),
            commission=sum(float(f["commission"]) for f in data.get("fills", [])),
            order_id=data["orderId"],
            broker=self.name,
            source=self.name,
            correlation_id=order.correlation_id,
        )

    async def cancel_order(self, order_id: str) -> None:
        await self._client.delete("/api/v3/order", params={"orderId": order_id})

    def stream_bars(self, _symbols: list[str], _timeframe: str) -> Generator[Bar, None, None]:
        yield Bar(
            symbol="",
            asset_class=AssetClass.CRYPTO,
            timeframe="",
            open=0.0,
            high=0.0,
            low=0.0,
            close=0.0,
            volume=0.0,
            timestamp=datetime.now(),
        )

    async def get_market_hours(self, _symbol: str) -> MarketHours:
        return MarketHours(always_open=True)

    @staticmethod
    def _to_binance_interval(timeframe: str) -> str:
        mapping = {
            "1m": "1m",
            "3m": "3m",
            "5m": "5m",
            "15m": "15m",
            "30m": "30m",
            "1h": "1h",
            "2h": "2h",
            "4h": "4h",
            "6h": "6h",
            "8h": "8h",
            "12h": "12h",
            "1d": "1d",
            "3d": "3d",
            "1w": "1w",
            "1M": "1M",
        }
        return mapping.get(timeframe, "1d")

    async def close(self) -> None:
        await self._client.aclose()
