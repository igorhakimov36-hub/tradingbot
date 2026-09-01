from datetime import datetime, timedelta, timezone

import pytest

from data.timeframe_manager import TimeframeManager

START = datetime(2024, 1, 1, 0, 0, tzinfo=timezone.utc)


def _candle(minute_offset: int, open_, high, low, close, volume):
    return {
        "timestamp": START + timedelta(minutes=minute_offset),
        "open": open_,
        "high": high,
        "low": low,
        "close": close,
        "volume": volume,
    }


def _make_1m_series(count: int):
    return [
        _candle(i, 100 + i, 101 + i, 99 + i, 100 + i, 10)
        for i in range(count)
    ]


def test_bucket_stays_forming_until_next_bucket_starts():
    manager = TimeframeManager(["5m"])
    candles = _make_1m_series(5)

    manager.sync(candles)

    assert manager.get_history("5m") == []
    assert manager.get_forming_candle("5m") is not None


def test_bucket_closes_once_next_bucket_begins():
    manager = TimeframeManager(["5m"])
    candles = _make_1m_series(6)

    manager.sync(candles)

    closed = manager.get_history("5m")

    assert len(closed) == 1
    assert closed[0]["timestamp"] == START
    assert closed[0]["open"] == candles[0]["open"]
    assert closed[0]["close"] == candles[4]["close"]
    assert closed[0]["high"] == max(c["high"] for c in candles[:5])
    assert closed[0]["low"] == min(c["low"] for c in candles[:5])
    assert closed[0]["volume"] == sum(c["volume"] for c in candles[:5])

    forming = manager.get_forming_candle("5m")
    assert forming["timestamp"] == START + timedelta(minutes=5)
    assert forming["open"] == candles[5]["open"]


def test_multiple_timeframes_close_independently():
    manager = TimeframeManager(["5m", "15m"])
    candles = _make_1m_series(16)

    manager.sync(candles)

    assert len(manager.get_history("5m")) == 3
    assert len(manager.get_history("15m")) == 1


def test_incremental_sync_matches_single_shot_sync():
    candles = _make_1m_series(37)

    incremental = TimeframeManager(["5m", "15m", "1h"])
    for i in range(1, len(candles) + 1):
        incremental.sync(candles[:i])

    single_shot = TimeframeManager(["5m", "15m", "1h"])
    single_shot.sync(candles)

    for timeframe in ["5m", "15m", "1h"]:
        assert incremental.get_history(timeframe) == single_shot.get_history(timeframe)
        assert incremental.get_forming_candle(timeframe) == single_shot.get_forming_candle(timeframe)


def test_get_all_histories_returns_every_configured_timeframe():
    manager = TimeframeManager(["5m", "15m"])
    manager.sync(_make_1m_series(20))

    histories = manager.get_all_histories()

    assert set(histories.keys()) == {"5m", "15m"}
    assert len(histories["5m"]) == 3
    assert len(histories["15m"]) == 1


def test_unknown_timeframe_raises():
    manager = TimeframeManager(["5m"])
    manager.sync(_make_1m_series(5))

    with pytest.raises(ValueError):
        manager.get_history("1h")


def test_rewinding_history_raises():
    manager = TimeframeManager(["5m"])
    candles = _make_1m_series(10)

    manager.sync(candles)

    with pytest.raises(ValueError):
        manager.sync(candles[:5])


def test_diverging_history_raises():
    manager = TimeframeManager(["5m"])
    manager.sync(_make_1m_series(5))

    diverging = _make_1m_series(6)
    diverging[4] = _candle(4, 999, 999, 999, 999, 1)

    with pytest.raises(ValueError):
        manager.sync(diverging)


def test_invalid_timeframe_string_raises():
    with pytest.raises(ValueError):
        TimeframeManager(["5x"])


def test_timeframe_not_larger_than_source_raises():
    with pytest.raises(ValueError):
        TimeframeManager(["1m"])


def test_returned_history_is_a_copy():
    manager = TimeframeManager(["5m"])
    manager.sync(_make_1m_series(6))

    history = manager.get_history("5m")
    history.append("tampered")

    assert manager.get_history("5m") != history


def _native_15m_candle(minute_offset: int, open_, high, low, close, volume):
    return {
        "timestamp": START + timedelta(minutes=minute_offset),
        "open": open_,
        "high": high,
        "low": low,
        "close": close,
        "volume": volume,
    }


