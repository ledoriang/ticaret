from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from trading.data.news.base import NewsProvider

NEWS_PROVIDER_REGISTRY: dict[str, type["NewsProvider"]] = {}


def register_provider(
    cls: type["NewsProvider"],
) -> type["NewsProvider"]:
    NEWS_PROVIDER_REGISTRY[cls.name] = cls
    return cls


def get_provider(name: str) -> type["NewsProvider"]:
    if name not in NEWS_PROVIDER_REGISTRY:
        raise KeyError(
            f"Unknown news provider: {name}. "
            f"Available: {list(NEWS_PROVIDER_REGISTRY)}"
        )
    return NEWS_PROVIDER_REGISTRY[name]
