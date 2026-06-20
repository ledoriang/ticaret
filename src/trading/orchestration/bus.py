import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

import redis.asyncio as aioredis
from redis.asyncio.client import PubSub

from trading.core.config import RedisConfig
from trading.core.events import BaseEvent

EventHandler = Callable[[BaseEvent], Awaitable[None] | None]


class EventBus:
    def __init__(self, config: RedisConfig) -> None:
        self._redis: aioredis.Redis = aioredis.Redis(
            host=config.host, port=config.port, decode_responses=True
        )
        self._pubsub: PubSub | None = None
        self._listener_task: asyncio.Task[Any] | None = None
        self._handlers: dict[str, list[EventHandler]] = {}
        self._pattern_handlers: dict[str, list[EventHandler]] = {}

    async def publish(self, topic: str, event: BaseEvent) -> None:
        payload = event.model_dump_json()
        await self._redis.publish(topic, payload)

    def subscribe(self, topic: str, handler: EventHandler) -> None:
        self._handlers.setdefault(topic, []).append(handler)
        if self._pubsub is not None:
            asyncio.ensure_future(self._subscribe_topic(topic))

    async def _subscribe_topic(self, topic: str) -> None:
        if self._pubsub:
            await self._pubsub.subscribe(topic)

    def subscribe_pattern(self, pattern: str, handler: EventHandler) -> None:
        self._pattern_handlers.setdefault(pattern, []).append(handler)
        if self._pubsub is not None:
            asyncio.ensure_future(self._subscribe_pattern(pattern))

    async def _subscribe_pattern(self, pattern: str) -> None:
        if self._pubsub:
            await self._pubsub.psubscribe(pattern)

    async def _process_message(self, topic: str, data: str) -> None:
        from trading.core.events import (
            BarEvent,
            CommandEvent,
            FillEvent,
            OrderEvent,
            RiskBlockEvent,
            SentimentEvent,
            SignalEvent,
        )

        event_map: dict[str, type[BaseEvent]] = {
            "bars": BarEvent,
            "signals": SignalEvent,
            "orders": OrderEvent,
            "fills": FillEvent,
            "sentiment": SentimentEvent,
            "commands": CommandEvent,
            "risk_block": RiskBlockEvent,
        }
        topic_prefix = topic.split(":")[0]
        event_cls = event_map.get(topic_prefix)
        if event_cls is None:
            return
        event = event_cls.model_validate_json(data)
        for handler in self._handlers.get(topic, []):
            result = handler(event)
            if asyncio.iscoroutine(result):
                await result
        for pattern, handlers in self._pattern_handlers.items():
            if self._topic_matches_pattern(topic, pattern):
                for handler in handlers:
                    result = handler(event)
                    if asyncio.iscoroutine(result):
                        await result

    @staticmethod
    def _topic_matches_pattern(topic: str, pattern: str) -> bool:
        import fnmatch

        return fnmatch.fnmatch(topic, pattern)

    async def start(self) -> None:
        pubsub = self._redis.pubsub()
        self._pubsub = pubsub
        topics = list(self._handlers)
        if topics:
            await pubsub.subscribe(*topics)
        patterns = list(self._pattern_handlers)
        if patterns:
            await pubsub.psubscribe(*patterns)

        async def _listener() -> None:
            assert self._pubsub
            async for message in self._pubsub.listen():
                msg_type = message.get("type")
                if msg_type in ("message", "pmessage"):
                    await self._process_message(message["channel"], message["data"])

        self._listener_task = asyncio.create_task(_listener())

    async def stop(self) -> None:
        if self._listener_task:
            self._listener_task.cancel()
        if self._pubsub:
            await self._pubsub.unsubscribe()
            await self._pubsub.punsubscribe()
            await self._pubsub.aclose()  # type: ignore[no-untyped-call]
        await self._redis.aclose()

    @property
    def is_running(self) -> bool:
        return self._listener_task is not None and not self._listener_task.done()
