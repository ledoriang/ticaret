from trading.core.config import BrokersConfig
from trading.core.enums import AssetClass
from trading.core.events import FillEvent, OrderEvent
from trading.execution.adapters.base import AbstractBrokerAdapter


class Dispatcher:
    def __init__(
        self,
        adapters: dict[str, AbstractBrokerAdapter],
        brokers_config: BrokersConfig | None = None,
    ) -> None:
        self.adapters = adapters
        self.routing: dict[AssetClass, str] = {}
        if brokers_config:
            self.init_routes(brokers_config)

    def init_routes(self, brokers_config: BrokersConfig) -> None:
        active = brokers_config.active
        if active.crypto and active.crypto in self.adapters:
            self.routing[AssetClass.CRYPTO] = active.crypto
        if active.equity and active.equity in self.adapters:
            self.routing[AssetClass.EQUITY] = active.equity

    def register_route(self, asset_class: AssetClass, adapter_name: str) -> None:
        if adapter_name not in self.adapters:
            raise ValueError(f"Unknown adapter '{adapter_name}'. Available: {list(self.adapters)}")
        self.routing[asset_class] = adapter_name

    async def dispatch(self, order: OrderEvent) -> FillEvent:
        adapter_name = self.routing.get(order.asset_class)
        if adapter_name is None:
            raise KeyError(
                f"No route registered for asset class '{order.asset_class}'. "
                f"Available routes: {self.routing}"
            )
        adapter = self.adapters[adapter_name]
        result = await adapter.submit_order(order)
        return result
