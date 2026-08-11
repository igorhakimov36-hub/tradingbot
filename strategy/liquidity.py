def calculate_liquidity_score(liquidity_strength: float):
    if liquidity_strength >= 3.0:
        return 30

    elif liquidity_strength >= 2.0:
        return 20

    elif liquidity_strength >= 1.0:
        return 10

    return 0


def detect_liquidity_sweep(
    current_high: float,
    current_low: float,
    current_close: float,
    previous_swing_high: float,
    previous_swing_low: float
):
    if previous_swing_high is None or previous_swing_low is None:
        return "NO_SWEEP"

    if (
        current_high > previous_swing_high
        and current_close < previous_swing_high
    ):
        return "BEARISH_SWEEP"

    if (
        current_low < previous_swing_low
        and current_close > previous_swing_low
    ):
        return "BULLISH_SWEEP"

    return "NO_SWEEP"


def calculate_sweep_strength(
    sweep_type: str,
    current_high: float,
    current_low: float,
    current_close: float,
    previous_swing_high: float,
    previous_swing_low: float
):
    if sweep_type == "BEARISH_SWEEP":
        penetration = (
            (current_high - previous_swing_high)
            / previous_swing_high
        ) * 100

        rejection = (
            (current_high - current_close)
            / current_high
        ) * 100

    elif sweep_type == "BULLISH_SWEEP":
        penetration = (
            (previous_swing_low - current_low)
            / previous_swing_low
        ) * 100

        rejection = (
            (current_close - current_low)
            / current_low
        ) * 100

    else:
        return 0.0

    return penetration + rejection


def normalize_liquidity_strength(sweep_strength: float):
    if sweep_strength >= 5.0:
        return 3.0

    if sweep_strength >= 3.0:
        return 2.0

    if sweep_strength > 0:
        return 1.0

    return 0.0