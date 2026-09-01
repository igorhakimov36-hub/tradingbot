import time
from datetime import datetime, timedelta, timezone

import pytest

from strategy.features.fair_value_gap import FairValueGapTracker

START = datetime(2024, 1, 1, tzinfo=timezone.utc)


def _candle(minute_offset, open_, high, low, close, volume=100.0):
    return {
        "timestamp": START + timedelta(minutes=minute_offset),
        "open": open_,
        "high": high,
        "low": low,
        "close": close,
        "volume": volume,
    }


def _flat_candles(count, price=100.0):
    """Neutral filler candles with no gaps - just to build up ATR history."""
    return [_candle(i, price, price + 1, price - 1, price) for i in range(count)]


# =========================================================
# Detection - unit tests
# =========================================================


def test_bullish_gap_detected_on_third_candle_close():
    candles = _flat_candles(5, price=100.0) + [
        _candle(5, 100, 101, 99, 100),      # A
        _candle(6, 100, 115, 100, 114),     # B - impulsive up candle
        _candle(7, 116, 120, 116, 118),     # C - low (116) > A.high (101)
    ]

    tracker = FairValueGapTracker()
    tracker.sync(candles)

    snapshot = tracker.snapshot()
    assert len(snapshot["active"]) == 1

    gap = snapshot["active"][0]
    assert gap["direction"] == "bullish"
    assert gap["zone_low"] == 101.0
    assert gap["zone_high"] == 116.0
    assert gap["fill_status"] == "active"
    assert gap["fill_pct"] == 0.0
    assert gap["formation_volume"] == 100.0
    assert gap["age_in_bars"] == 0


def test_bearish_gap_detected_on_third_candle_close():
    candles = _flat_candles(5, price=100.0) + [
        _candle(5, 100, 101, 99, 100),      # A
        _candle(6, 100, 100, 85, 86),       # B - impulsive down candle
        _candle(7, 84, 84, 80, 82),         # C - high (84) < A.low (99)
    ]

    tracker = FairValueGapTracker()
    tracker.sync(candles)

    snapshot = tracker.snapshot()
    assert len(snapshot["active"]) == 1

    gap = snapshot["active"][0]
    assert gap["direction"] == "bearish"
    assert gap["zone_low"] == 84.0
    assert gap["zone_high"] == 99.0


def test_no_gap_when_candles_overlap_normally():
    candles = _flat_candles(10, price=100.0)

    tracker = FairValueGapTracker()
    tracker.sync(candles)

    snapshot = tracker.snapshot()
    assert snapshot["active"] == []
    assert snapshot["filled"] == []


def test_multiple_simultaneous_gaps_are_all_tracked():
    candles = (
        _flat_candles(5, price=100.0)
        + [
            _candle(5, 100, 101, 99, 100),    # A1
            _candle(6, 100, 115, 100, 114),   # B1
            _candle(7, 116, 120, 116, 118),   # C1 - bullish gap #1
            # Two settling candles wide enough to overlap both C1 and
            # A2 on every side, so the sliding 3-candle window does not
            # pick up an unintended extra gap at the boundary.
            _candle(8, 118, 120, 110, 115),
            _candle(9, 115, 120, 110, 118),
            _candle(10, 118, 119, 117, 118),  # A2
            _candle(11, 118, 135, 118, 134),  # B2
            _candle(12, 136, 140, 136, 138),  # C2 - bullish gap #2
        ]
    )

    tracker = FairValueGapTracker()
    tracker.sync(candles)

    snapshot = tracker.snapshot()
    assert len(snapshot["active"]) == 2


# =========================================================
# Fill tracking
# =========================================================


def test_bullish_gap_partially_fills_on_partial_retrace():
    candles = _flat_candles(5, price=100.0) + [
        _candle(5, 100, 101, 99, 100),      # A
        _candle(6, 100, 115, 100, 114),     # B
        _candle(7, 116, 120, 116, 118),     # C - zone [101, 116]
        _candle(8, 118, 118, 108, 110),     # retrace: low=108 -> half filled
    ]

    tracker = FairValueGapTracker()
    tracker.sync(candles)

    gap = tracker.snapshot()["active"][0]
    assert gap["fill_status"] == "partially_filled"
    # (116 - 108) / (116 - 101) = 8/15
    assert gap["fill_pct"] == pytest.approx(8 / 15)


