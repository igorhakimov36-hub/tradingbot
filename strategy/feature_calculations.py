from typing import Any


def calculate_volume_ratio(
    visible_history: list[dict[str, Any]],
    lookback: int = 20,
) -> float:
    """
    Calculate current candle volume relative to the
    average volume of previous candles.
    """

    if len(visible_history) < lookback + 1:
        return 1.0

    history = visible_history[-(lookback + 1) :]

    current = history[-1]["volume"]

    previous = [candle["volume"] for candle in history[:-1]]

    average = sum(previous) / len(previous)

    if average == 0:
        return 1.0

    return current / average


def calculate_open_interest_change(
    current_open_interest: float,
    previous_open_interest: float,
) -> float:
    """
    Percentage change in Open Interest.
    """

    if previous_open_interest <= 0:
        return 0.0

    return (
        (current_open_interest - previous_open_interest) / previous_open_interest
    ) * 100
