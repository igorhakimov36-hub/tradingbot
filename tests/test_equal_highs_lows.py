import time
from datetime import datetime, timedelta, timezone

import pytest

from strategy.features.equal_highs_lows import EqualLevelsTracker

START = datetime(2024, 1, 1, tzinfo=timezone.utc)


def _candle(minute_offset, high, low, close, open_=None):
    return {
        "timestamp": START + timedelta(minutes=minute_offset),
        "open": open_ if open_ is not None else close,
        "high": high,
        "low": low,
        "close": close,
        "volume": 1.0,
    }


def _baseline(count, start=0, high=100.0, low=90.0, close=95.0):
    return [_candle(start + i, high, low, close) for i in range(count)]


def _two_close_high_pivots(start_index):
    """
    Two swing-high pivots close together (110 and 111), separated by
    baseline candles - close enough to cluster under any reasonable
    ATR-relative tolerance.
    """
    return (
        _baseline(2, start=start_index)
        + [_candle(start_index + 2, 110.0, 95.0, 100.0)]  # pivot candidate #1
        + _baseline(2, start=start_index + 3)
        + [_candle(start_index + 5, 111.0, 95.0, 100.0)]  # pivot candidate #2
        + _baseline(2, start=start_index + 6)
    )


# =========================================================
# Pivot confirmation / clustering - unit tests
# =========================================================


def test_single_pivot_alone_forms_no_cluster():
    candles = _baseline(2) + [_candle(2, 110.0, 95.0, 100.0)] + _baseline(3, start=3)

    tracker = EqualLevelsTracker()
    tracker.sync(candles)

    snapshot = tracker.snapshot()
    assert snapshot["equal_highs"] == []


def test_two_close_pivots_form_a_cluster():
    candles = _two_close_high_pivots(0)

    tracker = EqualLevelsTracker()
    tracker.sync(candles)

    clusters = tracker.snapshot()["equal_highs"]
    assert len(clusters) == 1
    assert clusters[0]["pivot_count"] == 2
    assert clusters[0]["pivot_prices"] == [110.0, 111.0]
    assert clusters[0]["max_deviation"] == pytest.approx(1.0)
    assert clusters[0]["level"] == pytest.approx(110.5)


def test_far_apart_pivots_do_not_cluster():
    candles = (
        _baseline(2)
        + [_candle(2, 110.0, 95.0, 100.0)]
        + _baseline(2, start=3)
        + [_candle(5, 500.0, 95.0, 100.0)]  # wildly different level
        + _baseline(2, start=6)
    )

    tracker = EqualLevelsTracker()
    tracker.sync(candles)

    assert tracker.snapshot()["equal_highs"] == []


def test_third_pivot_extends_existing_cluster():
    candles = (
        _two_close_high_pivots(0)
        + _baseline(2, start=8)
        + [_candle(10, 109.5, 95.0, 100.0)]  # third close pivot
        + _baseline(2, start=11)
    )

    tracker = EqualLevelsTracker()
    tracker.sync(candles)

    clusters = tracker.snapshot()["equal_highs"]
    assert len(clusters) == 1
    assert clusters[0]["pivot_count"] == 3


def test_equal_lows_symmetric_to_equal_highs():
    candles = (
        _baseline(2, high=100.0, low=90.0, close=95.0)
        + [_candle(2, 100.0, 80.0, 90.0)]  # low pivot candidate #1
        + _baseline(2, start=3, high=100.0, low=90.0, close=95.0)
        + [_candle(5, 100.0, 81.0, 90.0)]  # low pivot candidate #2
        + _baseline(2, start=6, high=100.0, low=90.0, close=95.0)
    )

    tracker = EqualLevelsTracker()
    tracker.sync(candles)

    clusters = tracker.snapshot()["equal_lows"]
    assert len(clusters) == 1
    assert clusters[0]["direction"] == "equal_lows"
    assert clusters[0]["pivot_prices"] == [80.0, 81.0]


# =========================================================
# Sweep detection
# =========================================================


def test_sweep_detected_on_wick_beyond_then_close_back_inside():
    candles = _two_close_high_pivots(0) + [
        _candle(8, 115.0, 108.0, 109.0),  # wicks above 110.5, closes back below
    ]

    tracker = EqualLevelsTracker()
    tracker.sync(candles)

    cluster = tracker.snapshot()["equal_highs"][0]
    assert cluster["swept_status"] == "swept"
    assert cluster["swept_timestamp"] is not None


def test_no_sweep_when_wick_beyond_but_closes_beyond_too():
    candles = _two_close_high_pivots(0) + [
        _candle(8, 115.0, 112.0, 114.0),  # stays above the level at close
    ]

    tracker = EqualLevelsTracker()
    tracker.sync(candles)

    cluster = tracker.snapshot()["equal_highs"][0]
    assert cluster["swept_status"] == "unswept"


