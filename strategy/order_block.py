from typing import Literal

Signal = Literal[
    "bullish_order_block",
    "bearish_order_block",
    "no_order_block",
]


def detect_order_block(
    candles: list[dict],
) -> Signal:

    if len(candles) < 6:
        return "no_order_block"

    last = candles[-1]
    previous = candles[-2]

    # -------- Bullish Order Block --------

    if previous["close"] < previous["open"] and last["close"] > previous["high"]:
        return "bullish_order_block"

    # -------- Bearish Order Block --------

    if previous["close"] > previous["open"] and last["close"] < previous["low"]:
        return "bearish_order_block"

    return "no_order_block"
