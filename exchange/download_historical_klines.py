from datetime import datetime
from pathlib import Path
from typing import Any
import csv
import time

import httpx

BASE_URL = "https://fapi.binance.com"
KLINES_ENDPOINT = "/fapi/v1/klines"

MAX_LIMIT = 1500
REQUEST_DELAY_SECONDS = 0.2
MAX_PAGES = 1000

DOWNLOAD_DIR = Path("data")

DOWNLOAD_DIR.mkdir(
    parents=True,
    exist_ok=True,
)


def _to_ms(timestamp: datetime) -> int:
    return int(timestamp.timestamp() * 1000)


def _interval_to_ms(interval: str) -> int:
    unit = interval[-1]
    value = int(interval[:-1])

    if unit == "m":
        return value * 60_000

    if unit == "h":
        return value * 3_600_000

    if unit == "d":
        return value * 86_400_000

    raise ValueError(f"Unsupported interval: {interval}")


def _request_klines_page(
    symbol: str,
    interval: str,
    start_time_ms: int,
    end_time_ms: int,
    limit: int = MAX_LIMIT,
) -> list[list[Any]]:
    """
    Fetch one page of raw Binance Futures klines.

    Each kline is: [open_time, open, high, low, close, volume,
    close_time, quote_volume, trades, taker_buy_base, taker_buy_quote,
    ignore].
    """

    response = httpx.get(
        f"{BASE_URL}{KLINES_ENDPOINT}",
        params={
            "symbol": symbol,
            "interval": interval,
            "startTime": start_time_ms,
            "endTime": end_time_ms,
            "limit": limit,
        },
        timeout=10,
    )

    response.raise_for_status()

    return response.json()


def download_klines(
    symbol: str,
    interval: str,
    start_time: datetime,
    end_time: datetime,
) -> list[list[Any]]:
    """
    Download every kline for `symbol`/`interval` between `start_time`
    and `end_time` (inclusive), paginating automatically (Binance
    returns at most 1500 klines per request).
    """

    start_time_ms = _to_ms(start_time)
    end_time_ms = _to_ms(end_time)
    interval_ms = _interval_to_ms(interval)

    all_klines: list[list[Any]] = []
    cursor = start_time_ms
    pages_fetched = 0

    while True:
        if pages_fetched >= MAX_PAGES:
            raise RuntimeError(
                f"Reached MAX_PAGES={MAX_PAGES} while downloading "
                f"klines - the requested range may be larger than "
                f"expected"
            )

        page = _request_klines_page(
            symbol=symbol,
            interval=interval,
            start_time_ms=cursor,
            end_time_ms=end_time_ms,
        )
        pages_fetched += 1

        if not page:
            break

        page = [
            kline
            for kline in page
            if kline[0] <= end_time_ms
        ]

        all_klines.extend(page)

        if len(page) < MAX_LIMIT:
            break

        cursor = page[-1][0] + interval_ms

        if cursor > end_time_ms:
            break

        time.sleep(REQUEST_DELAY_SECONDS)

    return all_klines


def save_klines_csv(
    klines: list[list[Any]],
    file_path: Path,
) -> Path:
    """
    Save raw klines as CSV, using the same column names
    data/historical_loader.py already expects (open_time, open, high,
    low, close, volume).
    """

    with file_path.open(
        "w",
        encoding="utf-8",
        newline="",
    ) as csv_file:

        writer = csv.writer(csv_file)

        writer.writerow(
            [
                "open_time",
                "open",
                "high",
                "low",
                "close",
                "volume",
                "taker_buy_volume",
            ]
        )

        for kline in klines:
            writer.writerow(
                [
                    kline[0],
                    kline[1],
                    kline[2],
                    kline[3],
                    kline[4],
                    kline[5],
                    # index 9 = taker_buy_base_asset_volume - already
                    # returned by Binance on every kline request, just
                    # not persisted until now.
                    kline[9],
                ]
            )

    return file_path


def download_and_save(
    symbol: str,
    interval: str,
    start_time: datetime,
    end_time: datetime,
    filename: str | None = None,
) -> tuple[Path, int]:

    klines = download_klines(
        symbol=symbol,
        interval=interval,
        start_time=start_time,
        end_time=end_time,
    )

    if filename is None:
        filename = f"{symbol}-{interval}-recent30d.csv"

    file_path = DOWNLOAD_DIR / filename

    save_klines_csv(klines, file_path)

    return file_path, len(klines)