def test_swept_cluster_stays_swept_and_does_not_re_check():
    candles = (
        _two_close_high_pivots(0)
        + [_candle(8, 115.0, 108.0, 109.0)]  # sweep #1
        + [_candle(9, 120.0, 118.0, 119.0)]  # would "re-sweep" if not frozen
    )

    tracker = EqualLevelsTracker()
    tracker.sync(candles)

    cluster = tracker.snapshot()["equal_highs"][0]
    assert cluster["swept_status"] == "swept"
    assert cluster["swept_timestamp"] == (START + timedelta(minutes=8))


# =========================================================
# Distance / age
# =========================================================


def test_distance_from_price_reflects_current_close():
    candles = _two_close_high_pivots(0)

    tracker = EqualLevelsTracker()
    tracker.sync(candles)

    cluster = tracker.snapshot()["equal_highs"][0]
    last_close = candles[-1]["close"]
    assert cluster["distance_from_price"] == pytest.approx(abs(last_close - cluster["level"]))


def test_age_in_bars_increases_as_replay_advances():
    candles = _two_close_high_pivots(0) + _baseline(3, start=8)

    tracker = EqualLevelsTracker()
    tracker.sync(candles)

    cluster = tracker.snapshot()["equal_highs"][0]
    # cluster forms at the second pivot's confirmation bar (index 6,
    # since the pivot candle itself is at index 5 and confirms on the
    # following candle) - replay has advanced 3 more candles since.
    assert cluster["age_in_bars"] >= 3


# =========================================================
# Replay safety
# =========================================================


def test_rejects_rewound_history():
    tracker = EqualLevelsTracker()
    candles = _baseline(10)

    tracker.sync(candles)

    with pytest.raises(ValueError):
        tracker.sync(candles[:3])


def test_rejects_diverging_history():
    tracker = EqualLevelsTracker()
    candles = _baseline(5)

    tracker.sync(candles)

    diverging = candles[:4] + [_candle(4, 999, 999, 999)]

    with pytest.raises(ValueError):
        tracker.sync(diverging)


# =========================================================
# Live compatibility - incremental sync must match single-shot sync
# =========================================================


def test_incremental_sync_matches_single_shot_sync():
    candles = _two_close_high_pivots(0) + [
        _candle(8, 115.0, 108.0, 109.0),
    ] + _baseline(5, start=9)

    incremental = EqualLevelsTracker()
    for i in range(1, len(candles) + 1):
        incremental.sync(candles[:i])

    single_shot = EqualLevelsTracker()
    single_shot.sync(candles)

    assert incremental.snapshot() == single_shot.snapshot()


# =========================================================
# Edge cases
# =========================================================


def test_snapshot_before_any_candle_is_empty():
    tracker = EqualLevelsTracker()
    assert tracker.snapshot() == {
        "equal_highs": [],
        "equal_lows": [],
        "expired_count": 0,
    }


def test_expired_cluster_is_pruned_and_counted():
    candles = _two_close_high_pivots(0) + _baseline(20, start=8)

    tracker = EqualLevelsTracker(max_age_bars=5)
    tracker.sync(candles)

    snapshot = tracker.snapshot()
    assert snapshot["equal_highs"] == []
    assert snapshot["expired_count"] >= 1


def test_tracked_pivot_list_is_bounded():
    # Many isolated, never-clustering pivots (far apart every time).
    candles = []
    level = 100.0
    for i in range(50):
        base = i * 4
        candles += _baseline(2, start=base, high=level, low=level - 10, close=level - 5)
        candles.append(_candle(base + 2, level + 50, level - 10, level - 5))
        level += 200  # always far from the previous pivot

    tracker = EqualLevelsTracker(max_tracked_pivots=10)
    tracker.sync(candles)

    assert len(tracker._pivot_highs) <= 10


def test_zero_atr_uses_zero_tolerance_not_a_crash():
    # First few candles: ATR has no data yet (None), tolerance must
    # fall back to 0.0 rather than raising or clustering everything.
    candles = [
        _candle(0, 100.0, 90.0, 95.0),
        _candle(1, 110.0, 95.0, 100.0),
        _candle(2, 100.0, 90.0, 95.0),
    ]

    tracker = EqualLevelsTracker()
    tracker.sync(candles)  # must not raise

    assert tracker.snapshot()["equal_highs"] == []


# =========================================================
# Performance validation
# =========================================================


def test_large_history_stays_fast_and_bounded():
    candle_count = 20_000
    candles = _baseline(candle_count, high=100.0, low=90.0, close=95.0)

    tracker = EqualLevelsTracker()

    start_time = time.perf_counter()

    step = 500
    for i in range(step, candle_count + 1, step):
        tracker.sync(candles[:i])

    elapsed = time.perf_counter() - start_time

    assert elapsed < 5.0
    assert tracker.snapshot() == {
        "equal_highs": [],
        "equal_lows": [],
        "expired_count": 0,
    }
