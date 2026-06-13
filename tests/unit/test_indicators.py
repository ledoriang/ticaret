import pytest

pytest.importorskip("pandas_ta")

import pandas as pd

from trading.data.indicators import compute_sma


class TestIndicators:
    def test_sma_computation(self) -> None:
        df = pd.DataFrame({"close": [10.0, 20.0, 30.0, 40.0, 50.0]})
        sma = compute_sma(df, length=3)
        assert len(sma) == 5
        assert sma.iloc[-1] == 40.0
