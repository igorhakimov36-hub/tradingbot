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


def copy_snapshot_dict(cached: dict[str, Any]) -> dict[str, Any]:
    """
    A fast, purpose-built independent copy of a tracker snapshot()
    dict, for callers that cache their pre-built snapshot and must
    still hand out a fully mutation-isolated copy on every call
    (Sprint 1B, performance-only).

    Deliberately NOT copy.deepcopy(): measured directly (profiling a
    real 2-month backtest) to be catastrophically expensive at this
    object count - 400+ million internal calls, a ~7.5x REGRESSION
    versus not caching at all, because deepcopy's generic, memo-
    tracking, type-dispatch machinery pays large per-object overhead
    that a snapshot dict's actual shape never needs.

    Every tracker's snapshot() has the identical shape this assumes:
    a flat top-level dict whose list-valued entries ("active",
    "mitigated", "swept", "equal_highs", "equal_lows", ...) each hold
    flat per-object dicts of primitives (float/str/datetime/None) with
    exactly one nested mutable field, "context" (a dict). This copies
    exactly that shape - new top-level dict, new lists, new per-object
    dicts, new context dicts - without walking arbitrary depth or
    tracking object identity, which is what makes it fast: it is O(total
    fields) with small constant overhead, not O(total fields) with
    deepcopy's much larger per-field constant.

    If a tracker's snapshot() shape ever changes to include a NEW
    nested mutable field beyond "context", this function must be
    updated too - it does not generically detect nested mutability.
    """

    result: dict[str, Any] = {}

    for key, value in cached.items():
        if isinstance(value, list):
            result[key] = [
                {**item, "context": dict(item["context"])} if "context" in item else dict(item)
                for item in value
            ]
        else:
            result[key] = value

    return result


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
