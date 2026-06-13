from datetime import datetime

import asyncpg

from trading.core.config import DatabaseConfig
from trading.core.enums import AssetClass
from trading.core.models import Bar


class TimescaleRepository:
    def __init__(self, config: DatabaseConfig) -> None:
        self.config = config
        self._pool: asyncpg.Pool | None = None

    async def connect(self) -> None:
        self._pool = await asyncpg.create_pool(
            host=self.config.host,
            port=self.config.port,
            database=self.config.name,
            user=self.config.user,
            password=self.config.password,
            min_size=2,
            max_size=10,
        )

    async def ensure_schema(self) -> None:
        assert self._pool
        async with self._pool.acquire() as conn:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS bars (
                    time        TIMESTAMPTZ NOT NULL,
                    symbol      TEXT NOT NULL,
                    timeframe   TEXT NOT NULL,
                    open        DOUBLE PRECISION,
                    high        DOUBLE PRECISION,
                    low         DOUBLE PRECISION,
                    close       DOUBLE PRECISION,
                    volume      DOUBLE PRECISION
                );
                SELECT create_hypertable('bars', 'time', if_not_exists => TRUE);
            """)

    async def insert_bar(self, bar: Bar) -> None:
        assert self._pool
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO bars (time, symbol, timeframe, open, high, low, close, volume)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                """,
                bar.timestamp,
                bar.symbol,
                bar.timeframe,
                bar.open,
                bar.high,
                bar.low,
                bar.close,
                bar.volume,
            )

    async def get_bars(
        self, symbol: str, timeframe: str, start: datetime, end: datetime
    ) -> list[Bar]:
        assert self._pool
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT * FROM bars
                WHERE symbol = $1 AND timeframe = $2
                  AND time >= $3 AND time <= $4
                ORDER BY time ASC
                """,
                symbol,
                timeframe,
                start,
                end,
            )
        return [
            Bar(
                symbol=r["symbol"],
                asset_class=AssetClass.CRYPTO,
                timeframe=r["timeframe"],
                open=r["open"],
                high=r["high"],
                low=r["low"],
                close=r["close"],
                volume=r["volume"],
                timestamp=r["time"],
            )
            for r in rows
        ]

    async def bulk_insert_bars(self, file_path: str) -> None:
        pass

    async def close(self) -> None:
        if self._pool:
            await self._pool.close()
