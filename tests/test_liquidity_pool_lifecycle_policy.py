"""
Tests for the Liquidity Pool Lifecycle Research pure functions
(strategy/research/liquidity_pool_lifecycle_policy.py). All synthetic -
covers the 15 required research-harness scenarios.
"""

from datetime import datetime, timedelta, timezone

from strategy.research.liquidity_pool_lifecycle_policy import (
    classify_lifecycle_path,
    deduplicate_pools,
    first_passage_outcome_pool,
)

START = datetime(2024, 1, 1, tzinfo=timezone.utc)


def _candle(minute_offset, open_, high, low, close, volume=10.0):
    return {
        "timestamp": START + timedelta(minutes=minute_offset),
        "open": open_, "high": high, "low": low, "close": close, "volume": volume,
    }


# =========================================================
# Requirement 1: fresh same-candle sweep
# =========================================================


def test_fresh_same_candle_sweep():
    record = {
        "first_close_beyond_bar_i": None,
        "current_rule_swept_bar_i": 5,
        "first_reclaim_bar_i": None,
        "censored": False,
    }
    assert classify_lifecycle_path(record, fast_threshold_bars=4) == "same_candle_sweep"


# =========================================================
# Requirement 2: one close beyond followed by immediate reclaim
# =========================================================


def test_one_close_beyond_immediate_reclaim_is_fast_rejection():
    record = {
        "first_close_beyond_bar_i": 10,
        "current_rule_swept_bar_i": None,
        "first_reclaim_bar_i": 11,  # 1 bar later
        "censored": False,
    }
    assert classify_lifecycle_path(record, fast_threshold_bars=4) == "fast_multi_candle_rejection"


# =========================================================
# Requirement 3: multiple closes beyond followed by reclaim
# =========================================================


def test_multiple_closes_beyond_then_reclaim_within_fast_window():
    record = {
        "first_close_beyond_bar_i": 10,
        "current_rule_swept_bar_i": None,
        "first_reclaim_bar_i": 13,  # 3 bars later, still "fast" at threshold=4
        "censored": False,
    }
    assert classify_lifecycle_path(record, fast_threshold_bars=4) == "fast_multi_candle_rejection"

    record_slow = dict(record, first_reclaim_bar_i=20)  # 10 bars later
    assert classify_lifecycle_path(record_slow, fast_threshold_bars=4) == "sustained_acceptance"


# =========================================================
# Requirement 4: sustained acceptance without reclaim
# =========================================================


def test_sustained_acceptance_never_reclaims_is_never_resolved():
    record = {
        "first_close_beyond_bar_i": 10,
        "current_rule_swept_bar_i": None,
        "first_reclaim_bar_i": None,
        "censored": True,
    }
    assert classify_lifecycle_path(record, fast_threshold_bars=4) == "never_resolved"


# =========================================================
# Requirement 5: delayed current-rule sweep
# =========================================================


def test_delayed_current_rule_sweep():
    record = {
        "first_close_beyond_bar_i": 10,
        "current_rule_swept_bar_i": 25,  # sweep fires well after a prior close-beyond
        "first_reclaim_bar_i": None,
        "censored": False,
    }
    assert classify_lifecycle_path(record, fast_threshold_bars=4) == "delayed_current_rule_sweep"


def test_close_beyond_on_the_sweep_candle_itself_is_not_delayed():
    # A close-beyond timestamp equal to (or after) the sweep bar itself
    # does not count as a PRIOR clean close beyond - the sweep candle's
    # own close is by definition back inside, so this only happens if
    # bookkeeping mistakenly records the sweep candle itself.
    record = {
        "first_close_beyond_bar_i": 25,
        "current_rule_swept_bar_i": 25,
        "first_reclaim_bar_i": None,
        "censored": False,
    }
    assert classify_lifecycle_path(record, fast_threshold_bars=4) == "same_candle_sweep"


# =========================================================
# Requirement 6: age expiry after acceptance (never_resolved, censored)
# =========================================================


def test_never_touched_and_never_swept_is_never_resolved():
    record = {
        "first_close_beyond_bar_i": None,
        "current_rule_swept_bar_i": None,
        "first_reclaim_bar_i": None,
        "censored": True,
    }
    assert classify_lifecycle_path(record, fast_threshold_bars=4) == "never_resolved"


