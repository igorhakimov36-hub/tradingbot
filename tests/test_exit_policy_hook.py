from datetime import datetime, timezone

from strategy.trade_setup import create_trade_setup

from backtesting.backtest_runner import BacktestRunner
from backtesting.window_manager import TimeWindow, WindowManager
from tests.test_backtest_runner import create_candles, create_window_manager


def utc_time(month: int, day: int, hour: int = 12) -> datetime:
    return datetime(2025, month, day, hour, 0, tzinfo=timezone.utc)


class _RecordingExitPolicy:
    """Two-phase stub: evaluate() only ever stores a PENDING value;
    apply_pending() is the only place a trade is ever mutated."""

    def __init__(self, new_stop_loss=None, new_take_profit=None):
        self.eval_calls = []
        self.apply_calls = []
        self._new_stop_loss = new_stop_loss
        self._new_take_profit = new_take_profit
        self._pending_stop = None
        self._pending_tp = None

    def evaluate(self, trade, current_candle, market_snapshot):
        self.eval_calls.append((current_candle["timestamp"], trade.stop_loss, trade.take_profit))
        if self._new_stop_loss is not None:
            self._pending_stop = self._new_stop_loss
        if self._new_take_profit is not None:
            self._pending_tp = self._new_take_profit

    def apply_pending(self, trade):
        if self._pending_stop is not None:
            trade.stop_loss = self._pending_stop
            self._pending_stop = None
        if self._pending_tp is not None:
            trade.take_profit = self._pending_tp
            self._pending_tp = None
        # Recorded AFTER applying - this is the level actually active
        # for this bar's upcoming stop/target check.
        self.apply_calls.append((trade.stop_loss, trade.take_profit))


class _RaisingExitPolicy:
    def evaluate(self, trade, current_candle, market_snapshot):
        raise AssertionError("exit_policy.evaluate must not be called with no open trade")

    def apply_pending(self, trade):
        raise AssertionError("exit_policy.apply_pending must not be called with no open trade")


def _always_ignore(current_candle, market_snapshot):
    return {"decision": "IGNORE", "score": 0.0}


def _open_long_once():
    first_call = True

    def strategy_callback(current_candle, market_snapshot):
        nonlocal first_call
        if first_call:
            first_call = False
            return {"decision": "LONG", "score": 90.0}
        return {"decision": "IGNORE", "score": 0.0}

    return strategy_callback


def _fixed_trade_setup_callback(decision, current_candle, market_snapshot, current_equity):
    return create_trade_setup(
        side="LONG", entry_price=102.0, stop_loss=100.0, take_profit=120.0, quantity=1.0,
    )


# =========================================================
# Basic wiring
# =========================================================


def test_exit_policy_defaults_to_none_and_is_never_invoked_implicitly():
    runner = BacktestRunner(window_manager=create_window_manager(), candles=create_candles())

    result = runner.run_strategy(
        window_name="VALIDATION",
        strategy_callback=_open_long_once(),
        trade_setup_callback=_fixed_trade_setup_callback,
    )

    assert result.performance.total_trades == 1


def test_exit_policy_not_called_when_no_trade_is_open():
    runner = BacktestRunner(window_manager=create_window_manager(), candles=create_candles())

    result = runner.run_strategy(
        window_name="VALIDATION",
        strategy_callback=_always_ignore,
        trade_setup_callback=_fixed_trade_setup_callback,
        exit_policy=_RaisingExitPolicy(),
    )

    assert result.performance.total_trades == 0


