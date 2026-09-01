from dataclasses import dataclass
from typing import Literal
import random


Side = Literal["LONG", "SHORT"]


@dataclass(frozen=True)
class ExecutionConfig:
    fee_rate: float = 0.0004
    slippage_rate: float = 0.0002

    # Number of candles before the order can execute.
    latency_bars: int = 0

    # Probability that an order actually gets filled.
    # 1.0 = always filled
    # 0.0 = never filled
    fill_probability: float = 1.0

    # Fixed seed keeps backtests reproducible.
    random_seed: int = 42

    def __post_init__(self):
        if self.fee_rate < 0:
            raise ValueError(
                "fee_rate cannot be negative"
            )

        if self.slippage_rate < 0:
            raise ValueError(
                "slippage_rate cannot be negative"
            )

        if not isinstance(self.latency_bars, int):
            raise TypeError(
                "latency_bars must be an integer"
            )

        if self.latency_bars < 0:
            raise ValueError(
                "latency_bars cannot be negative"
            )

        if not 0.0 <= self.fill_probability <= 1.0:
            raise ValueError(
                "fill_probability must be between 0 and 1"
            )

        if not isinstance(self.random_seed, int):
            raise TypeError(
                "random_seed must be an integer"
            )


@dataclass
class PendingOrder:
    side: Side

    requested_entry: float
    stop_loss: float
    take_profit: float
    quantity: float

    bars_remaining: int

    # Defaults to "UNKNOWN" rather than being required - portfolio
    # support is being prepared for, but a single-symbol caller (all
    # current callers) should never be forced to name it.
    symbol: str = "UNKNOWN"


@dataclass
class RejectedOrder:
    side: Side

    requested_entry: float
    stop_loss: float
    take_profit: float
    quantity: float

    reason: str = "NOT_FILLED"
    symbol: str = "UNKNOWN"


@dataclass
class SimulatedTrade:
    side: Side

    requested_entry: float
    entry_price: float

    stop_loss: float
    take_profit: float

    quantity: float

    entry_fee: float

    exit_price: float | None = None
    exit_fee: float = 0.0

    exit_reason: str | None = None

    gross_pnl: float = 0.0
    net_pnl: float = 0.0

    is_open: bool = True

    symbol: str = "UNKNOWN"


