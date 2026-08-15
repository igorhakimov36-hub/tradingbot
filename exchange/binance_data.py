from typing import Any

import httpx

BASE_URL = "https://fapi.binance.com"


def _request(
    endpoint: str,
    params: dict[str, Any],
) -> Any:
    """
    Send a GET request to the Binance Futures API.

    Raises:
        httpx.HTTPStatusError:
            If Binance returns a non-2xx response.
    """

    response = httpx.get(
        f"{BASE_URL}{endpoint}",
        params=params,
        timeout=10,
    )

    response.raise_for_status()

    return response.json()


def get_funding_rate(symbol: str) -> float:
    """
    Return the latest Binance Futures funding rate.
    """

    data = _request(
        "/fapi/v1/premiumIndex",
        {
            "symbol": symbol,
        },
    )

    return float(data["lastFundingRate"])


def get_open_interest(symbol: str) -> float:
    """
    Return the current Binance Futures Open Interest.
    """

    data = _request(
        "/fapi/v1/openInterest",
        {
            "symbol": symbol,
        },
    )

    return float(data["openInterest"])


def get_klines(
    symbol: str,
    interval: str = "1m",
    limit: int = 20,
) -> list[list[Any]]:
    """
    Return raw Binance Futures OHLCV candles.

    Each candle is returned as a Binance kline array.
    """

    return _request(
        "/fapi/v1/klines",
        {
            "symbol": symbol,
            "interval": interval,
            "limit": limit,
        },
    )


def get_volume_ratio(
    symbol: str,
    interval: str = "1m",
    lookback: int = 20,
) -> float:
    """
    Compare the latest closed candle volume against the
    average volume of previous closed candles.
    """

    klines = get_klines(
        symbol,
        interval,
        lookback + 2,
    )

    closed_candles = klines[:-1]

    previous_candles = closed_candles[:-1]
    current_closed_candle = closed_candles[-1]

    previous_volumes = [float(candle[5]) for candle in previous_candles]

    current_volume = float(current_closed_candle[5])

    average_volume = sum(previous_volumes) / len(previous_volumes)

    return current_volume / average_volume


def get_open_interest_history(
    symbol: str,
    period: str = "5m",
    limit: int = 10,
) -> list[dict[str, Any]]:
    """
    Return historical Open Interest data from Binance.
    """

    return _request(
        "/futures/data/openInterestHist",
        {
            "symbol": symbol,
            "period": period,
            "limit": limit,
        },
    )


def get_open_interest_change(
    symbol: str,
    period: str = "5m",
    lookback: int = 10,
) -> float:
    """
    Return the percentage change in Open Interest over
    the requested lookback period.
    """

    history = get_open_interest_history(
        symbol,
        period,
        lookback,
    )

    old_oi = float(history[0]["sumOpenInterest"])

    new_oi = float(history[-1]["sumOpenInterest"])

    return ((new_oi - old_oi) / old_oi) * 100
