import random
from datetime import datetime, timedelta

import pytest

from backtesting.point_in_time import get_available_data, get_available_data_sorted

START = datetime(2026, 1, 1, 12, 0)


def _records(offsets):
    return [{"timestamp": START + timedelta(minutes=m), "value": m} for m in offsets]


# =========================================================
# Direct behavior
# =========================================================


def test_empty_dataset_returns_empty():
    assert get_available_data_sorted([], START) == []


def test_single_record_before_current_time_is_visible():
    records = _records([0])
    assert get_available_data_sorted(records, START + timedelta(minutes=1)) == records


def test_single_record_after_current_time_is_not_visible():
    records = _records([5])
    assert get_available_data_sorted(records, START) == []


def test_current_time_before_any_record_returns_empty():
    records = _records([1, 2, 3])
    assert get_available_data_sorted(records, START) == []


def test_boundary_timestamp_exactly_equal_is_included():
    records = _records([0, 5, 10])
    result = get_available_data_sorted(records, START + timedelta(minutes=5))
    assert [r["value"] for r in result] == [0, 5]


def test_no_future_data_is_ever_visible():
    records = _records([-2, -1, 0, 1, 2])
    result = get_available_data_sorted(records, START)
    assert all(r["timestamp"] <= START for r in result)
    assert [r["value"] for r in result] == [-2, -1, 0]


def test_repeated_calls_at_the_same_timestamp_are_stable():
    records = _records([0, 1, 2, 3])
    current_time = START + timedelta(minutes=2)

    first = get_available_data_sorted(records, current_time)
    second = get_available_data_sorted(records, current_time)

    assert first == second


def test_non_monotonic_ad_hoc_queries_are_each_independently_correct():
    """No monotonicity is assumed anywhere in get_available_data_sorted -
    querying an earlier current_time after a later one must still be
    exactly correct, since each call recomputes from the sorted array."""
    records = _records([0, 1, 2, 3, 4])

    late = get_available_data_sorted(records, START + timedelta(minutes=4))
    early = get_available_data_sorted(records, START + timedelta(minutes=1))
    later_again = get_available_data_sorted(records, START + timedelta(minutes=3))

    assert [r["value"] for r in late] == [0, 1, 2, 3, 4]
    assert [r["value"] for r in early] == [0, 1]
    assert [r["value"] for r in later_again] == [0, 1, 2, 3]


def test_duplicate_timestamps_are_all_included_and_order_preserved():
    same_time = START + timedelta(minutes=5)
    records = [
        {"timestamp": START, "value": "a"},
        {"timestamp": same_time, "value": "b"},
        {"timestamp": same_time, "value": "c"},
        {"timestamp": START + timedelta(minutes=10), "value": "d"},
    ]

    result = get_available_data_sorted(records, same_time)
    assert [r["value"] for r in result] == ["a", "b", "c"]


# =========================================================
# Equivalence against the original O(n) implementation
# =========================================================


def test_equivalent_to_original_over_a_representative_random_sequence():
    """The optimized function must be byte-identical to the original
    full-scan get_available_data() for the same (sorted) input, across
    a range of query points including duplicates and out-of-range
    values - not just the hand-picked cases above."""
    rng = random.Random(1234)

    offsets = sorted(rng.choices(range(-50, 250), k=400))  # includes duplicates
    records = _records(offsets)

    query_offsets = [rng.randint(-100, 300) for _ in range(200)] + [-50, 0, 249, -100, 300]

    for q in query_offsets:
        current_time = START + timedelta(minutes=q)

        expected = get_available_data(records=records, current_time=current_time)
        actual = get_available_data_sorted(sorted_records=records, current_time=current_time)

        assert actual == expected, f"mismatch at offset {q}"


def test_equivalent_to_original_on_empty_and_single_record_datasets():
    assert get_available_data_sorted([], START) == get_available_data(records=[], current_time=START)

    records = _records([0])
    for q in (-1, 0, 1):
        current_time = START + timedelta(minutes=q)
        assert get_available_data_sorted(records, current_time) == get_available_data(
            records=records, current_time=current_time
        )


def test_missing_timestamp_key_raises_key_error_same_as_original():
    records = [{"value": 1}]
    with pytest.raises(KeyError):
        get_available_data_sorted(records, START, timestamp_key="timestamp")
