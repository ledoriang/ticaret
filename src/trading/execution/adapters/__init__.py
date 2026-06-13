from trading.execution.adapters.base import AbstractBrokerAdapter
from trading.execution.adapters.binance import BinanceAdapter

ADAPTER_REGISTRY: dict[str, type[AbstractBrokerAdapter]] = {
    "binance": BinanceAdapter,
}

__all__ = ["ADAPTER_REGISTRY", "AbstractBrokerAdapter", "BinanceAdapter"]
