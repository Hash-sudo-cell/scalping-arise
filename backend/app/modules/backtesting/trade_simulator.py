"""
Scalping Arise — Trade Simulator

Simulates order execution, fills, slippage, and spread costs
for backtesting. Supports multiple fill methods and slippage models.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from app.modules.backtesting.config import BacktestingSettings, get_backtesting_settings
from app.modules.backtesting.models import (
    CloseReason,
    FillMethod,
    HistoricalCandle,
    OrderSide,
    OrderStatus,
    OrderType,
    SlippageModel,
    SimulatedFill,
    SimulatedOrder,
    SimulatedPosition,
)
from app.modules.trade_planning.instrument_specs import get_spec

logger = logging.getLogger(__name__)


class TradeSimulator:
    """
    Simulates order execution with realistic fill modeling.

    Supports:
    - Market orders (fill at next bar open or current close)
    - Limit orders (fill when price touches limit)
    - Stop orders (fill when price touches stop)
    - Slippage modeling (fixed, percentage, ATR-based, spread-based)
    - Spread cost calculation
    - Partial fills
    """

    def __init__(
        self,
        fill_method: FillMethod = FillMethod.NEXT_BAR_OPEN,
        slippage_model: SlippageModel = SlippageModel.FIXED,
        slippage_pips: float = 1.0,
        spread_pips: float = 3.0,
        settings: Optional[BacktestingSettings] = None,
    ) -> None:
        self._settings = settings or get_backtesting_settings()
        self._fill_method = fill_method
        self._slippage_model = slippage_model
        self._slippage_pips = slippage_pips
        self._spread_pips = spread_pips
        self._pending_orders: list[SimulatedOrder] = []
        self._filled_orders: list[SimulatedFill] = []

    @property
    def pending_orders(self) -> list[SimulatedOrder]:
        return list(self._pending_orders)

    @property
    def filled_orders(self) -> list[SimulatedFill]:
        return list(self._filled_orders)

    def submit_order(self, order: SimulatedOrder) -> None:
        """Submit an order for simulation."""
        self._pending_orders.append(order)
        logger.debug(
            "Order submitted: %s %s %.4f %s @ %s",
            order.side.value,
            order.instrument,
            order.lots,
            order.order_type.value,
            order.price or "market",
        )

    def cancel_order(self, order_id: str) -> bool:
        """Cancel a pending order. Returns True if found and cancelled."""
        for i, order in enumerate(self._pending_orders):
            if order.order_id == order_id:
                self._pending_orders.pop(i)
                logger.debug("Order cancelled: %s", order_id)
                return True
        return False

    def process_orders(
        self,
        candle: HistoricalCandle,
        previous_candle: Optional[HistoricalCandle] = None,
    ) -> list[SimulatedFill]:
        """
        Process all pending orders against the current candle.

        Returns list of fills that occurred.
        """
        fills: list[SimulatedFill] = []
        remaining: list[SimulatedOrder] = []

        for order in self._pending_orders:
            fill = self._try_fill(order, candle, previous_candle)
            if fill is not None:
                fills.append(fill)
                self._filled_orders.append(fill)
            elif order.expires_at and candle.timestamp > order.expires_at:
                # Order expired
                logger.debug("Order expired: %s", order.order_id)
            else:
                remaining.append(order)

        self._pending_orders = remaining
        return fills

    def create_position_from_fill(
        self,
        fill: SimulatedFill,
        signal_id: Optional[str] = None,
        strategy_id: Optional[str] = None,
        plan_id: Optional[str] = None,
    ) -> SimulatedPosition:
        """Create a simulated position from a fill."""
        return SimulatedPosition(
            instrument=fill.instrument,
            side=fill.side,
            entry_price=fill.fill_price,
            current_price=fill.fill_price,
            lots=fill.lots,
            initial_lots=fill.lots,
            margin_used=self._calculate_margin(fill),
            signal_id=signal_id,
            strategy_id=strategy_id,
            plan_id=plan_id,
            opened_at=fill.timestamp,
            last_price_update=fill.timestamp,
        )

    def check_sl_tp_hit(
        self,
        position: SimulatedPosition,
        candle: HistoricalCandle,
    ) -> Optional[CloseReason]:
        """
        Check if stop-loss or take-profit is hit by the candle.

        Returns CloseReason if hit, None if position remains open.
        """
        # Check stop-loss
        if position.stop_loss_price is not None:
            if position.side == OrderSide.BUY:
                if candle.low <= position.stop_loss_price:
                    return CloseReason.STOP_LOSS
            else:
                if candle.high >= position.stop_loss_price:
                    return CloseReason.STOP_LOSS

        # Check take-profit
        if position.take_profit_price is not None:
            if position.side == OrderSide.BUY:
                if candle.high >= position.take_profit_price:
                    return CloseReason.TAKE_PROFIT
            else:
                if candle.low <= position.take_profit_price:
                    return CloseReason.TAKE_PROFIT

        return None

    def calculate_exit_price(
        self,
        position: SimulatedPosition,
        close_reason: CloseReason,
        candle: HistoricalCandle,
    ) -> float:
        """
        Calculate the exit price based on close reason.

        SL hits use the stop price (with slippage).
        TP hits use the take-profit price (with slippage).
        Other exits use the close price.
        """
        if close_reason == CloseReason.STOP_LOSS and position.stop_loss_price:
            base_price = position.stop_loss_price
        elif close_reason == CloseReason.TAKE_PROFIT and position.take_profit_price:
            base_price = position.take_profit_price
        else:
            base_price = candle.close

        # Apply slippage on exit
        return self._apply_slippage(
            base_price,
            position.side,
            candle,
            is_exit=True,
        )

    def reset(self) -> None:
        """Reset the simulator state."""
        self._pending_orders.clear()
        self._filled_orders.clear()

    # ------------------------------------------------------------------
    # Private: fill logic
    # ------------------------------------------------------------------

    def _try_fill(
        self,
        order: SimulatedOrder,
        candle: HistoricalCandle,
        previous_candle: Optional[HistoricalCandle],
    ) -> Optional[SimulatedFill]:
        """Try to fill an order against the current candle."""
        if order.order_type == OrderType.MARKET:
            return self._fill_market(order, candle)
        elif order.order_type == OrderType.LIMIT:
            return self._fill_limit(order, candle, previous_candle)
        elif order.order_type == OrderType.STOP:
            return self._fill_stop(order, candle, previous_candle)
        return None

    def _fill_market(
        self,
        order: SimulatedOrder,
        candle: HistoricalCandle,
    ) -> Optional[SimulatedFill]:
        """Fill a market order."""
        # Determine fill price based on fill method
        if self._fill_method in (
            FillMethod.NEXT_BAR_OPEN,
            FillMethod.NEXT_BAR_WITH_SLIPPAGE,
        ):
            base_price = candle.open
        else:
            base_price = candle.close

        # Apply spread for buy orders
        if order.side == OrderSide.BUY:
            base_price += self._spread_pips * self._get_pip_value(order.instrument)

        # Apply slippage
        if self._fill_method in (
            FillMethod.CURRENT_CLOSE_WITH_SLIPPAGE,
            FillMethod.NEXT_BAR_WITH_SLIPPAGE,
        ):
            fill_price = self._apply_slippage(base_price, order.side, candle, is_exit=False)
        else:
            fill_price = base_price

        # Calculate costs
        slippage_pips = abs(fill_price - base_price) / self._get_pip_value(order.instrument)
        slippage_cost = slippage_pips * order.lots * self._get_pip_value_per_lot(order.instrument)
        spread_cost = self._spread_pips * order.lots * self._get_pip_value_per_lot(order.instrument)

        return SimulatedFill(
            order_id=order.order_id,
            instrument=order.instrument,
            side=order.side,
            lots=order.lots,
            fill_price=fill_price,
            slippage_pips=slippage_pips,
            slippage_cost=slippage_cost,
            spread_cost=spread_cost,
            commission=0.0,
            total_cost=slippage_cost + spread_cost,
            fill_method=self._fill_method,
            timestamp=candle.timestamp,
        )

    def _fill_limit(
        self,
        order: SimulatedOrder,
        candle: HistoricalCandle,
        previous_candle: Optional[HistoricalCandle],
    ) -> Optional[SimulatedFill]:
        """Fill a limit order if price touches the limit level."""
        if order.price is None:
            return None

        # Check if price crossed the limit level
        touched = False
        if order.side == OrderSide.BUY:
            # Buy limit: price must drop to or below limit
            touched = candle.low <= order.price
        else:
            # Sell limit: price must rise to or above limit
            touched = candle.high >= order.price

        if not touched:
            return None

        fill_price = order.price
        slippage_pips = 0.0
        slippage_cost = 0.0
        spread_cost = self._spread_pips * order.lots * self._get_pip_value_per_lot(order.instrument)

        return SimulatedFill(
            order_id=order.order_id,
            instrument=order.instrument,
            side=order.side,
            lots=order.lots,
            fill_price=fill_price,
            slippage_pips=slippage_pips,
            slippage_cost=slippage_cost,
            spread_cost=spread_cost,
            commission=0.0,
            total_cost=spread_cost,
            fill_method=FillMethod.CURRENT_CLOSE,
            timestamp=candle.timestamp,
        )

    def _fill_stop(
        self,
        order: SimulatedOrder,
        candle: HistoricalCandle,
        previous_candle: Optional[HistoricalCandle],
    ) -> Optional[SimulatedFill]:
        """Fill a stop order if price touches the stop level."""
        if order.price is None:
            return None

        touched = False
        if order.side == OrderSide.BUY:
            # Buy stop: price must rise to or above stop
            touched = candle.high >= order.price
        else:
            # Sell stop: price must drop to or below stop
            touched = candle.low <= order.price

        if not touched:
            return None

        fill_price = order.price
        slippage_pips = 0.0
        slippage_cost = 0.0
        spread_cost = self._spread_pips * order.lots * self._get_pip_value_per_lot(order.instrument)

        return SimulatedFill(
            order_id=order.order_id,
            instrument=order.instrument,
            side=order.side,
            lots=order.lots,
            fill_price=fill_price,
            slippage_pips=slippage_pips,
            slippage_cost=slippage_cost,
            spread_cost=spread_cost,
            commission=0.0,
            total_cost=spread_cost,
            fill_method=FillMethod.CURRENT_CLOSE,
            timestamp=candle.timestamp,
        )

    def _apply_slippage(
        self,
        price: float,
        side: OrderSide,
        candle: HistoricalCandle,
        is_exit: bool,
    ) -> float:
        """Apply slippage to a fill price."""
        if self._slippage_pips <= 0:
            return price

        pip_value = self._get_pip_value(candle.instrument)

        if self._slippage_model == SlippageModel.FIXED:
            slippage_amount = self._slippage_pips * pip_value
        elif self._slippage_model == SlippageModel.PERCENTAGE:
            slippage_amount = price * (self._slippage_pips / 10000)
        elif self._slippage_model == SlippageModel.ATR_MULTIPLE:
            # Use candle range as ATR proxy
            atr_proxy = candle.high - candle.low
            slippage_amount = atr_proxy * (self._slippage_pips / 10)
        elif self._slippage_model == SlippageModel.SPREAD_BASED:
            slippage_amount = self._spread_pips * pip_value * 0.5
        else:
            slippage_amount = self._slippage_pips * pip_value

        # Slippage always worsens the fill
        if (side == OrderSide.BUY and not is_exit) or (side == OrderSide.SELL and is_exit):
            return price + slippage_amount
        else:
            return price - slippage_amount

    def _calculate_margin(self, fill: SimulatedFill) -> float:
        """Calculate margin required for a fill."""
        spec = get_spec(fill.instrument)
        if spec is None:
            return fill.lots * fill.fill_price * 0.05
        contract_value = fill.lots * spec.contract_size * fill.fill_price
        return contract_value * spec.margin_rate

    def _get_pip_value(self, instrument: str) -> float:
        """Get the pip value in price units for an instrument."""
        spec = get_spec(instrument)
        if spec is None:
            return 0.01
        return spec.tick_size * 10

    def _get_pip_value_per_lot(self, instrument: str) -> float:
        """Get the monetary value of 1 pip per lot."""
        spec = get_spec(instrument)
        if spec is None:
            return 1.0
        return spec.pip_value_per_lot

    def summary(self) -> dict:
        """Return summary of simulator state."""
        return {
            "fill_method": self._fill_method.value,
            "slippage_model": self._slippage_model.value,
            "slippage_pips": self._slippage_pips,
            "spread_pips": self._spread_pips,
            "pending_orders": len(self._pending_orders),
            "filled_orders": len(self._filled_orders),
        }