def test_bullish_gap_completely_fills_when_price_reaches_zone_low():
    candles = _flat_candles(5, price=100.0) + [
        _candle(5, 100, 101, 99, 100),      # A
        _candle(6, 100, 115, 100, 114),     # B
        _candle(7, 116, 120, 116, 118),     # C - zone [101, 116]
        _candle(8, 118, 118, 90, 95),       # low=90 <= zone_low(101)
    ]

    tracker = FairValueGapTracker()
    tracker.sync(candles)

    snapshot = tracker.snapshot()
    assert snapshot["active"] == []
    assert len(snapshot["filled"]) == 1
    assert snapshot["filled"][0]["fill_status"] == "completely_filled"
    assert snapshot["filled"][0]["fill_pct"] == 1.0


def test_bearish_gap_fills_on_upward_retrace():
    candles = _flat_candles(5, price=100.0) + [
        _candle(5, 100, 101, 99, 100),      # A
        _candle(6, 100, 100, 85, 86),       # B
        _candle(7, 84, 84, 80, 82),         # C - zone [84, 99]
        _candle(8, 82, 99, 82, 95),         # high=99 -> fully touches zone_high
    ]

    tracker = FairValueGapTracker()
    tracker.sync(candles)

    snapshot = tracker.snapshot()
    assert snapshot["active"] == []
    assert snapshot["filled"][0]["fill_status"] == "completely_filled"


def test_fill_never_exceeds_100_percent_on_deep_overshoot():
    candles = _flat_candles(5, price=100.0) + [
        _candle(5, 100, 101, 99, 100),
        _candle(6, 100, 115, 100, 114),
        _candle(7, 116, 120, 116, 118),
        _candle(8, 118, 118, 10, 15),  # massive overshoot past zone_low
    ]

    tracker = FairValueGapTracker()
    tracker.sync(candles)

    filled = tracker.snapshot()["filled"]
    assert filled[0]["fill_pct"] == 1.0


def test_confirming_candle_itself_does_not_count_as_a_fill():
    # C's own low (116) sits exactly at zone_high - it must not be
    # treated as having already partially filled its own gap.
    candles = _flat_candles(5, price=100.0) + [
        _candle(5, 100, 101, 99, 100),
        _candle(6, 100, 115, 100, 114),
        _candle(7, 116, 120, 116, 118),
    ]

    tracker = FairValueGapTracker()
    tracker.sync(candles)

    gap = tracker.snapshot()["active"][0]
    assert gap["fill_pct"] == 0.0
    assert gap["fill_status"] == "active"


# =========================================================
# ATR-relative sizing
# =========================================================


def test_gap_size_atr_ratio_is_populated_even_on_earliest_possible_gap():
    # ATR needs only 2 candles for its first value (one True Range
    # measurement); FVG detection needs 3. Since 2 <= 3, ATR is always
    # ready by the time the very first gap can possibly be confirmed -
    # there is no real "not enough history yet" window to observe here.
    candles = [
        _candle(0, 100, 101, 99, 100),
        _candle(1, 100, 115, 100, 114),
        _candle(2, 116, 120, 116, 118),
    ]

    tracker = FairValueGapTracker()
    tracker.sync(candles)

    gap = tracker.snapshot()["active"][0]
    assert gap["gap_size_atr_ratio"] is not None
    assert gap["gap_size_atr_ratio"] > 0


def test_gap_size_atr_ratio_is_populated_with_enough_history():
    candles = _flat_candles(20, price=100.0) + [
        _candle(20, 100, 101, 99, 100),
        _candle(21, 100, 115, 100, 114),
        _candle(22, 116, 120, 116, 118),
    ]

    tracker = FairValueGapTracker()
    tracker.sync(candles)

    gap = tracker.snapshot()["active"][0]
    assert gap["gap_size_atr_ratio"] is not None
    assert gap["gap_size_atr_ratio"] > 0


# =========================================================
# Age / distance
# =========================================================


def test_age_in_bars_increases_as_replay_advances():
    candles = _flat_candles(5, price=100.0) + [
        _candle(5, 100, 101, 99, 100),
        _candle(6, 100, 115, 100, 114),
        _candle(7, 116, 120, 116, 118),
        _candle(8, 118, 119, 117, 118),
        _candle(9, 118, 119, 117, 118),
    ]

    tracker = FairValueGapTracker()
    tracker.sync(candles)

    gap = tracker.snapshot()["active"][0]
    assert gap["age_in_bars"] == 2


def test_distance_from_price_is_zero_when_price_inside_zone():
    candles = _flat_candles(5, price=100.0) + [
        _candle(5, 100, 101, 99, 100),
        _candle(6, 100, 115, 100, 114),
        _candle(7, 116, 120, 116, 118),
        _candle(8, 118, 118, 105, 108),  # close now inside the zone
    ]

    tracker = FairValueGapTracker()
    tracker.sync(candles)

    gap = tracker.snapshot()["active"][0]
    assert gap["distance_from_price"] == 0.0


