import logging

import pandas as pd
import vectorbt as vbt

from trading.backtest.brokerage import CommissionModel
from trading.backtest.metrics import BacktestMetrics
from trading.backtest.slippage import SlippageModel
from trading.backtest.trade_journal import TradeJournal, TradeRecord
from trading.core.config import TradingConfig
from trading.core.enums import Side
from trading.strategy.sma_crossover import _sma as compute_sma

logger = logging.getLogger(__name__)


class BacktestRunner:
    def __init__(self, config: TradingConfig) -> None:
        self.config = config
        self.commission_model = CommissionModel(config.backtest.commission)
        self.slippage_model = SlippageModel(config.backtest.slippage)

    async def run(
        self,
        symbol: str = "BTC/USDT",
        start: str = "2020-01-01",
        end: str = "2025-01-01",
        initial_cash: float = 10_000.0,
        journal_path: str | None = None,
    ) -> BacktestMetrics:
        logger.warning(
            "Backtest runner is using synthetic price data. "
            "Configure real data sources for production use."
        )
        start_dt = pd.Timestamp(start)
        end_dt = pd.Timestamp(end)
        index = pd.date_range(start=start_dt, end=end_dt, freq="D")
        close = pd.Series(100.0 + (index - start_dt).days * 0.01, index=index)

        df = pd.DataFrame({"close": close, "symbol": symbol}, index=index)
        signals = self._compute_signals(df)

        pf = vbt.Portfolio.from_orders(
            close=close,
            size=signals,
            price=close,
            init_cash=initial_cash,
            freq="D",
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

                indicator_values = {}
                entry_dt = pd.Timestamp(row["Entry Timestamp"])
                if entry_dt in df.index:
                    indicator_values["fast_sma"] = float(self._fast_sma.loc[entry_dt])
                    indicator_values["slow_sma"] = float(self._slow_sma.loc[entry_dt])
                trade_journal.add(
                    TradeRecord(
                        symbol=symbol,
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
                        indicator_values=indicator_values,
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

    def _compute_signals(self, df: pd.DataFrame) -> pd.Series:
        self._fast_sma = fast_sma = compute_sma(df["close"], length=20)
        self._slow_sma = slow_sma = compute_sma(df["close"], length=50)

        entries = (fast_sma > slow_sma) & (fast_sma.shift(1) <= slow_sma.shift(1))
        exits = (fast_sma < slow_sma) & (fast_sma.shift(1) >= slow_sma.shift(1))

        position = pd.Series(0, index=df.index)
        in_position = False
        for i in range(len(df)):
            if not in_position and entries.iloc[i]:
                position.iloc[i] = 1
                in_position = True
            elif in_position and exits.iloc[i]:
                position.iloc[i] = -1
                in_position = False

        return position
