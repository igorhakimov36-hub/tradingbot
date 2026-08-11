from datetime import datetime, timedelta

import pytest

from backtesting.point_in_time import (
    PointInTimeViolation,
    validate_timestamp,
    get_available_data,
    get_latest_available_record,
)


def test_past_timestamp_is_allowed():
    current_time = datetime(2026, 1, 1, 12, 0)
    data_time = datetime(2026, 1, 1, 11, 59)

    validate_timestamp(
        data_timestamp=data_time,
        current_time=current_time
    )


def test_current_timestamp_is_allowed():
    current_time = datetime(2026, 1, 1, 12, 0)

    validate_timestamp(
        data_timestamp=current_time,
        current_time=current_time
    )


def test_future_timestamp_is_blocked():
    current_time = datetime(2026, 1, 1, 12, 0)
    future_time = current_time + timedelta(minutes=1)

    with pytest.raises(PointInTimeViolation):
        validate_timestamp(
            data_timestamp=future_time,
            current_time=current_time
        )


def test_available_data_excludes_future_records():
    current_time = datetime(2026, 1, 1, 12, 0)

    records = [
        {
            "timestamp": datetime(2026, 1, 1, 11, 58),
            "value": 100
        },
        {
            "timestamp": datetime(2026, 1, 1, 12, 0),
            "value": 200
        },
        {
            "timestamp": datetime(2026, 1, 1, 12, 2),
            "value": 300
        }
    ]

    result = get_available_data(
        records=records,
        current_time=current_time
    )

    assert len(result) == 2
    assert result[0]["value"] == 100
    assert result[1]["value"] == 200


def test_latest_available_record_does_not_use_future():
    current_time = datetime(2026, 1, 1, 12, 0)

    records = [
        {
            "timestamp": datetime(2026, 1, 1, 11, 55),
            "value": 100
        },
        {
            "timestamp": datetime(2026, 1, 1, 11, 59),
            "value": 200
        },
        {
            "timestamp": datetime(2026, 1, 1, 12, 5),
            "value": 999
        }
    ]

    result = get_latest_available_record(
        records=records,
        current_time=current_time
    )

    assert result is not None
    assert result["value"] == 200


def test_no_available_record_returns_none():
    current_time = datetime(2026, 1, 1, 12, 0)

    records = [
        {
            "timestamp": datetime(2026, 1, 1, 12, 1),
            "value": 100
        }
    ]

    result = get_latest_available_record(
        records=records,
        current_time=current_time
    )

    assert result is None


def test_missing_timestamp_raises_error():
    records = [
        {
            "value": 100
        }
    ]

    with pytest.raises(KeyError):
        get_available_data(
            records=records,
            current_time=datetime(2026, 1, 1, 12, 0)
        )


def test_invalid_timestamp_type_raises_error():
    records = [
        {
            "timestamp": "2026-01-01 12:00:00",
            "value": 100
        }
    ]

    with pytest.raises(TypeError):
        get_available_data(
            records=records,
            current_time=datetime(2026, 1, 1, 12, 0)
        )