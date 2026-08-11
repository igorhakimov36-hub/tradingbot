from strategy.liquidity import calculate_liquidity_score
from strategy.volume import calculate_volume_score
from strategy.open_interest import calculate_open_interest_score
from strategy.funding import calculate_funding_score


def make_decision(
    signal: str,
    liquidity_sweep: str,
    liquidity_strength: float,
    market_structure: str,
    bos_quality: dict,
    choch: str,
    volume_ratio: float,
    open_interest_change: float,
    funding_rate: float
):
    # -------------------------
    # Liquidity Score
    # -------------------------

    liquidity_score = calculate_liquidity_score(liquidity_strength)

    if (
        signal == "bullish_order_block"
        and liquidity_sweep != "BULLISH_SWEEP"
    ):
        liquidity_score = 0

    elif (
        signal == "bearish_order_block"
        and liquidity_sweep != "BEARISH_SWEEP"
    ):
        liquidity_score = 0


    # -------------------------
    # BOS Score
    # -------------------------

    bos_score = 0

    if signal == "bullish_order_block":
        if bos_quality["bos"] == "BULLISH_BOS":

            if bos_quality["quality"] == "STRONG":
                bos_score = 30

            elif bos_quality["quality"] == "MEDIUM":
                bos_score = 20

            elif bos_quality["quality"] == "WEAK":
                bos_score = 10

    elif signal == "bearish_order_block":
        if bos_quality["bos"] == "BEARISH_BOS":

            if bos_quality["quality"] == "STRONG":
                bos_score = 30

            elif bos_quality["quality"] == "MEDIUM":
                bos_score = 20

            elif bos_quality["quality"] == "WEAK":
                bos_score = 10


    # -------------------------
    # CHOCH Score
    # -------------------------

    choch_score = 0

    if signal == "bullish_order_block":
        if choch == "BEARISH_CHOCH":
            choch_score = -20

    elif signal == "bearish_order_block":
        if choch == "BULLISH_CHOCH":
            choch_score = -20


    # -------------------------
    # Other Scores
    # -------------------------

    volume_score = calculate_volume_score(volume_ratio)

    open_interest_score = calculate_open_interest_score(
        open_interest_change
    )

    funding_score = calculate_funding_score(funding_rate)


    # -------------------------
    # Total Score
    # -------------------------

    score = 0

    score += liquidity_score
    score += bos_score
    score += choch_score
    score += volume_score
    score += open_interest_score
    score += funding_score


    # -------------------------
    # Decision
    # -------------------------

    if signal == "bullish_order_block" and score >= 80:
        return {
            "decision": "LONG",
            "score": score,
            "liquidity_score": liquidity_score,
            "bos_score": bos_score,
            "choch_score": choch_score,
            "volume_score": volume_score,
            "open_interest_score": open_interest_score,
            "funding_score": funding_score
        }

    elif signal == "bearish_order_block" and score >= 80:
        return {
            "decision": "SHORT",
            "score": score,
            "liquidity_score": liquidity_score,
            "bos_score": bos_score,
            "choch_score": choch_score,
            "volume_score": volume_score,
            "open_interest_score": open_interest_score,
            "funding_score": funding_score
        }

    return {
        "decision": "IGNORE",
        "score": score,
        "liquidity_score": liquidity_score,
        "bos_score": bos_score,
        "choch_score": choch_score,
        "volume_score": volume_score,
        "open_interest_score": open_interest_score,
        "funding_score": funding_score
    }