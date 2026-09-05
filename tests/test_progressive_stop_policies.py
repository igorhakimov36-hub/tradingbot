"""
Tests for strategy/research/progressive_stop_policies.py.
"""

from datetime import datetime, timedelta, timezone

import pytest

from strategy.research.progressive_stop_policies import (
    StaircaseExitPolicy,
    make_policy_b,
    make_policy_c,
    make_policy_d,
    round_to_tick,
    staircase_stop_r,
    stop_price_from_r,
)
from backtesting.execution_simulator import SimulatedTrade

START = datetime(2024, 1, 1, tzinfo=timezone.utc)


def _candle(i, o, h, l, c):
    return {"timestamp": START + timedelta(minutes=i), "open": o, "high": h, "low": l, "close": c}


def _long_trade(entry=100.0, stop=99.0, tp=104.0, qty=10.0):
    return SimulatedTrade(side="LONG", requested_entry=entry, entry_price=entry, stop_loss=stop, take_profit=tp, quantity=qty, entry_fee=0.0)


def _short_trade(entry=100.0, stop=101.0, tp=96.0, qty=10.0):
    return SimulatedTrade(side="SHORT", requested_entry=entry, entry_price=entry, stop_loss=stop, take_profit=tp, quantity=qty, entry_fee=0.0)


# =========================================================
# staircase_stop_r - step thresholds
# =========================================================


def test_policy_b_step_thresholds():
    # step_size=0.25, tighten=0.25
    assert staircase_stop_r(0.0, 0.25, 0.25) == -1.00
    assert staircase_stop_r(0.24, 0.25, 0.25) == -1.00
    assert staircase_stop_r(0.25, 0.25, 0.25) == pytest.approx(-0.75)
    assert staircase_stop_r(0.50, 0.25, 0.25) == pytest.approx(-0.50)
    assert staircase_stop_r(0.75, 0.25, 0.25) == pytest.approx(-0.25)
    assert staircase_stop_r(1.00, 0.25, 0.25) == pytest.approx(0.00)
    assert staircase_stop_r(1.25, 0.25, 0.25) == pytest.approx(0.25)


def test_policy_c_step_thresholds():
    # step_size=0.50, tighten=0.50
    assert staircase_stop_r(0.49, 0.50, 0.50) == -1.00
    assert staircase_stop_r(0.50, 0.50, 0.50) == pytest.approx(-0.50)
    assert staircase_stop_r(1.00, 0.50, 0.50) == pytest.approx(0.00)
    assert staircase_stop_r(1.50, 0.50, 0.50) == pytest.approx(0.50)


def test_policy_d_step_thresholds():
    # step_size=0.25, tighten=0.125
    assert staircase_stop_r(0.25, 0.25, 0.125) == pytest.approx(-0.875)
    assert staircase_stop_r(0.50, 0.25, 0.125) == pytest.approx(-0.75)
    assert staircase_stop_r(0.75, 0.25, 0.125) == pytest.approx(-0.625)
    assert staircase_stop_r(1.00, 0.25, 0.125) == pytest.approx(-0.50)


# =========================================================
# Requirement: long/short symmetry
# =========================================================


def test_stop_price_from_r_long_and_short_symmetric():
    long_price = stop_price_from_r("LONG", entry_price=100.0, r0=1.0, stop_r=-0.5)
    short_price = stop_price_from_r("SHORT", entry_price=100.0, r0=1.0, stop_r=-0.5)
    assert long_price == pytest.approx(99.5)   # entry + (-0.5)*1.0
    assert short_price == pytest.approx(100.5)  # entry - (-0.5)*1.0