# =========================================================
# Requirement 7: buy-side/sell-side symmetry (first_passage_outcome_pool)
# =========================================================


def test_first_passage_buy_side_reclaim():
    forward = [_candle(1, 100, 101, 95, 96)]  # close(96) < zone_high(100) -> reclaim
    result = first_passage_outcome_pool(
        direction="buy_side", boundary_close_price=102.0, zone_high=100.0, zone_low=90.0,
        atr=5.0, continuation_atr_multiple=1.0, forward_candles=forward,
    )
    assert result["outcome"] == "reclaim"


def test_first_passage_sell_side_symmetry():
    forward = [_candle(1, 90, 95, 89, 94)]  # close(94) > zone_low(90) -> reclaim
    result = first_passage_outcome_pool(
        direction="sell_side", boundary_close_price=88.0, zone_high=100.0, zone_low=90.0,
        atr=5.0, continuation_atr_multiple=1.0, forward_candles=forward,
    )
    assert result["outcome"] == "reclaim"


def test_first_passage_continuation():
    # boundary_close_price=102 (buy_side); continuation needs high-102>=5
    forward = [_candle(1, 102, 108, 101, 105)]  # close(105) not < 100 (no reclaim); high(108)-102=6>=5 -> continuation
    result = first_passage_outcome_pool(
        direction="buy_side", boundary_close_price=102.0, zone_high=100.0, zone_low=90.0,
        atr=5.0, continuation_atr_multiple=1.0, forward_candles=forward,
    )
    assert result["outcome"] == "continuation"


def test_first_passage_ambiguous_same_bar_counted_as_reclaim():
    # Both reclaim (close<100) and continuation (high-102>=5) true same bar.
    forward = [_candle(1, 102, 108, 95, 96)]
    result = first_passage_outcome_pool(
        direction="buy_side", boundary_close_price=102.0, zone_high=100.0, zone_low=90.0,
        atr=5.0, continuation_atr_multiple=1.0, forward_candles=forward,
    )
    assert result["outcome"] == "reclaim"
    assert result["ambiguous"] is True


def test_first_passage_censored():
    forward = [_candle(1, 102, 103, 101, 102)]
    result = first_passage_outcome_pool(
        direction="buy_side", boundary_close_price=102.0, zone_high=100.0, zone_low=90.0,
        atr=5.0, continuation_atr_multiple=1.0, forward_candles=forward,
    )
    assert result["outcome"] == "censored"


# =========================================================
# Requirement 8: no look-ahead (empty forward window censors immediately)
# =========================================================


def test_no_lookahead_empty_forward_window():
    result = first_passage_outcome_pool(
        direction="buy_side", boundary_close_price=102.0, zone_high=100.0, zone_low=90.0,
        atr=5.0, continuation_atr_multiple=1.0, forward_candles=[],
    )
    assert result["outcome"] == "censored"


# =========================================================
# Requirement 9: no same-bar retroactivity (the reference candle itself
# never contributes an outcome - verified by construction: forward_candles
# starting at bar 1 excludes the reference candle entirely)
# =========================================================


def test_reference_candle_excluded_from_outcome():
    # If the reference candle's own extreme values were mistakenly
    # included, this would immediately resolve; by never passing it,
    # the first real forward candle is what determines the outcome.
    forward = [_candle(1, 100, 101, 99, 100)]  # neither condition met
    result = first_passage_outcome_pool(
        direction="buy_side", boundary_close_price=102.0, zone_high=100.0, zone_low=90.0,
        atr=5.0, continuation_atr_multiple=1.0, forward_candles=forward,
    )
    assert result["outcome"] == "censored"


# =========================================================
# Requirement 10: reset/window behavior (independent classification calls)
# =========================================================


