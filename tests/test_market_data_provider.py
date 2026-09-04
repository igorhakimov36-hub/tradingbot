from datetime import datetime, timedelta, timezone

from data.market_data_provider import (
    BarSeriesProvider,
    PointEventProvider,
    ReplayContext,
)

START = datetime(2024, 1, 1, tzinfo=timezone.utc)


def _candle(minute_offset, close):
    return {
        "timestamp": START + timedelta(minutes=minute_offset),
        "open": close,
        "high": close,
        "low": close,
        "close": close,
        "volume": 1.0,
    }


def _context(minute_offset, history):
    current_candle = history[-1]

    return ReplayContext(
        current_time=current_candle["timestamp"],
        current_candle=current_candle,
        visible_history_1m=history,
    )


# =========================================================
# PointEventProvider
# =========================================================


def test_point_event_provider_returns_none_before_any_record():
    provider = PointEventProvider("funding", records=[])

    history = [_candle(0, 100.0)]
    provider.sync(_context(0, history))

    snapshot = provider.snapshot()
    assert snapshot["current"] is None
    assert snapshot["previous"] is None


def test_point_event_provider_never_leaks_future_records():
    records = [
        {"timestamp": START, "rate": 0.0001},
        {"timestamp": START + timedelta(minutes=10), "rate": 0.9999},
    ]

    provider = PointEventProvider("funding", records=records)

    history = [_candle(5, 100.0)]
    provider.sync(_context(5, history))

    snapshot = provider.snapshot()
    assert snapshot["current"]["rate"] == 0.0001
    assert snapshot["previous"] is None


def test_point_event_provider_advances_as_time_passes():
    records = [
        {"timestamp": START, "rate": 0.0001},
        {"timestamp": START + timedelta(minutes=10), "rate": 0.0002},
    ]

    provider = PointEventProvider("funding", records=records)

    history = [_candle(15, 100.0)]
    provider.sync(_context(15, history))

    snapshot = provider.snapshot()
    assert snapshot["current"]["rate"] == 0.0002
    assert snapshot["previous"]["rate"] == 0.0001


def test_point_event_provider_sorts_unsorted_input_at_construction():
    """records is now sorted once in __init__ (needed for the binary
    search lookup) - must behave identically whether the caller passes
    them in chronological order or not, matching the old
    get_latest_two_available_records()-based implementation's
    behavior (which was order-independent by construction)."""
    records = [
        {"timestamp": START + timedelta(minutes=10), "rate": 0.0002},
        {"timestamp": START, "rate": 0.0001},
    ]

    provider = PointEventProvider("funding", records=records)

    history = [_candle(15, 100.0)]
    provider.sync(_context(15, history))

    snapshot = provider.snapshot()
    assert snapshot["current"]["rate"] == 0.0002
    assert snapshot["previous"]["rate"] == 0.0001


def test_point_event_provider_duplicate_timestamps_preserve_relative_order():
    """Two records at the exact same timestamp must resolve to
    'current'/'previous' the same way the original stable-sort-based
    implementation did - the later-inserted record wins as 'current'."""
    same_time = START + timedelta(minutes=5)
    records = [
        {"timestamp": START, "rate": 0.0001},
        {"timestamp": same_time, "rate": 0.0002},
        {"timestamp": same_time, "rate": 0.0003},
    ]

    provider = PointEventProvider("funding", records=records)

    history = [_candle(5, 100.0)]
    provider.sync(_context(5, history))

    snapshot = provider.snapshot()
    assert snapshot["current"]["rate"] == 0.0003
    assert snapshot["previous"]["rate"] == 0.0002


def test_point_event_provider_has_a_name():
    provider = PointEventProvider("open_interest", records=[])
    assert provider.name == "open_interest"


# =========================================================
# BarSeriesProvider
# =========================================================


def test_bar_series_provider_only_exposes_closed_bars():
    native_15m = [
        {
            "timestamp": START,
            "open": 100.0,
            "high": 105.0,
            "low": 95.0,
            "close": 102.0,
            "volume": 500.0,
        },
    ]

    provider = BarSeriesProvider(
        "15m",
        timeframe="15m",
        native_series=native_15m,
    )

    history = [_candle(i, 100.0 + i) for i in range(14)]
    provider.sync(_context(13, history))

    assert provider.snapshot() == []


def test_bar_series_provider_closes_once_boundary_reached():
    native_15m = [
        {
            "timestamp": START,
            "open": 100.0,
            "high": 105.0,
            "low": 95.0,
            "close": 102.0,
            "volume": 500.0,
        },
    ]

    provider = BarSeriesProvider(
        "15m",
        timeframe="15m",
        native_series=native_15m,
    )

    history = [_candle(i, 100.0 + i) for i in range(16)]
    provider.sync(_context(15, history))

    closed = provider.snapshot()
    assert len(closed) == 1
    assert closed[0]["close"] == 102.0


def test_bar_series_provider_has_a_name():
    provider = BarSeriesProvider("15m", timeframe="15m", native_series=[])
    assert provider.name == "15m"
