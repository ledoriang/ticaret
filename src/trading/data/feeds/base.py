from typing import Protocol

from trading.core.models import Bar


class FeedHandler(Protocol):
    """Interface for exchange-specific WebSocket feed parsing.

    Each exchange's WebSocket feed has its own:
    - URL format and subscription model
    - Message structure
    - Symbol naming convention
    - Kline vs ticker vs trade data

    A FeedHandler implementation encapsulates all of these differences.
    The WebSocketShovel calls these methods to connect, parse, and manage
    the feed — it has zero knowledge of the specific exchange.
    """

    name: str

    def build_url(self, symbols: list[str], timeframe: str) -> str:
        """Construct the WebSocket URL for the given symbols and timeframe."""

    def parse_message(self, raw: str) -> Bar | None:
        """Parse a raw WebSocket message into a Bar, or None if not a bar update."""

    def build_subscribe(self, symbols: list[str]) -> str | None:
        """Build a SUBSCRIBE control frame, or None if URL-based subscription is used."""

    def build_unsubscribe(self, symbols: list[str]) -> str | None:
        """Build an UNSUBSCRIBE control frame, or None if URL-based subscription is used."""

    def is_closed_message(self, _raw: str) -> bool:
        """Return True if the message indicates the connection should close."""
        return False
