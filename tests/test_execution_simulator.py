import pytest

from backtesting.execution_simulator import (
    ExecutionConfig,
    ExecutionSimulator,
    PendingOrder,
    RejectedOrder,
    SimulatedTrade,
)


def create_simulator():
    return ExecutionSimulator(
        ExecutionConfig(
            fee_rate=0.001,
            slippage_rate=0.001,
            latency_bars=0,
        )
    )


# =========================================================
# CONFIG / VALIDATION
# =========================================================

def test_negative_fee_rate_is_rejected():
    with pytest.raises(ValueError):
        ExecutionConfig(
            fee_rate=-0.001,
            slippage_rate=0.0,
        )


def test_negative_slippage_is_rejected():
    with pytest.raises(ValueError):
        ExecutionConfig(
            fee_rate=0.0,
            slippage_rate=-0.001,
        )


def test_invalid_long_levels_are_rejected():
    simulator = create_simulator()

    with pytest.raises(ValueError):
        simulator.open_trade(
            side="LONG",
            entry_price=100.0,
            stop_loss=101.0,
            take_profit=110.0,
            quantity=1.0,
        )


def test_invalid_short_levels_are_rejected():
    simulator = create_simulator()

    with pytest.raises(ValueError):
        simulator.open_trade(
            side="SHORT",
            entry_price=100.0,
            stop_loss=90.0,
            take_profit=80.0,
            quantity=1.0,
        )


# =========================================================
# ENTRY
# =========================================================

def test_long_entry_slippage_is_adverse():
    simulator = create_simulator()

    trade = simulator.open_trade(
        side="LONG",
        entry_price=100.0,
        stop_loss=90.0,
        take_profit=110.0,
        quantity=1.0,
    )

    assert isinstance(trade, SimulatedTrade)
    assert trade.requested_entry == 100.0
    assert trade.entry_price == pytest.approx(100.1)
    assert trade.entry_fee == pytest.approx(0.1001)
    assert trade.is_open is True


def test_short_entry_slippage_is_adverse():
    simulator = create_simulator()

    trade = simulator.open_trade(
        side="SHORT",
        entry_price=100.0,
        stop_loss=110.0,
        take_profit=90.0,
        quantity=1.0,
    )

    assert isinstance(trade, SimulatedTrade)
    assert trade.entry_price == pytest.approx(99.9)
    assert trade.entry_fee == pytest.approx(0.0999)


# =========================================================
# LONG EXIT
# =========================================================

def test_long_take_profit_closes_trade():
    simulator = create_simulator()

    trade = simulator.open_trade(
        side="LONG",
        entry_price=100.0,
        stop_loss=90.0,
        take_profit=110.0,
        quantity=1.0,
    )

    simulator.process_candle(
        trade=trade,
        high=111.0,
        low=100.0,
    )

    assert trade.is_open is False
    assert trade.exit_reason == "TAKE_PROFIT"
    assert trade.exit_price == pytest.approx(109.89)
    assert trade.gross_pnl > 0
    assert trade.net_pnl < trade.gross_pnl


def test_long_stop_loss_closes_trade():
    simulator = create_simulator()

    trade = simulator.open_trade(
        side="LONG",
        entry_price=100.0,
        stop_loss=90.0,
        take_profit=110.0,
        quantity=1.0,
    )

    simulator.process_candle(
        trade=trade,
        high=105.0,
        low=89.0,
    )

    assert trade.is_open is False
    assert trade.exit_reason == "STOP_LOSS"
    assert trade.net_pnl < 0


# =========================================================
# SHORT EXIT
# =========================================================

def test_short_take_profit_closes_trade():
    simulator = create_simulator()

    trade = simulator.open_trade(
        side="SHORT",
        entry_price=100.0,
        stop_loss=110.0,
        take_profit=90.0,
        quantity=1.0,
    )

    simulator.process_candle(
        trade=trade,
        high=100.0,
        low=89.0,
    )

    assert trade.is_open is False
    assert trade.exit_reason == "TAKE_PROFIT"
    assert trade.exit_price == pytest.approx(90.09)
    assert trade.gross_pnl > 0
    assert trade.net_pnl < trade.gross_pnl


