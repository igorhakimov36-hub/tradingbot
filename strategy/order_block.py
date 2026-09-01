from typing import Any, Callable, Literal

from strategy.market_structure import detect_bos, get_last_swing_levels

Signal = Literal[
    "bullish_order_block",
    "bearish_order_block",
    "no_order_block",
]


def _is_bearish_candle(candle: dict[str, Any]) -> bool:
    return candle["close"] < candle["open"]


def _is_bullish_candle(candle: dict[str, Any]) -> bool:
    return candle["close"] > candle["open"]


def _find_last_opposite_candle(
    candles: list[dict[str, Any]],
    is_opposite: Callable[[dict[str, Any]], bool],
) -> dict[str, Any] | None:
    """
    The order block is the most recent candle that absorbed the
    opposing side of the market right before the impulsive leg that
    broke structure - i.e. the last opposite-colored candle in it.
    """

    for candle in reversed(candles):
        if is_opposite(candle):
            return candle

    return None


DEFAULT_LOOKBACK = 500


def detect_order_block(
    candles: list[dict[str, Any]],
    lookback: int = DEFAULT_LOOKBACK,
) -> Signal:
    if len(candles) < 6:
        return "no_order_block"

    # The relevant swing structure is always within a few dozen bars
    # of "now" for real market data - bounding the search window keeps
    # this O(lookback) instead of O(total history), which matters once
    # a backtest spans months rather than weeks. `lookback` is generous
    # enough that it never changes the result for real candle series.
    candles = candles[-lookback:]

    highs = [candle["high"] for candle in candles]
    lows = [candle["low"] for candle in candles]
    current_close = candles[-1]["close"]

    # A candidate order block only counts once structure has actually
    # broken - without this, any two adjacent candles can look like one.
    previous_swing_high, previous_swing_low = get_last_swing_levels(
        highs[:-1],
        lows[:-1],
    )

    bos = detect_bos(
        current_close,
        previous_swing_high,
        previous_swing_low,
    )

    leg = candles[:-1]

    if bos == "BULLISH_BOS":
        order_block = _find_last_opposite_candle(leg, _is_bearish_candle)

        if order_block is not None:
            return "bullish_order_block"

    elif bos == "BEARISH_BOS":
        order_block = _find_last_opposite_candle(leg, _is_bullish_candle)

        if order_block is not None:
            return "bearish_order_block"

    return "no_order_block"
