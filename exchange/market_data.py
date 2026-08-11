from strategy.market_structure import (
    get_last_swing_levels,
    detect_market_structure,
    detect_bos,
    detect_choch,
    evaluate_bos_quality

)


from strategy.liquidity import (
    detect_liquidity_sweep,
    calculate_sweep_strength,
    normalize_liquidity_strength
)


from exchange.binance_data import (


    get_funding_rate,
    get_open_interest_change,
    get_volume_ratio,
    get_klines
)

def get_market_data(symbol: str):
    funding_rate = get_funding_rate(symbol)
    open_interest_change = get_open_interest_change(symbol)
    volume_ratio = get_volume_ratio(symbol)
    klines = get_klines(symbol, "1m", 20)
    closed_klines = klines[:-1]
    highs = [float(candle[2]) for candle in closed_klines]
    lows = [float(candle[3]) for candle in closed_klines]
    closes = [float(candle[4]) for candle in closed_klines]
    current_high = highs[-1]
    current_low = lows[-1]
    current_close = closes[-1]

    previous_swing_high, previous_swing_low = get_last_swing_levels(
        highs[:-1],
        lows[:-1]
)

    market_structure = detect_market_structure(
    highs[:-1],
    lows[:-1]
)

    bos = detect_bos(
        current_close,
        previous_swing_high,
        previous_swing_low
)

    bos_quality = evaluate_bos_quality(
        bos,
        volume_ratio,
        open_interest_change
)


    choch = detect_choch(
        market_structure,
        current_close,
        previous_swing_high,
        previous_swing_low
)



    liquidity_sweep = detect_liquidity_sweep(
        current_high,
        current_low,
        current_close,
        previous_swing_high,
        previous_swing_low
)

    sweep_strength = calculate_sweep_strength(
        liquidity_sweep,
        current_high,
        current_low,
        current_close,
        previous_swing_high,
        previous_swing_low
)



    liquidity_strength = normalize_liquidity_strength(sweep_strength)


    return {
        "symbol": symbol,
        "funding_rate": funding_rate,
        "open_interest_change": open_interest_change,
        "volume_ratio": volume_ratio,
        "liquidity_sweep": liquidity_sweep,
        "liquidity_strength": liquidity_strength,
        "market_structure": market_structure,
        "bos": bos,
        "bos_quality": bos_quality,
        "choch": choch
    }