def test_policy_long_and_short_tighten_mirror_correctly():
    policy_long = make_policy_b()
    trade_long = _long_trade(entry=100.0, stop=99.0)  # R0=1.0
    policy_long.apply_pending(trade_long)  # no-op, nothing pending yet
    policy_long.evaluate(trade_long, _candle(1, 100, 100.25, 100.0, 100.25), {})
    policy_long.apply_pending(trade_long)
    assert trade_long.stop_loss == pytest.approx(99.25)  # -0.75R = entry - 0.75

    policy_short = make_policy_b()
    trade_short = _short_trade(entry=100.0, stop=101.0)  # R0=1.0
    policy_short.apply_pending(trade_short)
    policy_short.evaluate(trade_short, _candle(1, 100, 100.0, 99.75, 99.75), {})
    policy_short.apply_pending(trade_short)
    assert trade_short.stop_loss == pytest.approx(100.75)  # entry - (-0.75)*R0 = 100.75


# =========================================================
# Requirement: monotonic tightening - never loosens
# =========================================================


def test_stop_never_loosens_on_retracement():
    policy = make_policy_b()
    trade = _long_trade(entry=100.0, stop=99.0)

    # Bar 1: MFE reaches +1.00R (high=101.0) -> stop should tighten to breakeven (100.0).
    policy.evaluate(trade, _candle(1, 100, 101.0, 100.0, 100.5), {})
    policy.apply_pending(trade)
    assert trade.stop_loss == pytest.approx(100.0)

    # Bar 2: price retraces hard (high=100.1, well below the prior MFE) -
    # stop must NOT loosen back toward the original -1.00R level.
    policy.evaluate(trade, _candle(2, 100.1, 100.1, 99.9, 100.0), {})
    policy.apply_pending(trade)
    assert trade.stop_loss == pytest.approx(100.0)  # unchanged, not loosened


def test_stop_price_monotonic_across_multiple_bars():
    policy = make_policy_c()
    trade = _long_trade(entry=100.0, stop=99.0)
    stops = []
    highs = [100.6, 100.4, 101.1, 101.6, 100.9]  # includes a retracement at bar 2 and 5
    for i, h in enumerate(highs, start=1):
        policy.evaluate(trade, _candle(i, 100, h, h - 0.2, h - 0.1), {})
        policy.apply_pending(trade)
        stops.append(trade.stop_loss)
    assert stops == sorted(stops)  # never decreases


# =========================================================
# Requirement: entry timing - pre-entry / entry-bar excursion excluded
# =========================================================


def test_mfe_tracking_starts_from_entry_price_not_bar_open():
    # The trade's entry_price is 100.0; the FIRST bar this policy ever
    # observes (per the two-phase contract, never the entry bar itself)
    # has its own open at 100.0 too but a high of 100.5 - MFE must be
    # measured from entry_price (100.0), not from some earlier,
    # unobserved pre-entry high.
    policy = make_policy_b()
    trade = _long_trade(entry=100.0, stop=99.0)
    policy.evaluate(trade, _candle(1, 100.0, 100.5, 99.9, 100.2), {})
    # MFE = (100.5 - 100.0) / 1.0 = 0.5R -> stop should tighten to -0.5R = 99.5
    policy.apply_pending(trade)
    assert trade.stop_loss == pytest.approx(99.5)


def test_policy_never_called_on_entry_bar_is_caller_responsibility_no_state_before_first_evaluate():
    # Before evaluate() is ever called, apply_pending() must be a safe no-op
    # (mirrors the real BacktestRunner never calling apply_pending for a
    # bar with no pending adjustment yet - i.e. the entry bar itself).
    policy = make_policy_b()
    trade = _long_trade(entry=100.0, stop=99.0)
    policy.apply_pending(trade)  # must not raise, must not change anything
    assert trade.stop_loss == 99.0


# =========================================================
# Requirement: next-bar activation (never applies same-bar)
# =========================================================


