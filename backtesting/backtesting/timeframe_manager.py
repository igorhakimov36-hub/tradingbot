from typing import Any


class TimeframeManager:
    """
    Supplies point-in-time-safe higher timeframe history.
    """

    def __init__(
        self,
        candles_15m: list[dict[str, Any]],
    ):
        self.candles_15m = candles_15m

    def get_visible_15m_history(
        self,
        current_time,
    ) -> list[dict[str, Any]]:
        """
        Return only 15m candles that already existed
        at the current replay timestamp.
        """

        return [
            candle for candle in self.candles_15m if candle["timestamp"] <= current_time
        ]
