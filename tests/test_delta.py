import time
from datetime import datetime, timedelta, timezone

import pytest

from strategy.features.delta import DeltaTracker, calculate_delta

START = datetime(2024, 1, 1, tzinfo=timezone.utc)


def _candle(minute_offset, volume, taker_buy_volume=None):
    candle = {
        "timestamp": START + timedelta(minutes=minute_offset),
        "open": 100.0,
        "high": 101.0,
        "low": 99.0,
        "close": 100.0,
        "volume": volume,
    }

    if taker_buy_volume is not None:
        candle["taker_buy_volume"] = taker_buy_volume

    return candle


# =========================================================
# calculate_delta - unit tests
# =========================================================


def test_bullish_delta_when_buying_dominates():
    result = calculate_delta(_candle(0, volume=100.0, taker_buy_volume=80.0))

    assert result["delta"] == pytest.approx(60.0)  # 80 - 20
    assert result["delta_pct"] == pytest.approx(60.0)
    assert result["delta_direction"] == "BULLISH"
    assert result["delta_strength"] == pytest.approx(60.0)


def test_bearish_delta_when_selling_dominates():
    result = calculate_delta(_candle(0, volume=100.0, taker_buy_volume=20.0))

    assert result["delta"] == pytest.approx(-60.0)
    assert result["delta_pct"] == pytest.approx(-60.0)
    assert result["delta_direction"] == "BEARISH"
    assert result["delta_strength"] == pytest.approx(60.0)


def test_neutral_delta_when_perfectly_balanced():
    result = calculate_delta(_candle(0, volume=100.0, taker_buy_volume=50.0))

    assert result["delta"] == pytest.approx(0.0)
    assert result["delta_direction"] == "NEUTRAL"


def test_delta_strength_is_always_non_negative():
    bullish = calculate_delta(_candle(0, volume=100.0, taker_buy_volume=90.0))
    bearish = calculate_delta(_candle(0, volume=100.0, taker_buy_volume=10.0))

    assert bullish["delta_strength"] >= 0
    assert bearish["delta_strength"] >= 0
    assert bullish["delta_strength"] == pytest.approx(bearish["delta_strength"])


# =========================================================
# Edge cases
# =========================================================


def test_missing_taker_buy_volume_returns_none_not_zero():
    result = calculate_delta(_candle(0, volume=100.0))

    assert result["delta"] is None
    assert result["delta_pct"] is None
    assert result["delta_direction"] is None
    assert result["delta_strength"] is None


def test_missing_volume_returns_none_fields():
    candle = _candle(0, volume=100.0, taker_buy_volume=50.0)
    del candle["volume"]

    result = calculate_delta(candle)

    assert result["delta"] is None


def test_zero_volume_returns_zero_not_none():
    result = calculate_delta(_candle(0, volume=0.0, taker_buy_volume=0.0))

    assert result["delta"] == 0.0
    assert result["delta_pct"] == 0.0
    assert result["delta_direction"] == "NEUTRAL"


def test_all_buying_produces_maximum_positive_delta():
    result = calculate_delta(_candle(0, volume=100.0, taker_buy_volume=100.0))

    assert result["delta"] == pytest.approx(100.0)
    assert result["delta_pct"] == pytest.approx(100.0)


def test_all_selling_produces_maximum_negative_delta():
    result = calculate_delta(_candle(0, volume=100.0, taker_buy_volume=0.0))

    assert result["delta"] == pytest.approx(-100.0)
    assert result["delta_pct"] == pytest.approx(-100.0)


# =========================================================
# DeltaTracker - unit tests
# =========================================================


def test_tracker_starts_at_zero():
    tracker = DeltaTracker()
    snapshot = tracker.snapshot()

    assert snapshot["cumulative_delta"] == 0.0
    assert snapshot["bars_accumulated"] == 0
    assert snapshot["bars_with_missing_data"] == 0
    assert snapshot["delta"] is None
    assert snapshot["delta_pct"] is None
    assert snapshot["delta_direction"] is None
    assert snapshot["delta_strength"] is None


# =========================================================
# Per-bar snapshot fields (Phase 2.1 - Market Intelligence Snapshot
# Builder needs the CURRENT bar's reading, not just the cumulative sum)
# =========================================================


def test_snapshot_exposes_only_the_most_recent_bars_delta():
    tracker = DeltaTracker()

    candles = [
        _candle(0, volume=100.0, taker_buy_volume=80.0),  # +60
        _candle(1, volume=100.0, taker_buy_volume=20.0),  # -60
    ]
    tracker.sync(candles)

    snapshot = tracker.snapshot()
    assert snapshot["delta"] == pytest.approx(-60.0)  # only the LAST bar
    assert snapshot["delta_direction"] == "BEARISH"
    assert snapshot["cumulative_delta"] == pytest.approx(0.0)  # unaffected - still the sum