def test_apply_pending_called_before_evaluate_on_a_surviving_bar():
    # Uses the 3-candle causal-correctness fixture (defined below) since
    # create_candles()'s one post-entry bar hits the original stop
    # outright (low=96 < stop=100) and never survives to be evaluated -
    # this test needs a bar the trade actually survives.
    window_manager, candles = _causal_correctness_window()
    runner = BacktestRunner(window_manager=window_manager, candles=candles)
    policy = _RecordingExitPolicy()

    runner.run_strategy(
        window_name="VALIDATION",
        strategy_callback=_open_long_once(),
        trade_setup_callback=_fixed_trade_setup_callback,
        exit_policy=policy,
    )

    # This policy never proposes an adjustment, so the original stop
    # (100.0) is never approached by either bar2 (low=100.5) or bar3
    # (low=100.7) - the trade survives both, and each surviving bar
    # gets exactly one apply_pending() (first, a no-op) followed by one
    # evaluate() (second) call, in that order.
    assert len(policy.apply_calls) == 2
    assert len(policy.eval_calls) == 2
    assert policy.apply_calls[0][0] == 100.0  # unchanged - no pending existed yet
    assert policy.eval_calls[0][1] == 100.0   # evaluate saw the still-original stop


def test_exit_policy_none_backtest_matches_no_exit_policy_argument():
    runner_a = BacktestRunner(window_manager=create_window_manager(), candles=create_candles())
    runner_b = BacktestRunner(window_manager=create_window_manager(), candles=create_candles())

    result_a = runner_a.run_strategy(
        window_name="VALIDATION",
        strategy_callback=_open_long_once(),
        trade_setup_callback=_fixed_trade_setup_callback,
    )
    result_b = runner_b.run_strategy(
        window_name="VALIDATION",
        strategy_callback=_open_long_once(),
        trade_setup_callback=_fixed_trade_setup_callback,
        exit_policy=None,
    )

    assert result_a.performance.total_net_pnl == result_b.performance.total_net_pnl
    assert [c.exit_reason for c in result_a.journal.closed_trades()] == [c.exit_reason for c in result_b.journal.closed_trades()]


# =========================================================
# Causal correctness: next-bar activation
# =========================================================
#
# Entry: LONG @ 102.0, original stop=100.0, tp=120.0 (fixed, via
# _fixed_trade_setup_callback - unaffected by candle prices).
#
# Bar 1 (entry bar): irrelevant OHLC, the trade opens processing it and
# step 1 (existing-trade checks) never runs on the same bar it opened.
#
# Bar 2 (first bar the trade is open): low=100.5 - ABOVE the original
# stop (100.0, survives) but BELOW what a stop of 101.0 decided FROM
# THIS SAME BAR would immediately hit if (incorrectly) applied
# same-bar. The policy decides a pending stop of 101.0 from this bar's
# close.
#
# Bar 3: apply_pending() applies the 101.0 decided at the end of bar 2
# BEFORE this bar's own check. low=100.7 - still above the original
# 100.0, but at/below the newly-applied 101.0 - triggers STOP_LOSS at
# the trailed level, one full bar after the decision that produced it.


def _causal_correctness_window():
    window_manager = WindowManager(
        train=TimeWindow(name="TRAIN", start=utc_time(1, 1, 0), end=utc_time(1, 2, 0)),
        validation=TimeWindow(name="VALIDATION", start=utc_time(1, 2, 0), end=utc_time(1, 3, 0)),
        held_out=TimeWindow(name="HELD_OUT", start=utc_time(1, 3, 0), end=utc_time(1, 4, 0)),
    )
    candles = [
        {"timestamp": utc_time(1, 2, 1), "open": 102.0, "high": 103.0, "low": 101.0, "close": 102.0, "volume": 1.0},
        {"timestamp": utc_time(1, 2, 2), "open": 102.0, "high": 105.0, "low": 100.5, "close": 103.0, "volume": 1.0},
        {"timestamp": utc_time(1, 2, 3), "open": 102.5, "high": 103.0, "low": 100.7, "close": 101.5, "volume": 1.0},
    ]
    return window_manager, candles


