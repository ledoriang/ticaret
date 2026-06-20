from datetime import datetime, timedelta

import pytest

from trading.core.config import TradingConfig
from trading.core.enums import AssetClass
from trading.core.models import Bar
from trading.execution.dispatcher import Dispatcher
from trading.execution.paper import PaperAdapter
from trading.orchestration.bar_buffer import BarBuffer
from trading.orchestration.orchestrator import Orchestrator
from trading.risk.manager import RiskManager
from trading.risk.rules import MaxDrawdownRule, MaxExposureRule
from trading.strategy.registry import StrategyRegistry


def _bar(symbol: str, close: float, dt: datetime | None = None) -> Bar:
    return Bar(
        symbol=symbol,
        asset_class=AssetClass.CRYPTO,
        timeframe="1d",
        open=close - 0.5,
        high=close + 0.5,
        low=close - 1.0,
        close=close,
        volume=100.0,
        timestamp=dt or datetime.now(),
    )


def _make_bar_event(symbol: str, close: float, dt: datetime | None = None):
    from trading.core.events import BarEvent

    return BarEvent(
        symbol=symbol,
        open=close - 0.5,
        high=close + 0.5,
        low=close - 1.0,
        close=close,
        volume=100.0,
        timestamp=dt or datetime.now(),
        asset_class=AssetClass.CRYPTO,
        source="test",
    )


@pytest.fixture(autouse=True)
def ensure_strategies() -> None:
    StrategyRegistry._load_all()


@pytest.fixture
def bar_buffer() -> BarBuffer:
    return BarBuffer(max_size=100)


@pytest.fixture
def paper() -> PaperAdapter:
    return PaperAdapter(initial_cash=100_000.0)


@pytest.fixture
def dispatcher(paper: PaperAdapter) -> Dispatcher:
    d = Dispatcher(adapters={"paper": paper})
    d.register_route(AssetClass.CRYPTO, "paper")
    return d


@pytest.fixture
def risk_mgr() -> RiskManager:
    return RiskManager(
        [
            MaxDrawdownRule(max_drawdown_pct=0.20, current_drawdown=0.05),
            MaxExposureRule(max_exposure_pct=0.30, current_exposure=0.10),
        ]
    )


@pytest.fixture
def orch(
    bar_buffer: BarBuffer, paper: PaperAdapter, dispatcher: Dispatcher, risk_mgr: RiskManager
) -> Orchestrator:
    o = Orchestrator(
        TradingConfig(),
        dispatcher,
        risk_mgr,
        bar_buffer=bar_buffer,
        paper_adapter=paper,
    )
    o.load_strategy("sma_crossover")
    return o


@pytest.mark.asyncio
class TestOrchestratorBarReplay:
    async def test_on_bar_feeds_bar_buffer(self, orch: Orchestrator) -> None:
        assert orch.bar_buffer is not None
        bar1 = _make_bar_event("BTC/USDT", 50000.0)
        await orch._on_bar(bar1)
        assert orch.bar_buffer.size("BTC/USDT") == 1

    async def test_multiple_bars_accumulate(self, orch: Orchestrator) -> None:
        for i in range(5):
            bar = _make_bar_event("BTC/USDT", float(50000 + i * 100))
            await orch._on_bar(bar)
        df = orch.bar_buffer.get("BTC/USDT")
        assert len(df) == 5
        assert df["close"].iloc[-1] == 50400.0

    async def test_sma_crossover_generates_signal_after_enough_bars(
        self, orch: Orchestrator
    ) -> None:
        # Build a price series that triggers a golden cross:
        # downtrend then uptrend so fast SMA crosses above slow SMA
        now = datetime.now()
        prices: list[float] = []
        # 30 days of downtrend: 100 → 80
        for i in range(30):
            prices.append(100.0 - i * (20.0 / 30))
        # 30 days of uptrend: 80 → 110
        for i in range(30):
            prices.append(80.0 + i * (30.0 / 30))

        for i, p in enumerate(prices):
            bar = _make_bar_event("BTC/USDT", p, dt=now + timedelta(minutes=i))
            await orch._on_bar(bar)

        # With 60 bars (more than SMA 50 lookback), a golden cross should trigger
        # Check if the paper adapter received any order
        acc = await orch.paper_adapter.get_account()
        assert acc.cash < 100_000.0  # at least one buy order reduced cash

    async def test_no_signal_with_insufficient_bars(self, orch: Orchestrator) -> None:
        for i in range(5):
            bar = _make_bar_event("BTC/USDT", float(50000 + i))
            await orch._on_bar(bar)
        acc = await orch.paper_adapter.get_account()
        assert acc.cash == 100_000.0  # no trade happened

    async def test_bar_buffer_eviction(self, orch: Orchestrator) -> None:
        assert orch.bar_buffer is not None
        for i in range(110):
            bar = _make_bar_event("BTC/USDT", float(50000 + i))
            await orch._on_bar(bar)
        assert orch.bar_buffer.size("BTC/USDT") == 100  # max_size

    async def test_full_pipeline_bar_to_fill(self, orch: Orchestrator, paper: PaperAdapter) -> None:
        now = datetime.now()
        for i in range(60):
            p = 100.0 - i * (20.0 / 30) if i < 30 else 80.0 + (i - 30) * (30.0 / 30)
            bar = _make_bar_event("BTC/USDT", p, dt=now + timedelta(minutes=i))
            await orch._on_bar(bar)

        positions = await paper.get_positions()
        total_positions = sum(p.quantity for p in positions)
        assert total_positions > 0

    async def test_strategy_not_loaded_does_not_prevent_bars(
        self, orch: Orchestrator, bar_buffer: BarBuffer
    ) -> None:
        bar = _make_bar_event("ETH/USDT", 3000.0)
        await orch._on_bar(bar)
        # Even with no strategy for ETH, bars still accumulate
        assert bar_buffer.size("ETH/USDT") == 1
