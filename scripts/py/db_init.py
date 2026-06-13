"""
Create TimescaleDB schema (hypertables, indexes).
Usage: uv run python scripts/py/db_init.py [--config configs/development.yaml]
"""

import argparse
import asyncio

from trading.core.config import load_config
from trading.data.repository import TimescaleRepository


async def main() -> None:
    parser = argparse.ArgumentParser(description="Create TimescaleDB schema")
    parser.add_argument("--config", default="configs/development.yaml")
    args = parser.parse_args()

    config = load_config(args.config)
    repo = TimescaleRepository(config.database)
    await repo.connect()
    await repo.ensure_schema()
    await repo.close()
    print("Schema created successfully")


if __name__ == "__main__":
    asyncio.run(main())
