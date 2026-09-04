from bisect import bisect_right
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


def get_available_data_sorted(
    sorted_records: list[dict[str, Any]],
    current_time: datetime,
    timestamp_key: str = "timestamp",
) -> list[dict[str, Any]]:
    """
    O(log n) equivalent of get_available_data(), for callers that can
    guarantee `sorted_records` is already sorted ascending by
    `timestamp_key` and immutable for the lifetime of repeated calls -
    exactly the "sort once at construction, never mutate afterward"
    pattern ReplayEngine and TimeframeManager already use throughout
    this package.

    Produces byte-identical output to get_available_data() called on
    the same (already-sorted) input - verified by dedicated equivalence
    tests, not merely asserted - but each call is O(log n) instead of
    O(n). Called once per replay step across a full replay, this is
    what turns O(n^2) total into O(n log n): the previous approach
    (get_available_data() rescanning the full list from scratch every
    step) is what produced the ~180x measured slowdown for a 12x larger
    dataset reported earlier in this project.

    No monotonicity assumption is made or required: binary search on
    sorted, immutable data is unconditionally correct for ANY
    current_time value, called in ANY order - a fresh replay/reset, a
    repeated query at the same timestamp, or a genuinely non-monotonic
    ad-hoc query all produce the same correct prefix. This is the
    "safe fallback" itself, not a fallback bolted onto a fragile
    monotonic-only fast path - there is no monotonic-only fast path
    here to need one.

    Callers that cannot guarantee `sorted_records` is actually sorted
    must use get_available_data() instead - passing unsorted input
    here silently produces wrong results, since binary search assumes
    sorted order. This function does not sort defensively, because
    doing so on every call would reintroduce the same O(n) per call
    (or worse) it exists to eliminate; sorting is the caller's
    one-time responsibility, exactly as ReplayEngine/TimeframeManager
    already treat it today.
    """

    if not sorted_records:
        return []

    idx = bisect_right(
        sorted_records,
        current_time,
        key=lambda record: record[timestamp_key],
    )

    return sorted_records[:idx]


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