def test_short_stop_loss_closes_trade():
    simulator = create_simulator()

    trade = simulator.open_trade(
        side="SHORT",
        entry_price=100.0,
        stop_loss=110.0,
        take_profit=90.0,
        quantity=1.0,
    )

    simulator.process_candle(
        trade=trade,
        high=111.0,
        low=100.0,
    )

    assert trade.is_open is False
    assert trade.exit_reason == "STOP_LOSS"
    assert trade.net_pnl < 0


# =========================================================
# AMBIGUOUS CANDLE
# =========================================================

def test_long_same_candle_sl_and_tp_uses_stop_loss():
    simulator = create_simulator()

    trade = simulator.open_trade(
        side="LONG",
        entry_price=100.0,
        stop_loss=90.0,
        take_profit=110.0,
        quantity=1.0,
    )

    simulator.process_candle(
        trade=trade,
        high=111.0,
        low=89.0,
    )

    assert trade.is_open is False
    assert trade.exit_reason == "STOP_LOSS_AMBIGUOUS"
    assert trade.net_pnl < 0


def test_short_same_candle_sl_and_tp_uses_stop_loss():
    simulator = create_simulator()

    trade = simulator.open_trade(
        side="SHORT",
        entry_price=100.0,
        stop_loss=110.0,
        take_profit=90.0,
        quantity=1.0,
    )

    simulator.process_candle(
        trade=trade,
        high=111.0,
        low=89.0,
    )

    assert trade.is_open is False
    assert trade.exit_reason == "STOP_LOSS_AMBIGUOUS"
    assert trade.net_pnl < 0


# =========================================================
# TRADE LIFECYCLE
# =========================================================

def test_trade_stays_open_when_no_exit_level_is_hit():
    simulator = create_simulator()

    trade = simulator.open_trade(
        side="LONG",
        entry_price=100.0,
        stop_loss=90.0,
        take_profit=110.0,
        quantity=1.0,
    )

    simulator.process_candle(
        trade=trade,
        high=105.0,
        low=95.0,
    )

    assert trade.is_open is True
    assert trade.exit_price is None
    assert trade.exit_reason is None


def test_closed_trade_is_not_processed_again():
    simulator = create_simulator()

    trade = simulator.open_trade(
        side="LONG",
        entry_price=100.0,
        stop_loss=90.0,
        take_profit=110.0,
        quantity=1.0,
    )

    simulator.process_candle(
        trade=trade,
        high=111.0,
        low=100.0,
    )

    first_exit_price = trade.exit_price
    first_net_pnl = trade.net_pnl

    simulator.process_candle(
        trade=trade,
        high=200.0,
        low=1.0,
    )

    assert trade.exit_price == first_exit_price
    assert trade.net_pnl == first_net_pnl


def test_closing_trade_twice_is_rejected():
    simulator = create_simulator()

    trade = simulator.open_trade(
        side="LONG",
        entry_price=100.0,
        stop_loss=90.0,
        take_profit=110.0,
        quantity=1.0,
    )

    simulator.close_trade(
        trade=trade,
        exit_price=105.0,
        reason="MANUAL",
    )

    with pytest.raises(ValueError):
        simulator.close_trade(
            trade=trade,
            exit_price=106.0,
            reason="MANUAL",
        )


def test_invalid_candle_is_rejected():
    simulator = create_simulator()

    trade = simulator.open_trade(
        side="LONG",
        entry_price=100.0,
        stop_loss=90.0,
        take_profit=110.0,
        quantity=1.0,
    )

    with pytest.raises(ValueError):
        simulator.process_candle(
            trade=trade,
            high=90.0,
            low=100.0,
        )


# =========================================================
# LATENCY
# =========================================================

def test_zero_latency_executes_immediately():
    simulator = create_simulator()

    trade = simulator.open_trade(
        side="LONG",
        entry_price=100.0,
        stop_loss=90.0,
        take_profit=110.0,
        quantity=1.0,
    )

    assert isinstance(trade, SimulatedTrade)
    assert trade.entry_price == pytest.approx(100.1)


