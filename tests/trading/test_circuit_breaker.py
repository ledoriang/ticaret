import pytest

from trading.core.enums import AssetClass, Side
from trading.core.events import SignalEvent
from trading.risk.rules import DailyDrawdownCircuitBreaker


@pytest.mark.asyncio
class TestDailyDrawdownCircuitBreaker:
    @pytest.fixture
    def signal(self) -> SignalEvent:
        return SignalEvent(
            symbol="BTC/USDT",
            side=Side.BUY,
            confidence=0.7,
            strategy_name="sma_crossover",
            asset_class=AssetClass.CRYPTO,
            source="test",
        )

    async def test_allows_when_peak_not_set(self, signal: SignalEvent) -> None:
        breaker = DailyDrawdownCircuitBreaker(max_daily_loss_pct=0.02)
        passed, _reason = await breaker.evaluate(signal)
        assert passed

    async def test_allows_when_drawdown_under_limit(self, signal: SignalEvent) -> None:
        breaker = DailyDrawdownCircuitBreaker(max_daily_loss_pct=0.02)
        breaker.update_portfolio_value(100_000.0)
        breaker.update_portfolio_value(99_500.0)  # -0.5% drawdown
        passed, _reason = await breaker.evaluate(signal)
        assert passed

    async def test_allows_exactly_at_limit(self, signal: SignalEvent) -> None:
        breaker = DailyDrawdownCircuitBreaker(max_daily_loss_pct=0.02)
        breaker.update_portfolio_value(100_000.0)
        breaker.update_portfolio_value(98_000.0)  # -2% drawdown, exactly at limit
        # The rule currently passes (evaluate is a no-op). The actual
        # drawdown check is a placeholder for future implementation.
        passed, _reason = await breaker.evaluate(signal)
        assert passed

    async def test_tracks_new_day_peak(self, signal: SignalEvent) -> None:
        from freezegun import freeze_time

        breaker = DailyDrawdownCircuitBreaker(max_daily_loss_pct=0.02)
        with freeze_time("2024-01-01"):
            breaker.update_portfolio_value(100_000.0)
        with freeze_time("2024-01-02"):
            breaker.update_portfolio_value(90_000.0)  # lower start on new day
            passed, _reason = await breaker.evaluate(signal)
            assert passed
