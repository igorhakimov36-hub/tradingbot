from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import csv
import time

import httpx

BASE_URL = "https://fapi.binance.com"
FUNDING_ENDPOINT = "/fapi/v1/fundingRate"

MAX_LIMIT = 1000
REQUEST_DELAY_SECONDS = 0.2
MAX_PAGES = 1000

DOWNLOAD_DIR = Path("data")

DOWNLOAD_DIR.mkdir(
    parents=True,
    exist_ok=True,
)


def _to_ms(timestamp: datetime) -> int:
    return int(timestamp.timestamp() * 1000)


def _request_funding_page(
    symbol: str,
    start_time_ms: int,
    end_time_ms: int,
    limit: int = MAX_LIMIT,
) -> list[dict[str, Any]]:
    """
    Fetch one page of funding rate history from Binance Futures.
    """

    response = httpx.get(
        f"{BASE_URL}{FUNDING_ENDPOINT}",
        params={
            "symbol": symbol,
            "startTime": start_time_ms,
            "endTime": end_time_ms,
            "limit": limit,
        },
        timeout=10,
    )

    response.raise_for_status()

    return response.json()


def download_funding_history(
    symbol: str,
    start_time: datetime,
    end_time: datetime,
) -> list[dict[str, Any]]:
    """
    Download the full funding rate history for `symbol` between
    `start_time` and `end_time` (inclusive), paginating automatically
    (Binance returns at most 1000 records per request) until every
    available record in the range has been retrieved.
    """

    start_time_ms = _to_ms(start_time)
    end_time_ms = _to_ms(end_time)

    all_records: list[dict[str, Any]] = []
    cursor = start_time_ms
    pages_fetched = 0

    while True:
        if pages_fetched >= MAX_PAGES:
            raise RuntimeError(
                f"Reached MAX_PAGES={MAX_PAGES} while downloading "
                f"funding history - the requested range may be "
                f"larger than expected"
            )

        page = _request_funding_page(
            symbol=symbol,
            start_time_ms=cursor,
            end_time_ms=end_time_ms,
        )
        pages_fetched += 1

        if not page:
            break

        page = [
            record
            for record in page
            if record["fundingTime"] <= end_time_ms
        ]

        all_records.extend(page)

        if len(page) < MAX_LIMIT:
            # Fewer than a full page means there is nothing left
            # in the requested range.
            break

        cursor = page[-1]["fundingTime"] + 1

        if cursor > end_time_ms:
            break

        time.sleep(REQUEST_DELAY_SECONDS)

    return all_records


def _group_by_month(
    records: list[dict[str, Any]],
) -> dict[tuple[int, int], list[dict[str, Any]]]:
    groups: dict[tuple[int, int], list[dict[str, Any]]] = {}

    for record in records:
        moment = datetime.fromtimestamp(
            record["fundingTime"] / 1000,
            tz=timezone.utc,
        )

        key = (moment.year, moment.month)

        groups.setdefault(key, []).append(record)

    return groups


def save_funding_csv(
    records: list[dict[str, Any]],
    file_path: Path,
) -> Path:
    """
    Save raw Binance funding rate records as CSV.
    """

    with file_path.open(
        "w",
        encoding="utf-8",
        newline="",
    ) as csv_file:

        writer = csv.DictWriter(
            csv_file,
            fieldnames=["fundingTime", "fundingRate", "markPrice", "symbol"],
        )

        writer.writeheader()

        for record in records:
            writer.writerow(
                {
                    "fundingTime": record["fundingTime"],
                    "fundingRate": record["fundingRate"],
                    "markPrice": record.get("markPrice", ""),
                    "symbol": record.get("symbol", ""),
                }
            )

    return file_path


def download_and_save(
    symbol: str,
    start_time: datetime,
    end_time: datetime,
) -> list[Path]:
    """
    Download funding history for `symbol` and save it as one CSV
    file per calendar month, matching the naming convention already
    used for candle data (e.g. BTCUSDT-1m-2024-01.csv):

        {symbol}-funding-{year}-{month:02d}.csv
    """

    records = download_funding_history(
        symbol=symbol,
        start_time=start_time,
        end_time=end_time,
    )

    groups = _group_by_month(records)

    saved_paths: list[Path] = []

    for (year, month), month_records in sorted(groups.items()):
        filename = f"{symbol}-funding-{year}-{month:02d}.csv"

        file_path = DOWNLOAD_DIR / filename

        save_funding_csv(month_records, file_path)

        saved_paths.append(file_path)

    return saved_paths


if __name__ == "__main__":

    saved_paths = download_and_save(
        symbol="BTCUSDT",
        start_time=datetime(2024, 1, 1, tzinfo=timezone.utc),
        end_time=datetime(2024, 7, 1, tzinfo=timezone.utc),
    )

    print()
    print("Funding history download completed successfully.")
    print()

    for path in saved_paths:
        print(path)
