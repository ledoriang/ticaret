import pandas as pd


def _get_ta():
    import pandas_ta as ta

    return ta


def compute_sma(df: pd.DataFrame, length: int = 20) -> pd.Series:
    return _get_ta().sma(df["close"], length=length)


def compute_ema(df: pd.DataFrame, length: int = 20) -> pd.Series:
    return _get_ta().ema(df["close"], length=length)


def compute_rsi(df: pd.DataFrame, length: int = 14) -> pd.Series:
    return _get_ta().rsi(df["close"], length=length)


def compute_macd(df: pd.DataFrame) -> pd.DataFrame:
    return _get_ta().macd(df["close"])


def compute_bollinger_bands(df: pd.DataFrame, length: int = 20, std: float = 2.0) -> pd.DataFrame:
    return _get_ta().bbands(df["close"], length=length, std=std)


def compute_atr(df: pd.DataFrame, length: int = 14) -> pd.Series:
    return _get_ta().atr(df["high"], df["low"], df["close"], length=length)
