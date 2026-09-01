from datetime import datetime, timezone

import pytest

from data.open_interest_loader import (
    load_open_interest_csv,
    load_open_interest_csvs,
    normalize_open_interest_record,
    normalize_open_interest_records,
)


def test_normalize_open_interest_record_maps_fields():
    record = normalize_open_interest_record(
        {
            "timestamp": 1704067200000,
            "sumOpenInterest": "108407.766",
        }
    )

    assert record["timestamp"] == datetime(2024, 1, 1, tzinfo=timezone.utc)
    assert record["value"] == pytest.approx(108407.766)


def test_normalize_open_interest_record_missing_field_raises():
    with pytest.raises(ValueError):
        normalize_open_interest_record({"timestamp": 1704067200000})


def test_normalize_open_interest_records_sorts_chronologically():
    records = normalize_open_interest_records(
        [
            {"timestamp": 1704096000000, "sumOpenInterest": "100"},
            {"timestamp": 1704067200000, "sumOpenInterest": "200"},
        ]
    )

    assert records[0]["timestamp"] < records[1]["timestamp"]


def test_load_open_interest_csv_reads_real_file(tmp_path):
    csv_path = tmp_path / "BTCUSDT-open_interest-recent30d.csv"
    csv_path.write_text(
        "timestamp,sumOpenInterest,sumOpenInterestValue,symbol\n"
        "1704067200000,108407.766,8000000000,BTCUSDT\n"
        "1704067500000,108456.463,8001000000,BTCUSDT\n",
        encoding="utf-8",
    )

    records = load_open_interest_csv(csv_path)

    assert len(records) == 2
    assert records[0]["timestamp"] == datetime(2024, 1, 1, tzinfo=timezone.utc)
    assert records[0]["value"] == pytest.approx(108407.766)


def test_load_open_interest_csv_missing_file_raises():
    with pytest.raises(FileNotFoundError):
        load_open_interest_csv("does_not_exist.csv")


def test_load_open_interest_csvs_merges_and_sorts(tmp_path):
    first = tmp_path / "first.csv"
    first.write_text(
        "timestamp,sumOpenInterest,sumOpenInterestValue,symbol\n"
        "1706745600000,100,8000000000,BTCUSDT\n",
        encoding="utf-8",
    )

    second = tmp_path / "second.csv"
    second.write_text(
        "timestamp,sumOpenInterest,sumOpenInterestValue,symbol\n"
        "1707004800000,200,8100000000,BTCUSDT\n",
        encoding="utf-8",
    )

    records = load_open_interest_csvs([second, first])

    assert len(records) == 2
    assert records[0]["timestamp"] < records[1]["timestamp"]
