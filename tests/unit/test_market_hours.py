from datetime import time

from trading.core.enums import AssetClass
from trading.core.market_hours import MarketHours, get_market_hours


class TestMarketHours:
    def test_crypto_always_open(self) -> None:
        mh = get_market_hours(AssetClass.CRYPTO)
        assert mh.always_open is True
        assert mh.is_open() is True

    def test_equity_market_hours(self) -> None:
        mh = get_market_hours(AssetClass.EQUITY)
        assert mh.always_open is False
        assert mh.open_time == time(9, 30)
        assert mh.close_time == time(16, 0)

    def test_always_open_custom(self) -> None:
        mh = MarketHours(always_open=True)
        assert mh.is_open() is True
