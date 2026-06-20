from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any

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
