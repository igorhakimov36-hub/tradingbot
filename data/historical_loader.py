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
        try:
            return parse_timestamp(float(value))
        except ValueError:
            pass

        try:
            return parse_timestamp(datetime.fromisoformat(value.replace("Z", "+00:00")))
        except ValueError as exc:
            raise ValueError(f"unrecognized timestamp string: {value!r}") from exc

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

    open_price = _to_float(record["open"], "open")
    high = _to_float(record["high"], "high")
    low = _to_float(record["low"], "low")
    close = _to_float(record["close"], "close")
    volume = _to_float(record["volume"], "volume")

    if high < low:
        raise ValueError(f"high ({high}) cannot be below low ({low})")

    if high < open_price or high < close:
        raise ValueError(f"high ({high}) must be >= open ({open_price}) and close ({close})")

    if low > open_price or low > close:
        raise ValueError(f"low ({low}) must be <= open ({open_price}) and close ({close})")

    if volume < 0:
        raise ValueError(f"volume cannot be negative: {volume}")

    normalized = {
        "timestamp": parse_timestamp(record["timestamp"]),
        "open": open_price,
        "high": high,
        "low": low,
        "close": close,
        "volume": volume,
    }

    # Optional: not every source provides this (older/third-party CSV
    # dumps may not), so it is never required - callers must handle
    # None explicitly rather than assume it is always present.
    taker_buy_volume = record.get("taker_buy_volume")

    normalized["taker_buy_volume"] = (
        _to_float(taker_buy_volume, "taker_buy_volume")
        if taker_buy_volume not in (None, "")
        else None
    )

    return normalized


def normalize_ohlcv_records(
    records: list[dict[str, Any]],
) -> list[dict[str, Any]]:

    normalized = [normalize_ohlcv_record(record) for record in records]

    normalized.sort(key=lambda candle: candle["timestamp"])

    for previous, current in zip(normalized, normalized[1:]):
        if previous["timestamp"] == current["timestamp"]:
            raise ValueError(f"duplicate timestamp: {current['timestamp']}")

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

            record = {
                # Binance Vision monthly dumps use "open_time"; other
                # OHLCV CSV sources may use the plainer "timestamp" -
                # both name the same field, so accept either rather
                # than only the one this project's own downloads happen
                # to produce.
                "timestamp": row["open_time"] if "open_time" in row else row["timestamp"],
                "open": row["open"],
                "high": row["high"],
                "low": row["low"],
                "close": row["close"],
                "volume": row["volume"],
            }

            # Present in Binance Vision monthly dumps; absent from the
            # slimmer REST-downloaded CSVs. Optional either way.
            if "taker_buy_volume" in row:
                record["taker_buy_volume"] = row["taker_buy_volume"]

            records.append(record)

    return normalize_ohlcv_records(records)
