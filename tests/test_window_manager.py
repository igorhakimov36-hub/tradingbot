from datetime import datetime

import pytest

from backtesting.window_manager import (
    TimeWindow,
    WindowManager,
)


def create_window_manager():
    return WindowManager(
        train=TimeWindow(
            name="TRAIN",
            start=datetime(2025, 1, 1),
            end=datetime(2025, 4, 1),
        ),
        validation=TimeWindow(
            name="VALIDATION",
            start=datetime(2025, 4, 1),
            end=datetime(2025, 7, 1),
        ),
        held_out=TimeWindow(
            name="HELD_OUT",
            start=datetime(2025, 7, 1),
            end=datetime(2025, 10, 1),
        ),
    )


def test_time_window_rejects_invalid_dates():
    with pytest.raises(ValueError):
        TimeWindow(
            name="INVALID",
            start=datetime(2025, 4, 1),
            end=datetime(2025, 4, 1),
        )


def test_train_contains_correct_timestamp():
    manager = create_window_manager()

    result = manager.identify_window(
        datetime(2025, 2, 15)
    )

    assert result == "TRAIN"


def test_validation_contains_correct_timestamp():
    manager = create_window_manager()

    result = manager.identify_window(
        datetime(2025, 5, 15)
    )

    assert result == "VALIDATION"


def test_held_out_contains_correct_timestamp():
    manager = create_window_manager()

    result = manager.identify_window(
        datetime(2025, 8, 15)
    )

    assert result == "HELD_OUT"


def test_timestamp_outside_all_windows_returns_none():
    manager = create_window_manager()

    result = manager.identify_window(
        datetime(2025, 12, 1)
    )

    assert result is None


def test_boundary_belongs_only_to_next_window():
    manager = create_window_manager()

    boundary = datetime(2025, 4, 1)

    assert manager.train.contains(boundary) is False
    assert manager.validation.contains(boundary) is True

    assert manager.identify_window(boundary) == "VALIDATION"


def test_train_and_validation_overlap_is_rejected():
    with pytest.raises(ValueError):
        WindowManager(
            train=TimeWindow(
                name="TRAIN",
                start=datetime(2025, 1, 1),
                end=datetime(2025, 5, 1),
            ),
            validation=TimeWindow(
                name="VALIDATION",
                start=datetime(2025, 4, 1),
                end=datetime(2025, 7, 1),
            ),
            held_out=TimeWindow(
                name="HELD_OUT",
                start=datetime(2025, 7, 1),
                end=datetime(2025, 10, 1),
            ),
        )


def test_validation_and_held_out_overlap_is_rejected():
    with pytest.raises(ValueError):
        WindowManager(
            train=TimeWindow(
                name="TRAIN",
                start=datetime(2025, 1, 1),
                end=datetime(2025, 4, 1),
            ),
            validation=TimeWindow(
                name="VALIDATION",
                start=datetime(2025, 4, 1),
                end=datetime(2025, 8, 1),
            ),
            held_out=TimeWindow(
                name="HELD_OUT",
                start=datetime(2025, 7, 1),
                end=datetime(2025, 10, 1),
            ),
        )


def test_get_records_returns_only_requested_window():
    manager = create_window_manager()

    records = [
        {
            "timestamp": datetime(2025, 2, 1),
            "close": 100.0,
        },
        {
            "timestamp": datetime(2025, 5, 1),
            "close": 200.0,
        },
        {
            "timestamp": datetime(2025, 8, 1),
            "close": 300.0,
        },
    ]

    result = manager.get_records(
        records=records,
        window_name="VALIDATION",
    )

    assert len(result) == 1
    assert result[0]["close"] == 200.0


def test_get_records_returns_data_in_chronological_order():
    manager = create_window_manager()

    records = [
        {
            "timestamp": datetime(2025, 3, 1),
            "close": 300.0,
        },
        {
            "timestamp": datetime(2025, 1, 15),
            "close": 100.0,
        },
        {
            "timestamp": datetime(2025, 2, 1),
            "close": 200.0,
        },
    ]

    result = manager.get_records(
        records=records,
        window_name="TRAIN",
    )

    assert result[0]["close"] == 100.0
    assert result[1]["close"] == 200.0
    assert result[2]["close"] == 300.0


def test_unknown_window_name_is_rejected():
    manager = create_window_manager()

    with pytest.raises(ValueError):
        manager.get_window("MAGIC_WINDOW")


def test_missing_timestamp_is_rejected():
    manager = create_window_manager()

    records = [
        {
            "close": 100.0
        }
    ]

    with pytest.raises(KeyError):
        manager.get_records(
            records=records,
            window_name="TRAIN",
        )


def test_invalid_timestamp_type_is_rejected():
    manager = create_window_manager()

    records = [
        {
            "timestamp": "2025-02-01",
            "close": 100.0,
        }
    ]

    with pytest.raises(TypeError):
        manager.get_records(
            records=records,
            window_name="TRAIN",
        )