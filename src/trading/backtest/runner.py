from datetime import datetime

import pandas as pd
import structlog

from trading.backtest.backtest_types import ClosedTrade, OpenTrade
from trading.backtest.brokerage import CommissionModel
from trading.backtest.metrics import BacktestMetrics, compute_metrics_from_trades
from trading.backtest.slippage import SlippageModel
from trading.core.config import TradingConfig
from trading.core.enums import AssetClass, OrderType, Side
from trading.core.events import BarEvent, FillEvent, OrderEvent, SentimentEvent
from trading.core.models import Bar
from trading.execution.adapters.binance import BinanceAdapter
from trading.execution.paper import PaperAdapter
from trading.orchestration.bar_buffer import BarBuffer
from trading.orchestration.exit_manager import ExitManager
from trading.risk.manager import RiskManager
from trading.risk.regime_filter import RegimeFilter
from trading.risk.rules import RiskRule
from trading.strategy.filters import SignalFilter
from trading.strategy.registry import StrategyRegistry

logger = structlog.get_logger(__name__)


def _bar_to_event(bar: Bar) -> BarEvent:
    return BarEvent(
        symbol=bar.symbol,
        open=bar.open,
        high=bar.high,
        low=bar.low,
        close=bar.close,
        volume=bar.volume,
        asset_class=bar.asset_class,
        timestamp=bar.timestamp,
    )


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
        source: str = "adapter",
        _journal_path: str | None = None,
        filters: list[SignalFilter] | None = None,
        regime_filter: RegimeFilter | None = None,
        risk_rules: list[RiskRule] | None = None,
        sentiment_source: str | None = None,
    ) -> BacktestMetrics:
        bars = await self._load_bars(symbol, timeframe, start, end, source)

        strategy_cls = StrategyRegistry.get(strategy_name)
        strategy = strategy_cls()
        await strategy.initialize()

        paper = PaperAdapter(initial_cash=initial_cash)
        exit_mgr = ExitManager()
        bar_buffer = BarBuffer(max_size=100)
        risk_mgr = RiskManager(risk_rules if risk_rules is not None else [])

        sentiment_map: dict[datetime, SentimentEvent] = {}
        if sentiment_source:
            sentiment_map = await self._load_sentiment(symbol, start, end, sentiment_source)

        trades: list[ClosedTrade] = []
        open_trade: OpenTrade | None = None

        for bar in bars:
            bar_event = _bar_to_event(bar)
            paper.update_last_price(symbol, bar.close)

            df = bar_buffer.add(symbol, bar)

            exit_order = exit_mgr.on_bar(bar_event)
            if exit_order is not None:
                fill = await paper.submit_order(exit_order)
                if open_trade is not None:
                    self._close_trade(
                        trades, open_trade, fill, bar, "stop_loss"
                        if fill.correlation_id and fill.correlation_id.startswith("stop_")
                        else "take_profit"
                        if fill.correlation_id and fill.correlation_id.startswith("tp_")
                        else "time_exit",
                    )
                    open_trade = None

            sentiment = sentiment_map.get(bar.timestamp)
            result = await strategy.on_data(df, sentiment)

            if result.signal is not None:
                # Quality filters
                if filters:
                    passed = True
                    for flt in filters:
                        ok, _ = await flt.evaluate(df, result.signal)
                        if not ok:
                            passed = False
                            break
                    if not passed:
                        continue

                # Regime filter
                if regime_filter is not None:
                    ok, _ = await regime_filter.check(df, result.signal)
                    if not ok:
                        continue

                # Risk rules
                if risk_mgr.rules:
                    ok, _ = await risk_mgr.check(result.signal)
                    if not ok:
                        continue

                # Position sizing
                entry_price = result.signal.entry_price or result.signal.price or bar.close
                stop_price = result.signal.stop_loss_price
                if entry_price > 0 and stop_price is not None:
                    stop_distance = abs(entry_price - stop_price)
                    risk_amount = paper._cash * self.config.risk.risk_per_trade
                    quantity = risk_amount / stop_distance if stop_distance > 0 else 1.0
                else:
                    quantity = 1.0

                order_event = OrderEvent(
                    symbol=result.signal.symbol,
                    side=result.signal.side,
                    order_type=OrderType.MARKET,
                    quantity=quantity,
                    price=entry_price,
                    stop_price=stop_price,
                    strategy_name=strategy_name,
                    asset_class=result.signal.asset_class,
                    source="backtest",
                    correlation_id=result.signal.correlation_id,
                )

                try:
                    fill = await paper.submit_order(order_event)
                except Exception:
                    logger.exception("backtest_order_failed", symbol=symbol)
                    continue

                exit_mgr.on_fill(fill)

                if fill.side == Side.BUY:
                    high = bar.high
                    low = bar.low
                    open_trade = OpenTrade(
                        symbol=symbol,
                        side=Side.BUY,
                        entry_price=fill.fill_price,
                        quantity=fill.quantity,
                        entry_time=bar.timestamp,
                        stop_loss_price=stop_price or entry_price * 0.95,
                        take_profit_price=result.signal.take_profit_price,
                        highest_price=high,
                        lowest_price=low,
                    )
                elif fill.side == Side.SELL and open_trade is not None:
                    self._close_trade(trades, open_trade, fill, bar, "signal")
                    open_trade = None

            if open_trade is not None:
                if bar.high > open_trade.highest_price:
                    open_trade.highest_price = bar.high
                if bar.low < open_trade.lowest_price:
                    open_trade.lowest_price = bar.low
                open_trade.bars_held += 1

        # Close any remaining open trade at last price
        if open_trade is not None and bars:
            last_bar = bars[-1]
            gross = (last_bar.close - open_trade.entry_price) * open_trade.quantity
            commission = self.commission_model.compute(last_bar.close, open_trade.quantity)
            slippage_cost = self.slippage_model.compute_cost(
                last_bar.close, open_trade.quantity, Side.SELL
            )
            trades.append(
                ClosedTrade(
                    symbol=symbol,
                    side=open_trade.side,
                    entry_time=open_trade.entry_time,
                    exit_time=last_bar.timestamp,
                    entry_price=open_trade.entry_price,
                    exit_price=last_bar.close,
                    quantity=open_trade.quantity,
                    gross_pnl=gross,
                    net_pnl=gross - commission - slippage_cost,
                    commission=commission,
                    slippage_cost=slippage_cost,
                    exit_reason="end_of_data",
                    mae=open_trade.entry_price - open_trade.lowest_price,
                    mfe=open_trade.highest_price - open_trade.entry_price,
                    bars_held=open_trade.bars_held,
                )
            )

        return compute_metrics_from_trades(trades, initial_cash)

    async def _load_bars(
        self, symbol: str, timeframe: str, start: str, end: str, source: str
    ) -> list[Bar]:
        if source == "adapter":
            return await self._fetch_bars(symbol, timeframe, start, end)
        if source == "db":
            return await self._fetch_bars_from_db(symbol, timeframe, start, end)
        return self._synthetic_bars(symbol, start, end)

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
            logger.warning("Failed to fetch bars from Binance", exc=str(exc))
            return []
        finally:
            await adapter.close()

    async def _fetch_bars_from_db(
        self, symbol: str, timeframe: str, start: str, end: str
    ) -> list[Bar]:
        from trading.data.repository import TimescaleRepository

        repo = TimescaleRepository(self.config.database)
        await repo.connect()
        await repo.ensure_schema()
        start_dt = datetime.fromisoformat(start)
        end_dt = datetime.fromisoformat(end)
        try:
            return await repo.get_bars(symbol, timeframe, start_dt, end_dt)
        finally:
            await repo.close()

    def _synthetic_bars(self, symbol: str, start: str, end: str) -> list[Bar]:
        import math

        start_dt = pd.Timestamp(start)
        end_dt = pd.Timestamp(end)
        index = pd.date_range(start=start_dt, end=end_dt, freq="D")
        days = (index - start_dt).days
        # Oscillating series: base 100 + sine wave + slight uptrend
        sine_vals = [math.sin(2 * math.pi * d / 120) for d in days]
        close = pd.Series(
            100.0 + 10.0 * (days / 365) + 15.0 * pd.Series(sine_vals, index=index),
            index=index,
        )

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

    async def _load_sentiment(
        self, symbol: str, start: str, end: str, source: str
    ) -> dict[datetime, SentimentEvent]:
        if source != "db":
            return {}
        from trading.data.sentiment_repository import SentimentRepository

        repo = SentimentRepository(self.config.database)
        await repo.connect()
        try:
            events = await repo.get_recent(symbol, limit=10000)
        finally:
            await repo.close()
        return {ev.timestamp: ev for ev in events if start <= ev.timestamp.isoformat()[:10] <= end}

    def _close_trade(
        self,
        trades: list[ClosedTrade],
        open_t: OpenTrade,
        fill: FillEvent,
        bar: Bar,
        exit_reason: str,
    ) -> None:
        gross_pnl = (fill.fill_price - open_t.entry_price) * open_t.quantity
        commission = self.commission_model.compute(fill.fill_price, open_t.quantity)
        slippage_cost = self.slippage_model.compute_cost(
            fill.fill_price, open_t.quantity, Side.SELL
        )
        trades.append(
            ClosedTrade(
                symbol=open_t.symbol,
                side=open_t.side,
                entry_time=open_t.entry_time,
                exit_time=bar.timestamp,
                entry_price=open_t.entry_price,
                exit_price=fill.fill_price,
                quantity=open_t.quantity,
                gross_pnl=gross_pnl,
                net_pnl=gross_pnl - commission - slippage_cost,
                commission=commission,
                slippage_cost=slippage_cost,
                exit_reason=exit_reason,
                mae=open_t.entry_price - open_t.lowest_price,
                mfe=open_t.highest_price - open_t.entry_price,
                bars_held=open_t.bars_held,
            )
        )
