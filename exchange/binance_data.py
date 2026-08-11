import httpx


def get_funding_rate(symbol: str):
    url = "https://fapi.binance.com/fapi/v1/premiumIndex"

    params = {
        "symbol": symbol
    }

    response = httpx.get(url, params=params)
    data = response.json()

    return float(data["lastFundingRate"])


def get_open_interest(symbol: str):
    url = "https://fapi.binance.com/fapi/v1/openInterest"

    params = {
        "symbol": symbol
    }

    response = httpx.get(url, params=params)
    data = response.json()

    return float(data["openInterest"])


def get_klines(symbol: str, interval: str = "1m", limit: int = 20):
    url = "https://fapi.binance.com/fapi/v1/klines"

    params = {
        "symbol": symbol,
        "interval": interval,
        "limit": limit
    }

    response = httpx.get(url, params=params)
    data = response.json()

    return data

def get_volume_ratio(symbol: str, interval: str = "1m", lookback: int = 20):
    klines = get_klines(symbol, interval, lookback + 2)

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
    limit: int = 10
):
    url = "https://fapi.binance.com/futures/data/openInterestHist"

    params = {
        "symbol": symbol,
        "period": period,
        "limit": limit
    }

    response = httpx.get(url, params=params)
    data = response.json()

    return data



def get_open_interest_change(
    symbol: str,
    period: str = "5m",
    lookback: int = 10
):
    history = get_open_interest_history(symbol, period, lookback)

    old_oi = float(history[0]["sumOpenInterest"])
    new_oi = float(history[-1]["sumOpenInterest"])

    change_percent = ((new_oi - old_oi) / old_oi) * 100

    return change_percent