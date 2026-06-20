import logging
from datetime import datetime
from typing import Literal

import pandas as pd
import vectorbt as vbt

from trading.backtest.brokerage import CommissionModel
from trading.backtest.metrics import BacktestMetrics
from trading.backtest.slippage import SlippageModel
from trading.backtest.trade_journal import TradeJournal, TradeRecord
from trading.core.config import TradingConfig
from trading.core.enums import AssetClass, Side
from trading.core.models import Bar
from trading.execution.adapters.binance import BinanceAdapter
from trading.strategy.registry import StrategyRegistry

logger = logging.getLogger(__name__)


def _bars_to_dataframe(bars: list[Bar]) -> pd.DataFrame:
    rows = []
    for b in bars:
        rows.append(
            {
                "open": b.open,
                "high": b.high,
                "low": b.low,
                "close": b.close,
                "volume": b.volume,
                "symbol": b.symbol,
                "timestamp": b.timestamp,
            }
        )
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    df = df.set_index("timestamp").sort_index()
    df.index = pd.DatetimeIndex(df.index)
    numeric_cols = ["open", "high", "low", "close", "volume"]
    df[numeric_cols] = df[numeric_cols].apply(pd.to_numeric, errors="coerce")
    return df


def _infer_freq(index: pd.DatetimeIndex) -> str | None:
    freq = pd.infer_freq(index)
    return freq if freq else None


class BacktestRunner:
    def __init__(self, config: TradingConfig) -> None:
        self.config = config
        self.commission_model = CommissionModel(config.backtest.commission)
        self.slippage_model = SlippageModel(config.backtest.slippage)

    async def run(
        self,
        strategy_name: str = "sma_crossover",
        symbol: str = "BTC/USDT",
        timeframe: str = "1d",
        start: str = "2020-01-01",
        end: str = "2025-01-01",
        initial_cash: float = 10_000.0,
        source: Literal["adapter", "synthetic"] = "adapter",
        journal_path: str | None = None,
    ) -> BacktestMetrics:
        if source == "adapter":
            bars = await self._fetch_bars(symbol, timeframe, start, end)
            if not bars:
                raise RuntimeError(
                    f"Failed to fetch bars for {symbol} from adapter. "
                    f"Check network connectivity and API credentials."
                )
        else:
            bars = self._synthetic_bars(symbol, start, end)

        df = _bars_to_dataframe(bars)

        strategy_cls = StrategyRegistry.get(strategy_name)
        strategy = strategy_cls()
        await strategy.initialize()

        position_changes = pd.Series(0.0, index=df.index)
        in_position = False

        lookback = 100
        for i in range(len(df)):
            start_idx = max(0, i - lookback + 1)
            window = df.iloc[start_idx : i + 1]
            result = await strategy.on_data(window)
            if result.signal is None:
                continue
            if result.signal.side == Side.BUY and not in_position:
                position_changes.iloc[i] = 1.0
                in_position = True
            elif result.signal.side == Side.SELL and in_position:
                position_changes.iloc[i] = -1.0
                in_position = False

        freq = _infer_freq(df.index)
        pf = vbt.Portfolio.from_orders(
            close=df["close"],
            size=position_changes,
            price=df["close"],
            init_cash=initial_cash,
            freq=freq,
        )

        trades_df = pf.trades.records
        trade_journal = TradeJournal()
        total_commission = 0.0
        total_slippage_cost = 0.0

        if trades_df is not None and len(trades_df) > 0:
            for _, row in trades_df.iterrows():
                qty = abs(row["Size"])
                entry_price = row["Entry Price"]
                exit_price = row["Exit Price"]
                gross_pnl = row["PnL"]

                commission = self.commission_model.compute_entry_exit(entry_price, exit_price, qty)
                entry_slip = self.slippage_model.compute_cost(entry_price, qty, Side.BUY)
                exit_slip = self.slippage_model.compute_cost(exit_price, qty, Side.SELL)
                slippage = entry_slip + exit_slip
                net_pnl = gross_pnl - commission - slippage

                total_commission += commission
                total_slippage_cost += slippage

                trade_journal.add(
                    TradeRecord(
                        symbol=symbol,
                        strategy=strategy_name,
                        side=Side.BUY if row["Size"] > 0 else Side.SELL,
                        entry_time=row["Entry Timestamp"].to_pydatetime(),
                        exit_time=row["Exit Timestamp"].to_pydatetime(),
                        entry_price=entry_price,
                        exit_price=exit_price,
                        quantity=qty,
                        gross_pnl=gross_pnl,
                        commission=commission,
                        slippage_cost=slippage,
                        net_pnl=net_pnl,
                    )
                )

        if journal_path:
            trade_journal.to_csv(journal_path)

        return BacktestMetrics(
            total_return=pf.total_return(),
            sharpe_ratio=pf.sharpe_ratio(),
            max_drawdown=pf.max_drawdown(),
            sortino_ratio=pf.sortino_ratio(),
            total_trades=pf.trades.count(),
            win_rate=pf.trades.win_rate(),
            total_pnl=pf.total_profit(),
            total_commission=total_commission,
            total_slippage_cost=total_slippage_cost,
            net_pnl=pf.total_profit() - total_commission - total_slippage_cost,
            equity_curve=pf.value(),
            trades=trade_journal.to_dataframe(),
        )

    async def _fetch_bars(self, symbol: str, timeframe: str, start: str, end: str) -> list[Bar]:
        broker_cfg = self.config.brokers.binance
        adapter = BinanceAdapter(
            api_key=broker_cfg.api_key,
            api_secret=broker_cfg.api_secret,
            testnet=broker_cfg.testnet,
        )
        start_dt = datetime.fromisoformat(start)
        end_dt = datetime.fromisoformat(end)
        try:
            return await adapter.get_bars(symbol, timeframe, start_dt, end_dt)
        except Exception as exc:
            logger.warning("Failed to fetch bars from Binance: %s.", exc)
            return []
        finally:
            await adapter.close()

    def _synthetic_bars(self, symbol: str, start: str, end: str) -> list[Bar]:
        start_dt = pd.Timestamp(start)
        end_dt = pd.Timestamp(end)
        index = pd.date_range(start=start_dt, end=end_dt, freq="D")
        close = pd.Series(100.0 + (index - start_dt).days * 0.01, index=index)

        bars: list[Bar] = []
        for dt, pr in zip(index, close, strict=False):
            bars.append(
                Bar(
                    symbol=symbol,
                    asset_class=AssetClass.CRYPTO,
                    timeframe="1d",
                    open=float(pr - 0.5),
                    high=float(pr + 1.0),
                    low=float(pr - 1.0),
                    close=float(pr),
                    volume=100.0,
                    timestamp=dt.to_pydatetime(),
                )
            )
        return bars
