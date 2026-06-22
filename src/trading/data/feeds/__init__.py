from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from trading.data.feeds.base import FeedHandler

FEED_HANDLER_REGISTRY: dict[str, type["FeedHandler"]] = {}


def register_feed_handler(handler_cls: type["FeedHandler"]) -> type["FeedHandler"]:
    FEED_HANDLER_REGISTRY[handler_cls.name] = handler_cls
    return handler_cls


def get_feed_handler(name: str) -> type["FeedHandler"]:
    if name not in FEED_HANDLER_REGISTRY:
        raise KeyError(
            f"Unknown feed handler: {name}. "
            f"Available: {list(FEED_HANDLER_REGISTRY)}"
        )
    return FEED_HANDLER_REGISTRY[name]
