def detect_market_structure(highs: list[float], lows: list[float]):
    if len(highs) < 2 or len(lows) < 2:
        return "UNKNOWN"

    if highs[-1] > highs[-2] and lows[-1] > lows[-2]:
        return "BULLISH"

    if highs[-1] < highs[-2] and lows[-1] < lows[-2]:
        return "BEARISH"

    return "RANGE"


def find_swing_high(highs: list[float]):
    if len(highs) < 3:
        return False

    return highs[-2] > highs[-3] and highs[-2] > highs[-1]


def find_swing_low(lows: list[float]):
    if len(lows) < 3:
        return False

    return lows[-2] < lows[-3] and lows[-2] < lows[-1]


def detect_bos(
    current_close: float,
    previous_swing_high: float,
    previous_swing_low: float
):

    if previous_swing_high is None or previous_swing_low is None:
        return "NO_BOS"

    if current_close > previous_swing_high:
        return "BULLISH_BOS"

    if current_close < previous_swing_low:
        return "BEARISH_BOS"

    return "NO_BOS"

    

def confirm_bos_with_volume(volume_ratio: float):
    if volume_ratio >= 2.0:
        return "STRONG"

    if volume_ratio >= 1.3:
        return "MEDIUM"

    return "WEAK"


def confirm_bos_with_open_interest(open_interest_change: float):
    if open_interest_change >= 0.5:
        return "STRONG"

    if open_interest_change >= 0.1:
        return "MEDIUM"

    return "WEAK"


def evaluate_bos_quality(
    bos_direction: str,
    volume_ratio: float,
    open_interest_change: float
):
    volume_confirmation = confirm_bos_with_volume(volume_ratio)
    oi_confirmation = confirm_bos_with_open_interest(open_interest_change)

    if bos_direction == "NO_BOS":
        return {
            "bos": "NO_BOS",
            "quality": "NONE",
            "volume_confirmation": volume_confirmation,
            "oi_confirmation": oi_confirmation
        }

    if (
        volume_confirmation == "STRONG"
        and oi_confirmation == "STRONG"
    ):
        quality = "STRONG"

    elif (
        volume_confirmation in ["STRONG", "MEDIUM"]
        and oi_confirmation in ["STRONG", "MEDIUM"]
    ):
        quality = "MEDIUM"

    else:
        quality = "WEAK"

    return {
        "bos": bos_direction,
        "quality": quality,
        "volume_confirmation": volume_confirmation,
        "oi_confirmation": oi_confirmation
    }

def detect_choch(
    market_structure: str,
    current_close: float,
    previous_swing_high: float,
    previous_swing_low: float
):
    if previous_swing_high is None or previous_swing_low is None:
        return "NO_CHOCH"

    if (
        market_structure == "BULLISH"
        and current_close < previous_swing_low
    ):
        return "BEARISH_CHOCH"

    if (
        market_structure == "BEARISH"
        and current_close > previous_swing_high
    ):
        return "BULLISH_CHOCH"

    return "NO_CHOCH"

    



def get_last_swing_levels(
    highs: list[float],
    lows: list[float]
):
    last_swing_high = None
    last_swing_low = None

    for i in range(1, len(highs) - 1):
        if highs[i] > highs[i - 1] and highs[i] > highs[i + 1]:
            last_swing_high = highs[i]

        if lows[i] < lows[i - 1] and lows[i] < lows[i + 1]:
            last_swing_low = lows[i]

    return last_swing_high, last_swing_low