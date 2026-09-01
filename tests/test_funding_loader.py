from datetime import datetime, timezone
from pathlib import Path

import pytest

from data.funding_loader import (
    load_funding_csv,
    load_funding_csvs,
    normalize_funding_record,
    normalize_funding_records,
)


def test_normalize_funding_record_maps_fields():
    record = normalize_funding_record(
        {
            "fundingTime": 1704067200000,
            "fundingRate": "0.00037409",
        }
    )

    assert record["timestamp"] == datetime(2024, 1, 1, tzinfo=timezone.utc)
    assert record["rate"] == pytest.approx(0.00037409)


def test_normalize_funding_record_missing_field_raises():
    with pytest.raises(ValueError):
        normalize_funding_record({"fundingTime": 1704067200000})


def test_normalize_funding_records_sorts_chronologically():
    records = normalize_funding_records(
        [
            {"fundingTime": 1704096000000, "fundingRate": "0.0001"},
            {"fundingTime": 1704067200000, "fundingRate": "0.0002"},
        ]
    )

    assert records[0]["timestamp"] < records[1]["timestamp"]


def test_load_funding_csv_reads_real_file(tmp_path):
    csv_path = tmp_path / "BTCUSDT-funding-2024-01.csv"
    csv_path.write_text(
        "fundingTime,fundingRate,markPrice,symbol\n"
        "1704067200000,0.00037409,42313.9,BTCUSDT\n"
        "1704096000000,0.00027213,42525.1,BTCUSDT\n",
        encoding="utf-8",
    )

    records = load_funding_csv(csv_path)

    assert len(records) == 2
    assert records[0]["timestamp"] == datetime(2024, 1, 1, tzinfo=timezone.utc)
    assert records[0]["rate"] == pytest.approx(0.00037409)


def test_load_funding_csv_missing_file_raises():
    with pytest.raises(FileNotFoundError):
        load_funding_csv("does_not_exist.csv")


def test_load_funding_csvs_merges_and_sorts_multiple_months(tmp_path):
    january = tmp_path / "BTCUSDT-funding-2024-01.csv"
    january.write_text(
        "fundingTime,fundingRate,markPrice,symbol\n"
        "1706745600000,0.0001,50000,BTCUSDT\n",
        encoding="utf-8",
    )

    february = tmp_path / "BTCUSDT-funding-2024-02.csv"
    february.write_text(
        "fundingTime,fundingRate,markPrice,symbol\n"
        "1707004800000,0.0002,51000,BTCUSDT\n",
        encoding="utf-8",
    )

    records = load_funding_csvs([february, january])

    assert len(records) == 2
    assert records[0]["timestamp"] < records[1]["timestamp"]