def test_snapshot_delta_matches_calculate_delta_for_the_same_candle():
    tracker = DeltaTracker()
    candle = _candle(0, volume=100.0, taker_buy_volume=80.0)
    tracker.sync([candle])

    direct = calculate_delta(candle)
    snapshot = tracker.snapshot()

    assert snapshot["delta"] == direct["delta"]
    assert snapshot["delta_pct"] == direct["delta_pct"]
    assert snapshot["delta_direction"] == direct["delta_direction"]
    assert snapshot["delta_strength"] == direct["delta_strength"]


def test_snapshot_delta_is_none_when_most_recent_bar_is_missing_data():
    tracker = DeltaTracker()

    candles = [
        _candle(0, volume=100.0, taker_buy_volume=80.0),
        _candle(1, volume=100.0, taker_buy_volume=None),  # missing
    ]
    tracker.sync(candles)

    snapshot = tracker.snapshot()
    assert snapshot["delta"] is None
    assert snapshot["bars_with_missing_data"] == 1
    assert snapshot["cumulative_delta"] == pytest.approx(60.0)  # only the first bar counted


def test_tracker_accumulates_delta_across_candles():
    tracker = DeltaTracker()

    candles = [
        _candle(0, volume=100.0, taker_buy_volume=80.0),  # +60
        _candle(1, volume=100.0, taker_buy_volume=20.0),  # -60
        _candle(2, volume=100.0, taker_buy_volume=70.0),  # +40
    ]

    tracker.sync(candles)

    snapshot = tracker.snapshot()
    assert snapshot["cumulative_delta"] == pytest.approx(40.0)
    assert snapshot["bars_accumulated"] == 3
    assert snapshot["bars_with_missing_data"] == 0


def test_tracker_skips_missing_data_without_corrupting_total():
    tracker = DeltaTracker()

    candles = [
        _candle(0, volume=100.0, taker_buy_volume=80.0),  # +60
        _candle(1, volume=100.0),  # missing taker_buy_volume - skipped
        _candle(2, volume=100.0, taker_buy_volume=70.0),  # +40
    ]

    tracker.sync(candles)

    snapshot = tracker.snapshot()
    assert snapshot["cumulative_delta"] == pytest.approx(100.0)
    assert snapshot["bars_accumulated"] == 3
    assert snapshot["bars_with_missing_data"] == 1


# =========================================================
# Replay safety
# =========================================================


def test_tracker_rejects_rewound_history():
    tracker = DeltaTracker()
    candles = [_candle(i, volume=100.0, taker_buy_volume=50.0) for i in range(5)]

    tracker.sync(candles)

    with pytest.raises(ValueError):
        tracker.sync(candles[:2])


def test_tracker_rejects_diverging_history():
    tracker = DeltaTracker()
    candles = [_candle(i, volume=100.0, taker_buy_volume=50.0) for i in range(3)]

    tracker.sync(candles)

    diverging = candles[:2] + [_candle(2, volume=999.0, taker_buy_volume=1.0)]

    with pytest.raises(ValueError):
        tracker.sync(diverging)


# =========================================================
# Live compatibility - incremental sync must match single-shot sync
# =========================================================


def test_incremental_sync_matches_single_shot_sync():
    candles = [
        _candle(i, volume=100.0 + i, taker_buy_volume=(50.0 + (i % 7)))
        for i in range(50)
    ]

    incremental = DeltaTracker()
    for i in range(1, len(candles) + 1):
        incremental.sync(candles[:i])

    single_shot = DeltaTracker()
    single_shot.sync(candles)

    assert incremental.snapshot() == single_shot.snapshot()


# =========================================================
# Performance validation
# =========================================================


def test_large_history_stays_fast_and_bounded():
    candle_count = 20_000
    candles = [
        _candle(i, volume=100.0, taker_buy_volume=60.0)
        for i in range(candle_count)
    ]

    tracker = DeltaTracker()

    start_time = time.perf_counter()

    # Simulate a replay: sync repeatedly with a growing history, the
    # same pattern BacktestRunner uses every step.
    step = 500
    for i in range(step, candle_count + 1, step):
        tracker.sync(candles[:i])

    elapsed = time.perf_counter() - start_time

    assert elapsed < 5.0

    snapshot = tracker.snapshot()
    assert snapshot["bars_accumulated"] == candle_count
    assert snapshot["cumulative_delta"] == pytest.approx(candle_count * 20.0)
