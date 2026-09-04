"""
Causal defining-touch / eligibility resolution for the Wick-Extremity
Zone ablation.

Frozen eligibility rule (see docs/liquidity_pool_wick_extremity_train_protocol.md):
a pool is Wick-Zone-eligible at any point in its life iff its CURRENT
defining touch - the touch that set the pool's own current zone_high
(buy_side) / zone_low (sell_side), tracked causally using only touches
already registered by that point - has a resolvable real-candle anchor.
Frozen tie-break: if more than one touch shares the identical extreme
price, the EARLIEST timestamp among them wins.

This module operates purely on the touch ledger produced by
strategy/research/liquidity_pool_wick_extremity_ledger.py (a list of
per-touch dicts for ONE pool, already in chronological order) - it does
not touch production code and has no side effects.
"""

from typing import Any

from strategy.research.liquidity_pool_wick_extremity import WickZoneAnchor, resolve_anchor


def current_defining_touch(touches: list[dict[str, Any]], direction: str) -> dict[str, Any] | None:
    """
    Given a pool's own touches so far (chronological order, i.e. only
    touches causally known up to "now"), returns the touch dict that
    currently defines the pool's outer boundary, or None if `touches`
    is empty.
    """

    if not touches:
        return None

    if direction == "buy_side":
        extreme_price = max(t["price"] for t in touches)
    else:
        extreme_price = min(t["price"] for t in touches)

    tied = [t for t in touches if t["price"] == extreme_price]
    return min(tied, key=lambda t: t["timestamp"])


def anchor_for_defining_touch(
    defining_touch: dict[str, Any],
    candle_lookup: dict[Any, dict[str, Any]],
) -> WickZoneAnchor | None:
    """
    Resolves the Wick-Zone anchor for one defining touch, dispatching
    resolve_anchor's session_period / equal_level_cluster arguments by
    the touch's own recorded source. Returns None if the source is not
    anchorable (round_number) or the anchor candle cannot be located -
    a pool is simply not Wick-Zone-eligible at this point in that case.
    """

    source = defining_touch["source"]
    source_context = defining_touch.get("source_context")

    session_period = source_context if source in ("session_high", "session_low") else None
    equal_level_cluster = source_context if source in ("equal_highs", "equal_lows") else None

    return resolve_anchor(
        defining_touch_source=source,
        defining_touch_price=defining_touch["price"],
        session_period=session_period,
        equal_level_cluster=equal_level_cluster,
        candle_lookup=candle_lookup,
    )
