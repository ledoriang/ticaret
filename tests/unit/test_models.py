from datetime import datetime

from trading.core.enums import AssetClass, OrderStatus, OrderType, Side, TimeInForce
from trading.core.events import FillEvent, OrderEvent, SignalEvent
from trading.core.models import AccountInfo, Bar, Order, Portfolio, Position


class TestBar:
    def test_bar_creation(self) -> None:
        bar = Bar(
            symbol="BTC/USDT",
            asset_class=AssetClass.CRYPTO,
            timeframe="1d",
            open=100.0,
            high=110.0,
            low=90.0,
            close=105.0,
            volume=1000.0,
            timestamp=datetime(2024, 1, 1),
        )
        assert bar.symbol == "BTC/USDT"
        assert bar.asset_class == AssetClass.CRYPTO


class TestOrder:
    def test_order_defaults(self) -> None:
        order = Order(
            id="test-1",
            symbol="ETH/USDT",
            asset_class=AssetClass.CRYPTO,
            side=Side.BUY,
            order_type=OrderType.LIMIT,
            quantity=0.5,
            price=2000.0,
            created_at=datetime(2024, 1, 1),
        )
        assert order.status == OrderStatus.PENDING
        assert order.time_in_force == TimeInForce.GTC


class TestPosition:
    def test_position_creation(self) -> None:
        pos = Position(
            symbol="BTC/USDT",
            asset_class=AssetClass.CRYPTO,
            quantity=1.0,
            avg_entry_price=50000.0,
            current_price=51000.0,
            timestamp=datetime(2024, 1, 1),
        )
        assert pos.unrealized_pnl == 1000.0


class TestPortfolio:
    def test_portfolio_defaults(self) -> None:
        pf = Portfolio()
        assert pf.total_value == 0.0
        assert pf.positions == []


class TestAccountInfo:
    def test_account_info(self) -> None:
        acc = AccountInfo(
            broker="binance",
            total_equity=100000.0,
            cash=50000.0,
            buying_power=100000.0,
            timestamp=datetime(2024, 1, 1),
        )
        assert acc.broker == "binance"


class TestSignalEvent:
    def test_signal_event(self) -> None:
        signal = SignalEvent(
            symbol="BTC/USDT",
            side=Side.BUY,
            confidence=0.8,
            strategy_name="sma_crossover",
        )
        assert signal.side == Side.BUY
        assert signal.confidence == 0.8


class TestOrderEvent:
    def test_order_event(self) -> None:
        order = OrderEvent(
            symbol="BTC/USDT",
            side=Side.BUY,
            order_type=OrderType.MARKET,
            quantity=1.0,
        )
        assert order.quantity == 1.0


class TestFillEvent:
    def test_fill_event(self) -> None:
        fill = FillEvent(
            symbol="BTC/USDT",
            side=Side.BUY,
            quantity=1.0,
            fill_price=50000.0,
        )
        assert fill.fill_price == 50000.0
