"""Tests for WebSocketFeed with a mock handler."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from trading.data.feeds.feed import WebSocketFeed


class MockHandler:
    name = "mock"

    def __init__(self):
        self.build_url = MagicMock(return_value="ws://localhost:18799/mock")
        self.parse_message = MagicMock(return_value=None)
        self.build_subscribe = MagicMock(return_value=None)
        self.build_unsubscribe = MagicMock(return_value=None)
        self.is_closed_message = MagicMock(return_value=False)


class MockWs:
    """Simulates a WebSocket connection that immediately ends."""

    def __init__(self):
        self.send = AsyncMock()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass

    def __aiter__(self):
        return self

    async def __anext__(self):
        raise StopAsyncIteration


@pytest.mark.asyncio
class TestWebSocketFeed:
    async def test_build_url_called_on_stream(self):
        """Verify the feed calls handler.build_url to construct the WS URL."""
        handler = MockHandler()
        with patch("websockets.connect", return_value=MockWs()):
            feed = WebSocketFeed(handler)
            gen = feed.stream(["BTC/USDT"], "1m")
            async for _ in gen:
                pass
        handler.build_url.assert_called_once_with(["BTC/USDT"], "1m")

    async def test_build_subscribe_called(self):
        """Verify the feed calls handler.build_subscribe after connecting."""
        handler = MockHandler()
        handler.build_subscribe.return_value = "SUBSCRIBE"
        with patch("websockets.connect", return_value=MockWs()):
            feed = WebSocketFeed(handler)
            gen = feed.stream(["BTC/USDT"], "1m")
            async for _ in gen:
                pass
        handler.build_subscribe.assert_called_once_with(["BTC/USDT"])
