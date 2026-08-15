from datetime import datetime
from typing import Any

from backtesting.point_in_time import (
    get_latest_two_available_records,
)


def _validate_current_time(current_time: datetime) -> None:
    if not isinstance(current_time, datetime):
        raise TypeError("current_time must be a datetime object")


def _validate_candle(
    candle: dict[str, Any],
    current_time: datetime,
    timestamp_key: str,
) -> None:
    if timestamp_key not in candle:
        raise KeyError(f"Missing timestamp key in candle: {timestamp_key}")

    candle_time = candle[timestamp_key]

    if not isinstance(candle_time, datetime):
        raise TypeError(f"Candle {timestamp_key} must be a datetime object")

    if candle_time > current_time:
        raise ValueError("Cannot align a candle from the future")


def align_market_data(
    candle: dict[str, Any],
    current_time: datetime,
    open_interest_records: list[dict[str, Any]] | None = None,
    funding_records: list[dict[str, Any]] | None = None,
    timestamp_key: str = "timestamp",
) -> dict[str, Any]:
    """
    Align one candle with the latest available market data.
    """

    _validate_current_time(current_time)

    _validate_candle(
        candle=candle,
        current_time=current_time,
        timestamp_key=timestamp_key,
    )

    open_interest_records = open_interest_records or []
    funding_records = funding_records or []

    latest_oi, previous_oi = get_latest_two_available_records(
        records=open_interest_records,
        current_time=current_time,
        timestamp_key=timestamp_key,
    )

    latest_funding, previous_funding = get_latest_two_available_records(
        records=funding_records,
        current_time=current_time,
        timestamp_key=timestamp_key,
    )

    return {
        "timestamp": candle[timestamp_key],
        "candle": candle,
        "open_interest": {
            "current": latest_oi,
            "previous": previous_oi,
        },
        "funding": {
            "current": latest_funding,
            "previous": previous_funding,
        },
    }


def align_market_history(
    candles: list[dict[str, Any]],
    open_interest_records: list[dict[str, Any]] | None = None,
    funding_records: list[dict[str, Any]] | None = None,
    timestamp_key: str = "timestamp",
) -> list[dict[str, Any]]:
    """
    Align an entire candle history.
    """

    open_interest_records = open_interest_records or []
    funding_records = funding_records or []

    aligned_records = []

    sorted_candles = sorted(
        candles,
        key=lambda candle: candle[timestamp_key],
    )

    for candle in sorted_candles:

        current_time = candle[timestamp_key]

        aligned_records.append(
            align_market_data(
                candle=candle,
                current_time=current_time,
                open_interest_records=open_interest_records,
                funding_records=funding_records,
                timestamp_key=timestamp_key,
            )
        )

    return aligned_records
