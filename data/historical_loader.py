import csv
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REQUIRED_OHLCV_FIELDS = {
    "timestamp",
    "open",
    "high",
    "low",
    "close",
    "volume",
}


def parse_timestamp(value: Any) -> datetime:
    """
    Convert supported timestamp formats into a timezone-aware
    UTC datetime.

    Supported:
    - datetime
    - Unix timestamp in seconds
    - Unix timestamp in milliseconds
    - ISO formatted string
    """

    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)

        return value.astimezone(timezone.utc)

    if isinstance(value, (int, float)):
        timestamp = float(value)

        # Milliseconds are much larger than seconds.
        if timestamp > 10_000_000_000:
            timestamp /= 1000.0

        return datetime.fromtimestamp(
            timestamp,
            tz=timezone.utc
        )

    if isinstance(value, str):
        text = value.strip()

        if not text:
            raise ValueError("Timestamp cannot be empty")

        # Numeric timestamp stored as text.
        try:
            return parse_timestamp(float(text))
        except ValueError:
            pass

        # Support ISO timestamps ending in Z.
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"

        try:
            parsed = datetime.fromisoformat(text)
        except ValueError as exc:
            raise ValueError(
                f"Unsupported timestamp: {value}"
            ) from exc

        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)

        return parsed.astimezone(timezone.utc)

    raise TypeError(
        f"Unsupported timestamp type: {type(value).__name__}"
    )


def _to_float(
    value: Any,
    field_name: str
) -> float:
    """
    Convert a market-data value to float.
    """

    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"{field_name} must be numeric"
        ) from exc

    return result


def normalize_ohlcv_record(
    record: dict[str, Any]
) -> dict[str, Any]:
    """
    Validate and normalize one OHLCV candle.
    """

    missing_fields = (
        REQUIRED_OHLCV_FIELDS - record.keys()
    )

    if missing_fields:
        missing = ", ".join(sorted(missing_fields))

        raise ValueError(
            f"Missing OHLCV fields: {missing}"
        )

    timestamp = parse_timestamp(
        record["timestamp"]
    )

    open_price = _to_float(
        record["open"],
        "open"
    )

    high_price = _to_float(
        record["high"],
        "high"
    )

    low_price = _to_float(
        record["low"],
        "low"
    )

    close_price = _to_float(
        record["close"],
        "close"
    )

    volume = _to_float(
        record["volume"],
        "volume"
    )

    if high_price < low_price:
        raise ValueError(
            "OHLCV validation failed: high < low"
        )

    if high_price < max(
        open_price,
        close_price
    ):
        raise ValueError(
            "OHLCV validation failed: "
            "high is below open or close"
        )

    if low_price > min(
        open_price,
        close_price
    ):
        raise ValueError(
            "OHLCV validation failed: "
            "low is above open or close"
        )

    if volume < 0:
        raise ValueError(
            "OHLCV validation failed: volume < 0"
        )

    return {
        "timestamp": timestamp,
        "open": open_price,
        "high": high_price,
        "low": low_price,
        "close": close_price,
        "volume": volume,
    }


def normalize_ohlcv_records(
    records: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """
    Normalize multiple candles and return them
    in chronological order.
    """

    normalized = [
        normalize_ohlcv_record(record)
        for record in records
    ]

    normalized.sort(
        key=lambda record: record["timestamp"]
    )

    for previous, current in zip(
        normalized,
        normalized[1:]
    ):
        if (
            previous["timestamp"]
            == current["timestamp"]
        ):
            raise ValueError(
                "Duplicate OHLCV timestamp detected: "
                f"{current['timestamp']}"
            )

    return normalized


def load_ohlcv_csv(
    file_path: str | Path
) -> list[dict[str, Any]]:
    """
    Load OHLCV candles from a CSV file and normalize them.

    Expected columns:
    timestamp, open, high, low, close, volume
    """

    path = Path(file_path)

    if not path.exists():
        raise FileNotFoundError(
            f"Historical data file not found: {path}"
        )

    if not path.is_file():
        raise ValueError(
            f"Historical data path is not a file: {path}"
        )

    with path.open(
        "r",
        encoding="utf-8-sig",
        newline=""
    ) as csv_file:
        reader = csv.DictReader(csv_file)

        if reader.fieldnames is None:
            raise ValueError(
                "CSV file has no header"
            )

        records = list(reader)

    return normalize_ohlcv_records(records)