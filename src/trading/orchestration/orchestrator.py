import structlog

from trading.core.config import TradingConfig
from trading.core.enums import OrderType
from trading.core.events import (
    BarEvent,
    BaseEvent,
    CommandEvent,
    FillEvent,
    OrderEvent,
    SentimentEvent,
    SignalEvent,
)
from trading.data.live_stream import LiveStream
from trading.execution.dispatcher import Dispatcher
from trading.execution.paper import PaperAdapter
from trading.monitoring.metrics import (
    fills_received,
    orders_placed,
    risk_blocks,
    strategy_signals,
)
from trading.orchestration.bar_buffer import BarBuffer
from trading.orchestration.bus import EventBus
from trading.orchestration.commands import CommandHandler
from trading.risk.manager import RiskManager
from trading.strategy.base import Strategy
from trading.strategy.registry import StrategyRegistry

logger = structlog.get_logger(__name__)


class Orchestrator:
    def __init__(
        self,
        config: TradingConfig,
        dispatcher: Dispatcher,
        risk_manager: RiskManager,
        event_bus: EventBus | None = None,
        bar_buffer: BarBuffer | None = None,
        live_stream: LiveStream | None = None,
        paper_adapter: PaperAdapter | None = None,
    ) -> None:
        self.config = config
        self.dispatcher = dispatcher
        self.risk_manager = risk_manager
        self.event_bus = event_bus
        self.bar_buffer = bar_buffer
        self.live_stream = live_stream
        self.paper_adapter = paper_adapter
        self._strategies: dict[str, Strategy] = {}
        self._symbols: list[str] = []
        self._running = False
        self._command_handler = CommandHandler(self)

    def load_strategy(self, name: str, **kwargs: object) -> None:
        cls = StrategyRegistry.get(name)
        self._strategies[name] = cls(**kwargs)
        logger.info("strategy_loaded", name=name)

    async def start(self) -> None:
        self._running = True
        logger.info("orchestrator_started", mode=self.config.execution_mode)

        if self.event_bus:
            self._setup_bus_subscriptions()
            await self.event_bus.start()

        if self.live_stream:
            self.live_stream.on_bar(self._on_bar_from_stream)
            await self.live_stream.start()

    def _setup_bus_subscriptions(self) -> None:
        assert self.event_bus
        for symbol in self._symbols:
            self.event_bus.subscribe(f"bars:{symbol}", self._on_bar_via_bus)
            self.event_bus.subscribe(f"fills:{symbol}", self._on_fill_via_bus)
        self.event_bus.subscribe_pattern("sentiment:*", self._on_sentiment)
        self.event_bus.subscribe_pattern("commands:*", self._on_command)

    async def add_symbol(self, symbol: str) -> None:
        self._symbols.append(symbol)
        if self.event_bus:
            self.event_bus.subscribe(f"bars:{symbol}", self._on_bar_via_bus)
            self.event_bus.subscribe(f"fills:{symbol}", self._on_fill_via_bus)

    async def stop(self) -> None:
        self._running = False
        if self.live_stream:
            await self.live_stream.stop()
        if self.event_bus:
            await self.event_bus.stop()
        logger.info("orchestrator_stopped")

    async def _on_command(self, event: BaseEvent) -> None:
        if isinstance(event, CommandEvent):
            await self._command_handler.handle(event)

    async def _on_bar_via_bus(self, event: BaseEvent) -> None:
        if isinstance(event, BarEvent):
            await self._on_bar(event)

    async def _on_fill_via_bus(self, event: BaseEvent) -> None:
        if isinstance(event, FillEvent):
            await self._on_fill(event)

    async def _on_bar_from_stream(self, event: BarEvent) -> None:
        await self._on_bar(event)

    async def _on_bar(self, bar: BarEvent) -> None:
        import pandas as pd

        if self.paper_adapter:
            self.paper_adapter.update_last_price(bar.symbol, bar.close)

        if self.bar_buffer:
            from trading.core.models import Bar as BarModel

            bar_model = BarModel(
                symbol=bar.symbol,
                asset_class=bar.asset_class,
                timeframe="",
                open=bar.open,
                high=bar.high,
                low=bar.low,
                close=bar.close,
                volume=bar.volume,
                timestamp=bar.timestamp,
            )
            df = self.bar_buffer.add(bar.symbol, bar_model)
        else:
            df = pd.DataFrame(
                {
                    "open": [bar.open],
                    "high": [bar.high],
                    "low": [bar.low],
                    "close": [bar.close],
                    "volume": [bar.volume],
                },
                index=[bar.timestamp],
            )

        for name, strategy in self._strategies.items():
            result = await strategy.on_data(df)
            if result.signal:
                result.signal.source = name
                result.signal.correlation_id = bar.correlation_id or bar.event_id
                strategy_signals.labels(strategy=name, side=result.signal.side.value).inc()
                if self.event_bus:
                    await self.event_bus.publish(f"signals:{bar.symbol}", result.signal)
                await self._process_signal(result.signal)

    async def _on_sentiment(self, event: BaseEvent) -> None:
        if isinstance(event, SentimentEvent):
            logger.debug(
                "sentiment_received",
                symbol=event.symbol,
                score=event.score,
                source=event.source,
            )

    async def _process_signal(self, signal: SignalEvent) -> None:
        passed, blocks = await self.risk_manager.check(signal)
        if not passed:
            for block in blocks:
                risk_blocks.labels(rule=block.rule_that_blocked).inc()
                logger.warning(
                    "signal_blocked",
                    rule=block.rule_that_blocked,
                    reason=block.reason,
                )
                if self.event_bus:
                    await self.event_bus.publish(f"risk_block:{signal.symbol}", block)
            return

        order = OrderEvent(
            symbol=signal.symbol,
            side=signal.side,
            order_type=OrderType.MARKET,
            quantity=max(1.0, signal.confidence * 100),
            price=signal.price,
            broker=self.dispatcher.routing.get(signal.asset_class, "paper"),
            strategy_name=signal.strategy_name,
            source="orchestrator",
            correlation_id=signal.correlation_id,
            asset_class=signal.asset_class,
        )
        if self.event_bus:
            await self.event_bus.publish(f"orders:{signal.symbol}", order)
        orders_placed.labels(broker=order.broker, symbol=order.symbol).inc()
        try:
            fill = await self.dispatcher.dispatch(order)
            await self._on_fill(fill)
        except Exception:
            logger.exception("order_failed", symbol=order.symbol)

    async def _on_fill(self, fill: FillEvent) -> None:
        fills_received.labels(broker=fill.broker, symbol=fill.symbol).inc()
        logger.info(
            "fill_received",
            symbol=fill.symbol,
            price=fill.fill_price,
            qty=fill.quantity,
        )
        if self.paper_adapter:
            self.paper_adapter.update_last_price(fill.symbol, fill.fill_price)
