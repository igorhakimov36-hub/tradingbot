"""
Tests for the frozen Policy C state machine
(strategy/research/liquidity_pool_policy_c.py), per
docs/liquidity_pool_policy_c_validation_protocol.md. All synthetic - no
SOL data - covers the 16 required scenarios.
"""

from datetime import datetime, timedelta, timezone

from strategy.research.liquidity_pool_policy_c import PolicyCPoolState

START = datetime(2024, 1, 1, tzinfo=timezone.utc)


def _candle(minute_offset, open_, high, low, close, volume=10.0):
    return {
        "timestamp": START + timedelta(minutes=minute_offset),
        "open": open_, "high": high, "low": low, "close": close, "volume": volume,
    }


def _pool(direction="buy_side", window_bars=16):
    return PolicyCPoolState(direction=direction, created_at=START, window_bars=window_bars)


# =========================================================
# Requirement 1: same-candle fresh sweep
# =========================================================


def test_same_candle_fresh_sweep():
    pool = _pool()
    pool.apply_candle(_candle(1, 100, 106, 99, 100), bar_i=1, live_zone_high=105.0, live_zone_low=100.0)
    assert pool.state == "SWEPT"
    assert pool.sweep_type == "same_candle"
    assert pool.sweep_bar_i == 1


# =========================================================
# Requirement 2: first close beyond starts pending state
# =========================================================


def test_first_close_beyond_starts_pending():
    pool = _pool()
    pool.apply_candle(_candle(1, 105, 108, 104, 107), bar_i=1, live_zone_high=105.0, live_zone_low=100.0)
    assert pool.state == "ACCEPTANCE_PENDING"
    assert pool.frozen_boundary == 105.0
    assert pool.pending_entered_bar_i == 1


# =========================================================
# Requirement 3: reclaim inside 8/16/32 bars
# =========================================================


def test_reclaim_inside_window_all_sizes():
    for window in (8, 16, 32):
        pool = _pool(window_bars=window)
        pool.apply_candle(_candle(1, 105, 108, 104, 107), bar_i=1, live_zone_high=105.0, live_zone_low=100.0)
        assert pool.state == "ACCEPTANCE_PENDING"
        # Reclaim on bar 3 (well within any window size) - high stays at
        # or below zone_high so the same-candle check does not also fire;
        # only the close-based reclaim check applies once pending.
        pool.apply_candle(_candle(3, 106, 104, 103, 104), bar_i=3, live_zone_high=105.0, live_zone_low=100.0)
        assert pool.state == "SWEPT"
        assert pool.sweep_type == "multi_candle"
        assert pool.sweep_bar_i == 3


# =========================================================
# Requirement 4: reclaim exactly at the window boundary
# =========================================================


def test_reclaim_exactly_on_16th_candle_counts():
    pool = _pool(window_bars=16)
    pool.apply_candle(_candle(1, 105, 108, 104, 107), bar_i=1, live_zone_high=105.0, live_zone_low=100.0)
    # Stay pending through bars 2-16 (no reclaim, no same-candle sweep)
    for bar_i in range(2, 17):
        pool.apply_candle(_candle(bar_i, 106, 107, 104, 106), bar_i=bar_i, live_zone_high=105.0, live_zone_low=100.0)
        if bar_i < 17:
            assert pool.state == "ACCEPTANCE_PENDING", f"bar_i={bar_i}"
    # bar_i=17 is the 16th pending candle (17-1=16) - reclaim here counts
    pool.apply_candle(_candle(17, 106, 104, 103, 104), bar_i=17, live_zone_high=105.0, live_zone_low=100.0)
    assert pool.state == "SWEPT"
    assert pool.sweep_type == "multi_candle"
    assert pool.sweep_bar_i == 17


# =========================================================
# Requirement 5: acceptance after window expiry
# =========================================================


