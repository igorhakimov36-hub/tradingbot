import time as time_module
from datetime import datetime, timedelta, timezone

import pytest

from strategy.features.correlation import (
    COMMON_SMT_PAIRS,
    CorrelationTracker,
    SMTPair,
    _lagged_pearson,
    _pearson,
)

START = datetime(2024, 1, 1, tzinfo=timezone.utc)


def _candle(minute_offset, close, high=None, low=None):
    if high is None:
        high = close + 1
    if low is None:
        low = close - 1

    return {
        "timestamp": START + timedelta(minutes=minute_offset),
        "open": close,
        "high": high,
        "low": low,
        "close": close,
        "volume": 10.0,
    }


def _series(closes, high_offset=1.0, low_offset=1.0):
    return [
        _candle(i, c, high=c + high_offset, low=c - low_offset)
        for i, c in enumerate(closes)
    ]


# =========================================================
# Pure correlation math
# =========================================================


def test_pearson_perfect_positive_correlation():
    assert _pearson([1, 2, 3, 4], [10, 20, 30, 40]) == pytest.approx(1.0)


def test_pearson_perfect_negative_correlation():
    assert _pearson([1, 2, 3, 4], [40, 30, 20, 10]) == pytest.approx(-1.0)


def test_pearson_zero_variance_is_none():
    assert _pearson([1, 1, 1], [1, 2, 3]) is None


def test_pearson_needs_at_least_two_points():
    assert _pearson([1], [1]) is None


def test_lagged_pearson_detects_primary_leading():
    # reference[t] = primary[t-2] -> primary leads reference by 2 bars
    primary = [1, 5, 2, 8, 1, 9, 3, 7, 2, 6, 1, 8]
    reference = [0, 0] + primary[:-2]

    best_lag, best_corr = None, 0.0
    for lag in range(-4, 5):
        c = _lagged_pearson(primary, reference, lag, window=8)
        if c is not None and abs(c) > abs(best_corr):
            best_lag, best_corr = lag, c

    assert best_lag == 2
    assert best_corr == pytest.approx(1.0)


def test_lagged_pearson_detects_reference_leading():
    # primary[t] = reference[t-3] -> reference leads primary by 3 bars
    reference = [1, 5, 2, 8, 1, 9, 3, 7, 2, 6, 1, 8]
    primary = [0, 0, 0] + reference[:-3]

    best_lag, best_corr = None, 0.0
    for lag in range(-4, 5):
        c = _lagged_pearson(primary, reference, lag, window=8)
        if c is not None and abs(c) > abs(best_corr):
            best_lag, best_corr = lag, c

    assert best_lag == -3
    assert best_corr == pytest.approx(1.0)


# =========================================================
# Basic wiring / validation
# =========================================================


def test_snapshot_before_any_candle_has_none_windowed_stats():
    tracker = CorrelationTracker(window=3, max_lag=2)
    snap = tracker.snapshot()

    assert snap["price_correlation"] is None
    assert snap["relative_strength_ratio"] is None
    assert snap["relative_strength_change_over_window"] is None
    assert snap["lead_lag_bars"] is None
    assert snap["structural_agreement"] == "insufficient_data"
    assert snap["structural_divergence_flag"] == "none"
    assert snap["bars_since_start"] == 0


def test_relative_strength_ratio_tracks_current_prices():
    tracker = CorrelationTracker(window=3, max_lag=1)
    primary = _series([100, 102])
    reference = _series([50, 51])

    tracker.sync(primary, reference)

    assert tracker.snapshot()["relative_strength_ratio"] == pytest.approx(102 / 51)


def test_timestamp_mismatch_raises():
    tracker = CorrelationTracker(window=3, max_lag=1)
    primary = _series([100, 101])
    reference = [_candle(0, 50), _candle(5, 51)]  # different timestamp at index 1

    with pytest.raises(ValueError):
        tracker.sync(primary, reference)


def test_sync_rejects_rewound_history():
    tracker = CorrelationTracker(window=3, max_lag=1)
    primary = _series([100, 101, 102])
    reference = _series([50, 51, 52])

    tracker.sync(primary, reference)

    with pytest.raises(ValueError):
        tracker.sync(primary[:1], reference[:1])


def test_sync_rejects_diverging_history():
    tracker = CorrelationTracker(window=3, max_lag=1)
    primary = _series([100, 101])
    reference = _series([50, 51])

    tracker.sync(primary, reference)

    diverged_primary = _series([999, 998])
    with pytest.raises(ValueError):
        tracker.sync(diverged_primary, reference)


def test_reference_shorter_than_primary_processes_only_overlap():
    tracker = CorrelationTracker(window=3, max_lag=1)
    primary = _series([100, 101, 102, 103])
    reference = _series([50, 51])  # shorter - hasn't "started" yet for bars 2,3

    tracker.sync(primary, reference)
    assert tracker.snapshot()["bars_since_start"] == 2

    # reference catches up
    reference = _series([50, 51, 52, 53])
    tracker.sync(primary, reference)
    assert tracker.snapshot()["bars_since_start"] == 4


