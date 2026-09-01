import pytest

from backtesting.execution_simulator import ExecutionConfig

from strategy.trade_setup import (
    create_trade_setup,
    create_risk_based_trade_setup,
)

from datetime import datetime, timezone

from backtesting.backtest_runner import BacktestRunner, ProviderSpec
from backtesting.window_manager import (
    TimeWindow,
    WindowManager,
)


def utc_time(month: int, day: int, hour: int = 12) -> datetime:
    return datetime(
        2025,
        month,
        day,
        hour,
        0,
        tzinfo=timezone.utc,
    )


def create_window_manager():
    return WindowManager(
        train=TimeWindow(
            name="TRAIN",
            start=utc_time(1, 1, 0),
            end=utc_time(2, 1, 0),
        ),
        validation=TimeWindow(
            name="VALIDATION",
            start=utc_time(2, 1, 0),
            end=utc_time(3, 1, 0),
        ),
        held_out=TimeWindow(
            name="HELD_OUT",
            start=utc_time(3, 1, 0),
            end=utc_time(4, 1, 0),
        ),
    )


def create_candles():
    return [
        {
            "timestamp": utc_time(1, 10),
            "open": 100.0,
            "high": 110.0,
            "low": 90.0,
            "close": 101.0,
            "volume": 1000.0,
        },
        {
            "timestamp": utc_time(2, 10),
            "open": 101.0,
            "high": 111.0,
            "low": 95.0,
            "close": 102.0,
            "volume": 1100.0,
        },
        {
            "timestamp": utc_time(2, 11),
            "open": 102.0,
            "high": 112.0,
            "low": 96.0,
            "close": 103.0,
            "volume": 1200.0,
        },
        {
            "timestamp": utc_time(3, 10),
            "open": 103.0,
            "high": 113.0,
            "low": 97.0,
            "close": 104.0,
            "volume": 1300.0,
        },
    ]


def test_runner_uses_only_requested_window():
    runner = BacktestRunner(
        window_manager=create_window_manager(),
        candles=create_candles(),
    )

    processed = []

    def callback(current_candle, market_snapshot):
        processed.append(current_candle)

    runner.run(
        window_name="VALIDATION",
        callback=callback,
    )

    assert len(processed) == 2
    assert processed[0]["close"] == 102.0
    assert processed[1]["close"] == 103.0


def test_visible_history_contains_no_future_candles():
    runner = BacktestRunner(
        window_manager=create_window_manager(),
        candles=create_candles(),
    )

    future_detected = False

    def callback(current_candle, market_snapshot):
        nonlocal future_detected

        current_time = current_candle["timestamp"]

        for candle in market_snapshot["BTCUSDT"]["1m"]:
            if candle["timestamp"] > current_time:
                future_detected = True

    runner.run(
        window_name="VALIDATION",
        callback=callback,
    )

    assert future_detected is False


def test_visible_history_grows_inside_window():
    runner = BacktestRunner(
        window_manager=create_window_manager(),
        candles=create_candles(),
    )

    history_sizes = []

    def callback(current_candle, market_snapshot):
        history_sizes.append(len(market_snapshot["BTCUSDT"]["1m"]))

    runner.run(
        window_name="VALIDATION",
        callback=callback,
    )

    assert history_sizes == [1, 2]


def test_runner_aligns_latest_available_oi():
    oi_records = [
        {
            "timestamp": utc_time(2, 9),
            "open_interest": 1000.0,
        },
        {
            "timestamp": utc_time(2, 10),
            "open_interest": 1100.0,
        },
        {
            "timestamp": utc_time(2, 12),
            "open_interest": 9999.0,
        },
    ]

    runner = BacktestRunner(
        window_manager=create_window_manager(),
        candles=create_candles(),
        provider_specs={
            "BTCUSDT": {
                "open_interest": ProviderSpec(
                    kind="point_event",
                    records=oi_records,
                ),
            },
        },
    )

    snapshots = []

    def callback(current_candle, market_snapshot):
        snapshots.append(market_snapshot["BTCUSDT"]["open_interest"])

    runner.run(
        window_name="VALIDATION",
        callback=callback,
    )

    assert snapshots[0]["current"]["open_interest"] == 1100.0
    assert snapshots[1]["current"]["open_interest"] == 1100.0


