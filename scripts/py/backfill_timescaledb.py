"""
Bulk data import into TimescaleDB hypertables.
Usage: uv run python scripts/backfill_timescaledb.py --bars-path data/bars.parquet
"""

import argparse
import asyncio

from trading.core.config import load_config
from trading.data.repository import TimescaleRepository


async def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill TimescaleDB with historical data")
    parser.add_argument("--bars-path", required=True)
    parser.add_argument("--config", default="configs/development.yaml")
    args = parser.parse_args()

    config = load_config(args.config)
    repo = TimescaleRepository(config.database)
    await repo.connect()
    await repo.bulk_insert_bars(args.bars_path)
    await repo.close()
    print("Backfill complete")


if __name__ == "__main__":
    asyncio.run(main())