def test_window_below_two_is_rejected():
    with pytest.raises(ValueError):
        CorrelationTracker(window=1)


def test_negative_max_lag_is_rejected():
    with pytest.raises(ValueError):
        CorrelationTracker(max_lag=-1)


# =========================================================
# Price correlation over a window
# =========================================================


def test_price_correlation_none_before_window_fills():
    tracker = CorrelationTracker(window=5, max_lag=1)
    primary = _series([100, 101, 102])
    reference = _series([50, 51, 52])

    tracker.sync(primary, reference)
    assert tracker.snapshot()["price_correlation"] is None


def test_price_correlation_high_when_returns_move_together():
    tracker = CorrelationTracker(window=5, max_lag=1)
    primary_closes = [100, 102, 101, 104, 103, 106]
    # reference moves in the same direction each bar, different magnitude
    reference_closes = [50, 51, 50.5, 52, 51.5, 53]

    tracker.sync(_series(primary_closes), _series(reference_closes))

    corr = tracker.snapshot()["price_correlation"]
    assert corr is not None
    assert corr > 0.9


def test_price_correlation_negative_when_returns_move_opposite():
    tracker = CorrelationTracker(window=5, max_lag=1)
    primary_closes = [100, 102, 101, 104, 103, 106]
    reference_closes = [50, 49, 49.5, 48, 48.5, 47]  # inverse moves

    tracker.sync(_series(primary_closes), _series(reference_closes))

    corr = tracker.snapshot()["price_correlation"]
    assert corr is not None
    assert corr < -0.9


# =========================================================
# Relative strength change over window
# =========================================================


def test_relative_strength_change_over_window():
    tracker = CorrelationTracker(window=3, max_lag=1)
    # primary constant, reference constant -> ratio constant across window,
    # then primary jumps -> ratio changes measurably.
    primary_closes = [100, 100, 100, 200]
    reference_closes = [50, 50, 50, 50]

    tracker.sync(_series(primary_closes), _series(reference_closes))

    snap = tracker.snapshot()
    # window=3 samples: ratios [100/50, 100/50, 200/50] = [2, 2, 4]
    assert snap["relative_strength_change_over_window"] == pytest.approx(1.0)  # (4-2)/2


# =========================================================
# Structural agreement / divergence
# =========================================================


def _uptrend_series(count, start=100, step=5):
    """A clean zig-zag uptrend producing confirmed higher-high/higher-low pivots."""
    closes = []
    price = start
    for i in range(count):
        if i % 2 == 0:
            price += step
        else:
            price -= step / 2
        closes.append(price)
    return closes


def test_structural_agreement_both_bullish():
    tracker = CorrelationTracker(window=3, max_lag=1)

    primary_closes = _uptrend_series(12)
    reference_closes = _uptrend_series(12, start=50, step=3)

    tracker.sync(_series(primary_closes, high_offset=0.1, low_offset=0.1), _series(reference_closes, high_offset=0.1, low_offset=0.1))

    assert tracker.snapshot()["structural_agreement"] == "both_bullish"


def test_structural_divergence_primary_new_high_reference_not():
    tracker = CorrelationTracker(window=3, max_lag=1)

    # Primary: clean zig-zag uptrend -> confirmed higher highs.
    primary_closes = [100, 110, 105, 120, 112, 130, 118]
    # Reference: zig-zag but each high LOWER than the previous high.
    reference_closes = [50, 60, 55, 58, 54, 56, 53]

    primary_candles = _series(primary_closes, high_offset=0.1, low_offset=0.1)
    reference_candles = _series(reference_closes, high_offset=0.1, low_offset=0.1)

    tracker.sync(primary_candles, reference_candles)

    snap = tracker.snapshot()
    assert snap["structural_divergence_flag"] == "bearish_divergence"
    # The sustained zig-zag keeps confirming divergence at each new
    # pivot, not just the last one - history retains all of them.
    assert len(snap["structural_divergence_history"]) >= 1
    assert all(e["direction"] == "bearish_divergence" for e in snap["structural_divergence_history"])
    assert snap["structural_divergence_history"][-1]["primary_price"] == primary_candles[-1]["close"]


def test_structural_divergence_primary_new_low_reference_not():
    tracker = CorrelationTracker(window=3, max_lag=1)

    # Primary: zig-zag downtrend -> confirmed lower lows.
    primary_closes = [130, 120, 125, 110, 118, 100, 112]
    # Reference: zig-zag but each low HIGHER than the previous low.
    reference_closes = [50, 45, 48, 46, 49, 47, 50]

    primary_candles = _series(primary_closes, high_offset=0.1, low_offset=0.1)
    reference_candles = _series(reference_closes, high_offset=0.1, low_offset=0.1)

    tracker.sync(primary_candles, reference_candles)

    snap = tracker.snapshot()
    assert snap["structural_divergence_flag"] == "bullish_divergence"
    assert len(snap["structural_divergence_history"]) >= 1
    assert all(e["direction"] == "bullish_divergence" for e in snap["structural_divergence_history"])


