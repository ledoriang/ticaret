import pytest

from trading.core.enums import AssetClass, OrderType, Side
from trading.core.events import OrderEvent
from trading.execution.paper import PaperAdapter


@pytest.mark.asyncio
class TestPaperAdapter:
    @pytest.fixture
    def adapter(self) -> PaperAdapter:
        return PaperAdapter(initial_cash=100_000.0)

    @pytest.fixture
    def buy_order(self) -> OrderEvent:
        return OrderEvent(
            symbol="BTC/USDT",
            side=Side.BUY,
            order_type=OrderType.MARKET,
            quantity=1.0,
            price=50_000.0,
            asset_class=AssetClass.CRYPTO,
        )

    @pytest.fixture
    def sell_order(self) -> OrderEvent:
        return OrderEvent(
            symbol="BTC/USDT",
            side=Side.SELL,
            order_type=OrderType.MARKET,
            quantity=0.5,
            price=55_000.0,
            asset_class=AssetClass.CRYPTO,
        )

    async def test_buy_reduces_cash(self, adapter: PaperAdapter, buy_order: OrderEvent) -> None:
        initial_cash = (await adapter.get_account()).cash
        fill = await adapter.submit_order(buy_order)
        assert fill.quantity == 1.0
        assert fill.side == Side.BUY
        account = await adapter.get_account()
        assert account.cash < initial_cash

    async def test_get_account_after_trade(
        self, adapter: PaperAdapter, buy_order: OrderEvent
    ) -> None:
        await adapter.submit_order(buy_order)
        acc = await adapter.get_account()
        assert acc.cash < 100_000.0
        assert acc.total_equity < 100_000.0  # slippage + commission deducted

    async def test_buy_then_partial_sell_updates_positions(
        self, adapter: PaperAdapter, buy_order: OrderEvent, sell_order: OrderEvent
    ) -> None:
        await adapter.submit_order(buy_order)
        positions = await adapter.get_positions()
        assert len(positions) == 1
        assert positions[0].symbol == "BTC/USDT"
        assert positions[0].quantity == 1.0

        await adapter.submit_order(sell_order)
        positions = await adapter.get_positions()
        assert len(positions) == 1
        assert positions[0].quantity == 0.5

    async def test_sell_all_removes_position(
        self, adapter: PaperAdapter, buy_order: OrderEvent
    ) -> None:
        await adapter.submit_order(buy_order)
        sell_all = OrderEvent(
            symbol="BTC/USDT",
            side=Side.SELL,
            order_type=OrderType.MARKET,
            quantity=1.0,
            price=55_000.0,
            asset_class=AssetClass.CRYPTO,
        )
        await adapter.submit_order(sell_all)
        positions = await adapter.get_positions()
        assert len(positions) == 0

    async def test_no_slippage_when_price_set_and_market_order(self) -> None:
        adapter = PaperAdapter(
            simulated_slippage=0.0, simulated_fee_rate=0.0, initial_cash=100_000.0
        )
        order = OrderEvent(
            symbol="BTC/USDT",
            side=Side.BUY,
            order_type=OrderType.MARKET,
            quantity=1.0,
            price=50_000.0,
            asset_class=AssetClass.CRYPTO,
        )
        fill = await adapter.submit_order(order)
        assert fill.fill_price == 50_000.0
        assert fill.commission == 0.0

    async def test_get_positions_returns_empty_initially(self, adapter: PaperAdapter) -> None:
        positions = await adapter.get_positions()
        assert positions == []

    async def test_get_account_shows_initial_equity(self, adapter: PaperAdapter) -> None:
        acc = await adapter.get_account()
        assert acc.cash == 100_000.0
        assert acc.total_equity == 100_000.0
        assert acc.broker == "paper"
