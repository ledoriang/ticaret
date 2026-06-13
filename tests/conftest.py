import pytest

from trading.core.config import TradingConfig
from trading.core.enums import OrderType, Side
from trading.core.events import OrderEvent
from trading.execution.paper import PaperAdapter


@pytest.fixture
def paper_adapter() -> PaperAdapter:
    return PaperAdapter(initial_cash=100_000.0)


@pytest.fixture
def buy_order() -> OrderEvent:
    return OrderEvent(
        symbol="BTC/USDT",
        side=Side.BUY,
        order_type=OrderType.MARKET,
        quantity=1.0,
        price=50_000.0,
        broker="paper",
    )


@pytest.fixture
def sell_order() -> OrderEvent:
    return OrderEvent(
        symbol="BTC/USDT",
        side=Side.SELL,
        order_type=OrderType.MARKET,
        quantity=0.5,
        price=55_000.0,
        broker="paper",
    )


@pytest.fixture
def config() -> TradingConfig:
    return TradingConfig()
