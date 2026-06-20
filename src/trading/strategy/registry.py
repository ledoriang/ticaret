from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from trading.strategy.base import Strategy


def _ensure_strategies_loaded() -> None:
    import trading.strategy.sma_crossover  # noqa: F401 — triggers @StrategyRegistry.register


class StrategyRegistry:
    _strategies: dict[str, type["Strategy"]] = {}
    _loaded = False

    @classmethod
    def _load_all(cls) -> None:
        if not cls._loaded:
            _ensure_strategies_loaded()
            cls._loaded = True

    @classmethod
    def register(cls, strategy_cls: type["Strategy"]) -> type["Strategy"]:
        cls._strategies[strategy_cls.name] = strategy_cls
        return strategy_cls

    @classmethod
    def get(cls, name: str) -> type["Strategy"]:
        cls._load_all()
        if name not in cls._strategies:
            raise KeyError(f"Unknown strategy: {name}. Available: {list(cls._strategies)}")
        return cls._strategies[name]

    @classmethod
    def list_strategies(cls) -> list[str]:
        cls._load_all()
        return list(cls._strategies)
