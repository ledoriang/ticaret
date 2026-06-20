from typing import TYPE_CHECKING, Any

import structlog

from trading.core.events import CommandEvent

if TYPE_CHECKING:
    from trading.orchestration.orchestrator import Orchestrator

logger = structlog.get_logger(__name__)


class CommandHandler:
    def __init__(self, orchestrator: "Orchestrator") -> None:
        self.orchestrator = orchestrator

    async def handle(self, event: CommandEvent) -> None:
        command = event.command
        payload = event.payload
        logger.info("command_received", command=command, payload=payload)

        handler_map: dict[str, Any] = {
            "add_symbol": self._add_symbol,
            "remove_symbol": self._remove_symbol,
            "add_strategy": self._add_strategy,
            "remove_strategy": self._remove_strategy,
            "update_risk_rule": self._update_risk_rule,
        }
        handler = handler_map.get(command)
        if handler is None:
            logger.warning("command_unknown", command=command)
            return
        await handler(**payload)

    async def _add_symbol(self, symbol: str, timeframe: str = "1d", **_: Any) -> None:
        orch = self.orchestrator
        if symbol in orch._symbols:
            logger.info("symbol_already_added", symbol=symbol)
            return
        orch._symbols.append(symbol)
        if orch.live_stream:
            await orch.live_stream.add_symbol(symbol, timeframe)
        logger.info("symbol_added", symbol=symbol, timeframe=timeframe)

    async def _remove_symbol(self, symbol: str, **_: Any) -> None:
        orch = self.orchestrator
        if symbol not in orch._symbols:
            logger.warning("symbol_not_found", symbol=symbol)
            return
        orch._symbols.remove(symbol)
        if orch.bar_buffer:
            orch.bar_buffer.clear(symbol)
        if orch.live_stream:
            await orch.live_stream.remove_symbol(symbol)
        logger.info("symbol_removed", symbol=symbol)

    async def _add_strategy(self, name: str, **kwargs: Any) -> None:
        orch = self.orchestrator
        if name in orch._strategies:
            logger.info("strategy_already_loaded", name=name)
            return
        orch.load_strategy(name, **kwargs)
        logger.info("strategy_added", name=name, params=kwargs)

    async def _remove_strategy(self, name: str, **_: Any) -> None:
        orch = self.orchestrator
        if name not in orch._strategies:
            logger.warning("strategy_not_found", name=name)
            return
        del orch._strategies[name]
        logger.info("strategy_removed", name=name)

    async def _update_risk_rule(self, rule: str, params: dict[str, Any], **_: Any) -> None:
        for r in self.orchestrator.risk_manager.rules:
            if r.name == rule:
                r.update_params(**params)
                logger.info("risk_rule_updated", rule=rule, params=params)
                return
        logger.warning("risk_rule_not_found", rule=rule)
