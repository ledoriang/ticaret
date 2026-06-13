from trading.core.enums import AssetClass
from trading.core.events import FillEvent, OrderEvent
from trading.execution.adapters.base import AbstractBrokerAdapter


class Dispatcher:
    def __init__(self, adapters: dict[str, AbstractBrokerAdapter]) -> None:
        self.adapters = adapters
        self.routing: dict[AssetClass, str] = {}

    async def dispatch(self, order: OrderEvent) -> FillEvent:
        adapter_name = self.routing[order.asset_class]
        adapter = self.adapters[adapter_name]
        result = await adapter.submit_order(order)
        return result
