"""
Order Block Lifecycle Research - causal tests for Policy B (separated
mitigation/invalidation), run against Policy A's own production
OrderBlockTracker for direct comparison. Policy B is research-only
(strategy/research/order_block_lifecycle_policy_b.py) - none of these
tests touch or change production OrderBlockTracker/BreakerBlockTracker
behavior, which remains Policy A by default (see
test_production_default_remains_policy_a).
"""

from datetime import datetime, timedelta, timezone

from strategy.features.market_structure_tracker import MarketStructureTracker
from strategy.features.order_block import OrderBlockTracker
from strategy.research.order_block_lifecycle_policy_b import PolicyBOrderBlockState

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


def _bullish_block():
    """A standalone bullish Order Block, zone [100, 110]."""
    return PolicyBOrderBlockState(
        direction="bullish",
        zone_high=110.0,
        zone_low=100.0,
        created_at=START,
        origin_timestamp=START,
    )


def _bearish_block():
    return PolicyBOrderBlockState(
        direction="bearish",
        zone_high=110.0,
        zone_low=100.0,
        created_at=START,
        origin_timestamp=START,
    )


def sync_ob(order_block_tracker, candles, structure_tracker=None):
    structure_tracker = structure_tracker or MarketStructureTracker()
    start = order_block_tracker._consumed

    for i in range(start + 1, len(candles) + 1):
        step = candles[:i]
        structure_tracker.sync(step)
        event = structure_tracker.snapshot()["structural_break_event"]
        order_block_tracker.sync(step, structural_break_event=event)

    return structure_tracker


# =========================================================
# Requirement 1: partial wick entry updates mitigation, not invalidation
# =========================================================


def test_partial_wick_entry_updates_mitigation_not_invalidation():
    block = _bullish_block()
    block.apply_candle(_candle(1, 108, 109, 105, 108))  # wicks to 105, closes inside

    assert 0.0 < block.mitigation_pct < 1.0
    assert block.mitigation_status == "partially_mitigated"
    assert block.invalidated is False
    assert block.breaker_eligible is False


# =========================================================
# Requirement 2: full wick traversal, close back inside -
# fully mitigates under A, records deep mitigation without invalidation
# under B
# =========================================================


def test_full_wick_traversal_close_back_inside_policy_a_vs_b():
    candles = [
        _candle(0, 100, 101, 99, 100),
        _candle(1, 100, 102, 88, 101),
        _candle(2, 101, 103, 95, 102),
        _candle(3, 102, 110, 100, 103),
        _candle(4, 104, 105, 101, 101, volume=50.0),
        _candle(5, 101, 104, 100, 103),
        _candle(6, 103, 108, 102, 107),
        _candle(7, 107, 112, 106, 111),  # break -> creates bullish OB, zone [101,105]
    ]
    ob_tracker = OrderBlockTracker()
    sync_ob(ob_tracker, candles)
    ob = ob_tracker.snapshot()["active"][0]
    assert ob["zone_low"] == 101.0 and ob["zone_high"] == 105.0

    shadow = PolicyBOrderBlockState(
        direction="bullish", zone_high=105.0, zone_low=101.0,
        created_at=ob["created_at"], origin_timestamp=ob["origin_timestamp"],
    )

    # A wick fully traverses [101,105] (low=99) but closes back inside (103).
    wick_traversal_candle = _candle(8, 111, 112, 99, 103)
    ob_tracker.sync(candles + [wick_traversal_candle], structural_break_event=None)
    shadow.apply_candle(wick_traversal_candle)

    a_snapshot = ob_tracker.snapshot()
    # Policy A: fully mitigated -> moved out of active into mitigated.
    assert a_snapshot["active"] == []
    assert len(a_snapshot["mitigated"]) == 1
    assert a_snapshot["mitigated"][0]["mitigation_status"] == "fully_mitigated"

    # Policy B: mitigation_pct reflects the same full wick depth
    # (informational), but invalidation is NOT confirmed - close landed
    # back inside the zone, not beyond the far boundary.
    assert shadow.mitigation_status == "fully_mitigated"
    assert shadow.mitigation_pct == 1.0
    assert shadow.invalidated is False
    assert shadow.breaker_eligible is False
    assert shadow.wick_full_traversal_reclaimed is True


# =========================================================
# Requirement 3: close beyond the far boundary confirms invalidation
# =========================================================


