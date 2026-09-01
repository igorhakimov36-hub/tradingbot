from typing import Any

from strategy.decision_engine import make_decision
from strategy.liquidity import (
    calculate_sweep_strength,
    detect_liquidity_sweep,
    normalize_liquidity_strength,
)
from strategy.market_structure import (
    detect_bos,
    detect_choch,
    detect_market_structure,
    evaluate_bos_quality,
    get_last_swing_levels,
)
from strategy.order_block import detect_order_block

VOLUME_LOOKBACK = 20

# Real market data almost always contains a 3-bar swing pivot within a
# handful of candles, so this bounds the O(n) structure/liquidity scan
# to a constant instead of the whole (unbounded, ever-growing) history
# - the dominant cost in a multi-month backtest otherwise. Generous on
# purpose: it should never change the result for real candle series.
STRUCTURE_LOOKBACK = 500


def _calculate_volume_ratio(
    candles: list[dict[str, Any]],
    lookback: int = VOLUME_LOOKBACK,
) -> float:

    window = candles[-(lookback + 1) :]
    previous_volumes = [candle["volume"] for candle in window[:-1]]

    if not previous_volumes:
        return 1.0

    average_volume = sum(previous_volumes) / len(previous_volumes)

    if average_volume == 0:
        return 1.0

    return window[-1]["volume"] / average_volume


def _calculate_open_interest_change(
    open_interest_snapshot: dict[str, Any],
) -> float:

    current = open_interest_snapshot.get("current")
    previous = open_interest_snapshot.get("previous")

    if current is None or previous is None:
        return 0.0

    old_value = float(previous["value"])
    new_value = float(current["value"])

    if old_value == 0:
        return 0.0

    return ((new_value - old_value) / old_value) * 100


def _calculate_funding_rate(
    funding_snapshot: dict[str, Any],
) -> float:

    funding = funding_snapshot.get("current")

    if funding is None:
        return 0.0

    return float(funding.get("rate", 0.0))


class StrategyEngine:
    """
    Main strategy entry point.

    Reads only market_snapshot[self.symbol][...] - it never learns
    which exchange or transport (CSV replay, REST, WebSocket) any of
    that data came from, and adding a second StrategyEngine for a
    different symbol never requires changing this class.
    """

    def __init__(self, symbol: str = "BTCUSDT"):
        self.symbol = symbol

    def analyze(
        self,
        current_candle: dict[str, Any],
        market_snapshot: dict[str, Any],
    ) -> dict[str, Any]:

        symbol_data = market_snapshot[self.symbol]

        # symbol_data["1m"] already ends with current_candle.
        candles = symbol_data["1m"][-STRUCTURE_LOOKBACK:]

        highs = [candle["high"] for candle in candles]
        lows = [candle["low"] for candle in candles]

        previous_swing_high, previous_swing_low = get_last_swing_levels(
            highs[:-1],
            lows[:-1],
        )

        market_structure = detect_market_structure(
            highs[:-1],
            lows[:-1],
        )

        volume_ratio = _calculate_volume_ratio(candles)

        open_interest_change = _calculate_open_interest_change(
            symbol_data.get("open_interest", {}),
        )

        funding_rate = _calculate_funding_rate(
            symbol_data.get("funding", {}),
        )

        bos = detect_bos(
            current_candle["close"],
            previous_swing_high,
            previous_swing_low,
        )

        bos_quality = evaluate_bos_quality(
            bos,
            volume_ratio,
            open_interest_change,
        )

        choch = detect_choch(
            market_structure,
            current_candle["close"],
            previous_swing_high,
            previous_swing_low,
        )

        liquidity_sweep = detect_liquidity_sweep(
            current_candle["high"],
            current_candle["low"],
            current_candle["close"],
            previous_swing_high,
            previous_swing_low,
        )

        sweep_strength = calculate_sweep_strength(
            liquidity_sweep,
            current_candle["high"],
            current_candle["low"],
            current_candle["close"],
            previous_swing_high,
            previous_swing_low,
        )

        liquidity_strength = normalize_liquidity_strength(
            sweep_strength,
        )

        signal = detect_order_block(
            symbol_data.get("15m", []),
        )

        return make_decision(
            signal=signal,
            liquidity_sweep=liquidity_sweep,
            liquidity_strength=liquidity_strength,
            market_structure=market_structure,
            bos_quality=bos_quality,
            choch=choch,
            volume_ratio=volume_ratio,
            open_interest_change=open_interest_change,
            funding_rate=funding_rate,
        )


engine = StrategyEngine(symbol="BTCUSDT")


def strategy_callback(
    current_candle: dict[str, Any],
    market_snapshot: dict[str, Any],
) -> dict[str, Any]:
    """
    Callback expected by BacktestRunner.
    """

    return engine.analyze(
        current_candle=current_candle,
        market_snapshot=market_snapshot,
    )
