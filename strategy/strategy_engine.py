from typing import Any

from strategy.decision_engine import make_decision


class StrategyEngine:
    """
    Main strategy entry point.
    """

    def analyze(
        self,
        current_candle: dict[str, Any],
        visible_history: list[dict[str, Any]],
        market_snapshot: dict[str, Any],
    ) -> dict[str, Any]:

        funding_rate = 0.0

        funding = market_snapshot.get("funding", {}).get("current")

        if funding is not None:
            funding_rate = float(funding.get("lastFundingRate", 0.0))

        return make_decision(
            signal="bullish_order_block",
            liquidity_sweep="BULLISH_SWEEP",
            liquidity_strength=2.0,
            market_structure="BULLISH",
            bos_quality={
                "bos": "BULLISH_BOS",
                "quality": "STRONG",
            },
            choch="NO_CHOCH",
            volume_ratio=2.0,
            open_interest_change=2.0,
            funding_rate=funding_rate,
        )


engine = StrategyEngine()


def strategy_callback(
    current_candle: dict[str, Any],
    visible_history: list[dict[str, Any]],
    market_snapshot: dict[str, Any],
) -> dict[str, Any]:
    """
    Callback expected by BacktestRunner.
    """

    return engine.analyze(
        current_candle=current_candle,
        visible_history=visible_history,
        market_snapshot=market_snapshot,
    )
