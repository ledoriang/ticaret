from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import structlog

from trading.core.enums import OrderType, Side
from trading.core.events import BarEvent, FillEvent, OrderEvent

logger = structlog.get_logger(__name__)


@dataclass
class TrackedPosition:
    symbol: str
    side: Side
    entry_price: float
    quantity: float
    stop_loss_price: float
    take_profit_price: float | None
    current_stop: float
    bars_held: int = 0
    entry_time: datetime = field(default_factory=datetime.now)
    metadata: dict[str, Any] = field(default_factory=dict)


class ExitManager:
    def __init__(
        self,
        max_bars: int = 20,
        trail_method: str = "atr",
        trail_atr_mult: float = 2.0,
        trail_pct: float = 0.02,
    ) -> None:
        self.max_bars = max_bars
        self.trail_method = trail_method
        self.trail_atr_mult = trail_atr_mult
        self.trail_pct = trail_pct
        self._positions: dict[str, TrackedPosition] = {}

    def register_position(
        self,
        symbol: str,
        side: Side,
        entry_price: float,
        quantity: float,
        stop_loss_price: float,
        take_profit_price: float | None = None,
    ) -> None:
        self._positions[symbol] = TrackedPosition(
            symbol=symbol,
            side=side,
            entry_price=entry_price,
            quantity=quantity,
            stop_loss_price=stop_loss_price,
            take_profit_price=take_profit_price,
            current_stop=stop_loss_price,
        )
        logger.info(
            "position_registered",
            symbol=symbol,
            side=side.value,
            entry=entry_price,
            stop=stop_loss_price,
            tp=take_profit_price,
        )

    def remove_position(self, symbol: str) -> None:
        if symbol in self._positions:
            del self._positions[symbol]
            logger.info("position_removed", symbol=symbol)

    def on_fill(self, fill: FillEvent) -> None:
        if fill.side == Side.BUY:
            self.register_position(
                symbol=fill.symbol,
                side=Side.BUY,
                entry_price=fill.fill_price,
                quantity=fill.quantity,
                stop_loss_price=fill.fill_price * 0.95,
                take_profit_price=fill.fill_price * 1.10,
            )
        elif fill.side == Side.SELL:
            self.remove_position(fill.symbol)

    def on_bar(self, bar: BarEvent) -> OrderEvent | None:
        if bar.symbol not in self._positions:
            return None

        pos = self._positions[bar.symbol]
        pos.bars_held += 1

        # Check stop-loss
        if bar.close <= pos.current_stop:
            logger.warning(
                "stop_loss_hit",
                symbol=bar.symbol,
                stop=pos.current_stop,
                close=bar.close,
            )
            self.remove_position(bar.symbol)
            return OrderEvent(
                symbol=bar.symbol,
                side=Side.SELL,
                order_type=OrderType.MARKET,
                quantity=pos.quantity,
                price=bar.close,
                source="exit_manager",
                correlation_id=f"stop_{bar.event_id}",
            )

        # Check take-profit
        if pos.take_profit_price is not None and bar.close >= pos.take_profit_price:
            logger.info(
                "take_profit_hit",
                symbol=bar.symbol,
                tp=pos.take_profit_price,
                close=bar.close,
            )
            self.remove_position(bar.symbol)
            return OrderEvent(
                symbol=bar.symbol,
                side=Side.SELL,
                order_type=OrderType.MARKET,
                quantity=pos.quantity,
                price=bar.close,
                source="exit_manager",
                correlation_id=f"tp_{bar.event_id}",
            )

        # Check time-based exit
        if pos.bars_held >= self.max_bars:
            logger.info(
                "time_exit",
                symbol=bar.symbol,
                bars_held=pos.bars_held,
                max_bars=self.max_bars,
            )
            self.remove_position(bar.symbol)
            return OrderEvent(
                symbol=bar.symbol,
                side=Side.SELL,
                order_type=OrderType.MARKET,
                quantity=pos.quantity,
                price=bar.close,
                source="exit_manager",
                correlation_id=f"time_{bar.event_id}",
            )

        # Update trailing stop
        self._update_trailing_stop(pos, bar)

        return None

    def _update_trailing_stop(self, pos: TrackedPosition, bar: BarEvent) -> None:
        if self.trail_method == "atr":
            # ATR-based trailing stop
            atr_value = (bar.high - bar.low) * 0.5
            new_stop = bar.close - (atr_value * self.trail_atr_mult)
        else:
            # Percentage-based trailing stop
            new_stop = bar.close * (1 - self.trail_pct)

        # Only ratchet in favorable direction (never loosen)
        if new_stop > pos.current_stop:
            pos.current_stop = new_stop
            logger.debug(
                "trailing_stop_updated",
                symbol=pos.symbol,
                new_stop=new_stop,
                old_stop=pos.current_stop,
            )
