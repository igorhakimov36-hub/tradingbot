"""
Shared, pure-function mechanics for any "directional price zone that
gets touched/mitigated/extended over time" market object - Order
Blocks and Breaker Blocks both need identical math here; Liquidity
Pools and any future zone-shaped module will too. Extracted after the
second occurrence (Breaker Blocks) rather than guessed at up front.

Every function is a pure computation over primitive values - no class,
no hidden state - so each market object's dataclass owns its own
fields and simply calls these to update them. Kept independently unit
tested so a bug here cannot hide inside two different market objects'
test suites without being caught directly.
"""

from typing import Any, Literal

Direction = Literal["bullish", "bearish"]
MitigationStatus = Literal["unmitigated", "partially_mitigated", "fully_mitigated"]


def compute_mitigation(
    direction: Direction,
    zone_high: float,
    zone_low: float,
    deepest_penetration: float,
    candle: dict[str, Any],
) -> tuple[float, float]:
    """
    Returns (new_deepest_penetration, mitigation_pct in [0, 1]).

    Bullish zones sit below price and fill from the top (zone_high)
    downward; bearish zones sit above price and fill from the bottom
    (zone_low) upward. Uses wick (high/low) penetration - "did price
    trade at this level" - not a close-through-the-zone requirement.
    """

    zone_span = zone_high - zone_low

    if zone_span <= 0:
        # Defensive only - detection is expected to guarantee a
        # positive span; treat a degenerate zone as already resolved
        # rather than dividing by zero.
        return deepest_penetration, 1.0

    if direction == "bullish":
        new_deepest = min(deepest_penetration, candle["low"])
        raw = (zone_high - new_deepest) / zone_span

    else:
        new_deepest = max(deepest_penetration, candle["high"])
        raw = (new_deepest - zone_low) / zone_span

    return new_deepest, min(1.0, max(0.0, raw))


def mitigation_status_from_pct(mitigation_pct: float) -> MitigationStatus:
    if mitigation_pct >= 1.0:
        return "fully_mitigated"

    if mitigation_pct > 0.0:
        return "partially_mitigated"

    return "unmitigated"


def is_touching_zone(
    candle: dict[str, Any],
    zone_high: float,
    zone_low: float,
) -> bool:
    return candle["low"] <= zone_high and candle["high"] >= zone_low


def update_favorable_extreme(
    direction: Direction,
    current_extreme: float,
    candle: dict[str, Any],
) -> float:
    """
    Tracks the furthest the market has moved in the zone's own
    "continuation" direction since it formed - the raw ingredient for
    impulse_strength. Never capped, unlike mitigation_pct.
    """

    if direction == "bullish":
        return max(current_extreme, candle["high"])

    return min(current_extreme, candle["low"])


def compute_impulse_strength(
    direction: Direction,
    zone_high: float,
    zone_low: float,
    extreme_since_creation: float,
    atr_at_creation: float | None,
) -> float | None:
    if not atr_at_creation:
        return None

    if direction == "bullish":
        return (extreme_since_creation - zone_high) / atr_at_creation

    return (zone_low - extreme_since_creation) / atr_at_creation
