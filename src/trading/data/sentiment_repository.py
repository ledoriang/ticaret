import asyncpg

from trading.core.config import DatabaseConfig
from trading.core.events import SentimentEvent


class SentimentRepository:
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
            min_size=1,
            max_size=5,
        )

    async def ensure_schema(self) -> None:
        assert self._pool
        async with self._pool.acquire() as conn:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS news_sentiment (
                    time        TIMESTAMPTZ NOT NULL,
                    symbol      TEXT NOT NULL,
                    score       DOUBLE PRECISION,
                    confidence  DOUBLE PRECISION,
                    source      TEXT,
                    summary     TEXT
                );
                SELECT create_hypertable('news_sentiment', 'time', if_not_exists => TRUE);
            """)

    async def insert(self, event: SentimentEvent) -> None:
        assert self._pool
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO news_sentiment (time, symbol, score, confidence, source, summary)
                VALUES ($1, $2, $3, $4, $5, $6)
                """,
                event.timestamp,
                event.symbol,
                event.score,
                event.confidence,
                event.source,
                event.summary,
            )

    async def get_recent(
        self, symbol: str, limit: int = 10
    ) -> list[SentimentEvent]:
        assert self._pool
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT * FROM news_sentiment
                WHERE symbol = $1
                ORDER BY time DESC
                LIMIT $2
                """,
                symbol,
                limit,
            )
        return [
            SentimentEvent(
                symbol=r["symbol"],
                score=r["score"],
                confidence=r["confidence"],
                source=r["source"],
                summary=r["summary"],
                timestamp=r["time"],
            )
            for r in rows
        ]

    async def close(self) -> None:
        if self._pool:
            await self._pool.close()
