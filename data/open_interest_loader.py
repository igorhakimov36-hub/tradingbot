from pathlib import Path
from typing import Any
import csv

from data.historical_loader import parse_timestamp

REQUIRED_OPEN_INTEREST_FIELDS = {
    "timestamp",
    "sumOpenInterest",
}


def _to_float(
    value: Any,
    field_name: str,
) -> float:
    try:
        return float(value)

    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} must be numeric") from exc


def normalize_open_interest_record(
    record: dict[str, Any],
) -> dict[str, Any]:

    missing = REQUIRED_OPEN_INTEREST_FIELDS - record.keys()

    if missing:
        raise ValueError(f"Missing open interest fields: {missing}")

    return {
        "timestamp": parse_timestamp(record["timestamp"]),
        # Neutral name on purpose - this is what Strategy Engine reads.
        # Binance's own field name (sumOpenInterest) stays only in the
        # raw CSV/API layer, not up here, so a future non-Binance
        # provider can normalize into the same key.
        "value": _to_float(
            record["sumOpenInterest"],
            "sumOpenInterest",
        ),
    }


def normalize_open_interest_records(
    records: list[dict[str, Any]],
) -> list[dict[str, Any]]:

    normalized = [
        normalize_open_interest_record(record) for record in records
    ]

    normalized.sort(key=lambda record: record["timestamp"])

    return normalized


def load_open_interest_csv(
    file_path: str | Path,
) -> list[dict[str, Any]]:
    """
    Load one Open Interest history CSV, as produced by
    exchange/download_historical_open_interest.py.
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
                    "timestamp": row["timestamp"],
                    "sumOpenInterest": row["sumOpenInterest"],
                }
            )

    return normalize_open_interest_records(records)


def load_open_interest_csvs(
    file_paths: list[str | Path],
) -> list[dict[str, Any]]:
    """
    Load and merge multiple Open Interest history CSV files into a
    single chronologically-sorted list.
    """

    all_records: list[dict[str, Any]] = []

    for file_path in file_paths:
        all_records.extend(load_open_interest_csv(file_path))

    all_records.sort(key=lambda record: record["timestamp"])

    return all_records