def test_no_same_bar_retroactive_stop_adjustment():
    window_manager, candles = _causal_correctness_window()
    runner = BacktestRunner(window_manager=window_manager, candles=candles)
    policy = _RecordingExitPolicy(new_stop_loss=101.0)

    result = runner.run_strategy(
        window_name="VALIDATION",
        strategy_callback=_open_long_once(),
        trade_setup_callback=_fixed_trade_setup_callback,
        exit_policy=policy,
    )

    closed = result.journal.closed_trades()
    assert len(closed) == 1

    # If the adjustment had (incorrectly) applied retroactively within
    # bar 2, bar 2's own low=100.5 would have triggered STOP_LOSS right
    # there, on the SAME bar the decision was made from. It must not -
    # the trade must survive bar 2 and only stop out on bar 3, one full
    # bar after the decision, at the trailed (not original) level.
    assert closed[0].timestamp == utc_time(1, 2, 3)
    assert closed[0].exit_reason == "STOP_LOSS"
    assert closed[0].exit_price == 101.0 * (1 - 0.0002)  # LONG exit slippage


def test_pending_adjustment_is_not_applied_to_the_bar_that_decided_it():
    # Same scenario, inspected via the policy's own call log rather
    # than the journal: evaluate() must see the ORIGINAL stop (100.0)
    # on bar 2 (nothing has been applied yet when it runs), and
    # apply_pending() on bar 3 must be the call that actually moves it.
    window_manager, candles = _causal_correctness_window()
    runner = BacktestRunner(window_manager=window_manager, candles=candles)
    policy = _RecordingExitPolicy(new_stop_loss=101.0)

    runner.run_strategy(
        window_name="VALIDATION",
        strategy_callback=_open_long_once(),
        trade_setup_callback=_fixed_trade_setup_callback,
        exit_policy=policy,
    )

    # apply_pending calls: bar2 (no-op, nothing pending yet), bar3
    # (applies the 101.0 decided at the end of bar2).
    assert policy.apply_calls == [(100.0, 120.0), (101.0, 120.0)]
    # evaluate calls: only bar2 (bar3 closes the trade, so evaluate is
    # never called for it - see backtesting/exit_policy.py).
    assert policy.eval_calls == [(utc_time(1, 2, 2), 100.0, 120.0)]


def test_trade_closing_on_the_decision_candle_is_not_evaluated():
    # A trade that hits its (already-active) stop on the very bar that
    # would otherwise produce a new decision must not be evaluated at
    # all - there is no future bar left for a pending adjustment to
    # apply to.
    window_manager = WindowManager(
        train=TimeWindow(name="TRAIN", start=utc_time(1, 1, 0), end=utc_time(1, 2, 0)),
        validation=TimeWindow(name="VALIDATION", start=utc_time(1, 2, 0), end=utc_time(1, 3, 0)),
        held_out=TimeWindow(name="HELD_OUT", start=utc_time(1, 3, 0), end=utc_time(1, 4, 0)),
    )
    candles = [
        {"timestamp": utc_time(1, 2, 1), "open": 102.0, "high": 103.0, "low": 101.0, "close": 102.0, "volume": 1.0},
        {"timestamp": utc_time(1, 2, 2), "open": 102.0, "high": 103.0, "low": 99.0, "close": 99.5, "volume": 1.0},
    ]

    runner = BacktestRunner(window_manager=window_manager, candles=candles)
    policy = _RecordingExitPolicy(new_stop_loss=101.0)

    result = runner.run_strategy(
        window_name="VALIDATION",
        strategy_callback=_open_long_once(),
        trade_setup_callback=_fixed_trade_setup_callback,
        exit_policy=policy,
    )

    closed = result.journal.closed_trades()
    assert len(closed) == 1
    assert closed[0].exit_reason == "STOP_LOSS"
    assert closed[0].exit_price == 100.0 * (1 - 0.0002)  # the ORIGINAL stop, never adjusted

    assert policy.apply_calls == [(100.0, 120.0)]  # ran once, applied nothing (no prior pending)
    assert policy.eval_calls == []  # never evaluated - the trade closed on this same bar
