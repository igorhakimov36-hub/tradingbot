"""
Sprint 1B - snapshot-cache correctness and mutation-isolation tests for
OrderBlockTracker, EqualLevelsTracker, and LiquidityPoolTracker.

These trackers' pre-existing detection/mitigation/sweep logic is
already covered by test_order_block_feature.py, test_equal_highs_lows.py,
and test_liquidity_pool.py - none of that logic changed in Sprint 1B, and
those suites (unmodified) still pass. This file targets ONLY the new
caching behavior: correctness (a cache hit must equal a fresh rebuild)
and mutation isolation (returned snapshots must never share state with
the tracker, with each other, or across calls).

No reset() method exists on any of these three trackers (by design -
they are constructed fresh per backtest run) - not tested here for that
reason, not omitted by oversight.
"""

from datetime import datetime, timedelta, timezone

from strategy.features.equal_highs_lows import EqualLevelsTracker
from strategy.features.liquidity_pool import LiquidityPoolTracker
from strategy.features.order_block import OrderBlockTracker

START = datetime(2024, 1, 1, tzinfo=timezone.utc)


def _candle(minute_offset, open_, high, low, close, volume=10.0):
    return {
        "timestamp": START + timedelta(minutes=minute_offset),
        "open": open_,
        "high": high,
        "low": low,
        "close": close,
        "volume": volume,
    }


def _bullish_ob_setup():
    """Identical fixture to test_order_block_feature.py's own
    _bullish_setup() - produces exactly one active bullish Order Block."""
    return [
        _candle(0, 100, 101, 99, 100),
        _candle(1, 100, 102, 88, 101),
        _candle(2, 101, 103, 95, 102),
        _candle(3, 102, 110, 100, 103),
        _candle(4, 104, 105, 101, 101, volume=50.0),
        _candle(5, 101, 104, 100, 103),
        _candle(6, 103, 108, 102, 107),
        _candle(7, 107, 112, 106, 111),
    ]


def _bearish_ob_setup():
    return [
        _candle(0, 100, 101, 99, 100),
        _candle(1, 100, 112, 99, 100),
        _candle(2, 99, 105, 97, 98),
        _candle(3, 98, 100, 90, 91),
        _candle(4, 96, 99, 95, 99, volume=50.0),
        _candle(5, 99, 100, 96, 97),
        _candle(6, 97, 98, 92, 93),
        _candle(7, 93, 94, 88, 89),
    ]


# =========================================================
# OrderBlockTracker
# =========================================================


def test_order_block_repeated_snapshot_no_state_change_is_stable():
    tracker = OrderBlockTracker()
    tracker.sync(_bullish_ob_setup())

    first = tracker.snapshot()
    second = tracker.snapshot()

    assert first == second
    assert first is not second, "each call must return an independent object"
    assert first["active"][0] is not second["active"][0]


def test_order_block_cache_hit_equals_fresh_rebuild():
    tracker = OrderBlockTracker()
    tracker.sync(_bullish_ob_setup())

    cached = tracker.snapshot()
    fresh = tracker._build_snapshot()

    assert cached == fresh


def test_order_block_snapshot_updates_after_new_state():
    tracker = OrderBlockTracker()
    candles = _bullish_ob_setup()

    tracker.sync(candles[:7])  # before BOS confirms
    before = tracker.snapshot()
    assert before["active"] == []

    tracker.sync(candles)  # BOS confirms on the 8th candle
    after = tracker.snapshot()
    assert len(after["active"]) == 1


def test_order_block_touch_count_change_is_reflected():
    tracker = OrderBlockTracker()
    candles = _bullish_ob_setup()
    tracker.sync(candles)
    assert tracker.snapshot()["active"][0]["touch_count"] == 0

    # A candle re-entering the OB zone [101, 105]
    touching = candles + [_candle(8, 103, 104, 102, 103)]
    tracker.sync(touching)
    assert tracker.snapshot()["active"][0]["touch_count"] == 1


def test_order_block_mitigation_progression_is_reflected():
    tracker = OrderBlockTracker()
    candles = _bullish_ob_setup()
    tracker.sync(candles)

    partial = candles + [_candle(8, 103, 104, 103, 103)]  # wick to 103, mid-zone
    tracker.sync(partial)
    mid = tracker.snapshot()["active"][0]
    assert 0.0 < mid["mitigation_pct"] < 1.0
    assert mid["mitigation_status"] == "partially_mitigated"

    full = partial + [_candle(9, 103, 104, 100, 103)]  # wick to 100 = zone_low
    tracker.sync(full)
    snap = tracker.snapshot()
    assert snap["active"] == []
    assert len(snap["mitigated"]) == 1
    assert snap["mitigated"][0]["mitigation_status"] == "fully_mitigated"


