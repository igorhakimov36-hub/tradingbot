from datetime import datetime, timezone

import pytest

from data.market_data_aligner import (
    align_market_data,
    align_market_history,
)


def utc_time(hour: int, minute: int = 0) -> datetime:
    return datetime(
        2025,
        1,
        1,
        hour,
        minute,
        tzinfo=timezone.utc
    )


def create_candle(hour: int, minute: int = 0):
    return {
        "timestamp": utc_time(hour, minute),
        "open": 100.0,
        "high": 110.0,
        "low": 90.0,
        "close": 105.0,
        "volume": 1000.0,
    }


# =========================================================
# OPEN INTEREST TESTS
# =========================================================

def test_latest_available_oi_is_selected():
    candle = create_candle(12, 5)

    oi_records = [
        {
            "timestamp": utc_time(11, 59),
            "open_interest": 1000.0
        },
        {
            "timestamp": utc_time(12, 3),
            "open_interest": 1100.0
        },
        {
            "timestamp": utc_time(12, 7),
            "open_interest": 9999.0
        },
    ]

    result = align_market_data(
        candle=candle,
        current_time=utc_time(12, 5),
        open_interest_records=oi_records
    )

    assert result["open_interest"] is not None
    assert result["open_interest"]["open_interest"] == 1100.0
    assert result["open_interest"]["timestamp"] == utc_time(12, 3)


def test_future_oi_is_never_selected():
    candle = create_candle(12, 5)

    oi_records = [
        {
            "timestamp": utc_time(12, 6),
            "open_interest": 9999.0
        }
    ]

    result = align_market_data(
        candle=candle,
        current_time=utc_time(12, 5),
        open_interest_records=oi_records
    )

    assert result["open_interest"] is None


def test_oi_at_exact_current_time_is_allowed():
    candle = create_candle(12, 5)

    oi_records = [
        {
            "timestamp": utc_time(12, 5),
            "open_interest": 1200.0
        }
    ]

    result = align_market_data(
        candle=candle,
        current_time=utc_time(12, 5),
        open_interest_records=oi_records
    )

    assert result["open_interest"] is not None
    assert result["open_interest"]["open_interest"] == 1200.0


# =========================================================
# FUNDING TESTS
# =========================================================

def test_latest_available_funding_is_selected():
    candle = create_candle(12, 3)

    funding_records = [
        {
            "timestamp": utc_time(8, 0),
            "funding_rate": 0.0001
        },
        {
            "timestamp": utc_time(16, 0),
            "funding_rate": 0.9999
        },
    ]

    result = align_market_data(
        candle=candle,
        current_time=utc_time(12, 3),
        funding_records=funding_records
    )

    assert result["funding"] is not None
    assert result["funding"]["funding_rate"] == 0.0001
    assert result["funding"]["timestamp"] == utc_time(8, 0)


def test_future_funding_is_never_selected():
    candle = create_candle(12, 3)

    funding_records = [
        {
            "timestamp": utc_time(16, 0),
            "funding_rate": 0.9999
        }
    ]

    result = align_market_data(
        candle=candle,
        current_time=utc_time(12, 3),
        funding_records=funding_records
    )

    assert result["funding"] is None


# =========================================================
# MISSING DATA TESTS
# =========================================================

def test_missing_oi_and_funding_return_none():
    candle = create_candle(12, 0)

    result = align_market_data(
        candle=candle,
        current_time=utc_time(12, 0)
    )

    assert result["open_interest"] is None
    assert result["funding"] is None


def test_candle_is_preserved_in_result():
    candle = create_candle(12, 0)

    result = align_market_data(
        candle=candle,
        current_time=utc_time(12, 0)
    )

    assert result["candle"] == candle
    assert result["timestamp"] == candle["timestamp"]


# =========================================================
# SAFETY TESTS
# =========================================================

def test_future_candle_is_rejected():
    candle = create_candle(12, 5)

    with pytest.raises(ValueError):
        align_market_data(
            candle=candle,
            current_time=utc_time(12, 0)
        )


def test_invalid_current_time_is_rejected():
    candle = create_candle(12, 0)

    with pytest.raises(TypeError):
        align_market_data(
            candle=candle,
            current_time="2025-01-01T12:00:00Z"
        )


def test_missing_candle_timestamp_is_rejected():
    candle = {
        "close": 100.0
    }

    with pytest.raises(KeyError):
        align_market_data(
            candle=candle,
            current_time=utc_time(12, 0)
        )


# =========================================================
# FULL HISTORY TESTS
# =========================================================

def test_history_alignment_never_uses_future_data():
    candles = [
        create_candle(12, 0),
        create_candle(12, 5),
        create_candle(12, 10),
    ]

    oi_records = [
        {
            "timestamp": utc_time(11, 59),
            "open_interest": 1000.0
        },
        {
            "timestamp": utc_time(12, 3),
            "open_interest": 1100.0
        },
        {
            "timestamp": utc_time(12, 8),
            "open_interest": 1200.0
        },
    ]

    result = align_market_history(
        candles=candles,
        open_interest_records=oi_records
    )

    assert len(result) == 3

    # 12:00 can only see 11:59
    assert (
        result[0]["open_interest"]["open_interest"]
        == 1000.0
    )

    # 12:05 can see the 12:03 update
    assert (
        result[1]["open_interest"]["open_interest"]
        == 1100.0
    )

    # 12:10 can see the 12:08 update
    assert (
        result[2]["open_interest"]["open_interest"]
        == 1200.0
    )


def test_history_is_returned_chronologically():
    candles = [
        create_candle(12, 10),
        create_candle(12, 0),
        create_candle(12, 5),
    ]

    result = align_market_history(
        candles=candles
    )

    assert result[0]["timestamp"] == utc_time(12, 0)
    assert result[1]["timestamp"] == utc_time(12, 5)
    assert result[2]["timestamp"] == utc_time(12, 10)