def test_runner_never_uses_future_oi():
    oi_records = [
        {
            "timestamp": utc_time(2, 12),
            "open_interest": 9999.0,
        }
    ]

    runner = BacktestRunner(
        window_manager=create_window_manager(),
        candles=create_candles(),
        provider_specs={
            "BTCUSDT": {
                "open_interest": ProviderSpec(
                    kind="point_event",
                    records=oi_records,
                ),
            },
        },
    )

    snapshots = []

    def callback(current_candle, market_snapshot):
        snapshots.append(market_snapshot["BTCUSDT"]["open_interest"])

    runner.run(
        window_name="VALIDATION",
        callback=callback,
    )

    assert snapshots[0]["current"] is None
    assert snapshots[1]["current"] is None


def test_runner_aligns_funding_without_lookahead():
    funding_records = [
        {
            "timestamp": utc_time(2, 1, 8),
            "funding_rate": 0.0001,
        },
        {
            "timestamp": utc_time(2, 20),
            "funding_rate": 0.9999,
        },
    ]

    runner = BacktestRunner(
        window_manager=create_window_manager(),
        candles=create_candles(),
        provider_specs={
            "BTCUSDT": {
                "funding": ProviderSpec(
                    kind="point_event",
                    records=funding_records,
                ),
            },
        },
    )

    snapshots = []

    def callback(current_candle, market_snapshot):
        snapshots.append(market_snapshot["BTCUSDT"]["funding"])

    runner.run(
        window_name="VALIDATION",
        callback=callback,
    )

    assert snapshots[0]["current"]["funding_rate"] == 0.0001
    assert snapshots[1]["current"]["funding_rate"] == 0.0001


def test_runner_snapshot_1m_ends_with_current_candle():
    runner = BacktestRunner(
        window_manager=create_window_manager(),
        candles=create_candles(),
    )

    checked = []

    def callback(current_candle, market_snapshot):
        checked.append(
            market_snapshot["BTCUSDT"]["1m"][-1]["timestamp"]
            == current_candle["timestamp"]
        )

    runner.run(
        window_name="VALIDATION",
        callback=callback,
    )

    assert checked == [True, True]


def test_runner_can_run_held_out_separately():
    runner = BacktestRunner(
        window_manager=create_window_manager(),
        candles=create_candles(),
    )

    processed = []

    def callback(current_candle, market_snapshot):
        processed.append(current_candle["close"])

    runner.run(
        window_name="HELD_OUT",
        callback=callback,
    )

    assert processed == [104.0]


# =========================================================
# FULL STRATEGY INTEGRATION
# =========================================================


def test_run_strategy_records_ignore():
    runner = BacktestRunner(
        window_manager=create_window_manager(),
        candles=create_candles(),
    )

    def strategy_callback(current_candle, market_snapshot):
        return {
            "decision": "IGNORE",
            "score": 50.0,
        }

    def trade_setup_callback(decision, current_candle, market_snapshot, current_equity):
        raise AssertionError("trade_setup_callback must not run for IGNORE")

    result = runner.run_strategy(
        window_name="VALIDATION",
        strategy_callback=strategy_callback,
        trade_setup_callback=trade_setup_callback,
    )

    assert len(result.journal.by_event("SIGNAL")) == 2

    assert len(result.journal.ignored_signals()) == 2

    assert len(result.journal.closed_trades()) == 0

    assert result.performance.total_trades == 0
    assert result.performance.total_net_pnl == 0.0


def test_run_strategy_opens_long_trade():
    runner = BacktestRunner(
        window_manager=create_window_manager(),
        candles=create_candles(),
    )

    calls = 0

    def strategy_callback(current_candle, market_snapshot):
        nonlocal calls
        calls += 1

        if calls == 1:
            return {
                "decision": "LONG",
                "score": 90.0,
            }

        return {
            "decision": "IGNORE",
            "score": 40.0,
        }

    def trade_setup_callback(decision, current_candle, market_snapshot, current_equity):
        return create_trade_setup(
            side="LONG",
            entry_price=102.0,
            stop_loss=100.0,
            take_profit=120.0,
            quantity=1.0,
        )

    result = runner.run_strategy(
        window_name="VALIDATION",
        strategy_callback=strategy_callback,
        trade_setup_callback=trade_setup_callback,
    )

    opened = result.journal.by_event("OPENED")

    assert len(opened) == 1
    assert opened[0].side == "LONG"
    assert opened[0].stop_loss == 100.0
    assert opened[0].take_profit == 120.0
    assert opened[0].symbol == "BTCUSDT"