def test_latency_returns_pending_order():
    simulator = ExecutionSimulator(
        ExecutionConfig(
            fee_rate=0.001,
            slippage_rate=0.001,
            latency_bars=2,
        )
    )

    order = simulator.open_trade(
        side="LONG",
        entry_price=100.0,
        stop_loss=90.0,
        take_profit=110.0,
        quantity=1.0,
    )

    assert isinstance(order, PendingOrder)
    assert order.bars_remaining == 2
    assert order.requested_entry == 100.0


def test_pending_order_waits_for_required_bars():
    simulator = ExecutionSimulator(
        ExecutionConfig(
            latency_bars=2
        )
    )

    order = simulator.open_trade(
        side="LONG",
        entry_price=100.0,
        stop_loss=90.0,
        take_profit=110.0,
        quantity=1.0,
    )

    result = simulator.process_pending_order(
        order=order,
        market_price=101.0,
    )

    assert isinstance(result, PendingOrder)
    assert result.bars_remaining == 1


def test_long_executes_at_later_market_price():
    simulator = ExecutionSimulator(
        ExecutionConfig(
            fee_rate=0.001,
            slippage_rate=0.001,
            latency_bars=2,
        )
    )

    order = simulator.open_trade(
        side="LONG",
        entry_price=100.0,
        stop_loss=90.0,
        take_profit=110.0,
        quantity=1.0,
    )

    order = simulator.process_pending_order(
        order=order,
        market_price=101.0,
    )

    trade = simulator.process_pending_order(
        order=order,
        market_price=102.0,
    )

    assert isinstance(trade, SimulatedTrade)
    assert trade.requested_entry == 100.0
    assert trade.entry_price == pytest.approx(102.102)


def test_short_executes_at_later_market_price():
    simulator = ExecutionSimulator(
        ExecutionConfig(
            fee_rate=0.001,
            slippage_rate=0.001,
            latency_bars=1,
        )
    )

    order = simulator.open_trade(
        side="SHORT",
        entry_price=100.0,
        stop_loss=110.0,
        take_profit=90.0,
        quantity=1.0,
    )

    trade = simulator.process_pending_order(
        order=order,
        market_price=98.0,
    )

    assert isinstance(trade, SimulatedTrade)
    assert trade.requested_entry == 100.0
    assert trade.entry_price == pytest.approx(97.902)


def test_latency_uses_new_price_not_original_signal_price():
    simulator = ExecutionSimulator(
        ExecutionConfig(
            fee_rate=0.0,
            slippage_rate=0.0,
            latency_bars=1,
        )
    )

    order = simulator.open_trade(
        side="LONG",
        entry_price=100.0,
        stop_loss=90.0,
        take_profit=110.0,
        quantity=1.0,
    )

    trade = simulator.process_pending_order(
        order=order,
        market_price=105.0,
    )

    assert isinstance(trade, SimulatedTrade)
    assert trade.requested_entry == 100.0
    assert trade.entry_price == 105.0


def test_negative_latency_is_rejected():
    with pytest.raises(ValueError):
        ExecutionConfig(
            latency_bars=-1
        )


def test_non_integer_latency_is_rejected():
    with pytest.raises(TypeError):
        ExecutionConfig(
            latency_bars=1.5
        )


def test_invalid_pending_market_price_is_rejected():
    simulator = ExecutionSimulator(
        ExecutionConfig(
            latency_bars=1
        )
    )

    order = simulator.open_trade(
        side="LONG",
        entry_price=100.0,
        stop_loss=90.0,
        take_profit=110.0,
        quantity=1.0,
    )

    with pytest.raises(ValueError):
        simulator.process_pending_order(
            order=order,
            market_price=0.0,
        )

        # =========================================================
# FILL PROBABILITY
# =========================================================

def test_fill_probability_one_always_fills():
    simulator = ExecutionSimulator(
        ExecutionConfig(
            fill_probability=1.0,
            random_seed=42,
        )
    )

    result = simulator.open_trade(
        side="LONG",
        entry_price=100.0,
        stop_loss=90.0,
        take_profit=110.0,
        quantity=1.0,
    )

    assert isinstance(result, SimulatedTrade)
    assert result.is_open is True


