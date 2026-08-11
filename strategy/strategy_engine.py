from typing import Any


class StrategyEngine:
    """
    Coordinates the complete trading strategy.

    Pipeline:

        Liquidity
            -> Market Structure
            -> BOS / CHOCH
            -> Volume
            -> Open Interest
            -> Funding
            -> Decision Engine
    """

    def analyze(
        self,
        current_candle: dict[str, Any],
        visible_history: list[dict[str, Any]],
        market_snapshot: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Placeholder.

        In the next step this method will run the
        complete strategy pipeline.

        For now it behaves exactly like the old
        strategy callback.
        """

        return {
            "decision": "IGNORE",
            "score": 0.0,
        }