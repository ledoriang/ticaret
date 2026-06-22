from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from trading.core.config import DatabaseConfig
from trading.core.events import SentimentEvent
from trading.data.sentiment_repository import SentimentRepository


@pytest.mark.asyncio
class TestSentimentRepository:
    async def test_connect_creates_pool(self) -> None:
        config = DatabaseConfig(host="localhost", port=5432)
        repo = SentimentRepository(config)
        with patch("asyncpg.create_pool", AsyncMock()) as mock_pool:
            await repo.connect()
            mock_pool.assert_called_once()
        await repo.close()

    async def test_ensure_schema_executes_sql(self) -> None:
        config = DatabaseConfig(host="localhost", port=5432)
        repo = SentimentRepository(config)
        mock_conn = AsyncMock()
        mock_pool = MagicMock()
        mock_pool.acquire.return_value.__aenter__.return_value = mock_conn
        repo._pool = mock_pool

        await repo.ensure_schema()
        assert mock_conn.execute.called
        call_args = " ".join(mock_conn.execute.call_args[0])
        assert "news_sentiment" in call_args
        assert "create_hypertable" in call_args

    async def test_insert_event(self) -> None:
        config = DatabaseConfig(host="localhost", port=5432)
        repo = SentimentRepository(config)
        mock_conn = AsyncMock()
        mock_pool = MagicMock()
        mock_pool.acquire.return_value.__aenter__.return_value = mock_conn
        repo._pool = mock_pool

        event = SentimentEvent(
            symbol="BTC/USDT",
            score=0.65,
            confidence=0.8,
            source="test",
            summary="Test sentiment",
        )
        await repo.insert(event)
        assert mock_conn.execute.called
        args = mock_conn.execute.call_args[0][1:]
        assert args[1] == "BTC/USDT"
        assert args[2] == 0.65

    async def test_get_recent_returns_events(self) -> None:
        config = DatabaseConfig(host="localhost", port=5432)
        repo = SentimentRepository(config)
        mock_conn = AsyncMock()
        mock_conn.fetch.return_value = [
            {
                "symbol": "BTC/USDT",
                "score": 0.65,
                "confidence": 0.8,
                "source": "test",
                "summary": "Test",
                "time": "2024-01-01T00:00:00",
            }
        ]
        mock_pool = MagicMock()
        mock_pool.acquire.return_value.__aenter__.return_value = mock_conn
        repo._pool = mock_pool

        results = await repo.get_recent("BTC/USDT")
        assert len(results) == 1
        assert results[0].symbol == "BTC/USDT"
        assert results[0].score == 0.65
