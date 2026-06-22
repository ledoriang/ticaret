from trading.data.news.registry import NEWS_PROVIDER_REGISTRY, get_provider, register_provider


class _DummyProvider:
    name = "dummy"

    def __init__(self) -> None:
        pass


class TestNewsRegistry:
    def test_registry_contains_all_providers(self) -> None:
        assert "alpha_vantage" in NEWS_PROVIDER_REGISTRY
        assert "marketaux" in NEWS_PROVIDER_REGISTRY
        assert "finnhub" in NEWS_PROVIDER_REGISTRY
        assert "stockgeist" in NEWS_PROVIDER_REGISTRY
        assert "cached" in NEWS_PROVIDER_REGISTRY

    def test_get_provider_returns_class(self) -> None:
        from trading.data.news.alpha_vantage import AlphaVantageProvider

        cls = get_provider("alpha_vantage")
        assert cls is AlphaVantageProvider

    def test_get_provider_raises_on_unknown(self) -> None:
        import pytest

        with pytest.raises(KeyError):
            get_provider("nonexistent")

    def test_register_provider_decorator(self) -> None:
        @register_provider
        class TestProvider:
            name = "test_provider"

            def __init__(self) -> None:
                pass

        assert "test_provider" in NEWS_PROVIDER_REGISTRY
        assert NEWS_PROVIDER_REGISTRY["test_provider"] is TestProvider
