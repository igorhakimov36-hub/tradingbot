import csv
from pathlib import Path

SOURCE_FILE = Path("data/BTCUSDT-1m-2024-01.csv")
TARGET_FILE = Path("data/BTCUSDT-15m-2024-01.csv")

TIMEFRAME = 15


def load_rows(path: Path):
    with path.open("r", newline="", encoding="utf-8-sig") as file:
        return list(csv.DictReader(file))


def save_rows(path: Path, rows):
    if not rows:
        return

    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(
            file,
            fieldnames=rows[0].keys(),
        )
        writer.writeheader()
        writer.writerows(rows)


def aggregate(rows):

    candles = []

    for i in range(0, len(rows), TIMEFRAME):

        chunk = rows[i : i + TIMEFRAME]

        if len(chunk) < TIMEFRAME:
            break

        first = chunk[0]
        last = chunk[-1]

        candle = {
            "open_time": first["open_time"],
            "open": first["open"],
            "high": max(float(c["high"]) for c in chunk),
            "low": min(float(c["low"]) for c in chunk),
            "close": last["close"],
            "volume": sum(float(c["volume"]) for c in chunk),
            "close_time": last["close_time"],
            "quote_volume": sum(float(c["quote_volume"]) for c in chunk),
            "count": sum(int(c["count"]) for c in chunk),
            "taker_buy_volume": sum(float(c["taker_buy_volume"]) for c in chunk),
            "taker_buy_quote_volume": sum(
                float(c["taker_buy_quote_volume"]) for c in chunk
            ),
            "ignore": "0",
        }

        candles.append(candle)

    return candles


def main():

    rows = load_rows(SOURCE_FILE)

    candles = aggregate(rows)

    save_rows(TARGET_FILE, candles)

    print(f"Created {len(candles)} candles")
    print(TARGET_FILE)


if __name__ == "__main__":
    main()