def test_order_block_multiple_active_objects_both_reflected():
    tracker = OrderBlockTracker()
    bull = _bullish_ob_setup()
    combined = bull + [
        _candle(8, 111, 115, 109, 112),
        _candle(9, 112, 113, 105, 106, volume=30.0),  # bullish -> new bearish-break origin
        _candle(10, 106, 108, 100, 102),
        _candle(11, 102, 103, 90, 91),
        _candle(12, 91, 92, 85, 86),  # breaks below a swing low -> BEARISH_BOS
    ]
    tracker.sync(combined)
    snap = tracker.snapshot()
    total = len(snap["active"]) + len(snap["mitigated"])
    assert total >= 1  # at minimum the original bullish OB persists; exact count not the point here
    # The real assertion: snapshot() reflects however many objects are
    # ACTUALLY tracked, consistent with a fresh rebuild.
    assert snap == tracker._build_snapshot()


def test_order_block_pruning_reflected_in_snapshot():
    tracker = OrderBlockTracker(max_age_bars=2)
    candles = _bullish_ob_setup()
    tracker.sync(candles)
    assert len(tracker.snapshot()["active"]) == 1

    aged = candles + [_candle(8 + i, 103, 104, 102, 103) for i in range(5)]
    tracker.sync(aged)
    snap = tracker.snapshot()
    assert snap["active"] == []
    assert snap["expired_count"] >= 1


def test_order_block_bearish_symmetry():
    tracker = OrderBlockTracker()
    tracker.sync(_bearish_ob_setup())
    snap = tracker.snapshot()
    assert len(snap["active"]) == 1
    assert snap["active"][0]["direction"] == "bearish"


def test_order_block_empty_state_snapshot():
    tracker = OrderBlockTracker()
    snap = tracker.snapshot()
    assert snap == {"active": [], "mitigated": [], "expired_count": 0}
    # calling again with still no data must not error or change anything
    assert tracker.snapshot() == snap


def test_order_block_determinism_across_many_calls():
    tracker = OrderBlockTracker()
    tracker.sync(_bullish_ob_setup())
    results = [tracker.snapshot() for _ in range(20)]
    assert all(r == results[0] for r in results)


def test_order_block_mutating_returned_snapshot_does_not_corrupt_tracker():
    tracker = OrderBlockTracker()
    tracker.sync(_bullish_ob_setup())

    snap = tracker.snapshot()
    snap["active"][0]["context"]["poisoned"] = True
    snap["active"].append({"fake": "entry"})
    snap["expired_count"] = 999999

    fresh = tracker.snapshot()
    assert "poisoned" not in fresh["active"][0]["context"]
    assert len(fresh["active"]) == 1
    assert fresh["expired_count"] == 0


def test_order_block_mutating_one_snapshot_does_not_alter_a_later_one():
    tracker = OrderBlockTracker()
    tracker.sync(_bullish_ob_setup())

    first = tracker.snapshot()
    first["active"][0]["touch_count"] = -999

    second = tracker.snapshot()
    assert second["active"][0]["touch_count"] == 0


def test_order_block_two_callers_do_not_affect_each_other():
    tracker = OrderBlockTracker()
    tracker.sync(_bullish_ob_setup())

    caller_a = tracker.snapshot()
    caller_b = tracker.snapshot()

    caller_a["active"][0]["zone_high"] = -1.0

    assert caller_b["active"][0]["zone_high"] == 105.0


# =========================================================
# EqualLevelsTracker - cache correctness (mutation isolation identical
# pattern to OrderBlockTracker, not fully re-repeated per case)
# =========================================================


def test_equal_levels_cache_hit_equals_fresh_rebuild():
    tracker = EqualLevelsTracker()
    candles = [
        _candle(0, 100, 105, 99, 104),
        _candle(1, 104, 106, 103, 105),
        _candle(2, 105, 107, 104, 106),
        _candle(3, 106, 105.2, 100, 101),  # first equal-high pivot area
        _candle(4, 101, 104, 100, 102),
        _candle(5, 102, 105.1, 101, 103),  # second, close pivot -> cluster
        _candle(6, 103, 104, 99, 100),
    ]
    tracker.sync(candles)

    cached = tracker.snapshot()
    fresh = tracker._build_snapshot()
    assert cached == fresh
    assert cached is not fresh


def test_equal_levels_repeated_snapshot_stable_and_isolated():
    tracker = EqualLevelsTracker()
    tracker.sync([_candle(i, 100, 101, 99, 100) for i in range(10)])

    a = tracker.snapshot()
    b = tracker.snapshot()
    assert a == b
    assert a is not b


