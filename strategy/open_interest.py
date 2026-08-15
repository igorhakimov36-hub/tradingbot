def calculate_open_interest_score(
    open_interest_change: float,
    signal: str,
):
    if signal == "bullish_order_block":

        if open_interest_change >= 3.0:
            return 30

        elif open_interest_change >= 1.5:
            return 20

        elif open_interest_change >= 0.5:
            return 10

    elif signal == "bearish_order_block":

        if open_interest_change <= -3.0:
            return 30

        elif open_interest_change <= -1.5:
            return 20

        elif open_interest_change <= -0.5:
            return 10

    return 0