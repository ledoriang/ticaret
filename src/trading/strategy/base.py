from abc import ABC, abstractmethod

import pandas as pd

from trading.core.events import SignalEvent


class StrategyResult:
    def __init__(self, signal: SignalEvent | None = None) -> None:
        self.signal = signal


class Strategy(ABC):
    name: str = ""

    @abstractmethod
    async def on_data(self, df: pd.DataFrame) -> StrategyResult: ...

    @abstractmethod
    async def initialize(self) -> None: ...