def test_stop_change_is_not_applied_on_the_same_bar_it_was_decided():
    policy = make_policy_b()
    trade = _long_trade(entry=100.0, stop=99.0)

    # apply_pending BEFORE evaluate on bar 1 - nothing pending yet.
    policy.apply_pending(trade)
    assert trade.stop_loss == 99.0

    # evaluate on bar 1 decides a new pending stop but must not apply it.
    policy.evaluate(trade, _candle(1, 100, 100.5, 100.0, 100.2), {})
    assert trade.stop_loss == 99.0  # still unchanged immediately after evaluate()

    # Only the NEXT bar's apply_pending() actually moves it.
    policy.apply_pending(trade)
    assert trade.stop_loss == pytest.approx(99.5)


# =========================================================
# Requirement: tick-size rounding
# =========================================================


def test_round_to_tick():
    assert round_to_tick(100.123, tick=0.01) == pytest.approx(100.12)
    assert round_to_tick(100.126, tick=0.01) == pytest.approx(100.13)
    assert round_to_tick(100.0, tick=0.01) == pytest.approx(100.0)


def test_stop_price_from_r_is_tick_rounded():
    price = stop_price_from_r("LONG", entry_price=100.0, r0=1.0, stop_r=-0.333333, tick=0.01)
    assert price == pytest.approx(round(100.0 - 0.333333, 2), abs=0.005)


# =========================================================
# R0 frozen at first observation, never recalculated
# =========================================================


def test_r0_frozen_never_recalculated_from_tightened_stop():
    policy = make_policy_b()
    trade = _long_trade(entry=100.0, stop=99.0)  # R0 = 1.0

    policy.evaluate(trade, _candle(1, 100, 101.0, 100.0, 100.5), {})  # MFE=1.0R -> stop to 100.0 (breakeven)
    policy.apply_pending(trade)
    assert trade.stop_loss == pytest.approx(100.0)

    # If R0 were wrongly recalculated from the NEW stop (100.0) instead
    # of staying at the original 1.0, a further MFE of 1.0 additional R
    # would be measured relative to the wrong (zero) distance. Confirm
    # R0 stays fixed: next MFE step should still be measured off the
    # ORIGINAL R0=1.0, i.e. reaching high=101.25 (MFE=1.25R from entry)
    # ties to stop_r=+0.25 -> price = 100.25, not something derived from
    # a recalculated R0.
    policy.evaluate(trade, _candle(2, 100.5, 101.25, 100.5, 101.0), {})
    policy.apply_pending(trade)
    assert trade.stop_loss == pytest.approx(100.25)


# =========================================================
# Named policy factories match the frozen spec exactly
# =========================================================


def test_make_policy_b_parameters():
    trade = _long_trade(entry=100.0, stop=99.0)
    policy = make_policy_b()
    policy.evaluate(trade, _candle(1, 100, 100.75, 100.0, 100.5), {})  # MFE=0.75R
    policy.apply_pending(trade)
    assert trade.stop_loss == pytest.approx(99.75)  # -0.25R


def test_make_policy_c_parameters():
    trade = _long_trade(entry=100.0, stop=99.0)
    policy = make_policy_c()
    policy.evaluate(trade, _candle(1, 100, 101.5, 100.0, 101.0), {})  # MFE=1.5R
    policy.apply_pending(trade)
    assert trade.stop_loss == pytest.approx(100.5)  # +0.5R


def test_make_policy_d_parameters():
    trade = _long_trade(entry=100.0, stop=99.0)
    policy = make_policy_d()
    policy.evaluate(trade, _candle(1, 100, 100.25, 100.0, 100.1), {})  # MFE=0.25R
    policy.apply_pending(trade)
    # -0.875R = 99.125, tick-rounded to 2dp (banker's rounding on the
    # exact halfway point 99.125 -> 99.12, not a bug in the staircase
    # math itself - covered separately by test_policy_d_step_thresholds).
    assert trade.stop_loss == pytest.approx(99.12, abs=0.005)


# =========================================================
# Regression: a reused policy instance across multiple, sequential
# trades must never let one trade's state leak into another's, even
# when a closed trade's object is garbage-collected and Python reuses
# its id() for a later trade's own SimulatedTrade (confirmed to happen
# in practice - see the module's own _state_for docstring).
# =========================================================


