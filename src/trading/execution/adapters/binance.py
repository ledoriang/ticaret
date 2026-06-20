from collections.abc import AsyncGenerator
from datetime import datetime
from typing import Any
from urllib.parse import urlencode

import httpx
import structlog

from trading.core.enums import AssetClass
from trading.core.events import FillEvent, OrderEvent
from trading.core.market_hours import MarketHours
from trading.core.models import AccountInfo, Bar, Position
from trading.execution.adapters.base import AbstractBrokerAdapter

logger = structlog.get_logger(__name__)


class BinanceAdapter(AbstractBrokerAdapter):
    name = "binance"
    asset_classes = [AssetClass.CRYPTO]

    BASE_URL = "https://api.binance.com"
    TESTNET_URL = "https://testnet.binance.vision"
    WS_BASE = "wss://stream.binance.com:9443/ws"
    TESTNET_WS = "wss://testnet.binance.vision/ws"

    def __init__(self, api_key: str = "", api_secret: str = "", testnet: bool = True) -> None:
        self.api_key = api_key
        self.api_secret = api_secret
        self._testnet = testnet
        self._base_url = self.TESTNET_URL if testnet else self.BASE_URL
        self._ws_url = self.TESTNET_WS if testnet else self.WS_BASE
        self._client = httpx.AsyncClient(base_url=self._base_url, headers=self._headers())

    def _headers(self) -> dict[str, str]:
        headers: dict[str, str] = {}
        if self.api_key:
            headers["X-MBX-APIKEY"] = self.api_key
        return headers

    def _sign(self, params: dict[str, Any]) -> dict[str, Any]:
        import hashlib
        import hmac

        params["timestamp"] = int(datetime.now().timestamp() * 1000)
        query = urlencode(params)
        signature = hmac.new(
            self.api_secret.encode("utf-8"),
            query.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        params["signature"] = signature
        return params

    def _check_error(self, data: dict[str, Any]) -> None:
        if "code" in data and data["code"] != 0:
            msg = data.get("msg", "Unknown error")
            raise ValueError(f"Binance API error {data['code']}: {msg}")

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
        data = resp.json()
        self._check_error(data)
        bars: list[Bar] = []
        for k in data:
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
        params = self._sign({})
        resp = await self._client.get("/api/v3/account", params=params)
        data = resp.json()
        self._check_error(data)
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
        params = self._sign({})
        resp = await self._client.get("/api/v3/account", params=params)
        data = resp.json()
        self._check_error(data)

        non_zero: list[dict[str, Any]] = [
            b for b in data.get("balances", []) if float(b["free"]) + float(b["locked"]) > 0
        ]

        stablecoins = ("USDT", "BUSD", "USDC", "DAI", "FDUSD")
        assets_to_price = [b["asset"] for b in non_zero if b["asset"] not in stablecoins]

        prices: dict[str, float] = {}
        if assets_to_price:
            try:
                ticker_resp = await self._client.get("/api/v3/ticker/price")
                ticker_data = ticker_resp.json()
                prices = {
                    item["symbol"]: float(item["price"])
                    for item in ticker_data
                    if item["symbol"].endswith("USDT")
                }
            except Exception:
                logger.warning("get_positions_failed_to_fetch_prices")

        positions: list[Position] = []
        now = datetime.now()

        for bal in non_zero:
            asset = bal["asset"]
            if asset in stablecoins:
                continue

            symbol = f"{asset}USDT"
            current_price = prices.get(symbol, 0.0)
            qty = float(bal["free"]) + float(bal["locked"])

            positions.append(
                Position(
                    symbol=f"{asset}/USDT",
                    asset_class=AssetClass.CRYPTO,
                    quantity=qty,
                    avg_entry_price=current_price,
                    current_price=current_price,
                    realized_pnl=0.0,
                    timestamp=now,
                    broker=self.name,
                )
            )

        return positions

    async def submit_order(self, order: OrderEvent) -> FillEvent:
        params = self._sign(
            {
                "symbol": order.symbol.replace("/", ""),
                "side": order.side.value.upper(),
                "type": order.order_type.value.upper(),
                "quantity": str(order.quantity),
            }
        )
        if order.price:
            params["price"] = str(order.price)
        resp = await self._client.post("/api/v3/order", params=params)
        data = resp.json()
        self._check_error(data)
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
        params = self._sign({"orderId": order_id})
        resp = await self._client.delete("/api/v3/order", params=params)
        data = resp.json()
        self._check_error(data)

    async def stream_bars(
        self, symbols: list[str], timeframe: str
    ) -> AsyncGenerator[Bar, None]:
        from trading.data.feeds.binance import BinanceFeedHandler
        from trading.data.feeds.feed import WebSocketFeed

        handler = BinanceFeedHandler(ws_url=self._ws_url)
        feed = WebSocketFeed(handler)
        async for bar in feed.stream(symbols, timeframe):
            yield bar

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
