"""
Small, shared primitives for the strategy/features/ package - kept here
instead of duplicated inside each module (Order Blocks, Liquidity Pools,
and Volatility Regime will all want ATR eventually too; better to define
it once now than reintroduce it three times later).
"""

from collections import deque
from typing import Any


def true_range(candle: dict[str, Any], previous_close: float) -> float:
    return max(
        candle["high"] - candle["low"],
        abs(candle["high"] - previous_close),
        abs(candle["low"] - previous_close),
    )


def is_bullish_candle(candle: dict[str, Any]) -> bool:
    return candle["close"] > candle["open"]


def is_bearish_candle(candle: dict[str, Any]) -> bool:
    return candle["close"] < candle["open"]


class AverageTrueRangeTracker:
    """
    Incremental rolling ATR (simple moving average of True Range).

    O(1) per new candle. Same sync()-with-a-consumed-pointer lifecycle
    as TimeframeManager/DeltaTracker: one instance per backtest run,
    call sync() with the full growing candle history each step.
    """

    def __init__(self, period: int = 14, timestamp_key: str = "timestamp"):
        self.period = period
        self.timestamp_key = timestamp_key

        self._consumed = 0
        self._last_candle: dict[str, Any] | None = None
        self._true_ranges: deque[float] = deque(maxlen=period)

    def sync(self, candles: list[dict[str, Any]]) -> None:
        """
        External contract: pass the full, growing candle history each
        call (matching TimeframeManager/DeltaTracker) - only candles
        added since the last call are processed.
        """

        if len(candles) < self._consumed:
            raise ValueError(
                "candles went backwards - AverageTrueRangeTracker "
                "does not support rewinding"
            )

        if self._consumed > 0:
            checkpoint = candles[self._consumed - 1]

            if checkpoint != self._last_candle:
                raise ValueError(
                    "candles does not extend the history previously "
                    "seen by this AverageTrueRangeTracker"
                )

        for candle in candles[self._consumed:]:
            self.ingest_one(candle)

        self._consumed = len(candles)

    def ingest_one(self, candle: dict[str, Any]) -> None:
        """
        Internal contract: feed exactly one new candle directly, with
        no full-history bookkeeping. Meant for another tracker (e.g.
        FairValueGapTracker) to compose this one candle-by-candle
        without ever reconstructing/slicing a growing list - slicing a
        growing list per candle would silently reintroduce the O(n^2)
        cost this whole codebase has already paid down once.
        """

        if self._last_candle is not None:
            self._true_ranges.append(
                true_range(candle, self._last_candle["close"])
            )

        self._last_candle = candle

    def current(self) -> float | None:
        """
        None until at least one True Range value is available (i.e.
        before the second candle) - never a fabricated default.
        """

        if not self._true_ranges:
            return None

        return sum(self._true_ranges) / len(self._true_ranges)