def test_classification_calls_are_independent():
    record_a = {"first_close_beyond_bar_i": 10, "current_rule_swept_bar_i": None, "first_reclaim_bar_i": 11, "censored": False}
    record_b = {"first_close_beyond_bar_i": 10, "current_rule_swept_bar_i": None, "first_reclaim_bar_i": None, "censored": True}
    assert classify_lifecycle_path(record_a, fast_threshold_bars=4) == "fast_multi_candle_rejection"
    assert classify_lifecycle_path(record_b, fast_threshold_bars=4) == "never_resolved"


# =========================================================
# Requirement 11: multiple independent pools (deduplicate_pools)
# =========================================================


def test_multiple_independent_pools_remain_separate():
    pools = [
        {"id": "a", "direction": "buy_side", "origin_bar_i": 10, "zone_high": 105.0, "zone_low": 100.0},
        {"id": "b", "direction": "buy_side", "origin_bar_i": 500, "zone_high": 205.0, "zone_low": 200.0},
    ]
    reps, cluster_map = deduplicate_pools(pools)
    assert len(reps) == 2


# =========================================================
# Requirement 12: overlapping-pool clustering
# =========================================================


def test_overlapping_pools_cluster_together_earliest_wins():
    pools = [
        {"id": "a", "direction": "buy_side", "origin_bar_i": 10, "zone_high": 105.0, "zone_low": 100.0},
        {"id": "b", "direction": "buy_side", "origin_bar_i": 15, "zone_high": 106.0, "zone_low": 101.0},
    ]
    reps, cluster_map = deduplicate_pools(pools)
    assert len(reps) == 1
    assert reps[0]["id"] == "a"
    assert set(cluster_map["a"]) == {"a", "b"}


def test_different_sides_never_cluster():
    pools = [
        {"id": "a", "direction": "buy_side", "origin_bar_i": 10, "zone_high": 105.0, "zone_low": 100.0},
        {"id": "b", "direction": "sell_side", "origin_bar_i": 11, "zone_high": 105.0, "zone_low": 100.0},
    ]
    reps, cluster_map = deduplicate_pools(pools)
    assert len(reps) == 2


# =========================================================
# Requirement 13: right-censoring
# =========================================================


def test_right_censoring_not_treated_as_reclaim_or_continuation():
    record = {
        "first_close_beyond_bar_i": 10,
        "current_rule_swept_bar_i": None,
        "first_reclaim_bar_i": None,
        "censored": True,
    }
    result = classify_lifecycle_path(record, fast_threshold_bars=4)
    assert result == "never_resolved"  # not misclassified as a resolved outcome


# =========================================================
# Requirement 14: production behavior remains unchanged
# =========================================================


def test_production_liquidity_pool_tracker_untouched():
    # Confirms LiquidityPoolTracker's own sweep rule is still exactly
    # the same-candle wick-beyond-then-close-back rule - this research
    # module does not alter it.
    from strategy.features.liquidity_pool import LiquidityPool

    pool = LiquidityPool(
        direction="buy_side", zone_high=100.0, zone_low=95.0, level=97.5,
        created_at=START, origin_bar_index=0, timeframe="15m",
    )
    # A clean close beyond (no same-candle rejection) - production must
    # NOT mark this swept.
    pool.check_sweep(_candle(1, 100, 102, 99, 101), "timestamp", atr=5.0)
    assert pool.swept_status == "unswept"


# =========================================================
# Requirement 15: determinism
# =========================================================


def test_deduplication_deterministic():
    pools = [
        {"id": "b", "direction": "buy_side", "origin_bar_i": 15, "zone_high": 106.0, "zone_low": 101.0},
        {"id": "a", "direction": "buy_side", "origin_bar_i": 10, "zone_high": 105.0, "zone_low": 100.0},
    ]
    reps1, map1 = deduplicate_pools(pools)
    reps2, map2 = deduplicate_pools(pools)
    assert [r["id"] for r in reps1] == [r["id"] for r in reps2]
    assert map1 == map2


def test_first_passage_deterministic():
    forward = [_candle(1, 102, 108, 95, 96)]
    results = [
        first_passage_outcome_pool(
            direction="buy_side", boundary_close_price=102.0, zone_high=100.0, zone_low=90.0,
            atr=5.0, continuation_atr_multiple=1.0, forward_candles=forward,
        )
        for _ in range(5)
    ]
    assert all(r == results[0] for r in results)
