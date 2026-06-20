from abc import ABC, abstractmethod

import pandas as pd

from trading.core.events import SentimentEvent, SignalEvent


class StrategyResult:
    def __init__(self, signal: SignalEvent | None = None) -> None:
        self.signal = signal


class Strategy(ABC):
    name: str = ""

    @abstractmethod
    async def on_data(
        self, df: pd.DataFrame, sentiment: SentimentEvent | None = None
    ) -> StrategyResult: ...

    @abstractmethod
    async def initialize(self) -> None: ...