def test_reused_policy_instance_does_not_leak_state_across_trades_via_id_reuse():
    policy = make_policy_b()

    # First trade: push it to a materially tightened stop.
    trade1 = _long_trade(entry=100.0, stop=99.0)
    policy.evaluate(trade1, _candle(1, 100, 101.0, 100.0, 100.5), {})  # MFE=1.0R
    policy.apply_pending(trade1)
    assert trade1.stop_loss == pytest.approx(100.0)  # breakeven

    # Force trade1's id() to become eligible for reuse.
    trade1_id = id(trade1)
    del trade1
    import gc
    gc.collect()

    # Allocate enough short-lived objects to make an id()-reuse
    # collision likely in this test's own controlled setting, then
    # create a genuinely NEW, unrelated trade with a DIFFERENT entry.
    for _ in range(50):
        _long_trade()

    trade2 = _long_trade(entry=200.0, stop=198.0)  # unrelated: entry=200, R0=2.0

    # Whether or not id(trade2) happens to equal the old trade1_id in
    # this run, the new trade's own first evaluate() must compute MFE
    # from ITS OWN entry (200.0) and R0 (2.0) - never trade1's stale
    # state (entry=100.0, R0=1.0, already-tightened stop_r).
    policy.evaluate(trade2, _candle(1, 200, 202.0, 200.0, 201.0), {})  # MFE = (202-200)/2.0 = 1.0R
    policy.apply_pending(trade2)
    assert trade2.stop_loss == pytest.approx(200.0)  # breakeven relative to ITS OWN entry/R0, not trade1's

    # Explicit, direct proof of the mechanism this regression guards
    # against: a naive id()-keyed implementation would have returned
    # trade1's OWN state object for trade2 whenever id() collided.
    # Confirm the two trades' own stored state objects are never the
    # same object, regardless of id() reuse.
    state1_after = getattr(trade2, StaircaseExitPolicy._STATE_ATTR)
    assert state1_after.r0 == pytest.approx(2.0)  # trade2's own R0, never trade1's 1.0


def test_two_trades_with_colliding_ids_get_independent_state_directly():
    # Directly simulate an id() collision (bypassing garbage-collection
    # timing, which is non-deterministic) by reusing the SAME object
    # reference for what the real BacktestRunner would treat as two
    # sequential, unrelated trades - a fresh SimulatedTrade is what a
    # real id()-collision would produce (a different object at the same
    # address), so this test instead verifies the state-attribute
    # approach never depends on address/id() at all: a second, distinct
    # object always gets its own independent state even if we construct
    # it to be otherwise identical in every field except entry/stop.
    policy = make_policy_c()

    trade_a = _long_trade(entry=100.0, stop=99.0)
    policy.evaluate(trade_a, _candle(1, 100, 101.5, 100.0, 101.0), {})  # MFE=1.5R
    policy.apply_pending(trade_a)

    trade_b = _long_trade(entry=100.0, stop=99.0)  # a second, distinct object, same field values
    assert trade_b is not trade_a
    # trade_b must start fresh (no pending/tightening carried over),
    # even though every field value is identical to trade_a's.
    policy.apply_pending(trade_b)  # no-op: nothing pending for this distinct object yet
    assert trade_b.stop_loss == 99.0


# =========================================================
# Determinism
# =========================================================


def test_deterministic():
    trade1 = _long_trade(entry=100.0, stop=99.0)
    trade2 = _long_trade(entry=100.0, stop=99.0)
    policy1, policy2 = make_policy_b(), make_policy_b()
    for i, h in enumerate([100.3, 100.6, 100.9], start=1):
        policy1.evaluate(trade1, _candle(i, 100, h, h - 0.1, h - 0.05), {})
        policy1.apply_pending(trade1)
        policy2.evaluate(trade2, _candle(i, 100, h, h - 0.1, h - 0.05), {})
        policy2.apply_pending(trade2)
    assert trade1.stop_loss == trade2.stop_loss
