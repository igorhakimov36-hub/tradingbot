"""
Tests for strategy/research/paired_trade_simulator.py.
"""

from datetime import datetime, timedelta, timezone

from backtesting.execution_simulator import ExecutionConfig
from strategy.research.paired_trade_simulator import simulate_paired_trade
from strategy.research.progressive_stop_policies import make_policy_b

START = datetime(2024, 1, 1, tzinfo=timezone.utc)
NO_COST_CONFIG = ExecutionConfig(fee_rate=0.0, slippage_rate=0.0)


def _candle(i, o, h, l, c):
    return {"timestamp": START + timedelta(minutes=i), "open": o, "high": h, "low": l, "close": c}


def test_control_like_policy_hits_original_stop_unchanged():
    """A no-op ExitPolicy (never adjusts anything) must reproduce exactly
    what plain ExecutionSimulator.process_candle would do - i.e. behaves
    like the control."""

    class NoOpPolicy:
        def apply_pending(self, trade):
            pass

        def evaluate(self, trade, current_candle, market_snapshot):
            pass

    candles = [_candle(1, 100, 100.2, 98.5, 99.0)]  # low breaches original stop=99.0
    result = simulate_paired_trade(
        side="LONG", entry_price=100.0, entry_fee=0.0, stop_loss=99.0, take_profit=104.0,
        quantity=10.0, candles_1m_from_entry=candles, exit_policy=NoOpPolicy(), execution_config=NO_COST_CONFIG,
    )
    assert result.trade.is_open is False
    assert result.trade.exit_reason == "STOP_LOSS"
    assert result.trade.exit_price == 99.0
    assert result.exit_bar_index == 0


def test_staircase_policy_tightens_and_produces_a_different_exit_than_control():
    candles = [
        _candle(1, 100, 101.0, 100.0, 100.5),   # MFE=1.0R -> pending stop to 100.0
        _candle(2, 100.5, 100.6, 99.8, 100.0),  # applies pending (100.0), low=99.8 hits it
    ]
    result = simulate_paired_trade(
        side="LONG", entry_price=100.0, entry_fee=0.0, stop_loss=99.0, take_profit=104.0,
        quantity=10.0, candles_1m_from_entry=candles, exit_policy=make_policy_b(), execution_config=NO_COST_CONFIG,
    )
    assert result.trade.exit_reason == "STOP_LOSS"
    assert result.trade.exit_price == 100.0  # tightened stop, not the original 99.0
    assert result.exit_bar_index == 1


def test_pending_stop_never_applied_same_bar_it_was_decided():
    # Bar 1 has both a favorable high (triggers a new pending stop) AND
    # a low that would have hit that SAME new stop if wrongly applied
    # same-bar. It must NOT exit on bar 1.
    candles = [
        _candle(1, 100, 101.0, 99.9, 100.5),   # MFE=1.0R -> pending stop=100.0; low=99.9 would hit it if same-bar
        _candle(2, 100.5, 100.6, 100.3, 100.4),  # stop now active at 100.0, this bar doesn't hit it
    ]
    result = simulate_paired_trade(
        side="LONG", entry_price=100.0, entry_fee=0.0, stop_loss=99.0, take_profit=104.0,
        quantity=10.0, candles_1m_from_entry=candles, exit_policy=make_policy_b(), execution_config=NO_COST_CONFIG,
    )
    # Trade must survive bar 1 (original stop=99.0 not hit by low=99.9... wait 99.9>99.0 so
    # original stop not hit either) and remain open after bar 2 too.
    assert result.trade.is_open is True
    assert result.exit_bar_index is None


def test_take_profit_reached_unaffected_by_staircase_policy():
    candles = [_candle(1, 100, 104.5, 100.0, 104.0)]  # jumps straight to TP
    result = simulate_paired_trade(
        side="LONG", entry_price=100.0, entry_fee=0.0, stop_loss=99.0, take_profit=104.0,
        quantity=10.0, candles_1m_from_entry=candles, exit_policy=make_policy_b(), execution_config=NO_COST_CONFIG,
    )
    assert result.trade.exit_reason == "TAKE_PROFIT"
    assert result.trade.exit_price == 104.0


def test_never_closed_within_given_candles_stays_open():
    candles = [_candle(1, 100, 100.3, 99.9, 100.1)]
    result = simulate_paired_trade(
        side="LONG", entry_price=100.0, entry_fee=0.0, stop_loss=99.0, take_profit=104.0,
        quantity=10.0, candles_1m_from_entry=candles, exit_policy=make_policy_b(), execution_config=NO_COST_CONFIG,
    )
    assert result.trade.is_open is True
    assert result.exit_bar_index is None


def test_short_side_symmetric():
    candles = [
        _candle(1, 100, 100.0, 99.0, 99.5),   # MFE=1.0R -> pending stop to 100.0 (SHORT: entry - stop_r*R0)
        _candle(2, 99.5, 100.05, 99.4, 99.6),  # applies pending, high=100.05 hits it
    ]
    result = simulate_paired_trade(
        side="SHORT", entry_price=100.0, entry_fee=0.0, stop_loss=101.0, take_profit=96.0,
        quantity=10.0, candles_1m_from_entry=candles, exit_policy=make_policy_b(), execution_config=NO_COST_CONFIG,
    )
    assert result.trade.exit_reason == "STOP_LOSS"
    assert result.trade.exit_price == 100.0
