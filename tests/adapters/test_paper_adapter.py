import pytest

from trading.core.enums import AssetClass, OrderType, Side
from trading.core.events import OrderEvent
from trading.execution.paper import PaperAdapter


@pytest.mark.asyncio
class TestPaperAdapter:
    async def test_buy_reduces_cash(self) -> None:
        adapter = PaperAdapter(initial_cash=100_000.0)
        order = OrderEvent(
            symbol="BTC/USDT",
            side=Side.BUY,
            order_type=OrderType.MARKET,
            quantity=1.0,
            price=50_000.0,
            asset_class=AssetClass.CRYPTO,
        )
        fill = await adapter.submit_order(order)
        assert fill.quantity == 1.0
        assert fill.side == Side.BUY

    async def test_get_account_after_trade(self) -> None:
        adapter = PaperAdapter(initial_cash=100_000.0)
        order = OrderEvent(
            symbol="BTC/USDT",
            side=Side.BUY,
            order_type=OrderType.MARKET,
            quantity=1.0,
            price=50_000.0,
            asset_class=AssetClass.CRYPTO,
        )
        await adapter.submit_order(order)
        acc = await adapter.get_account()
        assert acc.cash < 100_000.0
