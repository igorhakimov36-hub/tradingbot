def calculate_funding_score(
    funding_rate: float,
    signal: str,
):
    if signal == "bullish_order_block":

        if funding_rate <= -0.0010:
            return 15

        elif funding_rate <= -0.0005:
            return 10

        elif funding_rate <= -0.0001:
            return 5

    elif signal == "bearish_order_block":

        if funding_rate >= 0.0010:
            return 15

        elif funding_rate >= 0.0005:
            return 10

        elif funding_rate >= 0.0001:
            return 5

    return 0