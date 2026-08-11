from dataclasses import dataclass
from typing import Any, Callable

from analytics.performance import (
    PerformanceReport,
    calculate_performance,
)
from backtesting.execution_simulator import (
    ExecutionConfig,
    ExecutionSimulator,
    PendingOrder,
    RejectedOrder,
    SimulatedTrade,
)
from backtesting.replay_engine import ReplayEngine
from backtesting.trade_journal import TradeJournal
from backtesting.window_manager import WindowManager
from data.market_data_aligner import align_market_data
from strategy.trade_setup import TradeSetup


@dataclass(frozen=True)
class BacktestResult:
    journal: TradeJournal
    performance: PerformanceReport


class BacktestRunner:
    """
    Coordinates the point-in-time-safe backtesting pipeline.

    Existing run():

        Window Manager
            -> Replay Engine
            -> Market Data Alignment
            -> callback

    Full run_strategy():

        Window Manager
            -> Replay Engine
            -> Market Data Alignment
            -> Strategy
            -> Trade Setup
            -> Execution Simulator
            -> Trade Journal
            -> Performance Report

    The existing run() API is intentionally preserved.
    """

    def __init__(
        self,
        window_manager: WindowManager,
        candles: list[dict[str, Any]],
        open_interest_records: list[dict[str, Any]] | None = None,
        funding_records: list[dict[str, Any]] | None = None,
        timestamp_key: str = "timestamp",
    ):
        self.window_manager = window_manager
        self.candles = candles
        self.open_interest_records = (
            open_interest_records or []
        )
        self.funding_records = (
            funding_records or []
        )
        self.timestamp_key = timestamp_key

    # =====================================================
    # ORIGINAL POINT-IN-TIME RUNNER
    # =====================================================

    def get_window_candles(
        self,
        window_name: str,
    ) -> list[dict[str, Any]]:
        """
        Return candles belonging only to the requested
        TRAIN / VALIDATION / HELD_OUT window.
        """

        return self.window_manager.get_records(
            records=self.candles,
            window_name=window_name,
        )

    def run(
        self,
        window_name: str,
        callback: Callable[
            [
                dict[str, Any],
                list[dict[str, Any]],
                dict[str, Any],
            ],
            None,
        ],
    ) -> None:
        """
        Run one isolated backtest window.

        callback receives:

        1. current candle
        2. visible candle history
        3. aligned market snapshot

        The snapshot contains only OI/Funding data
        available at the current candle timestamp.
        """

        window_candles = self.get_window_candles(
            window_name=window_name
        )

        replay_engine = ReplayEngine(
            records=window_candles,
            timestamp_key=self.timestamp_key,
        )

        def on_replay_step(
            current_candle: dict[str, Any],
            visible_history: list[dict[str, Any]],
        ) -> None:

            current_time = current_candle[
                self.timestamp_key
            ]

            market_snapshot = align_market_data(
                candle=current_candle,
                current_time=current_time,
                open_interest_records=(
                    self.open_interest_records
                ),
                funding_records=(
                    self.funding_records
                ),
                timestamp_key=self.timestamp_key,
            )

            callback(
                current_candle,
                visible_history,
                market_snapshot,
            )

        replay_engine.run(on_replay_step)

    # =====================================================
    # FULL STRATEGY BACKTEST
    # =====================================================

    def run_strategy(
        self,
        window_name: str,
        strategy_callback: Callable[
            [
                dict[str, Any],
                list[dict[str, Any]],
                dict[str, Any],
            ],
            dict[str, Any],
        ],
        trade_setup_callback: Callable[
            [
                str,
                dict[str, Any],
                list[dict[str, Any]],
                dict[str, Any],
                float,
            ],
            TradeSetup,
        ],
        execution_config: ExecutionConfig | None = None,
        initial_equity: float = 10_000.0,
    ) -> BacktestResult:
        
        """
        Run a complete strategy simulation.

        strategy_callback returns:

            {
                "decision": "LONG" | "SHORT" | "IGNORE",
                "score": ...,
                ...
            }

        trade_setup_callback is called only for LONG/SHORT.

        It receives:

            1. decision
            2. current candle
            3. visible history
            4. market snapshot
            5. current equity

        This allows position sizing to use the account
        equity available at that exact point in the backtest.

        Current limitation:
        Only one active trade/order is allowed at a time.
        """

        if not callable(strategy_callback):
            raise TypeError(
                "strategy_callback must be callable"
            )

        if not callable(trade_setup_callback):
            raise TypeError(
                "trade_setup_callback must be callable"
            )

        if initial_equity <= 0:
            raise ValueError(
                "initial_equity must be positive"
            )

        journal = TradeJournal()

        simulator = ExecutionSimulator(
            execution_config
            or ExecutionConfig()
        )

        active_trade: SimulatedTrade | None = None
        pending_order: PendingOrder | None = None

        # Equity changes only when a trade is closed.
        # net_pnl already includes fees, so fees must
        # NOT be deducted again here.
        current_equity = float(initial_equity)

        window_candles = self.get_window_candles(
            window_name=window_name
        )

        replay_engine = ReplayEngine(
            records=window_candles,
            timestamp_key=self.timestamp_key,
        )

        def on_replay_step(
            current_candle: dict[str, Any],
            visible_history: list[dict[str, Any]],
        ) -> None:

            nonlocal active_trade
            nonlocal pending_order
            nonlocal current_equity

            current_time = current_candle[
                self.timestamp_key
            ]

            market_snapshot = align_market_data(
                candle=current_candle,
                current_time=current_time,
                open_interest_records=(
                    self.open_interest_records
                ),
                funding_records=(
                    self.funding_records
                ),
                timestamp_key=self.timestamp_key,
            )

            # ---------------------------------------------
            # 1. Existing open trade
            # ---------------------------------------------

            if active_trade is not None:

                was_open = active_trade.is_open

                active_trade = simulator.process_candle(
                    trade=active_trade,
                    high=current_candle["high"],
                    low=current_candle["low"],
                )

                if (
                    was_open
                    and not active_trade.is_open
                ):
                    journal.record_closed(
                        timestamp=current_time,
                        side=active_trade.side,
                        entry_price=active_trade.entry_price,
                        exit_price=active_trade.exit_price,
                        quantity=active_trade.quantity,
                        entry_fee=active_trade.entry_fee,
                        exit_fee=active_trade.exit_fee,
                        gross_pnl=active_trade.gross_pnl,
                        net_pnl=active_trade.net_pnl,
                        exit_reason=active_trade.exit_reason,
                    )

                    # Dynamic equity:
                    # net_pnl already includes fees.
                    current_equity += (
                        active_trade.net_pnl
                    )

                    active_trade = None

                # Do not close one trade and generate a new
                # signal on the same OHLC candle.
                return

            # ---------------------------------------------
            # 2. Existing pending order
            # ---------------------------------------------

            if pending_order is not None:

                execution_result = (
                    simulator.process_pending_order(
                        order=pending_order,
                        market_price=current_candle["open"],
                    )
                )

                if isinstance(
                    execution_result,
                    PendingOrder,
                ):
                    pending_order = execution_result
                    return

                if isinstance(
                    execution_result,
                    RejectedOrder,
                ):
                    journal.record_rejected(
                        timestamp=current_time,
                        side=execution_result.side,
                        requested_entry=(
                            execution_result.requested_entry
                        ),
                        reason=execution_result.reason,
                    )

                    pending_order = None
                    return

                if isinstance(
                    execution_result,
                    SimulatedTrade,
                ):
                    active_trade = execution_result
                    pending_order = None

                    journal.record_opened(
                        timestamp=current_time,
                        side=active_trade.side,
                        requested_entry=(
                            active_trade.requested_entry
                        ),
                        entry_price=(
                            active_trade.entry_price
                        ),
                        stop_loss=active_trade.stop_loss,
                        take_profit=(
                            active_trade.take_profit
                        ),
                        quantity=active_trade.quantity,
                        entry_fee=active_trade.entry_fee,
                    )

                    return

                raise TypeError(
                    "Unexpected pending-order result"
                )

            # ---------------------------------------------
            # 3. Ask strategy for a decision
            # ---------------------------------------------

            decision_result = strategy_callback(
                current_candle,
                visible_history,
                market_snapshot,
            )

            if not isinstance(
                decision_result,
                dict,
            ):
                raise TypeError(
                    "strategy_callback must return "
                    "a dictionary"
                )

            decision = decision_result.get(
                "decision"
            )

            score = decision_result.get(
                "score"
            )

            journal.record_signal(
                timestamp=current_time,
                decision=str(decision),
                score=score,
                metadata=dict(decision_result),
            )

            # ---------------------------------------------
            # 4. IGNORE
            # ---------------------------------------------

            if decision == "IGNORE":

                journal.record_ignored(
                    timestamp=current_time,
                    score=score,
                    metadata=dict(decision_result),
                )

                return

            if decision not in {
                "LONG",
                "SHORT",
            }:
                raise ValueError(
                    "strategy decision must be "
                    "LONG, SHORT or IGNORE"
                )

            # ---------------------------------------------
            # 5. Build trade setup
            # ---------------------------------------------

            setup = trade_setup_callback(
                decision,
                current_candle,
                visible_history,
                market_snapshot,
                current_equity,
            )

            if not isinstance(
                setup,
                TradeSetup,
            ):
                raise TypeError(
                    "trade_setup_callback must "
                    "return TradeSetup"
                )

            if setup.side != decision:
                raise ValueError(
                    "TradeSetup side must match "
                    "strategy decision"
                )

            # ---------------------------------------------
            # 6. Submit to execution simulator
            # ---------------------------------------------

            execution_result = simulator.open_trade(
                side=setup.side,
                entry_price=setup.entry_price,
                stop_loss=setup.stop_loss,
                take_profit=setup.take_profit,
                quantity=setup.quantity,
            )

            # ---------------------------------------------
            # 7. Pending
            # ---------------------------------------------

            if isinstance(
                execution_result,
                PendingOrder,
            ):
                pending_order = execution_result

                journal.record_pending(
                    timestamp=current_time,
                    side=pending_order.side,
                    requested_entry=(
                        pending_order.requested_entry
                    ),
                    stop_loss=pending_order.stop_loss,
                    take_profit=(
                        pending_order.take_profit
                    ),
                    quantity=pending_order.quantity,
                    metadata={
                        "score": score,
                        "bars_remaining": (
                            pending_order.bars_remaining
                        ),
                        "equity_at_signal": (
                            current_equity
                        ),
                    },
                )

                return

            # ---------------------------------------------
            # 8. Rejected / not filled
            # ---------------------------------------------

            if isinstance(
                execution_result,
                RejectedOrder,
            ):
                journal.record_rejected(
                    timestamp=current_time,
                    side=execution_result.side,
                    requested_entry=(
                        execution_result.requested_entry
                    ),
                    reason=execution_result.reason,
                    metadata={
                        "score": score,
                        "equity_at_signal": (
                            current_equity
                        ),
                    },
                )

                return

            # ---------------------------------------------
            # 9. Opened immediately
            # ---------------------------------------------

            if isinstance(
                execution_result,
                SimulatedTrade,
            ):
                active_trade = execution_result

                journal.record_opened(
                    timestamp=current_time,
                    side=active_trade.side,
                    requested_entry=(
                        active_trade.requested_entry
                    ),
                    entry_price=active_trade.entry_price,
                    stop_loss=active_trade.stop_loss,
                    take_profit=active_trade.take_profit,
                    quantity=active_trade.quantity,
                    entry_fee=active_trade.entry_fee,
                    metadata={
                        "score": score,
                        "equity_at_signal": (
                            current_equity
                        ),
                    },
                )

                return

            raise TypeError(
                "Unexpected execution result"
            )

        replay_engine.run(on_replay_step)

        performance = calculate_performance(
            journal=journal,
            initial_equity=initial_equity,
        )

        return BacktestResult(
            journal=journal,
            performance=performance,
        )