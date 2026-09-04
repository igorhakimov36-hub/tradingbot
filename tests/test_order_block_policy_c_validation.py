"""
Tests for the frozen Policy C VALIDATION analysis functions
(strategy/research/order_block_policy_c_validation.py). All synthetic -
no SOL data is used here, matching the requirement to have the
validation harness tested BEFORE any VALIDATION data is loaded.
"""

from datetime import datetime, timedelta, timezone

from strategy.research.order_block_policy_c_validation import (
    deduplicate_events,
    first_passage_outcome,
)

START = datetime(2024, 1, 1, tzinfo=timezone.utc)


def _candle(minute_offset, open_, high, low, close, volume=10.0):
    return {
        "timestamp": START + timedelta(minutes=minute_offset),
        "open": open_, "high": high, "low": low, "close": close, "volume": volume,
    }


# =========================================================
# first_passage_outcome
# =========================================================


def test_favorable_wins_before_invalidation_bullish():
    forward = [
        _candle(1, 100, 101, 99, 100),   # neither
        _candle(2, 100, 106, 99, 105),   # favorable: high(106) - 100 >= 1.0*5 = 5 -> True; invalidation: close(105) < 95? No
    ]
    result = first_passage_outcome(
        direction="bullish", traversal_close=100.0, zone_high=110.0, zone_low=95.0,
        atr=5.0, favorable_atr_multiple=1.0, forward_candles=forward,
    )
    assert result == {"outcome": "favorable", "ambiguous": False, "bars": 2}


def test_invalidation_wins_before_favorable_bullish():
    forward = [
        _candle(1, 100, 101, 90, 92),  # invalidation: close(92) < 95 -> True; favorable: high(101)-100=1 >= 5? No
    ]
    result = first_passage_outcome(
        direction="bullish", traversal_close=100.0, zone_high=110.0, zone_low=95.0,
        atr=5.0, favorable_atr_multiple=1.0, forward_candles=forward,
    )
    assert result == {"outcome": "invalidation", "ambiguous": False, "bars": 1}


def test_ambiguous_same_bar_counted_as_invalidation():
    # Both favorable (high reaches +1 ATR) and invalidation (close beyond
    # far boundary) true on the SAME candle.
    forward = [
        _candle(1, 100, 106, 90, 92),  # high=106 (fav: 106-100=6>=5 True), close=92<95 True
    ]
    result = first_passage_outcome(
        direction="bullish", traversal_close=100.0, zone_high=110.0, zone_low=95.0,
        atr=5.0, favorable_atr_multiple=1.0, forward_candles=forward,
    )
    assert result["outcome"] == "invalidation"
    assert result["ambiguous"] is True
    assert result["bars"] == 1


def test_censored_when_neither_occurs():
    forward = [_candle(1, 100, 101, 99, 100), _candle(2, 100, 102, 98, 101)]
    result = first_passage_outcome(
        direction="bullish", traversal_close=100.0, zone_high=110.0, zone_low=95.0,
        atr=5.0, favorable_atr_multiple=1.0, forward_candles=forward,
    )
    assert result == {"outcome": "censored", "ambiguous": False, "bars": None}


def test_bearish_symmetry():
    forward = [
        _candle(1, 100, 101, 94, 95),  # favorable: 100-94=6 >= 5 True; invalidation: close(95)>110? No
    ]
    result = first_passage_outcome(
        direction="bearish", traversal_close=100.0, zone_high=110.0, zone_low=95.0,
        atr=5.0, favorable_atr_multiple=1.0, forward_candles=forward,
    )
    assert result == {"outcome": "favorable", "ambiguous": False, "bars": 1}

    forward_inv = [
        _candle(1, 100, 112, 99, 111),  # invalidation: close(111)>110 True; favorable: 100-99=1>=5? No
    ]
    result_inv = first_passage_outcome(
        direction="bearish", traversal_close=100.0, zone_high=110.0, zone_low=95.0,
        atr=5.0, favorable_atr_multiple=1.0, forward_candles=forward_inv,
    )
    assert result_inv == {"outcome": "invalidation", "ambiguous": False, "bars": 1}


def test_no_same_event_candle_credit():
    # The traversal candle itself must never be passed in forward_candles -
    # this test documents the contract: forward_candles[0] is already
    # "bar 1" (the first candle AFTER the traversal), so an empty list
    # correctly censors immediately rather than crediting bar 0.
    result = first_passage_outcome(
        direction="bullish", traversal_close=100.0, zone_high=110.0, zone_low=95.0,
        atr=5.0, favorable_atr_multiple=1.0, forward_candles=[],
    )
    assert result["outcome"] == "censored"


