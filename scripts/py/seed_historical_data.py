"""
Fetch and store historical bars for backtesting.
Usage: uv run python scripts/seed_historical_data.py --symbol BTC/USDT --start 2020-01-01 --end 2025-01-01
"""

import argparse
import asyncio

from trading.core.config import load_config
from trading.data.ingestion import HistoricalIngestion


async def main() -> None:
    parser = argparse.ArgumentParser(description="Seed historical OHLCV data")
    parser.add_argument("--symbol", default="BTC/USDT")
    parser.add_argument("--start", default="2020-01-01")
    parser.add_argument("--end", default="2025-01-01")
    parser.add_argument("--timeframe", default="1d")
    parser.add_argument("--config", default="configs/development.yaml")
    args = parser.parse_args()

    config = load_config(args.config)
    ingestion = HistoricalIngestion(config)
    bars = await ingestion.fetch_bars(args.symbol, args.timeframe, args.start, args.end)
    print(f"Fetched {len(bars)} bars for {args.symbol}")


if __name__ == "__main__":
    asyncio.run(main())
