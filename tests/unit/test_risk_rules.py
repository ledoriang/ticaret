import pytest
from freezegun import freeze_time

from trading.core.enums import AssetClass, Side
from trading.core.events import SignalEvent
from trading.risk.manager import RiskManager
from trading.risk.rules import (
    CorrelationRule,
    MaxDailyTradesRule,
    MaxDrawdownRule,
    MaxExposureRule,
)


@pytest.fixture
def signal() -> SignalEvent:
    return SignalEvent(
        symbol="BTC/USDT",
        side=Side.BUY,
        confidence=0.8,
        strategy_name="sma_crossover",
        asset_class=AssetClass.CRYPTO,
        source="test",
    )


@pytest.mark.asyncio
class TestMaxDrawdownRule:
    async def test_passes_when_drawdown_below_max(self, signal: SignalEvent) -> None:
        rule = MaxDrawdownRule(max_drawdown_pct=0.20, current_drawdown=0.10)
        passed, reason = await rule.evaluate(signal)
        assert passed
        assert reason == ""

    async def test_blocks_when_drawdown_exceeds_max(self, signal: SignalEvent) -> None:
        rule = MaxDrawdownRule(max_drawdown_pct=0.20, current_drawdown=0.25)
        passed, reason = await rule.evaluate(signal)
        assert not passed
        assert "exceeded" in reason

    async def test_blocks_at_exact_max(self, signal: SignalEvent) -> None:
        rule = MaxDrawdownRule(max_drawdown_pct=0.20, current_drawdown=0.20)
        passed, _reason = await rule.evaluate(signal)
        assert not passed


@pytest.mark.asyncio
class TestMaxExposureRule:
    async def test_passes_when_exposure_below_max(self, signal: SignalEvent) -> None:
        rule = MaxExposureRule(max_exposure_pct=0.30, current_exposure=0.15)
        passed, _reason = await rule.evaluate(signal)
        assert passed

    async def test_blocks_when_exposure_exceeds_max(self, signal: SignalEvent) -> None:
        rule = MaxExposureRule(max_exposure_pct=0.30, current_exposure=0.35)
        passed, _reason = await rule.evaluate(signal)
        assert not passed

    async def test_zero_exposure_always_passes(self, signal: SignalEvent) -> None:
        rule = MaxExposureRule(max_exposure_pct=0.05, current_exposure=0.0)
        passed, _reason = await rule.evaluate(signal)
        assert passed


@pytest.mark.asyncio
class TestMaxDailyTradesRule:
    async def test_passes_when_under_limit(self, signal: SignalEvent) -> None:
        rule = MaxDailyTradesRule(max_trades=10)
        passed, _reason = await rule.evaluate(signal)
        assert passed

    async def test_blocks_when_at_limit(self, signal: SignalEvent) -> None:
        rule = MaxDailyTradesRule(max_trades=1)
        rule.record_trade()
        passed, _reason = await rule.evaluate(signal)
        assert not passed

    @freeze_time("2024-01-01")
    async def test_resets_daily(self, signal: SignalEvent) -> None:
        rule = MaxDailyTradesRule(max_trades=2)
        rule.record_trade()
        rule.record_trade()
        passed, _reason = await rule.evaluate(signal)
        assert not passed

        with freeze_time("2024-01-02"):
            rule.record_trade()  # records one trade on new day
            passed2, _reason2 = await rule.evaluate(signal)
            assert passed2  # only 1 trade on Jan 2, limit is 2

    async def test_records_multiple_trades(self, signal: SignalEvent) -> None:
        rule = MaxDailyTradesRule(max_trades=3)
        for _ in range(3):
            rule.record_trade()
        passed, _reason = await rule.evaluate(signal)
        assert not passed


@pytest.mark.asyncio
class TestCorrelationRule:
    async def test_always_passes(self, signal: SignalEvent) -> None:
        rule = CorrelationRule()
        passed, _reason = await rule.evaluate(signal)
        assert passed


@pytest.mark.asyncio
class TestRiskManager:
    async def test_no_rules_always_passes(self, signal: SignalEvent) -> None:
        mgr = RiskManager(rules=[])
        passed, blocks = await mgr.check(signal)
        assert passed
        assert blocks == []

    async def test_single_failing_rule_blocks(self, signal: SignalEvent) -> None:
        rule = MaxDrawdownRule(max_drawdown_pct=0.10, current_drawdown=0.20)
        mgr = RiskManager(rules=[rule])
        passed, blocks = await mgr.check(signal)
        assert not passed
        assert len(blocks) == 1
        assert blocks[0].rule_that_blocked == "max_drawdown"
        assert blocks[0].original_signal == signal

    async def test_all_rules_must_pass(self, signal: SignalEvent) -> None:
        rules = [
            MaxDrawdownRule(max_drawdown_pct=0.20, current_drawdown=0.05),
            MaxExposureRule(max_exposure_pct=0.30, current_exposure=0.10),
            MaxDailyTradesRule(max_trades=10),
            CorrelationRule(),
        ]
        mgr = RiskManager(rules=rules)
        passed, blocks = await mgr.check(signal)
        assert passed
        assert blocks == []

    async def test_multiple_rules_can_block(self, signal: SignalEvent) -> None:
        rules = [
            MaxDrawdownRule(max_drawdown_pct=0.10, current_drawdown=0.20),
            MaxExposureRule(max_exposure_pct=0.10, current_exposure=0.20),
        ]
        mgr = RiskManager(rules=rules)
        passed, blocks = await mgr.check(signal)
        assert not passed
        assert len(blocks) == 2

    async def test_add_rule_appends(self, signal: SignalEvent) -> None:
        mgr = RiskManager()
        mgr.add_rule(MaxDrawdownRule(max_drawdown_pct=0.05, current_drawdown=0.10))
        passed, _blocks = await mgr.check(signal)
        assert not passed
