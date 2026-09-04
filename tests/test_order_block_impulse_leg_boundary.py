"""
Module Logic Correction 2, Phase 2B - confirms OrderBlockTracker's
bounded origin-candle search against the confirmed defect: an unbounded
scan of the full structure_lookback window could select an economically
unrelated candle from prior, already-used structure when the actual
impulse leg (the broken pivot's own candle through the breaking candle)
contained no opposite-colored candle at all. Demonstrated FAILING
against the Phase-2A-only code (see
docs/module_correction2_order_block_report.md); these tests confirm the
fix.
"""

from datetime import datetime, timedelta, timezone

from strategy.features.market_structure_tracker import MarketStructureTracker
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


def sync_ob(order_block_tracker, candles, structure_tracker=None):
    structure_tracker = structure_tracker or MarketStructureTracker()
    start = order_block_tracker._consumed

    for i in range(start + 1, len(candles) + 1):
        step = candles[:i]
        structure_tracker.sync(step)
        event = structure_tracker.snapshot()["structural_break_event"]
        order_block_tracker.sync(step, structural_break_event=event)

    return structure_tracker


def _canonical_bullish_setup():
    """The codebase's own established reference case (identical to
    test_order_block_feature.py's _bullish_setup()): swing high at
    idx3 (110), a brief consolidation (idx4-6), then breakout at idx7.
    Origin is idx4 - AFTER the swing high pivot, not before it - which
    is exactly why bounding the leg to "the broken pivot's own candle"
    (not "the most recent opposing swing pivot") is required to
    reproduce this already-established result (see order_block.py's
    _find_impulse_leg docstring)."""
    return [
        _candle(0, 100, 101, 99, 100),
        _candle(1, 100, 102, 88, 101),
        _candle(2, 101, 103, 95, 102),
        _candle(3, 102, 110, 100, 103),
        _candle(4, 104, 105, 101, 101, volume=50.0),  # origin
        _candle(5, 101, 104, 100, 103),
        _candle(6, 103, 108, 102, 107),
        _candle(7, 107, 112, 106, 111),  # break (111 > 110)
    ]


def _canonical_bearish_setup():
    return [
        _candle(0, 100, 101, 99, 100),
        _candle(1, 100, 112, 99, 100),
        _candle(2, 99, 105, 97, 98),
        _candle(3, 98, 100, 90, 91),
        _candle(4, 96, 99, 95, 99, volume=50.0),  # origin
        _candle(5, 99, 100, 96, 97),
        _candle(6, 97, 98, 92, 93),
        _candle(7, 93, 94, 88, 89),  # break (89 < 90)
    ]


def test_valid_opposite_candle_inside_leg_is_selected():
    """Requirement 1: a valid last opposite-colored candle inside the
    leg is found. Requirement 12: reproduces the pre-existing reference
    result exactly."""
    tracker = OrderBlockTracker()
    sync_ob(tracker, _canonical_bullish_setup())

    active = tracker.snapshot()["active"]
    assert len(active) == 1
    assert active[0]["zone_high"] == 105.0
    assert active[0]["zone_low"] == 101.0
    assert active[0]["origin_timestamp"] == START + timedelta(minutes=4)


def test_opposite_candle_only_before_leg_boundary_is_not_selected():
    """Requirements 2/3/4: an opposite-colored candle exists (idx4,
    bearish) but it belongs to a DIFFERENT, earlier leg (event A's own
    origin) - it lies before event B's leg boundary (idx8, the pivot B
    was broken from) and must not be selected for event B. No opposite
    candle exists inside event B's own leg (idx8-idx9, both non-bearish)
    - no Order Block should be created for event B at all, rather than
    reaching back into unrelated prior structure."""
    candles = _canonical_bullish_setup() + [
        _candle(8, 113, 118, 110, 113),  # doji - swing high B pivot (118)
        _candle(9, 111, 114, 111, 113),  # bullish - leg B has no bearish candle
        _candle(10, 113, 120, 112, 119),  # break B (119 > 118)
    ]
    tracker = OrderBlockTracker()
    sync_ob(tracker, candles)

    active = tracker.snapshot()["active"]
    # Only event A's Order Block exists - event B correctly produced none,
    # rather than incorrectly reusing idx4 (event A's own, unrelated origin).
    assert len(active) == 1
    assert active[0]["zone_high"] == 105.0
    assert active[0]["zone_low"] == 101.0


