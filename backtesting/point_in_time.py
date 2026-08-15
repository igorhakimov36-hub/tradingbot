from datetime import datetime
from typing import Any


class PointInTimeViolation(Exception):
    """Raised when backtest data contains information from the future."""

    pass


def validate_timestamp(data_timestamp: datetime, current_time: datetime) -> None:
    """
    Ensure that a data point was available at or before
    the current replay time.
    """

    if data_timestamp > current_time:
        raise PointInTimeViolation(
            f"Future data detected: "
            f"data_timestamp={data_timestamp}, "
            f"current_time={current_time}"
        )


def get_available_data(
    records: list[dict[str, Any]],
    current_time: datetime,
    timestamp_key: str = "timestamp",
) -> list[dict[str, Any]]:
    """
    Return only records that were available
    at or before current_time.
    """

    available_records = []

    for record in records:
        if timestamp_key not in record:
            raise KeyError(f"Missing timestamp key: {timestamp_key}")

        data_timestamp = record[timestamp_key]

        if not isinstance(data_timestamp, datetime):
            raise TypeError(f"{timestamp_key} must be a datetime object")

        if data_timestamp <= current_time:
            available_records.append(record)

    return available_records


def get_latest_available_record(
    records: list[dict[str, Any]],
    current_time: datetime,
    timestamp_key: str = "timestamp",
) -> dict[str, Any] | None:
    """
    Return the newest record that was actually available
    at current_time.
    """

    available_records = get_available_data(
        records=records, current_time=current_time, timestamp_key=timestamp_key
    )

    if not available_records:
        return None

    return max(available_records, key=lambda record: record[timestamp_key])


def get_latest_two_available_records(
    records: list[dict[str, Any]],
    current_time: datetime,
    timestamp_key: str = "timestamp",
) -> tuple[
    dict[str, Any] | None,
    dict[str, Any] | None,
]:
    """
    Return the latest and previous available records.
    """

    available = get_available_data(
        records=records,
        current_time=current_time,
        timestamp_key=timestamp_key,
    )

    if not available:
        return None, None

    available.sort(key=lambda record: record[timestamp_key])

    latest = available[-1]

    previous = available[-2] if len(available) >= 2 else None

    return latest, previous