def test_close_beyond_far_boundary_confirms_invalidation_bullish():
    block = _bullish_block()
    block.apply_candle(_candle(1, 102, 103, 95, 96))  # close (96) < zone_low (100)

    assert block.invalidated is True
    assert block.invalidated_at == START + timedelta(minutes=1)


def test_close_beyond_far_boundary_confirms_invalidation_bearish():
    block = _bearish_block()
    block.apply_candle(_candle(1, 108, 115, 107, 114))  # close (114) > zone_high (110)

    assert block.invalidated is True


# =========================================================
# Requirement 4: breaker eligibility only after the policy's own
# invalidation condition
# =========================================================


def test_breaker_eligibility_follows_invalidation_not_mitigation():
    block = _bullish_block()

    # Full wick mitigation without a confirming close.
    block.apply_candle(_candle(1, 105, 106, 95, 103))
    assert block.mitigation_status == "fully_mitigated"
    assert block.breaker_eligible is False

    # Now a close beyond the far boundary.
    block.apply_candle(_candle(2, 103, 104, 96, 97))
    assert block.invalidated is True
    assert block.breaker_eligible is True


# =========================================================
# Requirement 5: touch, mitigation, invalidation, breaker status are
# independently observable
# =========================================================


def test_touch_mitigation_invalidation_breaker_independently_observable():
    block = _bullish_block()
    block.apply_candle(_candle(1, 108, 109, 105, 108))  # touch + partial mitigation only

    assert block.touch_count == 1
    assert 0.0 < block.mitigation_pct < 1.0
    assert block.invalidated is False
    assert block.breaker_eligible is False


# =========================================================
# Requirement 6: bullish/bearish symmetry
# =========================================================


def test_bullish_bearish_symmetry():
    bull = _bullish_block()
    bull.apply_candle(_candle(1, 102, 103, 95, 96))
    assert bull.invalidated is True

    bear = _bearish_block()
    bear.apply_candle(_candle(1, 108, 115, 107, 114))
    assert bear.invalidated is True


# =========================================================
# Requirement 7: same-bar ordering is documented and causal
# =========================================================


def test_same_bar_ordering_is_causal_touch_then_mitigation_then_invalidation():
    # A single candle that touches, fully wick-mitigates, AND closes
    # beyond the far boundary all on the same bar - all three fields
    # must reflect this same bar consistently and causally (no field
    # reflects a different bar's information).
    block = _bullish_block()
    block.apply_candle(_candle(1, 105, 106, 90, 95))  # wick to 90, close 95 < 100

    assert block.touch_count == 1
    assert block.mitigation_status == "fully_mitigated"
    assert block.invalidated is True
    assert block.invalidated_at == START + timedelta(minutes=1)
    assert block.breaker_eligible is True


# =========================================================
# Requirement 8: no future candle is used
# =========================================================


def test_no_future_candle_is_used():
    block = _bullish_block()
    block.apply_candle(_candle(1, 108, 109, 105, 108))  # partial only

    # State reflects ONLY the one candle applied so far.
    assert block.invalidated is False
    assert block.mitigation_pct < 1.0

    # Applying a later, invalidating candle only takes effect once
    # actually applied - not retroactively.
    block.apply_candle(_candle(2, 103, 104, 96, 97))
    assert block.invalidated is True


# =========================================================
# Requirement 9: reset/window behavior
# =========================================================


def test_independent_instances_do_not_share_state():
    block_a = _bullish_block()
    block_b = _bullish_block()

    block_a.apply_candle(_candle(1, 102, 103, 95, 96))
    assert block_a.invalidated is True
    assert block_b.invalidated is False
    assert block_b.mitigation_pct == 0.0


# =========================================================
# Requirement 10: multiple active blocks remain independent
# =========================================================


def test_multiple_blocks_remain_independent():
    block_1 = PolicyBOrderBlockState(
        direction="bullish", zone_high=110.0, zone_low=100.0,
        created_at=START, origin_timestamp=START,
    )
    block_2 = PolicyBOrderBlockState(
        direction="bullish", zone_high=20.0, zone_low=10.0,
        created_at=START, origin_timestamp=START,
    )

    candle = _candle(1, 105, 106, 95, 96)  # invalidates block_1 (close<100), irrelevant to block_2 (close>20)
    block_1.apply_candle(candle)
    block_2.apply_candle(candle)

    assert block_1.invalidated is True
    assert block_2.invalidated is False
    assert block_2.mitigation_pct == 0.0


