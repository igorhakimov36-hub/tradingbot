"""
Tests for strategy/research/liquidity_pool_touch_volume.py.
"""

from datetime import datetime, timedelta, timezone

from strategy.research.liquidity_pool_touch_volume import (
    bucket_1m_candles,
    candle_zone_relative_volumes,
    candle_zone_volume,
    relative_volume_series,
    zone_overlapping_1m_indices,
)

START = datetime(2024, 1, 1, tzinfo=timezone.utc)


def _c1m(minute_offset, low, high, volume):
    return {"timestamp": START + timedelta(minutes=minute_offset), "low": low, "high": high, "volume": volume}


# =========================================================
# Requirement 7: non-overlapping 1-minute candles contribute zero
# =========================================================


def test_non_overlapping_1m_candles_excluded_entirely():
    candles = [_c1m(0, 90, 92, 100.0), _c1m(1, 101, 102, 50.0), _c1m(2, 200, 201, 999.0)]
    overlapping = zone_overlapping_1m_indices([0, 1, 2], candles, zone_low=100.0, zone_high=105.0)
    assert overlapping == [1]
    assert candle_zone_volume(overlapping, candles) == 50.0


def test_zero_zone_volume_when_no_1m_candle_overlaps():
    candles = [_c1m(0, 90, 92, 100.0), _c1m(1, 200, 201, 999.0)]
    overlapping = zone_overlapping_1m_indices([0, 1], candles, zone_low=100.0, zone_high=105.0)
    assert overlapping == []
    assert candle_zone_volume(overlapping, candles) == 0.0


# =========================================================
# Requirement 6 & 8: only completed, causal volume; no future leakage
# =========================================================


def test_relative_volume_uses_only_strictly_prior_candles():
    # 300 candles of constant volume=10, then one huge spike at the end.
    candles = [_c1m(i, 100, 101, 10.0) for i in range(300)]
    candles[-1]["volume"] = 100000.0  # a future spike

    series = relative_volume_series(candles, lookback_minutes=240, min_warmup=240)

    # Candle 250's relative volume must be computed from candles
    # [10:250) only - it cannot possibly "see" the spike at index 299.
    assert series[250] == 10.0 / 10.0  # baseline is still 10 (median of prior window)


def test_changing_a_future_candle_does_not_change_an_earlier_relative_volume():
    candles_a = [_c1m(i, 100, 101, 10.0) for i in range(300)]
    candles_b = [_c1m(i, 100, 101, 10.0) for i in range(300)]
    candles_b[299]["volume"] = 999999.0

    series_a = relative_volume_series(candles_a, lookback_minutes=240, min_warmup=240)
    series_b = relative_volume_series(candles_b, lookback_minutes=240, min_warmup=240)

    assert series_a[:299] == series_b[:299]


def test_relative_volume_none_during_warmup():
    candles = [_c1m(i, 100, 101, 10.0) for i in range(100)]
    series = relative_volume_series(candles, lookback_minutes=240, min_warmup=240)
    assert all(v is None for v in series)


def test_relative_volume_defined_after_warmup():
    candles = [_c1m(i, 100, 101, 10.0) for i in range(250)]
    candles[249]["volume"] = 20.0
    series = relative_volume_series(candles, lookback_minutes=240, min_warmup=240)
    assert series[249] == 2.0  # 20 / median(10,...,10) = 2.0


def test_candle_zone_relative_volumes_skips_warmup_none():
    relative_volumes = [None, None, 1.5, 2.0]
    result = candle_zone_relative_volumes([0, 1, 2, 3], relative_volumes)
    assert result == [1.5, 2.0]


# =========================================================
# bucket_1m_candles: 15m -> constituent 1m candles
# =========================================================


def test_bucket_1m_candles_returns_correct_window():
    candles_1m = [_c1m(i, 100, 101, 1.0) for i in range(45)]
    index_by_ts = {c["timestamp"]: i for i, c in enumerate(candles_1m)}
    ts_15m = START + timedelta(minutes=15)  # second 15m bucket: minutes 15-29

    indices = bucket_1m_candles(ts_15m, candles_1m, index_by_ts, minutes=15)
    assert indices == list(range(15, 30))


def test_bucket_1m_candles_missing_start_returns_empty():
    candles_1m = [_c1m(i, 100, 101, 1.0) for i in range(10)]
    index_by_ts = {c["timestamp"]: i for i, c in enumerate(candles_1m)}
    missing_ts = START + timedelta(minutes=999)
    assert bucket_1m_candles(missing_ts, candles_1m, index_by_ts) == []


# =========================================================
# Determinism
# =========================================================


def test_deterministic():
    candles = [_c1m(i, 100, 101, float(i % 7 + 1)) for i in range(300)]
    s1 = relative_volume_series(candles)
    s2 = relative_volume_series(candles)
    assert s1 == s2
