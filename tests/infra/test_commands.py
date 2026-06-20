from unittest.mock import MagicMock

import pytest

from trading.core.config import TradingConfig
from trading.core.enums import AssetClass, Side
from trading.core.events import CommandEvent, SignalEvent
from trading.execution.dispatcher import Dispatcher
from trading.execution.paper import PaperAdapter
from trading.orchestration.commands import CommandHandler
from trading.orchestration.orchestrator import Orchestrator
from trading.risk.manager import RiskManager
from trading.risk.rules import MaxDrawdownRule, MaxExposureRule
from trading.strategy.registry import StrategyRegistry


@pytest.fixture
def orch() -> Orchestrator:
    StrategyRegistry._load_all()
    paper = PaperAdapter(initial_cash=100_000.0)
    adapters = {"paper": paper}
    dispatcher = Dispatcher(adapters)
    dispatcher.register_route(AssetClass.CRYPTO, "paper")
    risk_mgr = RiskManager(
        [
            MaxDrawdownRule(max_drawdown_pct=0.20, current_drawdown=0.05),
            MaxExposureRule(max_exposure_pct=0.30, current_exposure=0.10),
        ]
    )
    return Orchestrator(TradingConfig(), dispatcher, risk_mgr)


class TestCommandHandler:
    async def test_handle_add_symbol(self, orch: Orchestrator) -> None:
        handler = CommandHandler(orch)
        await handler.handle(
            CommandEvent(
                command="add_symbol",
                payload={"symbol": "ETH/USDT", "timeframe": "1d"},
                source="test",
            )
        )
        assert "ETH/USDT" in orch._symbols

    async def test_handle_remove_symbol(self, orch: Orchestrator) -> None:
        orch._symbols.append("ETH/USDT")
        handler = CommandHandler(orch)
        await handler.handle(
            CommandEvent(
                command="remove_symbol",
                payload={"symbol": "ETH/USDT"},
                source="test",
            )
        )
        assert "ETH/USDT" not in orch._symbols

    async def test_handle_add_symbol_duplicate(self, orch: Orchestrator) -> None:
        orch._symbols.append("ETH/USDT")
        handler = CommandHandler(orch)
        await handler.handle(
            CommandEvent(
                command="add_symbol",
                payload={"symbol": "ETH/USDT"},
                source="test",
            )
        )
        assert len(orch._symbols) == 1  # no duplicate

    async def test_handle_add_strategy(self, orch: Orchestrator) -> None:
        handler = CommandHandler(orch)
        await handler.handle(
            CommandEvent(
                command="add_strategy",
                payload={"name": "sma_crossover"},
                source="test",
            )
        )
        assert "sma_crossover" in orch._strategies

    async def test_handle_add_strategy_duplicate(self, orch: Orchestrator) -> None:
        orch.load_strategy("sma_crossover")
        handler = CommandHandler(orch)
        await handler.handle(
            CommandEvent(
                command="add_strategy",
                payload={"name": "sma_crossover"},
                source="test",
            )
        )
        assert len(orch._strategies) == 1  # no duplicate

    async def test_handle_remove_strategy(self, orch: Orchestrator) -> None:
        orch.load_strategy("sma_crossover")
        handler = CommandHandler(orch)
        await handler.handle(
            CommandEvent(
                command="remove_strategy",
                payload={"name": "sma_crossover"},
                source="test",
            )
        )
        assert "sma_crossover" not in orch._strategies

    async def test_handle_remove_strategy_not_found(self, orch: Orchestrator) -> None:
        handler = CommandHandler(orch)
        await handler.handle(
            CommandEvent(
                command="remove_strategy",
                payload={"name": "nonexistent"},
                source="test",
            )
        )
        # no error, silently ignored

    async def test_handle_remove_symbol_not_found(self, orch: Orchestrator) -> None:
        handler = CommandHandler(orch)
        await handler.handle(
            CommandEvent(
                command="remove_symbol",
                payload={"symbol": "NONEXISTENT"},
                source="test",
            )
        )
        # no error, silently ignored

    async def test_handle_update_risk_rule(self, orch: Orchestrator) -> None:
        handler = CommandHandler(orch)
        signal = SignalEvent(
            symbol="BTC/USDT",
            side=Side.BUY,
            confidence=0.8,
            strategy_name="sma_crossover",
            asset_class=AssetClass.CRYPTO,
            source="test",
        )

        # Before update: drawdown at 5% < 20% max → passes
        passed, _ = await orch.risk_manager.check(signal)
        assert passed

        # Update max_drawdown to 3% (below current 5%)
        await handler.handle(
            CommandEvent(
                command="update_risk_rule",
                payload={"rule": "max_drawdown", "params": {"max_drawdown_pct": 0.03}},
                source="test",
            )
        )

        # After update: drawdown at 5% > 3% max → blocks
        passed, blocks = await orch.risk_manager.check(signal)
        assert not passed
        assert blocks[0].rule_that_blocked == "max_drawdown"

    async def test_handle_update_risk_rule_not_found(self, orch: Orchestrator) -> None:
        handler = CommandHandler(orch)
        await handler.handle(
            CommandEvent(
                command="update_risk_rule",
                payload={"rule": "nonexistent", "params": {}},
                source="test",
            )
        )
        # no error, silently ignored

    async def test_handle_unknown_command(self, orch: Orchestrator) -> None:
        handler = CommandHandler(orch)
        await handler.handle(CommandEvent(command="unknown_cmd", payload={}, source="test"))
        # no error, silently ignored

    async def test_orchestrator_subscribes_to_commands(self, orch: Orchestrator) -> None:
        from unittest.mock import AsyncMock

        mock_bus = MagicMock()
        mock_bus.subscribe = MagicMock()
        mock_bus.subscribe_pattern = MagicMock()
        mock_bus.start = AsyncMock()
        mock_bus.stop = AsyncMock()

        orch.event_bus = mock_bus
        await orch.start()

        mock_bus.subscribe_pattern.assert_any_call("commands:*", orch._on_command)
        mock_bus.start.assert_awaited_once()
        await orch.stop()