def test_equal_levels_mutation_does_not_corrupt_tracker():
    tracker = EqualLevelsTracker()
    tracker.sync([_candle(i, 100, 101, 99, 100) for i in range(10)])

    snap = tracker.snapshot()
    snap["equal_highs"].append({"fake": True})
    snap["expired_count"] = -1

    fresh = tracker.snapshot()
    assert fresh["equal_highs"] == []
    assert fresh["expired_count"] == 0


def test_equal_levels_empty_state():
    tracker = EqualLevelsTracker()
    assert tracker.snapshot() == {"equal_highs": [], "equal_lows": [], "expired_count": 0}


# =========================================================
# LiquidityPoolTracker - cache correctness + sweep/resolution
#
# Mirrors test_liquidity_pool.py's own fixtures exactly (LiquidityPoolTracker
# requires equal_levels_snapshot/session_snapshot inputs and exactly-
# one-new-candle-per-call, by design - not a detail invented here).
# =========================================================


def _lp_candle(minute_offset, high, low, close=None, volume=10.0):
    if close is None:
        close = (high + low) / 2
    return {
        "timestamp": START + timedelta(minutes=minute_offset),
        "open": close, "high": high, "low": low, "close": close, "volume": volume,
    }


def _lp_eqh(level, created_at):
    return {"direction": "equal_highs", "level": level, "created_at": created_at}


def _lp_empty_equal_levels():
    return {"equal_highs": [], "equal_lows": [], "expired_count": 0}


def _lp_empty_sessions():
    return {}


def _liquidity_pool_setup_active_pool():
    """Forms one active buy_side pool from two equal-highs candidates,
    exactly matching test_liquidity_pool.py's own proven formation
    pattern - not swept."""
    tracker = LiquidityPoolTracker()
    history = []
    for c in [_lp_candle(-2, 101, 99), _lp_candle(-1, 101, 99)]:  # ATR warm-up
        history.append(c)
        tracker.sync(history, equal_levels_snapshot=_lp_empty_equal_levels(), session_snapshot=_lp_empty_sessions())

    history.append(_lp_candle(0, 101, 99))
    tracker.sync(history, equal_levels_snapshot={"equal_highs": [_lp_eqh(100.0, START)], "equal_lows": [], "expired_count": 0}, session_snapshot=_lp_empty_sessions())

    eqh_snapshot = {"equal_highs": [_lp_eqh(100.0, START), _lp_eqh(100.02, START + timedelta(minutes=1))], "equal_lows": [], "expired_count": 0}
    history.append(_lp_candle(1, 101, 99))
    tracker.sync(history, equal_levels_snapshot=eqh_snapshot, session_snapshot=_lp_empty_sessions())

    return tracker, history, eqh_snapshot


def test_liquidity_pool_cache_hit_equals_fresh_rebuild():
    tracker, _, _ = _liquidity_pool_setup_active_pool()
    assert len(tracker.snapshot()["active"]) == 1  # sanity: a pool actually formed

    cached = tracker.snapshot()
    fresh = tracker._build_snapshot()
    assert cached == fresh
    assert cached is not fresh


def test_liquidity_pool_sweep_updates_snapshot():
    tracker, history, eqh_snapshot = _liquidity_pool_setup_active_pool()

    sweeping = _lp_candle(2, high=105, low=99, close=100.01)  # wicks above zone_high, closes back inside
    history.append(sweeping)
    tracker.sync(history, equal_levels_snapshot=eqh_snapshot, session_snapshot=_lp_empty_sessions())

    snap = tracker.snapshot()
    assert snap["active"] == []
    assert len(snap["swept"]) == 1
    assert snap["swept"][0]["swept_status"] == "swept"
    assert snap == tracker._build_snapshot()


def test_liquidity_pool_mutation_isolation():
    tracker, _, _ = _liquidity_pool_setup_active_pool()

    snap = tracker.snapshot()
    for pool in snap["active"]:
        pool["swept_status"] = "swept"
    snap["expired_count"] = 12345

    fresh = tracker.snapshot()
    assert fresh["expired_count"] == 0
    for pool in fresh["active"]:
        assert pool["swept_status"] == "unswept"


def test_liquidity_pool_empty_state():
    tracker = LiquidityPoolTracker()
    assert tracker.snapshot() == {"active": [], "swept": [], "expired_count": 0}


def test_liquidity_pool_determinism():
    tracker, _, _ = _liquidity_pool_setup_active_pool()
    results = [tracker.snapshot() for _ in range(10)]
    assert all(r == results[0] for r in results)
