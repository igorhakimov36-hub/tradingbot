from datetime import datetime, timezone

import pytest

from data.historical_loader import (
    load_ohlcv_csv,
    normalize_ohlcv_record,
    normalize_ohlcv_records,
    parse_timestamp,
)


# =========================================================
# TIMESTAMP TESTS
# =========================================================

def test_naive_datetime_becomes_utc():
    value = datetime(2025, 1, 1, 12, 0)

    result = parse_timestamp(value)

    assert result.tzinfo == timezone.utc
    assert result.hour == 12


def test_timezone_aware_datetime_becomes_utc():
    value = datetime(
        2025,
        1,
        1,
        12,
        0,
        tzinfo=timezone.utc
    )

    result = parse_timestamp(value)

    assert result.tzinfo == timezone.utc


def test_unix_seconds_timestamp():
    value = 1735732800

    result = parse_timestamp(value)

    assert isinstance(result, datetime)
    assert result.tzinfo == timezone.utc


def test_unix_milliseconds_timestamp():
    value = 1735732800000

    result = parse_timestamp(value)

    assert isinstance(result, datetime)
    assert result.tzinfo == timezone.utc


def test_iso_timestamp_with_z():
    value = "2025-01-01T12:00:00Z"

    result = parse_timestamp(value)

    assert result == datetime(
        2025,
        1,
        1,
        12,
        0,
        tzinfo=timezone.utc
    )


def test_empty_timestamp_is_rejected():
    with pytest.raises(ValueError):
        parse_timestamp("")


# =========================================================
# SINGLE CANDLE TESTS
# =========================================================

def test_valid_ohlcv_record_is_normalized():
    record = {
        "timestamp": "2025-01-01T12:00:00Z",
        "open": "100",
        "high": "110",
        "low": "90",
        "close": "105",
        "volume": "2500"
    }

    result = normalize_ohlcv_record(record)

    assert result["open"] == 100.0
    assert result["high"] == 110.0
    assert result["low"] == 90.0
    assert result["close"] == 105.0
    assert result["volume"] == 2500.0

    assert result["timestamp"].tzinfo == timezone.utc


def test_missing_ohlcv_field_is_rejected():
    record = {
        "timestamp": "2025-01-01T12:00:00Z",
        "open": 100,
        "high": 110,
        "low": 90,
        "close": 105
    }

    with pytest.raises(ValueError):
        normalize_ohlcv_record(record)


def test_high_below_low_is_rejected():
    record = {
        "timestamp": "2025-01-01T12:00:00Z",
        "open": 100,
        "high": 90,
        "low": 95,
        "close": 97,
        "volume": 1000
    }

    with pytest.raises(ValueError):
        normalize_ohlcv_record(record)


def test_high_below_close_is_rejected():
    record = {
        "timestamp": "2025-01-01T12:00:00Z",
        "open": 100,
        "high": 105,
        "low": 90,
        "close": 110,
        "volume": 1000
    }

    with pytest.raises(ValueError):
        normalize_ohlcv_record(record)


def test_low_above_open_is_rejected():
    record = {
        "timestamp": "2025-01-01T12:00:00Z",
        "open": 100,
        "high": 120,
        "low": 105,
        "close": 110,
        "volume": 1000
    }

    with pytest.raises(ValueError):
        normalize_ohlcv_record(record)


def test_negative_volume_is_rejected():
    record = {
        "timestamp": "2025-01-01T12:00:00Z",
        "open": 100,
        "high": 110,
        "low": 90,
        "close": 105,
        "volume": -1
    }

    with pytest.raises(ValueError):
        normalize_ohlcv_record(record)


# =========================================================
# MULTIPLE CANDLE TESTS
# =========================================================

def test_records_are_sorted_chronologically():
    records = [
        {
            "timestamp": "2025-01-01T12:02:00Z",
            "open": 102,
            "high": 110,
            "low": 100,
            "close": 105,
            "volume": 1000
        },
        {
            "timestamp": "2025-01-01T12:00:00Z",
            "open": 100,
            "high": 105,
            "low": 95,
            "close": 101,
            "volume": 1000
        },
        {
            "timestamp": "2025-01-01T12:01:00Z",
            "open": 101,
            "high": 108,
            "low": 99,
            "close": 102,
            "volume": 1000
        }
    ]

    result = normalize_ohlcv_records(records)

    assert result[0]["close"] == 101.0
    assert result[1]["close"] == 102.0
    assert result[2]["close"] == 105.0


def test_duplicate_timestamp_is_rejected():
    records = [
        {
            "timestamp": "2025-01-01T12:00:00Z",
            "open": 100,
            "high": 110,
            "low": 90,
            "close": 105,
            "volume": 1000
        },
        {
            "timestamp": "2025-01-01T12:00:00Z",
            "open": 105,
            "high": 115,
            "low": 100,
            "close": 110,
            "volume": 1500
        }
    ]

    with pytest.raises(ValueError):
        normalize_ohlcv_records(records)


# =========================================================
# CSV TESTS
# =========================================================

def test_csv_file_is_loaded_and_normalized(tmp_path):
    csv_file = tmp_path / "btc_test.csv"

    csv_file.write_text(
        "timestamp,open,high,low,close,volume\n"
        "2025-01-01T12:01:00Z,101,110,99,105,2000\n"
        "2025-01-01T12:00:00Z,100,105,95,101,1000\n",
        encoding="utf-8"
    )

    result = load_ohlcv_csv(csv_file)

    assert len(result) == 2

    assert result[0]["close"] == 101.0
    assert result[1]["close"] == 105.0

    assert result[0]["timestamp"].tzinfo == timezone.utc


def test_missing_csv_file_is_rejected(tmp_path):
    missing_file = tmp_path / "does_not_exist.csv"

    with pytest.raises(FileNotFoundError):
        load_ohlcv_csv(missing_file)