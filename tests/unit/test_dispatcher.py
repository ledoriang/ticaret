import pytest

from trading.core.config import ActiveBrokersConfig, BrokersConfig
from trading.core.enums import AssetClass, OrderType, Side
from trading.core.events import OrderEvent
from trading.execution.dispatcher import Dispatcher
from trading.execution.paper import PaperAdapter


@pytest.mark.asyncio
class TestDispatcher:
    @pytest.fixture
    def paper(self) -> PaperAdapter:
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

    async def test_dispatch_routes_to_correct_adapter(
        self, paper: PaperAdapter, buy_order: OrderEvent
    ) -> None:
        dispatcher = Dispatcher(adapters={"paper": paper})
        dispatcher.routing[AssetClass.CRYPTO] = "paper"
        fill = await dispatcher.dispatch(buy_order)
        assert fill.symbol == "BTC/USDT"
        assert fill.quantity == 1.0
        assert fill.broker == "paper"

    async def test_dispatch_via_init_routes(
        self, paper: PaperAdapter, buy_order: OrderEvent
    ) -> None:
        brokers = BrokersConfig(active=ActiveBrokersConfig(crypto="paper", equity="paper"))
        dispatcher = Dispatcher(adapters={"paper": paper}, brokers_config=brokers)
        fill = await dispatcher.dispatch(buy_order)
        assert fill.quantity == 1.0

    async def test_register_route_adds_routing(self, paper: PaperAdapter) -> None:
        dispatcher = Dispatcher(adapters={"paper": paper})
        assert AssetClass.CRYPTO not in dispatcher.routing
        dispatcher.register_route(AssetClass.CRYPTO, "paper")
        assert dispatcher.routing[AssetClass.CRYPTO] == "paper"

    async def test_register_route_unknown_adapter_raises(self, paper: PaperAdapter) -> None:
        dispatcher = Dispatcher(adapters={"paper": paper})
        with pytest.raises(ValueError, match="Unknown adapter 'nonexistent'"):
            dispatcher.register_route(AssetClass.CRYPTO, "nonexistent")

    async def test_dispatch_no_route_raises(
        self, paper: PaperAdapter, buy_order: OrderEvent
    ) -> None:
        dispatcher = Dispatcher(adapters={"paper": paper})
        buy_order.asset_class = AssetClass.EQUITY
        with pytest.raises(KeyError, match="No route registered for asset class 'equity'"):
            await dispatcher.dispatch(buy_order)

    async def test_init_routes_skips_missing_adapter(self) -> None:
        brokers = BrokersConfig(active=ActiveBrokersConfig(crypto="binance", equity="alpaca"))
        dispatcher = Dispatcher(adapters={"paper": PaperAdapter()}, brokers_config=brokers)
        assert AssetClass.CRYPTO not in dispatcher.routing
        assert AssetClass.EQUITY not in dispatcher.routing

    async def test_multiple_asset_classes_routed_separately(self, paper: PaperAdapter) -> None:
        second = PaperAdapter(initial_cash=50_000.0)
        adapters = {
            "paper": paper,
            "second": second,
        }
        dispatcher = Dispatcher(adapters=adapters)
        dispatcher.register_route(AssetClass.CRYPTO, "paper")
        dispatcher.register_route(AssetClass.EQUITY, "second")

        crypto_order = OrderEvent(
            symbol="BTC/USDT",
            side=Side.BUY,
            order_type=OrderType.MARKET,
            quantity=0.5,
            price=50_000.0,
            asset_class=AssetClass.CRYPTO,
        )
        equity_order = OrderEvent(
            symbol="AAPL/USD",
            side=Side.SELL,
            order_type=OrderType.MARKET,
            quantity=10.0,
            price=150.0,
            asset_class=AssetClass.EQUITY,
        )

        fill1 = await dispatcher.dispatch(crypto_order)
        assert fill1.symbol == "BTC/USDT"
        # FillEvent.broker reflects the adapter's own name, not the routing key.
        # Verify routing by checking each adapter's internal state:
        paper_cash = (await paper.get_account()).cash
        assert paper_cash < 100_000.0  # paper handled the crypto order

        fill2 = await dispatcher.dispatch(equity_order)
        assert fill2.symbol == "AAPL/USD"
        # Sell adds to cash:
        second_cash = (await second.get_account()).cash
        assert second_cash > 50_000.0  # second handled the sell order (cash increased)
