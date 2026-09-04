"""
LuxAlgo Wick-Extremity Zone — controlled geometry ablation.
RESEARCH-ONLY, not wired into production. `strategy/features/liquidity_pool.py`
is completely unmodified. See
docs/liquidity_pool_wick_extremity_train_report.md for the full
architecture audit this module's design is based on.

Architecture summary (full audit in the report; restated briefly here
since it directly motivates every function below)
------------------------------------------------------------------------
Production `LiquidityPool` is a BAND, not a line: `zone_high`/`zone_low`,
which widen as more same-direction candidates land within
`atr * tolerance_atr_multiplier` of the current band. Both wick-breach
and close-reclaim (Policy A's sweep check) are evaluated against the
SAME boundary - `zone_high` for buy_side, `zone_low` for sell_side - the
band's OUTER edge. Three source types contribute candidate touches:
`round_number` (pure arithmetic - NO candle anchor, ever),
`session_high`/`session_low` (the exact candle that set the session
extreme - directly anchorable via `high_timestamp`/`low_timestamp`),
and `equal_highs`/`equal_lows` (the contributed "price" is
`EqualLevelCluster.level`, a running MEAN of that cluster's own
`pivot_prices` - NOT any single candle's own wick - anchorable only by
looking one level deeper into the cluster's own `pivot_prices`/
`pivot_timestamps` to find its most extreme individual pivot).

Eligibility rule (frozen, declared before any outcome was computed)
------------------------------------------------------------------------
A pool is Wick-Zone-eligible if and only if the SPECIFIC touch that set
its final `zone_high` (buy_side) or `zone_low` (sell_side) - i.e. the
touch defining the pool's own outermost boundary - has a resolvable
candle anchor. `round_number`-sourced defining touches are never
eligible. `session_high`/`session_low`-sourced defining touches are
eligible using that period's own `high_timestamp`/`low_timestamp`.
`equal_highs`/`equal_lows`-sourced defining touches are eligible using
the contributing cluster's own most extreme individual pivot (its
`pivot_prices`/`pivot_timestamps`, captured at the exact moment the
touch was registered - never a later, further-evolved version of that
cluster). Mixed-source pools are evaluated purely by which touch set
the *boundary* - a pool with other, non-defining touches from
non-anchorable sources is still eligible if its OWN outermost touch is
anchorable.

Tie-break (frozen): if more than one candidate anchor shares the
identical extreme price, the EARLIEST timestamp among them wins,
deterministically.
"""

from dataclasses import dataclass
from typing import Any, Literal

Direction = Literal["buy_side", "sell_side"]


@dataclass(frozen=True)
class WickZoneAnchor:
    """A resolved, frozen anchor for one pool's Wick-Zone geometry."""

    anchor_timestamp: Any
    anchor_open: float
    anchor_high: float
    anchor_low: float
    anchor_close: float
    source: str


def wick_zone_boundaries(direction: Direction, anchor: WickZoneAnchor) -> tuple[float, float]:
    """
    Returns (outer_boundary, inner_boundary).
    High-side (buy_side): outer = anchor.high; inner = max(open, close).
    Low-side (sell_side): outer = anchor.low; inner = min(open, close).
    """

    if direction == "buy_side":
        return anchor.anchor_high, max(anchor.anchor_open, anchor.anchor_close)
    return anchor.anchor_low, min(anchor.anchor_open, anchor.anchor_close)


def check_wick_zone_sweep(
    direction: Direction,
    candle: dict[str, Any],
    outer_boundary: float,
    inner_boundary: float,
) -> bool:
    """
    Full rejection of the wick zone - NOT merely touching it.
    High-side (buy_side, bearish Wick-Zone Sweep): candle["high"] >
    outer (strictly) AND candle["close"] < inner (strictly).
    Low-side (sell_side, bullish Wick-Zone Sweep): candle["low"] < outer
    (strictly) AND candle["close"] > inner (strictly).
    """

    if direction == "buy_side":
        return candle["high"] > outer_boundary and candle["close"] < inner_boundary
    return candle["low"] < outer_boundary and candle["close"] > inner_boundary


def resolve_anchor(
    defining_touch_source: str,
    defining_touch_price: float,
    session_period: dict[str, Any] | None,
    equal_level_cluster: dict[str, Any] | None,
    candle_lookup: dict[Any, dict[str, Any]],
) -> WickZoneAnchor | None:
    """
    Resolves the frozen anchor for a pool's defining (outermost) touch,
    or returns None if the source is not anchorable (round_number) or
    the anchor candle cannot be located.

    `session_period`: the exact SessionBoundariesTracker period dict
    that contributed this touch (already matched by caller via
    direction/timestamp), used only for `session_high`/`session_low`.

    `equal_level_cluster`: the exact EqualLevelCluster snapshot dict
    that contributed this touch (already matched by caller), used only
    for `equal_highs`/`equal_lows` - captured at the moment of
    registration, never a later snapshot.

    `candle_lookup`: timestamp -> candle dict, for resolving a resolved
    anchor timestamp into its own OHLC.
    """

    if defining_touch_source == "round_number":
        return None

    if defining_touch_source in ("session_high", "session_low"):
        if session_period is None:
            return None
        anchor_ts = (
            session_period.get("high_timestamp") if defining_touch_source == "session_high"
            else session_period.get("low_timestamp")
        )
        if anchor_ts is None or anchor_ts not in candle_lookup:
            return None
        c = candle_lookup[anchor_ts]
        return WickZoneAnchor(anchor_ts, c["open"], c["high"], c["low"], c["close"], defining_touch_source)

    if defining_touch_source in ("equal_highs", "equal_lows"):
        if equal_level_cluster is None:
            return None
        prices = equal_level_cluster.get("pivot_prices", [])
        timestamps = equal_level_cluster.get("pivot_timestamps", [])
        if not prices or len(prices) != len(timestamps):
            return None

        if defining_touch_source == "equal_highs":
            extreme_price = max(prices)
        else:
            extreme_price = min(prices)

        # Deterministic tie-break: earliest timestamp among ties.
        candidates = sorted(
            (ts for p, ts in zip(prices, timestamps) if p == extreme_price)
        )
        if not candidates:
            return None
        anchor_ts = candidates[0]
        if anchor_ts not in candle_lookup:
            return None
        c = candle_lookup[anchor_ts]
        return WickZoneAnchor(anchor_ts, c["open"], c["high"], c["low"], c["close"], defining_touch_source)

    return None
