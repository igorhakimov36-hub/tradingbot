"""
Module Logic Correction 2, Phase 2A - confirms OrderBlockTracker's
event-consumption fix against the exact confirmed defect: a
direction-only "did BOS change" comparison collapsed a sustained trend
that broke several distinct structural levels in sequence into a
single detected Order Block. Demonstrated FAILING against the pre-2A
code (see docs/module_correction2_order_block_report.md); these tests
confirm it now passes.
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


def _bullish_two_level_setup():
    """Breaks swing high A (110, origin candle idx4) at candle idx7,
    then a distinct, higher swing high B (118, origin candle idx9) is
    confirmed and broken at candle idx10 - bos stays BULLISH_BOS
    continuously from idx7 onward, with no intervening NO_BOS."""
    return [
        _candle(0, 100, 101, 99, 100),
        _candle(1, 100, 102, 88, 101),
        _candle(2, 101, 103, 95, 102),
        _candle(3, 102, 110, 100, 103),
        _candle(4, 104, 105, 101, 101, volume=50.0),  # origin A (bearish)
        _candle(5, 101, 104, 100, 103),
        _candle(6, 103, 108, 102, 107),
        _candle(7, 107, 112, 106, 111),  # break A (111 > 110)
        _candle(8, 113, 118, 110, 113),
        _candle(9, 113, 114, 111, 109, volume=30.0),  # bearish -> origin B
        _candle(10, 113, 120, 112, 119),  # break B (119 > 118)
    ]


def _bearish_two_level_setup():
    """Mirror image: breaks swing low A (90) at idx7, then a distinct,
    lower swing low B (82) is confirmed and broken at idx10 - bos stays
    BEARISH_BOS continuously with no intervening NO_BOS."""
    return [
        _candle(0, 100, 101, 99, 100),
        _candle(1, 100, 112, 98, 99),
        _candle(2, 99, 105, 97, 98),
        _candle(3, 98, 100, 90, 97),
        _candle(4, 96, 99, 95, 99, volume=50.0),  # origin A (bullish)
        _candle(5, 99, 100, 96, 97),
        _candle(6, 97, 98, 92, 93),
        _candle(7, 93, 94, 88, 89),  # break A (89 < 90)
        _candle(8, 87, 90, 82, 87),
        _candle(9, 87, 89, 84, 91, volume=30.0),  # bullish -> origin B
        _candle(10, 87, 88, 80, 81),  # break B (81 < 82)
    ]


def test_bullish_distinct_levels_each_produce_their_own_order_block():
    candles = _bullish_two_level_setup()
    tracker = OrderBlockTracker()
    sync_ob(tracker, candles)

    active = tracker.snapshot()["active"]
    assert len(active) == 2

    zones = sorted((ob["zone_low"], ob["zone_high"]) for ob in active)
    assert zones == [(101.0, 105.0), (111.0, 114.0)]
    assert all(ob["direction"] == "bullish" for ob in active)


def test_bearish_distinct_levels_each_produce_their_own_order_block():
    candles = _bearish_two_level_setup()
    tracker = OrderBlockTracker()
    sync_ob(tracker, candles)

    active = tracker.snapshot()["active"]
    assert len(active) == 2

    zones = sorted((ob["zone_low"], ob["zone_high"]) for ob in active)
    assert zones == [(84.0, 89.0), (95.0, 99.0)]
    assert all(ob["direction"] == "bearish" for ob in active)


def test_repeated_candles_beyond_same_level_do_not_create_duplicate_blocks():
    candles = _bullish_two_level_setup() + [
        _candle(11, 119, 122, 118, 121),
        _candle(12, 121, 124, 120, 123),
    ]
    tracker = OrderBlockTracker()
    sync_ob(tracker, candles)

    assert len(tracker.snapshot()["active"]) == 2


def test_event_consumption_survives_repeated_snapshot_calls():
    candles = _bullish_two_level_setup()
    tracker = OrderBlockTracker()
    sync_ob(tracker, candles)

    first = tracker.snapshot()["active"]
    second = tracker.snapshot()["active"]
    assert len(first) == len(second) == 2
