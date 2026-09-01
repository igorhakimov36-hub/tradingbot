from dataclasses import dataclass
from typing import Any, Callable, Literal

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
from data.market_data_provider import (
    BarSeriesProvider,
    MarketDataProvider,
    PointEventProvider,
    ReplayContext,
)
from strategy.trade_setup import TradeSetup


@dataclass(frozen=True)
class BacktestResult:
    journal: TradeJournal
    performance: PerformanceReport


@dataclass(frozen=True)
class ProviderSpec:
    """
    Describes how to build a MarketDataProvider for one named market
    data stream, without committing to windowed/instantiated state
    up front. BacktestRunner turns this into a real, window-scoped,
    freshly-synced Provider inside each run() / run_strategy() call -
    exactly like a fresh TimeframeManager used to be built per run.

    kind="point_event": a value known at an instant (Funding, Open
        Interest, ...). `records` is the raw historical series.

    kind="bar_series": a value per closed time bucket (a secondary
        timeframe, or a future per-candle Delta/Footprint/CVD series).
        `records` is the native candle series; `timeframe` is required.
    """

    kind: Literal["point_event", "bar_series"]
    records: list[dict[str, Any]]
    timeframe: str | None = None


class BacktestRunner:
    """
    Coordinates the point-in-time-safe backtesting pipeline.

        Window Manager
            -> Replay Engine
            -> Market Data Providers (generic - any symbol, any
               datatype, any timeframe; adding one never requires
               touching this class or the Strategy Engine)
            -> Strategy               [run_strategy() only]
            -> Trade Setup            [run_strategy() only]
            -> Execution Simulator    [run_strategy() only]
            -> Trade Journal          [run_strategy() only]
            -> Performance Report     [run_strategy() only]

    `run()` and `run_strategy()` share the exact same market_snapshot
    assembly - there used to be two separate code paths (one hardcoded
    to Open Interest/Funding, one generic); now there's one.

    Current limitation (deliberate, not yet lifted):
    Only one symbol is actively traded per BacktestRunner instance,
    and only one active trade/order at a time. Other symbols CAN be
    attached as read-only context via provider_specs (e.g. for a
    future SMT/Correlation module) without being tradeable themselves.
    A true multi-symbol replay clock (independent trading per symbol
    in one run) is a bigger change, deliberately not made here - see
    the architecture note delivered alongside this change.
    """

    def __init__(
        self,
        window_manager: WindowManager,
        candles: list[dict[str, Any]],
        symbol: str = "BTCUSDT",
        provider_specs: dict[str, dict[str, ProviderSpec]] | None = None,
        timestamp_key: str = "timestamp",
    ):
        self.window_manager = window_manager
        self.candles = candles
        self.symbol = symbol
        self.provider_specs = provider_specs or {}
        self.timestamp_key = timestamp_key

    # =====================================================
    # SHARED HELPERS
    # =====================================================

    def _get_records_for_window(
        self,
        records: list[dict[str, Any]],
        window_name: str,
    ) -> list[dict[str, Any]]:
        return self.window_manager.get_records(
            records=records,
            window_name=window_name,
        )

    def get_window_candles(
        self,
        window_name: str,
    ) -> list[dict[str, Any]]:
        """
        Return candles belonging only to the requested
        TRAIN / VALIDATION / HELD_OUT window.
        """

        return self._get_records_for_window(
            records=self.candles,
            window_name=window_name,
        )

    def _build_providers(
        self,
        window_name: str,
    ) -> dict[str, dict[str, MarketDataProvider]]:
        """
        Build fresh, window-scoped providers from provider_specs.

        A new set per run() / run_strategy() call is required - state
        must never leak between TRAIN/VALIDATION/HELD_OUT runs.
        """

        providers: dict[str, dict[str, MarketDataProvider]] = {}

        for symbol, specs_by_name in self.provider_specs.items():

            providers[symbol] = {}

            for name, spec in specs_by_name.items():

                windowed_records = self._get_records_for_window(
                    records=spec.records,
                    window_name=window_name,
                )

                if spec.kind == "point_event":
                    providers[symbol][name] = PointEventProvider(
                        name=name,
                        records=windowed_records,
                        timestamp_key=self.timestamp_key,
                    )

                elif spec.kind == "bar_series":
                    if spec.timeframe is None:
                        raise ValueError(
                            f"bar_series provider '{name}' requires "
                            f"a timeframe"
                        )

                    providers[symbol][name] = BarSeriesProvider(
                        name=name,
                        timeframe=spec.timeframe,
                        native_series=windowed_records,
                        timestamp_key=self.timestamp_key,
                    )

                else:
                    raise ValueError(
                        f"Unknown provider kind: {spec.kind}"
                    )

        return providers

    def _build_market_snapshot(
        self,
        context: ReplayContext,
        providers: dict[str, dict[str, MarketDataProvider]],
    ) -> dict[str, Any]:
        """
        Assemble market_snapshot generically:

            market_snapshot[symbol][data_type]

        The primary (traded) symbol's 1m history is attached directly
        (it already IS the point-in-time-safe replay clock, no
        provider/sync needed for it). Every other registered stream -
        any symbol, any datatype, any timeframe - is synced against
        the same clock and attached the same way. Strategy Engine
        never learns whether a given entry came from Binance, Bybit,
        a CSV replay, or a live feed.
        """

        snapshot: dict[str, Any] = {
            self.symbol: {"1m": context.visible_history_1m},
        }

        for symbol, providers_by_name in providers.items():

            symbol_snapshot = snapshot.setdefault(symbol, {})

            for name, provider in providers_by_name.items():
                provider.sync(context)
                symbol_snapshot[name] = provider.snapshot()

        return snapshot

    # =====================================================
    # ORIGINAL POINT-IN-TIME RUNNER
    # =====================================================

    def run(
        self,
        window_name: str,
        callback: Callable[
            [
                dict[str, Any],
                dict[str, Any],
            ],
            None,
        ],
    ) -> None:
        """
        Run one isolated backtest window.

        callback receives:

        1. current candle
        2. market_snapshot (point-in-time-safe; market_snapshot[symbol]
           holds "1m" plus every registered provider's data)
        """

        window_candles = self.get_window_candles(
            window_name=window_name
        )

        providers = self._build_providers(
            window_name=window_name,
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

            context = ReplayContext(
                current_time=current_time,
                current_candle=current_candle,
                visible_history_1m=visible_history,
            )

            market_snapshot = self._build_market_snapshot(
                context=context,
                providers=providers,
            )

            callback(
                current_candle,
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
                dict[str, Any],
            ],
            dict[str, Any],
        ],
        trade_setup_callback: Callable[
            [
                str,
                dict[str, Any],
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

        strategy_callback receives:

            1. current candle (1m, primary symbol)
            2. market_snapshot (market_snapshot[symbol]["1m"/"15m"/
               "funding"/"open_interest"/...])

        and returns:

            {
                "decision": "LONG" | "SHORT" | "IGNORE",
                "score": ...,
                ...
            }

        trade_setup_callback is called only for LONG/SHORT.

        It receives:

            1. decision
            2. current candle
            3. market_snapshot
            4. current equity

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

        providers = self._build_providers(
            window_name=window_name,
        )

        active_trade: SimulatedTrade | None = None
        pending_order: PendingOrder | None = None

        # Which named setup (Strategy Engine V2) produced the
        # currently pending/open trade, if any - tracked alongside
        # active_trade/pending_order exactly the same way, so a CLOSED
        # event many bars later can still be attributed to the setup
        # that originated it. Stays None for the old score-based
        # engine, which never sets "setup_name" in its decision dict.
        active_setup_name: str | None = None

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
            visible_history_1m: list[dict[str, Any]],
        ) -> None:

            nonlocal active_trade
            nonlocal pending_order
            nonlocal current_equity
            nonlocal active_setup_name

            current_time = current_candle[
                self.timestamp_key
            ]

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
                        symbol=active_trade.symbol,
                        setup_name=active_setup_name,
                    )

                    # Dynamic equity:
                    # net_pnl already includes fees.
                    current_equity += (
                        active_trade.net_pnl
                    )

                    active_trade = None
                    active_setup_name = None

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
                        symbol=execution_result.symbol,
                        setup_name=active_setup_name,
                    )

                    pending_order = None
                    active_setup_name = None
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
                        symbol=active_trade.symbol,
                        setup_name=active_setup_name,
                    )

                    return

                raise TypeError(
                    "Unexpected pending-order result"
                )

            # ---------------------------------------------
            # 3. Ask strategy for a decision
            # ---------------------------------------------

            # Only computed here - steps 1/2 above return before ever
            # using it, so there is no point paying for it on every
            # single candle while a trade/order is already active.
            context = ReplayContext(
                current_time=current_time,
                current_candle=current_candle,
                visible_history_1m=visible_history_1m,
            )

            market_snapshot = self._build_market_snapshot(
                context=context,
                providers=providers,
            )

            decision_result = strategy_callback(
                current_candle,
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

            # Strategy Engine V2 (Phase 2.1): which named institutional
            # setup produced this decision, if any. Absent/None for the
            # old score-based engine's decision dicts.
            setup_name = decision_result.get(
                "setup_name"
            )

            journal.record_signal(
                timestamp=current_time,
                decision=str(decision),
                score=score,
                metadata=dict(decision_result),
                symbol=self.symbol,
                setup_name=setup_name,
            )

            # ---------------------------------------------
            # 4. IGNORE
            # ---------------------------------------------

            if decision == "IGNORE":

                journal.record_ignored(
                    timestamp=current_time,
                    score=score,
                    metadata=dict(decision_result),
                    symbol=self.symbol,
                    setup_name=setup_name,
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

            active_setup_name = setup_name

            # ---------------------------------------------
            # 5. Build trade setup
            # ---------------------------------------------

            setup = trade_setup_callback(
                decision,
                current_candle,
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
                symbol=self.symbol,
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
                    symbol=pending_order.symbol,
                    setup_name=active_setup_name,
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
                    symbol=execution_result.symbol,
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
                    symbol=active_trade.symbol,
                    setup_name=active_setup_name,
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