def test_run_strategy_long_stop_loss_flows_to_performance():
    runner = BacktestRunner(
        window_manager=create_window_manager(),
        candles=create_candles(),
    )

    first_call = True

    def strategy_callback(current_candle, market_snapshot):
        nonlocal first_call

        if first_call:
            first_call = False

            return {
                "decision": "LONG",
                "score": 90.0,
            }

        return {
            "decision": "IGNORE",
            "score": 40.0,
        }

    def trade_setup_callback(decision, current_candle, market_snapshot, current_equity):
        return create_trade_setup(
            side="LONG",
            entry_price=102.0,
            stop_loss=100.0,
            take_profit=120.0,
            quantity=1.0,
        )

    result = runner.run_strategy(
        window_name="VALIDATION",
        strategy_callback=strategy_callback,
        trade_setup_callback=trade_setup_callback,
    )

    closed = result.journal.closed_trades()

    assert len(closed) == 1
    assert closed[0].exit_reason == "STOP_LOSS"

    assert result.performance.total_trades == 1
    assert result.performance.losing_trades == 1
    assert result.performance.total_net_pnl < 0


def test_run_strategy_long_take_profit_flows_to_performance():
    candles = [
        {
            "timestamp": utc_time(2, 10),
            "open": 100.0,
            "high": 101.0,
            "low": 99.0,
            "close": 100.0,
            "volume": 1000.0,
        },
        {
            "timestamp": utc_time(2, 11),
            "open": 100.0,
            "high": 111.0,
            "low": 99.0,
            "close": 110.0,
            "volume": 1000.0,
        },
    ]

    runner = BacktestRunner(
        window_manager=create_window_manager(),
        candles=candles,
    )

    first_call = True

    def strategy_callback(current_candle, market_snapshot):
        nonlocal first_call

        if first_call:
            first_call = False

            return {
                "decision": "LONG",
                "score": 90.0,
            }

        return {
            "decision": "IGNORE",
            "score": 40.0,
        }

    def trade_setup_callback(decision, current_candle, market_snapshot, current_equity):

        return create_trade_setup(
            side="LONG",
            entry_price=100.0,
            stop_loss=95.0,
            take_profit=110.0,
            quantity=1.0,
        )

    result = runner.run_strategy(
        window_name="VALIDATION",
        strategy_callback=strategy_callback,
        trade_setup_callback=trade_setup_callback,
    )

    closed = result.journal.closed_trades()

    assert len(closed) == 1
    assert closed[0].exit_reason == "TAKE_PROFIT"

    assert result.performance.total_trades == 1
    assert result.performance.winning_trades == 1
    assert result.performance.total_net_pnl > 0


def test_run_strategy_rejects_setup_side_mismatch():
    runner = BacktestRunner(
        window_manager=create_window_manager(),
        candles=create_candles(),
    )

    def strategy_callback(current_candle, market_snapshot):
        return {
            "decision": "LONG",
            "score": 90.0,
        }

    def trade_setup_callback(decision, current_candle, market_snapshot, current_equity):
        return create_trade_setup(
            side="SHORT",
            entry_price=100.0,
            stop_loss=105.0,
            take_profit=90.0,
            quantity=1.0,
        )

    with pytest.raises(ValueError):
        runner.run_strategy(
            window_name="VALIDATION",
            strategy_callback=strategy_callback,
            trade_setup_callback=trade_setup_callback,
        )


def test_run_strategy_rejects_invalid_decision():
    runner = BacktestRunner(
        window_manager=create_window_manager(),
        candles=create_candles(),
    )

    def strategy_callback(current_candle, market_snapshot):
        return {
            "decision": "BUY_NOW",
            "score": 100.0,
        }

    def trade_setup_callback(decision, current_candle, market_snapshot, current_equity):
        raise AssertionError("trade setup must not be created")

    with pytest.raises(ValueError):
        runner.run_strategy(
            window_name="VALIDATION",
            strategy_callback=strategy_callback,
            trade_setup_callback=trade_setup_callback,
        )


def test_run_strategy_requires_strategy_dictionary():
    runner = BacktestRunner(
        window_manager=create_window_manager(),
        candles=create_candles(),
    )

    def strategy_callback(current_candle, market_snapshot):
        return "LONG"

    def trade_setup_callback(decision, current_candle, market_snapshot, current_equity):
        raise AssertionError("trade setup must not be created")

    with pytest.raises(TypeError):
        runner.run_strategy(
            window_name="VALIDATION",
            strategy_callback=strategy_callback,
            trade_setup_callback=trade_setup_callback,
        )