def test_divergence_history_accumulates_multiple_events_and_stays_bounded():
    tracker = CorrelationTracker(window=3, max_lag=1, max_tracked_divergence_events=2)

    # Three separate bearish-divergence-producing legs back to back.
    primary_closes = [100, 110, 105, 120, 112, 130, 118, 140, 128, 150, 138]
    reference_closes = [50, 60, 55, 58, 54, 56, 53, 55, 52, 54, 51]

    primary_candles = _series(primary_closes, high_offset=0.1, low_offset=0.1)
    reference_candles = _series(reference_closes, high_offset=0.1, low_offset=0.1)

    tracker.sync(primary_candles, reference_candles)

    history = tracker.snapshot()["structural_divergence_history"]
    assert len(history) == 2  # bounded by max_tracked_divergence_events
    assert all(e["direction"] == "bearish_divergence" for e in history)


def test_divergence_history_empty_before_any_divergence():
    tracker = CorrelationTracker(window=3, max_lag=1)

    primary_candles = _series(_uptrend_series(12))
    reference_candles = _series(_uptrend_series(12, start=50, step=3))

    tracker.sync(primary_candles, reference_candles)

    assert tracker.snapshot()["structural_divergence_history"] == []


# =========================================================
# SMT - documented configuration, not a new tracker (Phase 1.11)
# =========================================================


def test_common_smt_pairs_are_well_formed():
    names = [pair.name for pair in COMMON_SMT_PAIRS]
    assert len(names) == len(set(names))  # unique names

    for pair in COMMON_SMT_PAIRS:
        assert isinstance(pair, SMTPair)
        assert pair.primary_symbol
        assert pair.reference_symbol
        assert pair.primary_symbol != pair.reference_symbol


def test_smt_pair_is_just_a_correlation_tracker_configuration():
    # No new class, no new detection logic - constructing a
    # CorrelationTracker for a named SMT pair and reading its existing
    # structural outputs IS the SMT check.
    btc_eth = next(p for p in COMMON_SMT_PAIRS if p.name == "btc_eth")
    assert btc_eth.primary_symbol == "BTCUSDT"
    assert btc_eth.reference_symbol == "ETHUSDT"

    tracker = CorrelationTracker(timeframe="15m", window=3, max_lag=1)

    primary_candles = _series([100, 110, 105, 120, 112, 130, 118], high_offset=0.1, low_offset=0.1)
    reference_candles = _series([50, 60, 55, 58, 54, 56, 53], high_offset=0.1, low_offset=0.1)

    tracker.sync(primary_candles, reference_candles)

    snap = tracker.snapshot()
    assert snap["structural_divergence_flag"] == "bearish_divergence"


# =========================================================
# Determinism
# =========================================================


def test_two_independent_incremental_replays_are_deterministic():
    primary_closes = [100 + (i % 7) - 3 for i in range(30)]
    reference_closes = [50 + (i % 5) - 2 for i in range(30)]
    primary = _series(primary_closes)
    reference = _series(reference_closes)

    replay_a = CorrelationTracker(window=5, max_lag=3)
    replay_b = CorrelationTracker(window=5, max_lag=3)

    for n in range(1, len(primary) + 1):
        replay_a.sync(primary[:n], reference[:n])
        replay_b.sync(primary[:n], reference[:n])

    assert replay_a.snapshot() == replay_b.snapshot()


def test_incremental_matches_single_shot():
    primary_closes = [100 + (i % 7) - 3 for i in range(30)]
    reference_closes = [50 + (i % 5) - 2 for i in range(30)]
    primary = _series(primary_closes)
    reference = _series(reference_closes)

    incremental = CorrelationTracker(window=5, max_lag=3)
    for n in range(1, len(primary) + 1):
        incremental.sync(primary[:n], reference[:n])

    single_shot = CorrelationTracker(window=5, max_lag=3)
    single_shot.sync(primary, reference)

    assert incremental.snapshot() == single_shot.snapshot()


# =========================================================
# Performance validation
# =========================================================


def test_large_history_stays_fast_and_bounded():
    candle_count = 20_000
    primary_closes = [100 + (i % 11) for i in range(candle_count)]
    reference_closes = [50 + (i % 9) for i in range(candle_count)]
    primary = _series(primary_closes)
    reference = _series(reference_closes)

    tracker = CorrelationTracker(window=20, max_lag=10)

    start_time = time_module.perf_counter()

    step = 500
    for i in range(step, candle_count + 1, step):
        tracker.sync(primary[:i], reference[:i])

    elapsed = time_module.perf_counter() - start_time

    assert elapsed < 5.0
