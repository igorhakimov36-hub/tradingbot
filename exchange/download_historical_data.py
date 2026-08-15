from pathlib import Path
import zipfile

import httpx

VISION_BASE_URL = "https://data.binance.vision/data/futures/um/monthly/klines"

DOWNLOAD_DIR = Path("data")

DOWNLOAD_DIR.mkdir(
    parents=True,
    exist_ok=True,
)


def build_monthly_url(
    symbol: str,
    interval: str,
    year: int,
    month: int,
) -> str:
    """
    Build the Binance Vision URL for one monthly ZIP file.
    """

    filename = f"{symbol}-{interval}-{year}-{month:02d}.zip"

    return f"{VISION_BASE_URL}/" f"{symbol}/" f"{interval}/" f"{filename}"


def download_month(
    symbol: str,
    interval: str,
    year: int,
    month: int,
) -> Path:
    """
    Download one monthly ZIP file from Binance Vision.
    """

    url = build_monthly_url(
        symbol,
        interval,
        year,
        month,
    )

    filename = f"{symbol}-{interval}-{year}-{month:02d}.zip"

    destination = DOWNLOAD_DIR / filename

    response = httpx.get(
        url,
        timeout=30,
    )

    response.raise_for_status()

    destination.write_bytes(response.content)

    return destination


def extract_zip(
    zip_file: Path,
) -> Path:
    """
    Extract a Binance Vision ZIP file into the data folder.

    Returns
    -------
    Path
        Path to the extracted CSV file.
    """

    with zipfile.ZipFile(
        zip_file,
        "r",
    ) as archive:

        archive.extractall(DOWNLOAD_DIR)

        extracted_file = archive.namelist()[0]

    return DOWNLOAD_DIR / extracted_file


def download_and_extract(
    symbol: str,
    interval: str,
    year: int,
    month: int,
) -> Path:
    """
    Download and extract one month of Binance Vision data.

    Returns
    -------
    Path
        Path to the extracted CSV file.
    """

    zip_file = download_month(
        symbol,
        interval,
        year,
        month,
    )

    csv_file = extract_zip(zip_file)

    return csv_file


def download_range(
    symbol: str,
    interval: str,
    start_year: int,
    start_month: int,
    end_year: int,
    end_month: int,
) -> list[Path]:
    """
    Download and extract multiple months of Binance Vision data.
    """

    files: list[Path] = []

    year = start_year
    month = start_month

    while True:

        print(f"Downloading {year}-{month:02d}...")

        csv_file = download_and_extract(
            symbol=symbol,
            interval=interval,
            year=year,
            month=month,
        )

        files.append(csv_file)

        if year == end_year and month == end_month:
            break

        month += 1

        if month > 12:
            month = 1
            year += 1

    return files


if __name__ == "__main__":

    files = download_range(
        symbol="BTCUSDT",
        interval="1m",
        start_year=2024,
        start_month=1,
        end_year=2024,
        end_month=6,
    )

    print()

    print("Download completed successfully.")

    print()

    for file in files:
        print(file)