def test_distance_from_price_is_positive_when_price_outside_zone():
    candles = _flat_candles(5, price=100.0) + [
        _candle(5, 100, 101, 99, 100),
        _candle(6, 100, 115, 100, 114),
        _candle(7, 116, 120, 116, 118),  # close = 118, zone_high=116
    ]

    tracker = FairValueGapTracker()
    tracker.sync(candles)

    gap = tracker.snapshot()["active"][0]
    assert gap["distance_from_price"] == pytest.approx(2.0)  # 118 - 116


# =========================================================
# Replay safety
# =========================================================


def test_rejects_rewound_history():
    tracker = FairValueGapTracker()
    candles = _flat_candles(10)

    tracker.sync(candles)

    with pytest.raises(ValueError):
        tracker.sync(candles[:3])


def test_rejects_diverging_history():
    tracker = FairValueGapTracker()
    candles = _flat_candles(5)

    tracker.sync(candles)

    diverging = candles[:4] + [_candle(4, 999, 999, 999, 999)]

    with pytest.raises(ValueError):
        tracker.sync(diverging)


# =========================================================
# Live compatibility - incremental sync must match single-shot sync
# =========================================================


def test_incremental_sync_matches_single_shot_sync():
    candles = (
        _flat_candles(10, price=100.0)
        + [
            _candle(10, 100, 101, 99, 100),
            _candle(11, 100, 115, 100, 114),
            _candle(12, 116, 120, 116, 118),
            _candle(13, 118, 118, 108, 110),
            _candle(14, 110, 111, 90, 95),
        ]
        + _flat_candles(10, price=95.0)
    )
    # Fix up timestamps for the trailing flat block so they continue
    # forward in time rather than overlapping the earlier block.
    for i, candle in enumerate(candles[15:], start=15):
        candle["timestamp"] = START + timedelta(minutes=i)

    incremental = FairValueGapTracker()
    for i in range(1, len(candles) + 1):
        incremental.sync(candles[:i])

    single_shot = FairValueGapTracker()
    single_shot.sync(candles)

    assert incremental.snapshot() == single_shot.snapshot()


# =========================================================
# Edge cases
# =========================================================


def test_expired_gap_is_pruned_and_counted():
    candles = _flat_candles(5, price=100.0) + [
        _candle(5, 100, 101, 99, 100),
        _candle(6, 100, 115, 100, 114),
        _candle(7, 116, 120, 116, 118),
    ]
    # Never retrace - just let time pass well beyond max_age_bars. The
    # exact number of incidental gaps the sliding window also happens
    # to form at the boundary is not the point of this test; what
    # matters is that nothing unfilled survives past max_age_bars.
    candles += [
        _candle(8 + i, 118, 119, 117, 118) for i in range(15)
    ]

    tracker = FairValueGapTracker(max_age_bars=10)
    tracker.sync(candles)

    snapshot = tracker.snapshot()
    assert snapshot["active"] == []
    assert snapshot["expired_count"] >= 1


def test_filled_history_is_bounded_by_max_tracked_filled():
    candles = _flat_candles(3, price=100.0)
    price = 100.0

    for i in range(20):
        base = 3 + i * 3
        candles += [
            _candle(base, price, price + 1, price - 1, price),
            _candle(base + 1, price, price + 20, price, price + 19),
            _candle(base + 2, price + 21, price + 25, price + 21, price + 23),
            _candle(base + 3, price + 23, price + 23, price - 5, price),
        ]
        price += 0.01  # keep candles trending slightly to form fresh gaps

    tracker = FairValueGapTracker(max_tracked_filled=5)
    tracker.sync(candles)

    assert len(tracker.snapshot()["filled"]) <= 5


def test_snapshot_before_any_candle_is_empty():
    tracker = FairValueGapTracker()
    snapshot = tracker.snapshot()

    assert snapshot == {"active": [], "filled": [], "expired_count": 0}


# =========================================================
# Performance validation
# =========================================================


def test_large_history_stays_fast_and_bounded():
    candle_count = 20_000
    candles = _flat_candles(candle_count, price=100.0)

    tracker = FairValueGapTracker()

    start_time = time.perf_counter()

    step = 500
    for i in range(step, candle_count + 1, step):
        tracker.sync(candles[:i])

    elapsed = time.perf_counter() - start_time

    assert elapsed < 5.0
    assert tracker.snapshot() == {"active": [], "filled": [], "expired_count": 0}
