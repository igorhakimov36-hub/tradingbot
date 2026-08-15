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
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)

        return value.astimezone(timezone.utc)

    if isinstance(value, (int, float)):
        timestamp = float(value)

        # Binance Vision timestamps are milliseconds.
        if timestamp > 10_000_000_000:
            timestamp /= 1000.0

        return datetime.fromtimestamp(
            timestamp,
            tz=timezone.utc,
        )

    if isinstance(value, str):
        return parse_timestamp(float(value))

    raise TypeError(f"Unsupported timestamp type: {type(value).__name__}")


def _to_float(
    value: Any,
    field_name: str,
) -> float:
    try:
        return float(value)

    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} must be numeric") from exc


def normalize_ohlcv_record(
    record: dict[str, Any],
) -> dict[str, Any]:

    missing = REQUIRED_OHLCV_FIELDS - record.keys()

    if missing:
        raise ValueError(f"Missing OHLCV fields: {missing}")

    return {
        "timestamp": parse_timestamp(record["timestamp"]),
        "open": _to_float(
            record["open"],
            "open",
        ),
        "high": _to_float(
            record["high"],
            "high",
        ),
        "low": _to_float(
            record["low"],
            "low",
        ),
        "close": _to_float(
            record["close"],
            "close",
        ),
        "volume": _to_float(
            record["volume"],
            "volume",
        ),
    }


def normalize_ohlcv_records(
    records: list[dict[str, Any]],
) -> list[dict[str, Any]]:

    normalized = [normalize_ohlcv_record(record) for record in records]

    normalized.sort(key=lambda candle: candle["timestamp"])

    return normalized


def load_ohlcv_csv(
    file_path: str | Path,
) -> list[dict[str, Any]]:
    """
    Load Binance Vision OHLCV CSV files.
    """

    path = Path(file_path)

    if not path.exists():
        raise FileNotFoundError(path)

    records = []

    with path.open(
        "r",
        encoding="utf-8-sig",
        newline="",
    ) as csv_file:

        reader = csv.DictReader(csv_file)

        for row in reader:

            records.append(
                {
                    "timestamp": row["open_time"],
                    "open": row["open"],
                    "high": row["high"],
                    "low": row["low"],
                    "close": row["close"],
                    "volume": row["volume"],
                }
            )

    return normalize_ohlcv_records(records)
