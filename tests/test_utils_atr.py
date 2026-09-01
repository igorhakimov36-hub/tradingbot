from datetime import datetime, timedelta, timezone

import pytest

from strategy.features.utils import AverageTrueRangeTracker, true_range

START = datetime(2024, 1, 1, tzinfo=timezone.utc)


def _candle(minute_offset, high, low, close):
    return {
        "timestamp": START + timedelta(minutes=minute_offset),
        "open": close,
        "high": high,
        "low": low,
        "close": close,
        "volume": 1.0,
    }


def test_true_range_uses_largest_of_three_measures():
    candle = _candle(0, high=110, low=95, close=100)

    # high-low = 15, |high-prev_close|=10, |low-prev_close|=5 -> max=15
    assert true_range(candle, previous_close=100) == 15

    # high-low = 15, |high-prev_close|=30, |low-prev_close|=45 -> max=45
    assert true_range(candle, previous_close=140) == 45


def test_atr_is_none_before_two_candles():
    tracker = AverageTrueRangeTracker(period=3)
    tracker.sync([_candle(0, 105, 95, 100)])

    assert tracker.current() is None


def test_atr_averages_true_ranges_within_period():
    tracker = AverageTrueRangeTracker(period=3)

    candles = [
        _candle(0, 105, 95, 100),   # no TR yet (first candle)
        _candle(1, 110, 100, 105),  # TR = max(10, 10, 5) = 10
        _candle(2, 112, 104, 108),  # TR = max(8, 7, 1) = 8
    ]

    tracker.sync(candles)

    assert tracker.current() == pytest.approx((10 + 8) / 2)


def test_atr_rolls_off_oldest_value_beyond_period():
    tracker = AverageTrueRangeTracker(period=2)

    candles = [
        _candle(0, 100, 100, 100),
        _candle(1, 120, 100, 110),  # TR = 20
        _candle(2, 111, 109, 110),  # TR = 2
        _candle(3, 111, 109, 110),  # TR = 2
    ]

    tracker.sync(candles)

    # period=2 -> only the last two TR values (2, 2) should remain.
    assert tracker.current() == pytest.approx(2.0)


def test_ingest_one_matches_sync_incrementally():
    candles = [
        _candle(i, 100 + i + 5, 100 + i - 5, 100 + i)
        for i in range(20)
    ]

    via_sync = AverageTrueRangeTracker(period=5)
    via_sync.sync(candles)

    via_ingest_one = AverageTrueRangeTracker(period=5)
    for candle in candles:
        via_ingest_one.ingest_one(candle)

    assert via_sync.current() == pytest.approx(via_ingest_one.current())


def test_rejects_rewound_history():
    tracker = AverageTrueRangeTracker(period=3)
    candles = [_candle(i, 105, 95, 100) for i in range(5)]

    tracker.sync(candles)

    with pytest.raises(ValueError):
        tracker.sync(candles[:2])
