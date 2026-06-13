from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from trading.strategy.base import Strategy


class StrategyRegistry:
    _strategies: dict[str, type["Strategy"]] = {}

    @classmethod
    def register(cls, strategy_cls: type["Strategy"]) -> type["Strategy"]:
        cls._strategies[strategy_cls.name] = strategy_cls
        return strategy_cls

    @classmethod
    def get(cls, name: str) -> type["Strategy"]:
        if name not in cls._strategies:
            raise KeyError(f"Unknown strategy: {name}. Available: {list(cls._strategies)}")
        return cls._strategies[name]

    @classmethod
    def list_strategies(cls) -> list[str]:
        return list(cls._strategies)