def test_early_invalidation_not_discarded():
    forward = [_candle(1, 100, 101, 90, 91)]
    result = first_passage_outcome(
        direction="bullish", traversal_close=100.0, zone_high=110.0, zone_low=95.0,
        atr=5.0, favorable_atr_multiple=1.0, forward_candles=forward,
    )
    assert result["outcome"] == "invalidation"
    assert result["bars"] == 1


def test_different_favorable_thresholds():
    forward = [_candle(1, 100, 102, 99, 101)]  # high-close = 2
    result_05 = first_passage_outcome(
        direction="bullish", traversal_close=100.0, zone_high=110.0, zone_low=95.0,
        atr=2.0, favorable_atr_multiple=0.5, forward_candles=forward,  # needs 1.0, has 2 -> True
    )
    assert result_05["outcome"] == "favorable"

    result_20 = first_passage_outcome(
        direction="bullish", traversal_close=100.0, zone_high=110.0, zone_low=95.0,
        atr=2.0, favorable_atr_multiple=2.0, forward_candles=forward,  # needs 4.0, has 2 -> False
    )
    assert result_20["outcome"] == "censored"


# =========================================================
# deduplicate_events
# =========================================================


def test_overlapping_close_events_cluster_together():
    events = [
        {"id": "a", "direction": "bullish", "traversal_bar_i": 10, "zone_high": 105.0, "zone_low": 100.0},
        {"id": "b", "direction": "bullish", "traversal_bar_i": 15, "zone_high": 106.0, "zone_low": 101.0},  # overlaps a, within 20 bars
    ]
    reps, cluster_map = deduplicate_events(events)
    assert len(reps) == 1
    assert reps[0]["id"] == "a"  # earliest by traversal_bar_i
    assert set(cluster_map["a"]) == {"a", "b"}


def test_non_overlapping_events_remain_separate():
    events = [
        {"id": "a", "direction": "bullish", "traversal_bar_i": 10, "zone_high": 105.0, "zone_low": 100.0},
        {"id": "b", "direction": "bullish", "traversal_bar_i": 15, "zone_high": 205.0, "zone_low": 200.0},  # disjoint zone
    ]
    reps, cluster_map = deduplicate_events(events)
    assert len(reps) == 2
    assert {r["id"] for r in reps} == {"a", "b"}


def test_overlapping_but_far_apart_in_time_remain_separate():
    events = [
        {"id": "a", "direction": "bullish", "traversal_bar_i": 10, "zone_high": 105.0, "zone_low": 100.0},
        {"id": "b", "direction": "bullish", "traversal_bar_i": 100, "zone_high": 105.0, "zone_low": 100.0},  # same zone, far in time
    ]
    reps, cluster_map = deduplicate_events(events, max_bar_gap=20)
    assert len(reps) == 2


def test_different_directions_never_cluster_together():
    events = [
        {"id": "a", "direction": "bullish", "traversal_bar_i": 10, "zone_high": 105.0, "zone_low": 100.0},
        {"id": "b", "direction": "bearish", "traversal_bar_i": 11, "zone_high": 105.0, "zone_low": 100.0},
    ]
    reps, cluster_map = deduplicate_events(events)
    assert len(reps) == 2


def test_chain_of_three_overlapping_events_forms_one_cluster():
    events = [
        {"id": "a", "direction": "bullish", "traversal_bar_i": 10, "zone_high": 105.0, "zone_low": 100.0},
        {"id": "b", "direction": "bullish", "traversal_bar_i": 15, "zone_high": 107.0, "zone_low": 102.0},
        {"id": "c", "direction": "bullish", "traversal_bar_i": 20, "zone_high": 109.0, "zone_low": 104.0},
    ]
    reps, cluster_map = deduplicate_events(events)
    assert len(reps) == 1
    assert reps[0]["id"] == "a"
    assert set(cluster_map["a"]) == {"a", "b", "c"}


def test_deduplication_uses_only_structural_identity_not_price_outcome():
    # Confirms the function signature/behavior never references any
    # outcome/price-move field - only direction, traversal_bar_i, and
    # zone bounds are read, by construction (no other keys exist here).
    events = [
        {"id": "a", "direction": "bullish", "traversal_bar_i": 10, "zone_high": 105.0, "zone_low": 100.0},
    ]
    reps, _ = deduplicate_events(events)
    assert reps[0]["id"] == "a"


def test_deterministic_across_repeated_calls():
    events = [
        {"id": "b", "direction": "bullish", "traversal_bar_i": 15, "zone_high": 106.0, "zone_low": 101.0},
        {"id": "a", "direction": "bullish", "traversal_bar_i": 10, "zone_high": 105.0, "zone_low": 100.0},
    ]
    reps1, map1 = deduplicate_events(events)
    reps2, map2 = deduplicate_events(events)
    assert [r["id"] for r in reps1] == [r["id"] for r in reps2]
    assert map1 == map2