class ExecutionSimulator:
    """
    Execution Simulator V3.

    Supports:
    - LONG / SHORT
    - Entry latency
    - Fill probability
    - Deterministic random seed
    - Entry slippage
    - Exit slippage
    - Trading fees
    - Stop loss
    - Take profit
    - Gross and net PnL
    """

    def __init__(
        self,
        config: ExecutionConfig | None = None
    ):
        self.config = config or ExecutionConfig()

        self._random = random.Random(
            self.config.random_seed
        )


    def _validate_trade_inputs(
        self,
        side: Side,
        entry_price: float,
        stop_loss: float,
        take_profit: float,
        quantity: float,
    ) -> None:

        if side not in {"LONG", "SHORT"}:
            raise ValueError(
                "side must be LONG or SHORT"
            )

        if entry_price <= 0:
            raise ValueError(
                "entry_price must be positive"
            )

        if quantity <= 0:
            raise ValueError(
                "quantity must be positive"
            )

        if side == "LONG":

            if stop_loss >= entry_price:
                raise ValueError(
                    "LONG stop_loss must be below entry"
                )

            if take_profit <= entry_price:
                raise ValueError(
                    "LONG take_profit must be above entry"
                )

        else:

            if stop_loss <= entry_price:
                raise ValueError(
                    "SHORT stop_loss must be above entry"
                )

            if take_profit >= entry_price:
                raise ValueError(
                    "SHORT take_profit must be below entry"
                )


    def _apply_entry_slippage(
        self,
        side: Side,
        price: float
    ) -> float:

        if side == "LONG":
            return price * (
                1 + self.config.slippage_rate
            )

        return price * (
            1 - self.config.slippage_rate
        )


    def _apply_exit_slippage(
        self,
        side: Side,
        price: float
    ) -> float:

        if side == "LONG":
            return price * (
                1 - self.config.slippage_rate
            )

        return price * (
            1 + self.config.slippage_rate
        )


    def _order_is_filled(self) -> bool:
        """
        Decide whether an order fills.

        A fixed random seed makes the sequence
        reproducible across identical backtests.
        """

        if self.config.fill_probability == 1.0:
            return True

        if self.config.fill_probability == 0.0:
            return False

        return (
            self._random.random()
            < self.config.fill_probability
        )


    def _reject_order(
        self,
        side: Side,
        requested_entry: float,
        stop_loss: float,
        take_profit: float,
        quantity: float,
        symbol: str,
    ) -> RejectedOrder:

        return RejectedOrder(
            side=side,
            requested_entry=requested_entry,
            stop_loss=stop_loss,
            take_profit=take_profit,
            quantity=quantity,
            symbol=symbol,
        )


    def _attempt_execution(
        self,
        side: Side,
        requested_entry: float,
        execution_price: float,
        stop_loss: float,
        take_profit: float,
        quantity: float,
        symbol: str,
    ) -> SimulatedTrade | RejectedOrder:
        """
        Attempt to fill an order.

        If filled, execution uses the current market price
        plus adverse slippage.

        If not filled, no trade is created.
        """

        if not self._order_is_filled():
            return self._reject_order(
                side=side,
                requested_entry=requested_entry,
                stop_loss=stop_loss,
                take_profit=take_profit,
                quantity=quantity,
                symbol=symbol,
            )

        executed_entry = self._apply_entry_slippage(
            side=side,
            price=execution_price,
        )

        entry_notional = (
            executed_entry * quantity
        )

        entry_fee = (
            entry_notional
            * self.config.fee_rate
        )

        return SimulatedTrade(
            side=side,
            requested_entry=requested_entry,
            entry_price=executed_entry,
            stop_loss=stop_loss,
            take_profit=take_profit,
            quantity=quantity,
            entry_fee=entry_fee,
            symbol=symbol,
        )


    def open_trade(
        self,
        side: Side,
        entry_price: float,
        stop_loss: float,
        take_profit: float,
        quantity: float,
        symbol: str = "UNKNOWN",
    ) -> (
        SimulatedTrade
        | PendingOrder
        | RejectedOrder
    ):
        """
        Submit a new trade.

        latency_bars == 0:
            attempt execution immediately.

        latency_bars > 0:
            create a PendingOrder first.
        """

        self._validate_trade_inputs(
            side=side,
            entry_price=entry_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            quantity=quantity,
        )

        if self.config.latency_bars == 0:

            return self._attempt_execution(
                side=side,
                requested_entry=entry_price,
                execution_price=entry_price,
                stop_loss=stop_loss,
                take_profit=take_profit,
                quantity=quantity,
                symbol=symbol,
            )

        return PendingOrder(
            side=side,
            requested_entry=entry_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            quantity=quantity,
            bars_remaining=self.config.latency_bars,
            symbol=symbol,
        )


    def process_pending_order(
        self,
        order: PendingOrder,
        market_price: float,
    ) -> (
        PendingOrder
        | SimulatedTrade
        | RejectedOrder
    ):
        """
        Advance a pending order by one bar.

        Fill probability is checked only when
        the latency period expires.
        """

        if market_price <= 0:
            raise ValueError(
                "market_price must be positive"
            )

        if order.bars_remaining <= 0:
            raise ValueError(
                "Pending order has already expired"
            )

        order.bars_remaining -= 1

        if order.bars_remaining > 0:
            return order

        return self._attempt_execution(
            side=order.side,
            requested_entry=order.requested_entry,
            execution_price=market_price,
            stop_loss=order.stop_loss,
            take_profit=order.take_profit,
            quantity=order.quantity,
            symbol=order.symbol,
        )


    def close_trade(
        self,
        trade: SimulatedTrade,
        exit_price: float,
        reason: str,
    ) -> SimulatedTrade:

        if not trade.is_open:
            raise ValueError(
                "Trade is already closed"
            )

        if exit_price <= 0:
            raise ValueError(
                "exit_price must be positive"
            )

        executed_exit = self._apply_exit_slippage(
            side=trade.side,
            price=exit_price,
        )

        exit_notional = (
            executed_exit * trade.quantity
        )

        exit_fee = (
            exit_notional
            * self.config.fee_rate
        )

        if trade.side == "LONG":

            gross_pnl = (
                executed_exit
                - trade.entry_price
            ) * trade.quantity

        else:

            gross_pnl = (
                trade.entry_price
                - executed_exit
            ) * trade.quantity

        net_pnl = (
            gross_pnl
            - trade.entry_fee
            - exit_fee
        )

        trade.exit_price = executed_exit
        trade.exit_fee = exit_fee
        trade.exit_reason = reason

        trade.gross_pnl = gross_pnl
        trade.net_pnl = net_pnl

        trade.is_open = False

        return trade


    def process_candle(
        self,
        trade: SimulatedTrade,
        high: float,
        low: float,
    ) -> SimulatedTrade:

        if not trade.is_open:
            return trade

        if high < low:
            raise ValueError(
                "Candle high cannot be below low"
            )

        if trade.side == "LONG":

            stop_hit = low <= trade.stop_loss
            target_hit = high >= trade.take_profit

            if stop_hit and target_hit:

                return self.close_trade(
                    trade=trade,
                    exit_price=trade.stop_loss,
                    reason="STOP_LOSS_AMBIGUOUS",
                )

            if stop_hit:

                return self.close_trade(
                    trade=trade,
                    exit_price=trade.stop_loss,
                    reason="STOP_LOSS",
                )

            if target_hit:

                return self.close_trade(
                    trade=trade,
                    exit_price=trade.take_profit,
                    reason="TAKE_PROFIT",
                )

        else:

            stop_hit = high >= trade.stop_loss
            target_hit = low <= trade.take_profit

            if stop_hit and target_hit:

                return self.close_trade(
                    trade=trade,
                    exit_price=trade.stop_loss,
                    reason="STOP_LOSS_AMBIGUOUS",
                )

            if stop_hit:

                return self.close_trade(
                    trade=trade,
                    exit_price=trade.stop_loss,
                    reason="STOP_LOSS",
                )

            if target_hit:

                return self.close_trade(
                    trade=trade,
                    exit_price=trade.take_profit,
                    reason="TAKE_PROFIT",
                )

        return trade