def test_acceptance_after_window_expiry():
    pool = _pool(window_bars=16)
    pool.apply_candle(_candle(1, 105, 108, 104, 107), bar_i=1, live_zone_high=105.0, live_zone_low=100.0)
    # Never reclaims through bar 17 (the 16th pending candle)
    for bar_i in range(2, 18):
        pool.apply_candle(_candle(bar_i, 106, 107, 104, 106), bar_i=bar_i, live_zone_high=105.0, live_zone_low=100.0)
    assert pool.state == "ACCEPTANCE_PENDING"  # still pending through bar 17 (16th candle)
    # bar_i=18 is the 17th pending candle - window has now expired
    pool.apply_candle(_candle(18, 106, 107, 104, 106), bar_i=18, live_zone_high=105.0, live_zone_low=100.0)
    assert pool.state == "ACCEPTED_INVALIDATED"
    assert pool.invalidated_bar_i == 18


# =========================================================
# Requirement 6: very late reclaim cannot resurrect an invalidated pool
# =========================================================


def test_very_late_reclaim_cannot_resurrect():
    pool = _pool(window_bars=16)
    pool.apply_candle(_candle(1, 105, 108, 104, 107), bar_i=1, live_zone_high=105.0, live_zone_low=100.0)
    for bar_i in range(2, 19):
        pool.apply_candle(_candle(bar_i, 106, 107, 104, 106), bar_i=bar_i, live_zone_high=105.0, live_zone_low=100.0)
    assert pool.state == "ACCEPTED_INVALIDATED"

    # A much later candle that would otherwise look like a reclaim
    pool.apply_candle(_candle(100, 106, 107, 95, 96), bar_i=100, live_zone_high=105.0, live_zone_low=100.0)
    assert pool.state == "ACCEPTED_INVALIDATED"  # unchanged, terminal


# =========================================================
# Requirement 7: one sweep event per pool lifecycle
# =========================================================


def test_only_one_sweep_event_ever():
    pool = _pool()
    pool.apply_candle(_candle(1, 100, 106, 99, 100), bar_i=1, live_zone_high=105.0, live_zone_low=100.0)
    assert pool.state == "SWEPT"
    first_sweep_bar = pool.sweep_bar_i

    # Feeding more candles after termination must not change anything.
    pool.apply_candle(_candle(2, 100, 110, 95, 96), bar_i=2, live_zone_high=105.0, live_zone_low=100.0)
    assert pool.sweep_bar_i == first_sweep_bar
    assert pool.state == "SWEPT"


# =========================================================
# Requirement 8: creation of a genuinely new nearby pool
# =========================================================


def test_new_nearby_pool_has_distinct_identity():
    old_pool = PolicyCPoolState(direction="buy_side", created_at=START, window_bars=16)
    new_pool = PolicyCPoolState(direction="buy_side", created_at=START + timedelta(minutes=500), window_bars=16)
    assert old_pool.created_at != new_pool.created_at
    # Independent instances, independent state.
    old_pool.apply_candle(_candle(1, 105, 108, 104, 107), bar_i=1, live_zone_high=105.0, live_zone_low=100.0)
    assert new_pool.state == "UNSWEPT"


# =========================================================
# Requirement 9: bullish/bearish (buy_side/sell_side) symmetry
# =========================================================


def test_buy_sell_side_symmetry():
    buy_pool = _pool(direction="buy_side")
    buy_pool.apply_candle(_candle(1, 100, 106, 99, 100), bar_i=1, live_zone_high=105.0, live_zone_low=100.0)
    assert buy_pool.state == "SWEPT" and buy_pool.sweep_type == "same_candle"

    sell_pool = _pool(direction="sell_side")
    sell_pool.apply_candle(_candle(1, 100, 101, 94, 101), bar_i=1, live_zone_high=105.0, live_zone_low=100.0)
    assert sell_pool.state == "SWEPT" and sell_pool.sweep_type == "same_candle"


