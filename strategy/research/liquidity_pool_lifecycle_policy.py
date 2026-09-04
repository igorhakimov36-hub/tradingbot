"""
Liquidity Pool Lifecycle Research - pure, testable analysis functions.
RESEARCH-ONLY, not wired into production. LiquidityPoolTracker
(strategy/features/liquidity_pool.py) is completely unmodified by this
module.

Two confirmed limitations motivate this research (see
docs/liquidity_pool_lifecycle_research_report.md for full findings):
1. A pool may remain "active" (unswept) after one or many clean closes
   beyond its boundary, since the production sweep rule only fires on a
   same-candle wick-beyond-then-close-back pattern.
2. A later wick-beyond-and-close-back candle can be classified as a
   fresh sweep even though the pool may have already experienced
   sustained acceptance (multiple prior closes beyond) - its resting
   liquidity may already be gone by the time the "official" sweep fires.

Lifecycle path classification (six mutually exclusive terminal
categories, applied to a fully-recorded pool timeline)
------------------------------------------------------------------------
- "same_candle_sweep": the production tracker's own sweep condition
  fires (wick beyond + close back, same candle) with no clean close
  beyond ever occurring strictly before the sweep candle.
- "delayed_current_rule_sweep": the production tracker's sweep
  condition eventually fires, but only after at least one earlier,
  clean close beyond had already occurred on a prior candle - exactly
  the confirmed limitation #2 case.
- "fast_multi_candle_rejection": a clean close beyond occurred, the
  production tracker's rule never fired, but price closed back through
  the boundary within `fast_threshold_bars` bars of that first close
  beyond.
- "sustained_acceptance": same as above, but the reclaim (if any) took
  longer than `fast_threshold_bars` bars - or is still pending
  (unresolved, right-censored) at end of window while a clean close
  beyond has already occurred.
- "never_resolved": no clean close beyond ever occurred, AND the
  production tracker's sweep rule never fired either - the pool was
  simply never meaningfully tested before expiry/censoring.

"clean_break_acceptance" (candidate #2 in the original research
framing) is deliberately NOT a seventh terminal bucket - it describes
an intermediate EVENT (a close beyond with no same-candle rejection),
not a distinct final fate. Every pool classified as
"fast_multi_candle_rejection", "sustained_acceptance", or
"delayed_current_rule_sweep" experienced this event at least once; it
is exposed as `record["first_close_beyond_bar_i"] is not None`, not as
a mutually-exclusive category of its own. This interpretation is stated
explicitly rather than silently forcing an artificial seventh bucket.

`fast_threshold_bars` is NOT chosen here - it is a parameter, to be set
from the empirical TRAIN time-to-reclaim distribution (median or a
visible distributional feature), never from P&L, and passed in by the
caller after that distribution has been examined.
"""

from typing import Any, Literal

LifecyclePath = Literal[
    "same_candle_sweep",
    "delayed_current_rule_sweep",
    "fast_multi_candle_rejection",
    "sustained_acceptance",
    "never_resolved",
]


def classify_lifecycle_path(
    record: dict[str, Any],
    fast_threshold_bars: int,
) -> LifecyclePath:
    """
    record must have: "first_close_beyond_bar_i" (int | None),
    "current_rule_swept_bar_i" (int | None), "first_reclaim_bar_i"
    (int | None - the first candle, strictly after first_close_beyond,
    whose CLOSE is back on the inside of the boundary), "censored"
    (bool).
    """

    swept_bar = record["current_rule_swept_bar_i"]
    first_beyond = record["first_close_beyond_bar_i"]

    if swept_bar is not None:
        # A clean close beyond occurring on or after the sweep candle
        # itself does not count as "prior" - only a close beyond
        # strictly BEFORE the sweep candle indicates the pool had
        # already been clean-accepted before this "official" sweep.
        if first_beyond is None or first_beyond >= swept_bar:
            return "same_candle_sweep"
        return "delayed_current_rule_sweep"

    if first_beyond is None:
        return "never_resolved"

    reclaim_bar = record["first_reclaim_bar_i"]
    if reclaim_bar is None:
        return "never_resolved"

    bars_beyond = reclaim_bar - first_beyond
    if bars_beyond <= fast_threshold_bars:
        return "fast_multi_candle_rejection"
    return "sustained_acceptance"