def test_several_opposite_candles_in_leg_selects_the_correct_last_one():
    """Requirement 4: several opposite-colored candles exist within the
    leg - the LAST (most recent, closest to the break) one is selected,
    not the first."""
    candles = _canonical_bullish_setup() + [
        _candle(8, 113, 118, 110, 113),  # doji - swing high B pivot (118)
        _candle(9, 113, 114, 108, 110, volume=20.0),  # bearish (further from break)
        _candle(10, 115, 115, 109, 111, volume=30.0),  # bearish (closer to break)
        _candle(11, 112, 120, 111, 119),  # break B (119 > 118)
    ]
    tracker = OrderBlockTracker()
    sync_ob(tracker, candles)

    active = tracker.snapshot()["active"]
    assert len(active) == 2
    ob_b = max(active, key=lambda ob: ob["origin_timestamp"])
    # The closer bearish candle (idx10) must be selected, not the
    # earlier one (idx9).
    assert ob_b["origin_timestamp"] == START + timedelta(minutes=10)
    assert ob_b["zone_high"] == 115.0
    assert ob_b["zone_low"] == 109.0


def test_bullish_and_bearish_symmetry():
    """Requirement 5."""
    tracker_bull = OrderBlockTracker()
    sync_ob(tracker_bull, _canonical_bullish_setup())
    active_bull = tracker_bull.snapshot()["active"]
    assert len(active_bull) == 1
    assert active_bull[0]["direction"] == "bullish"

    tracker_bear = OrderBlockTracker()
    sync_ob(tracker_bear, _canonical_bearish_setup())
    active_bear = tracker_bear.snapshot()["active"]
    assert len(active_bear) == 1
    assert active_bear[0]["direction"] == "bearish"
    assert active_bear[0]["zone_high"] == 99.0
    assert active_bear[0]["zone_low"] == 95.0


def test_origin_candle_is_always_earlier_than_the_break_event():
    """Requirements 6/7: origin_timestamp must always be strictly
    earlier than created_at (the breaking candle), and never a candle
    that arrived after the break itself."""
    tracker = OrderBlockTracker()
    sync_ob(tracker, _canonical_bullish_setup())

    ob = tracker.snapshot()["active"][0]
    assert ob["origin_timestamp"] < ob["created_at"]


def test_break_event_and_leg_boundary_share_consistent_pivot_identity():
    """Requirement 8: the leg boundary is derived directly from
    structural_break_event.pivot_timestamp, so the leg always starts at
    exactly the candle identified by the break event - not a separately
    (and potentially inconsistently) re-derived pivot."""
    from strategy.features.order_block import _find_impulse_leg

    candles = _canonical_bullish_setup()
    structure = MarketStructureTracker()
    structure.sync(candles)
    event = structure.snapshot()["structural_break_event"]
    assert event is not None

    leg = _find_impulse_leg(candles, event, "timestamp")
    assert leg[0]["timestamp"] == event.pivot_timestamp


def test_long_same_color_momentum_sequence_produces_no_order_block():
    """Requirement 9: a long, uninterrupted same-direction run (no
    opposite-colored candle anywhere in the relevant leg) must not
    cause the search to reach back into earlier, unrelated structure -
    it must simply produce no Order Block for that break."""
    candles = _canonical_bullish_setup()
    price = 111.0
    # A long, purely bullish momentum run - price keeps climbing, no
    # bearish candle at all, eventually breaking a new swing high.
    for i in range(8, 40):
        candles.append(_candle(i, price, price + 3, price - 0.5, price + 2.5))
        price += 2.5

    tracker = OrderBlockTracker()
    sync_ob(tracker, candles)

    active = tracker.snapshot()["active"]
    # Only event A's Order Block (idx4) exists - no unrelated candle was
    # ever selected for any subsequent same-color-run break.
    assert len(active) == 1
    assert active[0]["origin_timestamp"] == START + timedelta(minutes=4)


def test_reset_window_independent_tracker_instances_do_not_share_state():
    """Requirement 10."""
    candles = _canonical_bullish_setup()

    tracker_a = OrderBlockTracker()
    sync_ob(tracker_a, candles)

    tracker_b = OrderBlockTracker()
    sync_ob(tracker_b, candles)

    assert tracker_a.snapshot() == tracker_b.snapshot()


def test_multiple_active_blocks_each_retain_their_own_correct_origin():
    """Requirement 11: several Order Blocks active at once, each
    correctly bounded to its own leg."""
    candles = _canonical_bullish_setup() + [
        _candle(8, 113, 118, 110, 113),
        _candle(9, 113, 114, 111, 109, volume=30.0),  # bearish -> origin B
        _candle(10, 113, 120, 112, 119),  # break B
    ]
    tracker = OrderBlockTracker()
    sync_ob(tracker, candles)

    active = tracker.snapshot()["active"]
    assert len(active) == 2
    zones = sorted((ob["zone_low"], ob["zone_high"]) for ob in active)
    assert zones == [(101.0, 105.0), (111.0, 114.0)]
