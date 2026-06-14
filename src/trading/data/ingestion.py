from datetime import datetime

from trading.core.config import TradingConfig
from trading.core.models import Bar
from trading.execution.adapters.binance import BinanceAdapter


class HistoricalIngestion:
    def __init__(self, config: TradingConfig) -> None:
        self.config = config
        broker_cfg = config.brokers.binance
        self.adapter = BinanceAdapter(
            api_key=broker_cfg.api_key,
            api_secret=broker_cfg.api_secret,
            testnet=broker_cfg.testnet,
        )

    async def fetch_bars(self, symbol: str, timeframe: str, start: str, end: str) -> list[Bar]:
        start_dt = datetime.fromisoformat(start)
        end_dt = datetime.fromisoformat(end)
        return await self.adapter.get_bars(symbol, timeframe, start_dt, end_dt)
