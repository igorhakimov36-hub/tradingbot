from datetime import datetime
from pathlib import Path
from typing import Any
import csv
import time

import httpx

BASE_URL = "https://fapi.binance.com"
OPEN_INTEREST_ENDPOINT = "/futures/data/openInterestHist"

# Binance only retains the last 30 days for this endpoint - there is
# no way to backfill Open Interest further back than that, for any
# symbol, regardless of pagination.
MAX_LIMIT = 500
REQUEST_DELAY_SECONDS = 0.2
MAX_PAGES = 1000

DOWNLOAD_DIR = Path("data")

DOWNLOAD_DIR.mkdir(
    parents=True,
    exist_ok=True,
)


def _to_ms(timestamp: datetime) -> int:
    return int(timestamp.timestamp() * 1000)


def _period_to_ms(period: str) -> int:
    unit = period[-1]
    value = int(period[:-1])

    if unit == "m":
        return value * 60_000

    if unit == "h":
        return value * 3_600_000

    if unit == "d":
        return value * 86_400_000

    raise ValueError(f"Unsupported period: {period}")


def _request_open_interest_page(
    symbol: str,
    period: str,
    start_time_ms: int,
    end_time_ms: int,
    limit: int = MAX_LIMIT,
) -> list[dict[str, Any]]:

    response = httpx.get(
        f"{BASE_URL}{OPEN_INTEREST_ENDPOINT}",
        params={
            "symbol": symbol,
            "period": period,
            "startTime": start_time_ms,
            "endTime": end_time_ms,
            "limit": limit,
        },
        timeout=10,
    )

    response.raise_for_status()

    return response.json()


def download_open_interest_history(
    symbol: str,
    period: str,
    start_time: datetime,
    end_time: datetime,
) -> list[dict[str, Any]]:
    """
    Download Open Interest history for `symbol` between `start_time`
    and `end_time` (inclusive), paginating automatically.

    Unlike /fapi/v1/klines and /fapi/v1/fundingRate, this endpoint
    does NOT page forward from `startTime`: when the range holds more
    than `limit` records, Binance silently returns the most recent
    `limit` records up to `endTime` and ignores `startTime` as a lower
    bound. Verified empirically - not documented. So pagination here
    must walk backward from `end_time`, one page at a time, moving
    `endTime` to just before the earliest record seen so far, until
    we reach `start_time` or run out of data.

    `start_time` must be within the last 30 days - Binance does not
    retain this data any further back, for any symbol.
    """

    start_time_ms = _to_ms(start_time)
    end_time_ms = _to_ms(end_time)

    all_records: list[dict[str, Any]] = []
    cursor_end = end_time_ms
    pages_fetched = 0

    while True:
        if pages_fetched >= MAX_PAGES:
            raise RuntimeError(
                f"Reached MAX_PAGES={MAX_PAGES} while downloading "
                f"open interest history - the requested range may "
                f"be larger than expected"
            )

        page = _request_open_interest_page(
            symbol=symbol,
            period=period,
            start_time_ms=start_time_ms,
            end_time_ms=cursor_end,
        )
        pages_fetched += 1

        if not page:
            break

        page = [
            record
            for record in page
            if start_time_ms <= record["timestamp"] <= end_time_ms
        ]

        all_records.extend(page)

        earliest_seen = page[0]["timestamp"] if page else None

        if (
            len(page) < MAX_LIMIT
            or earliest_seen is None
            or earliest_seen <= start_time_ms
        ):
            break

        cursor_end = earliest_seen - 1

        time.sleep(REQUEST_DELAY_SECONDS)

    unique_records = {
        record["timestamp"]: record for record in all_records
    }

    return sorted(
        unique_records.values(),
        key=lambda record: record["timestamp"],
    )


def save_open_interest_csv(
    records: list[dict[str, Any]],
    file_path: Path,
) -> Path:

    with file_path.open(
        "w",
        encoding="utf-8",
        newline="",
    ) as csv_file:

        writer = csv.DictWriter(
            csv_file,
            fieldnames=["timestamp", "sumOpenInterest", "sumOpenInterestValue", "symbol"],
        )

        writer.writeheader()

        for record in records:
            writer.writerow(
                {
                    "timestamp": record["timestamp"],
                    "sumOpenInterest": record["sumOpenInterest"],
                    "sumOpenInterestValue": record.get("sumOpenInterestValue", ""),
                    "symbol": record.get("symbol", ""),
                }
            )

    return file_path


def download_and_save(
    symbol: str,
    period: str,
    start_time: datetime,
    end_time: datetime,
    filename: str | None = None,
) -> tuple[Path, int]:

    records = download_open_interest_history(
        symbol=symbol,
        period=period,
        start_time=start_time,
        end_time=end_time,
    )

    if filename is None:
        filename = f"{symbol}-open_interest-recent30d.csv"

    file_path = DOWNLOAD_DIR / filename

    save_open_interest_csv(records, file_path)

    return file_path, len(records)