def test_buy_sell_side_pending_symmetry():
    sell_pool = _pool(direction="sell_side")
    sell_pool.apply_candle(_candle(1, 100, 101, 95, 96), bar_i=1, live_zone_high=105.0, live_zone_low=100.0)
    assert sell_pool.state == "ACCEPTANCE_PENDING"
    assert sell_pool.frozen_boundary == 100.0
    sell_pool.apply_candle(_candle(2, 96, 97, 100.5, 101), bar_i=2, live_zone_high=105.0, live_zone_low=100.0)
    assert sell_pool.state == "SWEPT" and sell_pool.sweep_type == "multi_candle"


# =========================================================
# Requirement 10: reset/window behavior (independent instances)
# =========================================================


def test_independent_instances_no_shared_state():
    pool_a = _pool()
    pool_b = _pool()
    pool_a.apply_candle(_candle(1, 100, 106, 99, 100), bar_i=1, live_zone_high=105.0, live_zone_low=100.0)
    assert pool_a.state == "SWEPT"
    assert pool_b.state == "UNSWEPT"


# =========================================================
# Requirement 11: right-censoring
# =========================================================


def test_right_censoring_via_finalize():
    pool = _pool()
    pool.apply_candle(_candle(1, 105, 108, 104, 107), bar_i=1, live_zone_high=105.0, live_zone_low=100.0)
    assert pool.state == "ACCEPTANCE_PENDING"
    pool.finalize_censoring()
    assert pool.censored is True
    assert pool.state == "ACCEPTANCE_PENDING"  # state itself is not overwritten, just flagged


def test_terminal_states_are_never_censored():
    pool = _pool()
    pool.apply_candle(_candle(1, 100, 106, 99, 100), bar_i=1, live_zone_high=105.0, live_zone_low=100.0)
    pool.finalize_censoring()
    assert pool.censored is False


# =========================================================
# Requirement 12: no look-ahead
# =========================================================


def test_no_lookahead_state_reflects_only_candles_applied_so_far():
    pool = _pool()
    pool.apply_candle(_candle(1, 105, 108, 104, 107), bar_i=1, live_zone_high=105.0, live_zone_low=100.0)
    assert pool.state == "ACCEPTANCE_PENDING"
    assert pool.sweep_bar_i is None  # not yet resolved - no future info leaked


# =========================================================
# Requirement 13: no same-bar retroactivity
# =========================================================


def test_same_candle_check_runs_before_pending_transition_same_bar():
    # A candle that, on the SAME bar as entering pending territory, ALSO
    # satisfies the same-candle wick+close-back condition must be
    # classified as same_candle_sweep, not pending - proving the
    # same-candle check takes precedence within one bar's own processing.
    pool = _pool()
    pool.apply_candle(_candle(1, 100, 106, 99, 100), bar_i=1, live_zone_high=105.0, live_zone_low=100.0)
    assert pool.sweep_type == "same_candle"


# =========================================================
# Requirement 14: determinism
# =========================================================


def test_determinism():
    def run():
        pool = _pool()
        pool.apply_candle(_candle(1, 105, 108, 104, 107), bar_i=1, live_zone_high=105.0, live_zone_low=100.0)
        pool.apply_candle(_candle(3, 106, 107, 103, 104), bar_i=3, live_zone_high=105.0, live_zone_low=100.0)
        return pool.to_dict()

    results = [run() for _ in range(5)]
    assert all(r == results[0] for r in results)


# =========================================================
# Requirement 15: production Policy A remains unchanged
# =========================================================


def test_production_policy_a_unchanged():
    from strategy.features.liquidity_pool import LiquidityPool

    pool = LiquidityPool(
        direction="buy_side", zone_high=105.0, zone_low=100.0, level=102.5,
        created_at=START, origin_bar_index=0, timeframe="15m",
    )
    pool.check_sweep(_candle(1, 105, 108, 104, 107), "timestamp", atr=5.0)
    assert pool.swept_status == "unswept"  # clean close beyond does not sweep under A


# =========================================================
# Requirement 16 (S001 linkage tests live in
# test_liquidity_pool_s001_exact_linkage.py, since they require the
# real backtest/setup machinery, not just this pure state machine)
# =========================================================