def test_run_strategy_preserves_point_in_time_snapshot():
    oi_records = [
        {
            "timestamp": utc_time(2, 9),
            "open_interest": 1000.0,
        },
        {
            "timestamp": utc_time(2, 12),
            "open_interest": 9999.0,
        },
    ]

    runner = BacktestRunner(
        window_manager=create_window_manager(),
        candles=create_candles(),
        provider_specs={
            "BTCUSDT": {
                "open_interest": ProviderSpec(
                    kind="point_event",
                    records=oi_records,
                ),
            },
        },
    )

    observed_oi = []

    def strategy_callback(current_candle, market_snapshot):
        oi = market_snapshot["BTCUSDT"]["open_interest"]["current"]

        observed_oi.append(None if oi is None else oi["open_interest"])

        return {
            "decision": "IGNORE",
            "score": 0.0,
        }

    def trade_setup_callback(decision, current_candle, market_snapshot, current_equity):
        raise AssertionError("trade setup must not run")

    runner.run_strategy(
        window_name="VALIDATION",
        strategy_callback=strategy_callback,
        trade_setup_callback=trade_setup_callback,
    )

    assert observed_oi == [
        1000.0,
        1000.0,
    ]


def test_run_strategy_uses_current_equity_for_risk_based_position_size():
    runner = BacktestRunner(
        window_manager=create_window_manager(),
        candles=create_candles(),
    )

    observed_equity = []
    observed_quantity = []

    def strategy_callback(current_candle, market_snapshot):
        return {
            "decision": "LONG",
            "score": 90.0,
        }

    def trade_setup_callback(decision, current_candle, market_snapshot, current_equity):
        observed_equity.append(current_equity)

        setup = create_risk_based_trade_setup(
            side=decision,
            entry_price=100.0,
            stop_loss=95.0,
            take_profit=110.0,
            equity=current_equity,
            risk_percent=1.0,
        )

        observed_quantity.append(setup.quantity)

        return setup

    runner.run_strategy(
        window_name="VALIDATION",
        strategy_callback=strategy_callback,
        trade_setup_callback=trade_setup_callback,
        initial_equity=300.0,
    )

    assert observed_equity[0] == pytest.approx(300.0)

    # 1% of $300 = $3 risk.
    # Entry-to-stop distance = $5.
    # Quantity = $3 / $5 = 0.6.
    assert observed_quantity[0] == pytest.approx(0.6)


def test_run_strategy_records_symbol_on_signal_events():
    runner = BacktestRunner(
        window_manager=create_window_manager(),
        candles=create_candles(),
        symbol="ETHUSDT",
    )

    def strategy_callback(current_candle, market_snapshot):
        assert "ETHUSDT" in market_snapshot
        return {"decision": "IGNORE", "score": 10.0}

    def trade_setup_callback(decision, current_candle, market_snapshot, current_equity):
        raise AssertionError("trade setup must not run")

    result = runner.run_strategy(
        window_name="VALIDATION",
        strategy_callback=strategy_callback,
        trade_setup_callback=trade_setup_callback,
    )

    signals = result.journal.by_event("SIGNAL")
    assert all(entry.symbol == "ETHUSDT" for entry in signals)


def test_context_symbol_attached_as_read_only_provider():
    # A second symbol's OWN higher-timeframe candles, attached purely
    # as context (e.g. for a future SMT/Correlation module) - never
    # traded, never touching StrategyEngine's tradeable-symbol logic.
    eth_candles_15m = [
        {
            "timestamp": utc_time(2, 1, 0),
            "open": 2000.0,
            "high": 2010.0,
            "low": 1990.0,
            "close": 2005.0,
            "volume": 500.0,
        },
    ]

    runner = BacktestRunner(
        window_manager=create_window_manager(),
        candles=create_candles(),
        symbol="BTCUSDT",
        provider_specs={
            "ETHUSDT": {
                "15m": ProviderSpec(
                    kind="bar_series",
                    records=eth_candles_15m,
                    timeframe="15m",
                ),
            },
        },
    )

    seen = []

    def callback(current_candle, market_snapshot):
        seen.append(market_snapshot.get("ETHUSDT"))

    runner.run(
        window_name="VALIDATION",
        callback=callback,
    )

    assert seen[0] is not None