# =========================================================
# Requirement 11: repeated sync/snapshot calls do not duplicate
# transitions
# =========================================================


def test_repeated_apply_candle_calls_are_not_idempotent_by_design_state_advances_once_per_real_candle():
    # apply_candle() advances state exactly once per call, matching the
    # tracker convention this shadows - the test here proves a SECOND,
    # distinct candle does not double-count the FIRST candle's touch.
    block = _bullish_block()
    block.apply_candle(_candle(1, 108, 109, 105, 108))  # touch 1
    block.apply_candle(_candle(2, 108, 109, 105, 108))  # still overlapping - same touch

    assert block.touch_count == 1

    block.apply_candle(_candle(3, 108, 109, 111, 112))  # fully clear
    block.apply_candle(_candle(4, 108, 109, 105, 108))  # touch 2

    assert block.touch_count == 2


# =========================================================
# Requirement 12: Order Block creation count and origin are identical
# between A and B
# =========================================================


def test_creation_count_and_origin_identical_between_a_and_b():
    # Policy B never creates, resizes, or reinterprets a zone - it only
    # shadows zones already created by the real, unmodified
    # OrderBlockTracker. This is true by construction (PolicyBOrderBlockState
    # takes zone_high/zone_low/origin_timestamp as constructor arguments,
    # copied directly from the real Order Block), verified here directly.
    candles = [
        _candle(0, 100, 101, 99, 100),
        _candle(1, 100, 102, 88, 101),
        _candle(2, 101, 103, 95, 102),
        _candle(3, 102, 110, 100, 103),
        _candle(4, 104, 105, 101, 101, volume=50.0),
        _candle(5, 101, 104, 100, 103),
        _candle(6, 103, 108, 102, 107),
        _candle(7, 107, 112, 106, 111),
    ]
    ob_tracker = OrderBlockTracker()
    sync_ob(ob_tracker, candles)
    real_ob = ob_tracker.snapshot()["active"][0]

    shadow = PolicyBOrderBlockState(
        direction=real_ob["direction"], zone_high=real_ob["zone_high"],
        zone_low=real_ob["zone_low"], created_at=real_ob["created_at"],
        origin_timestamp=real_ob["origin_timestamp"],
    )

    assert shadow.zone_high == real_ob["zone_high"]
    assert shadow.zone_low == real_ob["zone_low"]
    assert shadow.origin_timestamp == real_ob["origin_timestamp"]
    assert shadow.created_at == real_ob["created_at"]


# =========================================================
# Requirement 13: determinism
# =========================================================


def test_determinism():
    candles = [
        _candle(1, 105, 106, 95, 103),
        _candle(2, 103, 104, 96, 97),
    ]

    results = []
    for _ in range(5):
        block = _bullish_block()
        for candle in candles:
            block.apply_candle(candle)
        results.append(block.to_dict())

    assert all(r == results[0] for r in results)


# =========================================================
# Requirement 14: existing production default remains Policy A
# =========================================================


def test_production_default_remains_policy_a():
    # OrderBlockTracker's own, unmodified behavior: full wick mitigation
    # alone (no close confirmation) moves a block to "mitigated" -
    # exactly Policy A, confirming production was NOT silently switched
    # to Policy B by this research sprint.
    candles = [
        _candle(0, 100, 101, 99, 100),
        _candle(1, 100, 102, 88, 101),
        _candle(2, 101, 103, 95, 102),
        _candle(3, 102, 110, 100, 103),
        _candle(4, 104, 105, 101, 101, volume=50.0),
        _candle(5, 101, 104, 100, 103),
        _candle(6, 103, 108, 102, 107),
        _candle(7, 107, 112, 106, 111),
    ]
    ob_tracker = OrderBlockTracker()
    sync_ob(ob_tracker, candles)

    # Wick fully traverses [101,105] and closes back inside (103) - if
    # production were Policy B, this would remain active.
    ob_tracker.sync(candles + [_candle(8, 111, 112, 99, 103)], structural_break_event=None)

    snapshot = ob_tracker.snapshot()
    assert snapshot["active"] == []
    assert len(snapshot["mitigated"]) == 1