def test_native_series_stays_forming_before_its_close_boundary():
    native_15m = [_native_15m_candle(0, 100.0, 105.0, 95.0, 102.0, 500.0)]

    manager = TimeframeManager(["15m"], native_series={"15m": native_15m})

    # 1m clock reaches 00:14 - the 15m bar covering 00:00-00:15 has not
    # closed yet, since its own close boundary (00:15) hasn't arrived.
    manager.sync(_make_1m_series(15))

    assert manager.get_history("15m") == []

    forming = manager.get_forming_candle("15m")
    assert forming["timestamp"] == START
    assert forming["close"] == 102.0


def test_native_series_closes_exactly_at_its_close_boundary():
    native_15m = [
        _native_15m_candle(0, 100.0, 105.0, 95.0, 102.0, 500.0),
        _native_15m_candle(15, 102.0, 108.0, 101.0, 106.0, 600.0),
    ]

    manager = TimeframeManager(["15m"], native_series={"15m": native_15m})

    # 1m clock reaches 00:15 - the market has now moved past the first
    # 15m bar's close boundary, so it must be released.
    manager.sync(_make_1m_series(16))

    closed = manager.get_history("15m")
    assert len(closed) == 1
    assert closed[0] == native_15m[0]

    forming = manager.get_forming_candle("15m")
    assert forming["timestamp"] == START + timedelta(minutes=15)


def test_native_candle_values_are_not_recomputed_from_1m():
    # The native record's OHLCV is deliberately inconsistent with what
    # aggregating _make_1m_series would produce, to prove native mode
    # never recomputes it.
    native_15m = [_native_15m_candle(0, 999.0, 999.0, 999.0, 999.0, 1.0)]

    manager = TimeframeManager(["15m"], native_series={"15m": native_15m})
    manager.sync(_make_1m_series(16))

    assert manager.get_history("15m")[0]["close"] == 999.0


def test_native_and_derived_timeframes_coexist():
    native_15m = [_native_15m_candle(0, 100.0, 105.0, 95.0, 102.0, 500.0)]

    manager = TimeframeManager(["5m", "15m"], native_series={"15m": native_15m})
    manager.sync(_make_1m_series(16))

    # 5m is still derived by aggregation from the 1m feed.
    assert len(manager.get_history("5m")) == 3

    # 15m came from the native series untouched.
    assert manager.get_history("15m") == [native_15m[0]]


def test_native_series_for_undeclared_timeframe_raises():
    native_15m = [_native_15m_candle(0, 100.0, 105.0, 95.0, 102.0, 500.0)]

    with pytest.raises(ValueError):
        TimeframeManager(["5m"], native_series={"15m": native_15m})


# =========================================================
# taker_buy_volume aggregation - discovered missing while validating
# CVD (strategy/features/cvd.py) against real BTCUSDT data: derived
# (non-native) timeframes were silently dropping this field, even
# though every source 1m candle carried it.
# =========================================================


def _candle_with_taker(minute_offset: int, volume, taker_buy_volume):
    candle = _candle(minute_offset, 100, 101, 99, 100, volume)
    candle["taker_buy_volume"] = taker_buy_volume
    return candle


def test_taker_buy_volume_is_summed_across_a_derived_bucket():
    manager = TimeframeManager(["5m"])
    candles = [_candle_with_taker(i, volume=10, taker_buy_volume=6) for i in range(6)]

    manager.sync(candles)

    closed = manager.get_history("5m")
    assert len(closed) == 1
    assert closed[0]["taker_buy_volume"] == pytest.approx(30.0)  # 5 contributing minutes * 6


def test_taker_buy_volume_is_none_when_source_field_absent():
    manager = TimeframeManager(["5m"])
    candles = _make_1m_series(6)  # no taker_buy_volume key at all

    manager.sync(candles)

    assert manager.get_history("5m")[0]["taker_buy_volume"] is None


def test_taker_buy_volume_is_none_if_any_contributing_minute_is_missing_it():
    manager = TimeframeManager(["5m"])
    candles = [
        _candle_with_taker(0, volume=10, taker_buy_volume=6),
        _candle_with_taker(1, volume=10, taker_buy_volume=6),
        _candle(2, 100, 101, 99, 100, 10),  # missing taker_buy_volume entirely
        _candle_with_taker(3, volume=10, taker_buy_volume=6),
        _candle_with_taker(4, volume=10, taker_buy_volume=6),
        _candle_with_taker(5, volume=10, taker_buy_volume=6),  # closes the bucket
    ]

    manager.sync(candles)

    # A partial sum across some-known/some-missing minutes would be a
    # fabricated approximation - the whole bucket must poison to None,
    # never silently sum only the minutes that happened to have data.
    assert manager.get_history("5m")[0]["taker_buy_volume"] is None
