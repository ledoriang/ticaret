import structlog

from trading.core.events import RiskBlockEvent, SignalEvent
from trading.risk.rules import RiskRule

logger = structlog.get_logger(__name__)


class RiskManager:
    def __init__(self, rules: list[RiskRule] | None = None) -> None:
        self.rules: list[RiskRule] = rules or []

    def add_rule(self, rule: RiskRule) -> None:
        self.rules.append(rule)

    async def check(self, signal: SignalEvent) -> tuple[bool, list[RiskBlockEvent]]:
        blocks: list[RiskBlockEvent] = []
        for rule in self.rules:
            passed, reason = await rule.evaluate(signal)
            if not passed:
                block = RiskBlockEvent(
                    original_signal=signal,
                    reason=reason,
                    rule_that_blocked=rule.name,
                    source="risk_manager",
                    correlation_id=signal.correlation_id,
                    asset_class=signal.asset_class,
                )
                blocks.append(block)
                logger.warning("risk_rule_blocked", rule=rule.name, reason=reason)
        return len(blocks) == 0, blocks
