from dataclasses import dataclass
from typing import Any

import pandas as pd

from trading.backtest.backtest_types import ClosedTrade


@dataclass
class RegimeMetrics:
    regime: str
    bar_count: int
    trade_count: int
    win_count: int
    net_pnl: float
    win_rate: float
    avg_bars_held: float
    avg_mae: float
    avg_mfe: float


def _compute_adx(df: pd.DataFrame, period: int = 14) -> pd.Series:
    high = df.get("high", df["close"])
    low = df.get("low", df["close"])
    close = df["close"]

    tr = pd.concat(
        [
            high - low,
            (high - close.shift(1)).abs(),
            (low - close.shift(1)).abs(),
        ],
        axis=1,
    ).max(axis=1)
    atr = tr.rolling(window=period).mean()

    plus_dm = high.diff()
    minus_dm = low.diff().abs()
    plus_di = 100 * (plus_dm.rolling(window=period).mean() / atr)
    minus_di = 100 * (minus_dm.rolling(window=period).mean() / atr)
    dx = 100 * ((plus_di - minus_di).abs() / (plus_di + minus_di))
    adx = dx.rolling(window=period).mean()
    return adx


def _compute_atr_pct(df: pd.DataFrame, period: int = 14) -> pd.Series:
    high = df.get("high", df["close"])
    low = df.get("low", df["close"])
    close = df["close"]
    tr = pd.concat(
        [
            high - low,
            (high - close.shift(1)).abs(),
            (low - close.shift(1)).abs(),
        ],
        axis=1,
    ).max(axis=1)
    atr = tr.rolling(window=period).mean()
    return atr / close


def classify_regime(adx: float | None, atr_pct: float | None) -> str:
    if adx is None or atr_pct is None:
        return "unknown"
    if atr_pct > 0.05:
        return "volatile"
    if adx > 25:
        return "trending"
    return "ranging"


def compute_regime_report(
    trades: list[ClosedTrade], price_df: pd.DataFrame
) -> list[RegimeMetrics]:
    if price_df.empty or len(price_df) < 30:
        return []

    adx = _compute_adx(price_df, period=14)
    atr_pct = _compute_atr_pct(price_df, period=14)

    regime_map: dict[str, dict[str, Any]] = {}
    for idx in price_df.index:
        raw_adx = adx.loc[idx] if idx in adx.index else None
        raw_atr = atr_pct.loc[idx] if idx in atr_pct.index else None
        adx_val_n: float | None = (
            float(raw_adx) if raw_adx is not None and pd.notna(raw_adx) else None
        )
        atr_val_n: float | None = (
            float(raw_atr) if raw_atr is not None and pd.notna(raw_atr) else None
        )
        regime = classify_regime(adx_val_n, atr_val_n)
        if regime not in regime_map:
            regime_map[regime] = {"bar_count": 0, "trades": []}
        regime_map[regime]["bar_count"] += 1

    for trade in trades:
        trade_date = trade.exit_time.date()
        # Use exit time to determine regime context
        if trade_date in price_df.index:
            raw_adx = adx.loc[trade_date] if trade_date in adx.index else None
            raw_atr = atr_pct.loc[trade_date] if trade_date in atr_pct.index else None
            adx_val_f: float | None = (
                float(raw_adx) if raw_adx is not None and pd.notna(raw_adx) else None
            )
            atr_val_f: float | None = (
                float(raw_atr) if raw_atr is not None and pd.notna(raw_atr) else None
            )
            regime = classify_regime(adx_val_f, atr_val_f)
            if regime in regime_map:
                trade_list = regime_map[regime].get("trades", [])
                if isinstance(trade_list, list):
                    trade_list.append(trade)

    results: list[RegimeMetrics] = []
    for regime, data in regime_map.items():
        raw_trades = data.get("trades", [])
        assert isinstance(raw_trades, list)
        trades_list: list[ClosedTrade] = raw_trades
        wins_list = [t for t in trades_list if t.net_pnl > 0]
        n_trades = len(trades_list)
        n_wins = len(wins_list)

        def _safe_div(num: float, den: int) -> float:
            return num / den if den > 0 else 0.0

        results.append(
            RegimeMetrics(
                regime=regime,
                bar_count=int(data.get("bar_count", 0)),
                trade_count=n_trades,
                win_count=n_wins,
                net_pnl=sum(t.net_pnl for t in trades_list),
                win_rate=_safe_div(float(n_wins), n_trades),
                avg_bars_held=_safe_div(
                    sum(t.bars_held for t in trades_list), n_trades
                ),
                avg_mae=_safe_div(
                    sum(abs(t.mae) for t in trades_list), n_trades
                ),
                avg_mfe=_safe_div(
                    sum(abs(t.mfe) for t in trades_list), n_trades
                ),
            )
        )

    return results
