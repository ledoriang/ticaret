import json
from datetime import datetime

from trading.core.enums import AssetClass
from trading.core.models import Bar
from trading.data.feeds import register_feed_handler


@register_feed_handler
class BinanceFeedHandler:
    name = "binance"

    def __init__(self, ws_url: str = "wss://stream.binance.com:9443/ws") -> None:
        self._ws_url = ws_url

    def set_ws_url(self, url: str) -> None:
        self._ws_url = url

    def build_url(self, symbols: list[str], timeframe: str) -> str:
        interval = self._to_binance_interval(timeframe)
        streams = [f"{s.replace('/', '').lower()}@kline_{interval}" for s in symbols]
        return f"{self._ws_url}/{'/'.join(streams)}"

    def parse_message(self, raw: str) -> Bar | None:
        data = json.loads(raw)
        k = data.get("k", {})
        if not k.get("x", False):
            return None

        raw_symbol = data.get("s", "")
        symbol = self._parse_symbol(raw_symbol)

        return Bar(
            symbol=symbol,
            asset_class=AssetClass.CRYPTO,
            timeframe="",
            open=float(k["o"]),
            high=float(k["h"]),
            low=float(k["l"]),
            close=float(k["c"]),
            volume=float(k["v"]),
            timestamp=datetime.fromtimestamp(k["T"] / 1000),
        )

    def build_subscribe(self, _symbols: list[str]) -> str | None:
        # Binance uses URL-based multi-stream subscription
        return None

    def build_unsubscribe(self, _symbols: list[str]) -> str | None:
        return None

    def is_closed_message(self, _raw: str) -> bool:
        return False

    @staticmethod
    def _parse_symbol(raw: str) -> str:
        if len(raw) > 3:
            return f"{raw[:-4]}/{raw[-4:]}"
        return f"{raw}/USDT"

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