def deduplicate_pools(
    pools: list[dict[str, Any]],
    max_bar_gap: int = 20,
) -> tuple[list[dict[str, Any]], dict[Any, list[Any]]]:
    """
    Structural-identity-only clustering (never price outcome), mirroring
    the Order Block VALIDATION experiment's frozen rule: groups pools by
    direction (buy_side/sell_side), then clusters pools whose zone
    overlaps the most-recently-added cluster member's zone AND whose
    `origin_bar_i` is within `max_bar_gap` bars of it. The earliest pool
    (by `origin_bar_i`) in each cluster is the representative.

    Each pool dict must have: "id" (unique, hashable), "direction",
    "origin_bar_i", "zone_high", "zone_low" (the pool's zone bounds AT
    CREATION - clustering is a structural/timing judgment made at pool
    formation, not re-evaluated against a later, possibly-widened zone).

    Returns (representatives, cluster_map).
    """

    by_direction: dict[str, list[dict[str, Any]]] = {}
    for pool in pools:
        by_direction.setdefault(pool["direction"], []).append(pool)

    representatives: list[dict[str, Any]] = []
    cluster_map: dict[Any, list[Any]] = {}

    for direction, group in by_direction.items():
        group_sorted = sorted(group, key=lambda p: p["origin_bar_i"])
        clusters: list[list[dict[str, Any]]] = []

        for pool in group_sorted:
            placed = False
            for cluster in clusters:
                last = cluster[-1]
                overlap = pool["zone_low"] < last["zone_high"] and pool["zone_high"] > last["zone_low"]
                close_in_time = (pool["origin_bar_i"] - last["origin_bar_i"]) <= max_bar_gap
                if overlap and close_in_time:
                    cluster.append(pool)
                    placed = True
                    break
            if not placed:
                clusters.append([pool])

        for cluster in clusters:
            representative = cluster[0]
            representatives.append(representative)
            cluster_map[representative["id"]] = [member["id"] for member in cluster]

    return representatives, cluster_map


def first_passage_outcome_pool(
    direction: Literal["buy_side", "sell_side"],
    boundary_close_price: float,
    zone_high: float,
    zone_low: float,
    atr: float,
    continuation_atr_multiple: float,
    forward_candles: list[dict[str, Any]],
) -> dict[str, Any]:
    """
    Unconditional competing-risks first passage from the first clean
    close beyond the pool's outer boundary (the reference candle itself
    contributes no outcome - forward_candles must start with the candle
    STRICTLY AFTER that reference candle).

    Competing outcomes, per candle, checked in forward order:
    - "reclaim": close back through the (currently-live) boundary
      (buy_side: close < zone_high; sell_side: close > zone_low).
    - "continuation": price travels `continuation_atr_multiple` * atr
      FURTHER beyond the boundary than the reference close was
      (buy_side: high - boundary_close_price >= continuation_atr_multiple * atr;
      sell_side: boundary_close_price - low >= continuation_atr_multiple * atr).

    zone_high/zone_low may be passed as the CURRENT, live (possibly
    already-widened) zone bounds for the specific forward candle being
    evaluated by the caller - this function itself treats them as fixed
    for the whole call, so a caller wanting to track a live-updating
    zone must call this per-candle itself or pre-resolve the boundary
    sequence. In this research's own harness, the boundary is held fixed
    at its value at the reference (first-close-beyond) candle, since
    further pool growth after a clean break beyond is itself a
    diagnostic fact worth reporting separately, not folded silently into
    the boundary definition.

    Returns {"outcome": "reclaim" | "continuation" | "censored",
    "ambiguous": bool, "bars": int | None}. Same-candle ambiguity (both
    conditions true) is conservatively counted as "reclaim" - matching
    the Order Block VALIDATION protocol's own conservative convention.
    """

    for i, candle in enumerate(forward_candles, start=1):
        if direction == "buy_side":
            reclaimed = candle["close"] < zone_high
            continued = (candle["high"] - boundary_close_price) >= continuation_atr_multiple * atr
        else:
            reclaimed = candle["close"] > zone_low
            continued = (boundary_close_price - candle["low"]) >= continuation_atr_multiple * atr

        if reclaimed and continued:
            return {"outcome": "reclaim", "ambiguous": True, "bars": i}
        if reclaimed:
            return {"outcome": "reclaim", "ambiguous": False, "bars": i}
        if continued:
            return {"outcome": "continuation", "ambiguous": False, "bars": i}

    return {"outcome": "censored", "ambiguous": False, "bars": None}
