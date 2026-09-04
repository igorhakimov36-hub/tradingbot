"""
Order Block Hybrid Policy C - SOL VALIDATION experiment analysis
functions. RESEARCH-ONLY, not wired into production. Implements exactly
the frozen protocol in docs/order_block_policy_c_validation_protocol.md -
these functions must not be altered after VALIDATION results are seen;
any change here after the fact would invalidate the frozen-protocol
guarantee that document exists to provide.

Two pure, independently testable pieces:
- `first_passage_outcome`: the competing-risks resolution rule (favorable
  excursion vs. close-confirmed invalidation, first to occur wins).
- `deduplicate_events`: the frozen structural-identity/zone-overlap/
  timing-only clustering rule, never using price outcome.
"""

from typing import Any, Literal

from strategy.features.order_block import Direction

Outcome = Literal["favorable", "invalidation", "censored"]


def first_passage_outcome(
    direction: Direction,
    traversal_close: float,
    zone_high: float,
    zone_low: float,
    atr: float,
    favorable_atr_multiple: float,
    forward_candles: list[dict[str, Any]],
) -> dict[str, Any]:
    """
    forward_candles must be STRICTLY AFTER the traversal candle, in
    forward chronological order - the traversal candle itself
    contributes no outcome (per protocol: "no same-event-candle
    execution or outcome credit").

    Returns {"outcome": "favorable" | "invalidation" | "censored",
    "ambiguous": bool, "bars": int | None} - `bars` counts completed
    candles from the traversal candle (1 = the very next candle).
    `ambiguous` is True only when both conditions are met on the SAME
    candle (intrabar order unknown) - such a candle is conservatively
    classified as "invalidation" for the primary result, per protocol.
    """

    for i, candle in enumerate(forward_candles, start=1):
        if direction == "bullish":
            favorable = (candle["high"] - traversal_close) >= favorable_atr_multiple * atr
            invalidated = candle["close"] < zone_low
        else:
            favorable = (traversal_close - candle["low"]) >= favorable_atr_multiple * atr
            invalidated = candle["close"] > zone_high

        if favorable and invalidated:
            return {"outcome": "invalidation", "ambiguous": True, "bars": i}
        if invalidated:
            return {"outcome": "invalidation", "ambiguous": False, "bars": i}
        if favorable:
            return {"outcome": "favorable", "ambiguous": False, "bars": i}

    return {"outcome": "censored", "ambiguous": False, "bars": None}


def deduplicate_events(
    events: list[dict[str, Any]],
    max_bar_gap: int = 20,
) -> tuple[list[dict[str, Any]], dict[Any, list[Any]]]:
    """
    Frozen de-duplication rule (docs/order_block_policy_c_validation_protocol.md):
    groups events by direction, then clusters events whose zone overlaps
    the most-recently-added cluster member's zone AND whose
    `traversal_bar_i` is within `max_bar_gap` bars of it. The earliest
    event (by `traversal_bar_i`) in each cluster is the representative.

    Each event dict must have: "id" (any hashable, unique), "direction",
    "traversal_bar_i", "zone_high", "zone_low".

    Returns (representatives, cluster_map) - cluster_map maps each
    representative's "id" to the list of every member id in its cluster
    (including itself), for residual-dependence reporting.
    """

    by_direction: dict[str, list[dict[str, Any]]] = {}
    for event in events:
        by_direction.setdefault(event["direction"], []).append(event)

    representatives: list[dict[str, Any]] = []
    cluster_map: dict[Any, list[Any]] = {}

    for direction, group in by_direction.items():
        group_sorted = sorted(group, key=lambda e: e["traversal_bar_i"])
        clusters: list[list[dict[str, Any]]] = []

        for event in group_sorted:
            placed = False
            for cluster in clusters:
                last = cluster[-1]
                overlap = event["zone_low"] < last["zone_high"] and event["zone_high"] > last["zone_low"]
                close_in_time = (event["traversal_bar_i"] - last["traversal_bar_i"]) <= max_bar_gap
                if overlap and close_in_time:
                    cluster.append(event)
                    placed = True
                    break
            if not placed:
                clusters.append([event])

        for cluster in clusters:
            representative = cluster[0]  # already sorted ascending by traversal_bar_i
            representatives.append(representative)
            cluster_map[representative["id"]] = [member["id"] for member in cluster]

    return representatives, cluster_map