def test_fill_probability_zero_never_fills():
    simulator = ExecutionSimulator(
        ExecutionConfig(
            fill_probability=0.0,
            random_seed=42,
        )
    )

    result = simulator.open_trade(
        side="LONG",
        entry_price=100.0,
        stop_loss=90.0,
        take_profit=110.0,
        quantity=1.0,
    )

    assert isinstance(result, RejectedOrder)
    assert result.reason == "NOT_FILLED"


def test_invalid_fill_probability_above_one_is_rejected():
    with pytest.raises(ValueError):
        ExecutionConfig(
            fill_probability=1.01
    )


def test_invalid_fill_probability_below_zero_is_rejected():
    with pytest.raises(ValueError):
        ExecutionConfig(
            fill_probability=-0.01
    )


def test_invalid_random_seed_is_rejected():
    with pytest.raises(TypeError):
        ExecutionConfig(
            random_seed=1.5
        )


def test_same_seed_produces_same_fill_sequence():
    config_a = ExecutionConfig(
        fill_probability=0.5,
        random_seed=123,
     )

    config_b = ExecutionConfig(
        fill_probability=0.5,
        random_seed=123,
    )

    simulator_a = ExecutionSimulator(config_a)
    simulator_b = ExecutionSimulator(config_b)

    results_a = []
    results_b = []

    for _ in range(20):
        result_a = simulator_a.open_trade(
            side="LONG",
            entry_price=100.0,
            stop_loss=90.0,
            take_profit=110.0,
            quantity=1.0,
        )

        result_b = simulator_b.open_trade(
            side="LONG",
            entry_price=100.0,
            stop_loss=90.0,
            take_profit=110.0,
            quantity=1.0,
        )

        results_a.append(
            isinstance(result_a, SimulatedTrade)
        )

        results_b.append(
            isinstance(result_b, SimulatedTrade)
        )

    assert results_a == results_b


def test_partial_fill_probability_produces_fills_and_rejections():
    simulator = ExecutionSimulator(
        ExecutionConfig(
            fill_probability=0.5,
            random_seed=42,
        )
    )

    results = []

    for _ in range(20):
        result = simulator.open_trade(
            side="LONG",
            entry_price=100.0,
            stop_loss=90.0,
            take_profit=110.0,
            quantity=1.0,
        )

        results.append(result)

    filled = sum(
        isinstance(result, SimulatedTrade)
        for result in results
    )

    rejected = sum(
        isinstance(result, RejectedOrder)
        for result in results
    )

    assert filled > 0
    assert rejected > 0
    assert filled + rejected == 20


def test_latency_does_not_check_fill_before_expiry():
    simulator = ExecutionSimulator(
        ExecutionConfig(
            latency_bars=2,
            fill_probability=0.0,
            random_seed=42,
        )
    )

    order = simulator.open_trade(
        side="LONG",
        entry_price=100.0,
        stop_loss=90.0,
        take_profit=110.0,
        quantity=1.0,
    )

    assert isinstance(order, PendingOrder)

    result = simulator.process_pending_order(
        order=order,
        market_price=101.0,
    )

    # Latency has not expired yet.
    # The order must still be pending even though
    # fill_probability is zero.
    assert isinstance(result, PendingOrder)
    assert result.bars_remaining == 1


def test_fill_is_checked_when_latency_expires():
    simulator = ExecutionSimulator(
        ExecutionConfig(
            latency_bars=2,
            fill_probability=0.0,
            random_seed=42,
        )
    )

    order = simulator.open_trade(
        side="LONG",
        entry_price=100.0,
        stop_loss=90.0,
        take_profit=110.0,
        quantity=1.0,
    )

    order = simulator.process_pending_order(
        order=order,
        market_price=101.0,
    )

    result = simulator.process_pending_order(
        order=order,
        market_price=102.0,
    )

    assert isinstance(result, RejectedOrder)
    assert result.reason == "NOT_FILLED"