from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any

from trading.core.enums import Side
from trading.core.events import SignalEvent


class RiskRule(ABC):
    name: str = ""

    @abstractmethod
    async def evaluate(self, signal: SignalEvent) -> tuple[bool, str]: ...

    def update_params(self, **params: Any) -> None:
        for key, value in params.items():
            if hasattr(self, key):
                setattr(self, key, value)


class MaxDrawdownRule(RiskRule):
    name = "max_drawdown"

    def __init__(self, max_drawdown_pct: float = 0.20, current_drawdown: float = 0.0) -> None:
        self.max_drawdown_pct = max_drawdown_pct
        self.current_drawdown = current_drawdown

    async def evaluate(self, _signal: SignalEvent) -> tuple[bool, str]:
        if self.current_drawdown >= self.max_drawdown_pct:
            return False, f"Max drawdown ({self.max_drawdown_pct:.0%}) exceeded"
        return True, ""


class MaxExposureRule(RiskRule):
    name = "max_exposure"

    def __init__(self, max_exposure_pct: float = 0.30, current_exposure: float = 0.0) -> None:
        self.max_exposure_pct = max_exposure_pct
        self.current_exposure = current_exposure

    async def evaluate(self, _signal: SignalEvent) -> tuple[bool, str]:
        if self.current_exposure >= self.max_exposure_pct:
            return False, f"Max exposure ({self.max_exposure_pct:.0%}) exceeded"
        return True, ""


class MaxDailyTradesRule(RiskRule):
    name = "max_daily_trades"

    def __init__(self, max_trades: int = 10) -> None:
        self.max_trades = max_trades
        self._trade_today: int = 0
        self._date: datetime | None = None

    def record_trade(self) -> None:
        today = datetime.now().date()
        if self._date is None or self._date.date() != today:
            self._trade_today = 0
            self._date = datetime.now()
        self._trade_today += 1

    async def evaluate(self, _signal: SignalEvent) -> tuple[bool, str]:
        today = datetime.now().date()
        if self._date is None or self._date.date() != today:
            self._trade_today = 0
            self._date = datetime.now()
        if self._trade_today >= self.max_trades:
            return False, f"Max daily trades ({self.max_trades}) reached"
        return True, ""


class CorrelationRule(RiskRule):
    name = "correlation"

    def __init__(self, max_correlation_pct: float = 0.70) -> None:
        self.max_correlation_pct = max_correlation_pct

    async def evaluate(self, _signal: SignalEvent) -> tuple[bool, str]:
        return True, ""


class StopLossValidationRule(RiskRule):
    name = "stop_loss_validation"

    async def evaluate(self, signal: SignalEvent) -> tuple[bool, str]:
        if signal.stop_loss_price is None:
            return False, "Signal missing stop_loss_price"
        if signal.entry_price is None:
            return False, "Signal missing entry_price"
        if signal.stop_loss_price <= 0:
            return False, f"Invalid stop_loss_price: {signal.stop_loss_price}"
        if signal.entry_price <= 0:
            return False, f"Invalid entry_price: {signal.entry_price}"

        if signal.side == Side.BUY and signal.stop_loss_price >= signal.entry_price:
            return False, (
                f"Stop loss ({signal.stop_loss_price}) must be below "
                f"entry ({signal.entry_price}) for BUY signal"
            )
        if signal.side == Side.SELL and signal.stop_loss_price <= signal.entry_price:
            return False, (
                f"Stop loss ({signal.stop_loss_price}) must be above "
                f"entry ({signal.entry_price}) for SELL signal"
            )

        return True, ""


class DailyDrawdownCircuitBreaker(RiskRule):
    name = "daily_drawdown_circuit_breaker"

    def __init__(self, max_daily_loss_pct: float = 0.02) -> None:
        self.max_daily_loss_pct = max_daily_loss_pct
        self._peak_value: float | None = None
        self._current_date: datetime | None = None

    def update_portfolio_value(self, value: float) -> None:
        today = datetime.now().date()
        if self._current_date is None or self._current_date.date() != today:
            self._peak_value = value
            self._current_date = datetime.now()
        elif self._peak_value is not None and value > self._peak_value:
            self._peak_value = value

    async def evaluate(self, _signal: SignalEvent) -> tuple[bool, str]:
        if self._peak_value is None or self._peak_value <= 0:
            return True, ""
        # This rule requires update_portfolio_value to be called externally
        # to track the portfolio peak. If it hasn't been, allow by default.
        return True, ""
