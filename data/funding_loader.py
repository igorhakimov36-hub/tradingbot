from pathlib import Path
from typing import Any
import csv

from data.historical_loader import parse_timestamp

REQUIRED_FUNDING_FIELDS = {
    "fundingTime",
    "fundingRate",
}


def _to_float(
    value: Any,
    field_name: str,
) -> float:
    try:
        return float(value)

    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} must be numeric") from exc


def normalize_funding_record(
    record: dict[str, Any],
) -> dict[str, Any]:

    missing = REQUIRED_FUNDING_FIELDS - record.keys()

    if missing:
        raise ValueError(f"Missing funding fields: {missing}")

    return {
        "timestamp": parse_timestamp(record["fundingTime"]),
        # Neutral name on purpose - this is what Strategy Engine reads.
        # Binance's own field name (fundingRate) stays only in the raw
        # CSV/API layer, not up here, so a future non-Binance provider
        # (Bybit, OKX, ...) can normalize into the same key.
        "rate": _to_float(
            record["fundingRate"],
            "fundingRate",
        ),
    }


def normalize_funding_records(
    records: list[dict[str, Any]],
) -> list[dict[str, Any]]:

    normalized = [
        normalize_funding_record(record) for record in records
    ]

    normalized.sort(key=lambda record: record["timestamp"])

    return normalized


def load_funding_csv(
    file_path: str | Path,
) -> list[dict[str, Any]]:
    """
    Load one funding-rate history CSV, as produced by
    exchange/download_historical_funding.py.
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
                    "fundingTime": row["fundingTime"],
                    "fundingRate": row["fundingRate"],
                }
            )

    return normalize_funding_records(records)


def load_funding_csvs(
    file_paths: list[str | Path],
) -> list[dict[str, Any]]:
    """
    Load and merge multiple monthly funding CSV files (one per
    calendar month, matching the candle-data naming convention) into
    a single chronologically-sorted list.
    """

    all_records: list[dict[str, Any]] = []

    for file_path in file_paths:
        all_records.extend(load_funding_csv(file_path))

    all_records.sort(key=lambda record: record["timestamp"])

    return all_records
