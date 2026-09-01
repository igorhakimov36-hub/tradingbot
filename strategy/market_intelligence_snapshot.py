"""
Market Intelligence Snapshot Builder - Phase 2.1, Step 1.

Purpose
-------
The ONLY interface between the Market Intelligence modules
(strategy/features/*) and Strategy Engine V2. Per the approved Phase 2
architectural review (docs/strategy_engine_v2_architecture.md):

    Replay
      -> Market Intelligence Modules  (14 trackers, already synced this step)
      -> Snapshot Builder             (this file - pure mapping only)
      -> Market Intelligence Snapshot (one object per replay step)
      -> Strategy Engine V2           (reads ONLY the snapshot, never a tracker)

This module performs NO feature calculation, NO detection, and NO
scoring. Every value it produces is either copied verbatim from a
tracker's already-computed snapshot() output, or a simple structural
reshaping of already-known values (which list an item came from, a
plain absolute-distance arithmetic already used identically by every
zone/level module for itself). Nothing here decides whether a market
condition is "true" - that is Strategy Engine V2's job, reading this
object's raw fields.

The real taxonomy - four families, not fourteen modules
----------------------------------------------------------
Reviewing all fourteen Phase 1 modules' output side by side (Phase 2
review, section 2) found the same handful of institutional shapes
recurring across module boundaries:

- Zones: a price range with a lifecycle (created -> touched ->
  resolved) - Fair Value Gaps, Order Blocks, Breaker Blocks, Liquidity
  Pools. Unified here into one `zones` list.
- Levels: a single reference price, not a range - Equal Highs/Lows,
  Session highs/lows (previous CLOSED period only, not the full
  historical apparatus), Volume Profile POC/VAH/VAL/HVN/LVN. Unified
  into one `levels` list, deliberately looser than Zones.
- Order Flow: Delta (bar-level) and CVD (cumulative/anchored) - kept as
  their own `order_flow` section since they are always read together.
- Intermarket: Correlation Engine/SMT instances, keyed by pair name -
  inherently plural, kept as its own `intermarket` section.

Plus two cross-cutting, non-family pieces with their own top-level
slots: `structure` (BOS/CHOCH/swing levels, the most fundamental,
most-referenced fact) and `sessions` (a thin "which session is active
right now" projection).

Design decisions made while implementing (documented, not hidden)
--------------------------------------------------------------------
1. `status` on a Zone ("active"|"resolved") is derived purely
   STRUCTURALLY, from which list of its source tracker's snapshot() the
   entry came from (active vs mitigated/filled/swept) - never by
   string-matching a status field, so it introduces no new logic.
2. `zone_relative_position` needed a third value beyond the review's
   original above_price/below_price sketch: `inside_price`, for when
   current price sits inside the zone itself. A two-valued enum would
   have silently misclassified that case - found and fixed while
   implementing, not carried over from the sketch unchanged.
3. `resolved_at`: only Liquidity Pools track an explicit resolution
   timestamp (`swept_timestamp`). Fair Value Gaps, Order Blocks, and
   Breaker Blocks were never built with a "filled_at"/"mitigated_at"
   field - `resolved_at` is honestly `None` for those three kinds
   rather than fabricated from some heuristic. Flagged as a real,
   scoped gap in the validation report, not silently invented here.
4. `resolution_pct` is `None` for Liquidity Pools - sweeping is binary
   (swept/unswept), there is no partial-resolution concept for a pool
   the way there is a fill_pct/mitigation_pct for a zone.
5. `distance_from_price` for Levels sourced from Session Boundaries or
   Volume Profile (which do not compute this for themselves, unlike
   every zone-shaped tracker) is the one narrow arithmetic step this
   module performs directly: a plain absolute distance to an already-
   known price, identical in shape to what every zone tracker already
   computes for itself. This is bookkeeping consistency, not new
   market intelligence, and is applied via one small private helper
   (`_distance`) rather than duplicated inline per call site.
6. `order_flow.delta` is passed through IN FULL, including
   `cumulative_delta` - "reuse existing tracker outputs exactly as they
   are" means this module does not selectively drop fields. The Phase 2
   review's finding that `cumulative_delta` is inferior to CVD's
   anchored outputs is addressed by documentation here, not by
   filtering: Strategy Engine V2's setups should treat `order_flow.cvd`
   as authoritative for any cumulative/trend order-flow reasoning, and
   `order_flow.delta.cumulative_delta` as present for completeness/
   audit only.

Inputs
------
Every parameter is an already-computed tracker `.snapshot()` output (or
a dict of them, for multi-instance families like CVD's anchors or
Correlation Engine's pairs) - never a tracker object, never raw
candles. Every module input is optional (defaults to an empty/None
state) so a deployment that has not wired up every one of the fourteen
modules still gets a valid, honestly-partial snapshot rather than an
error.

Outputs
-------
One `MarketIntelligenceSnapshot` per call - see the dataclasses below
for the exact shape. Every Zone/Level also carries `raw`, the
completely unmodified original tracker dict, so unifying fields never
discards institution-specific detail (Order Block's `impulse_strength`,
Liquidity Pool's `sweep_penetration`/`sources`, etc.) - Context
Preservation applied to the aggregation layer itself, not just each
individual module.

Replay Safety
-------------
This module has no state of its own and performs no candle-history
bookkeeping - replay safety is entirely inherited from whichever
trackers' already-synced, already-replay-safe snapshot() outputs are
passed in. Calling this function twice with the same inputs always
produces an identical result (pure function, no hidden state).

Live Trading
------------
Identical code path in backtest and live - this function only ever
reads already-computed dicts, so it cannot behave differently depending
on how those dicts were produced.

Computational Complexity
-------------------------
O(total zones + total levels) per call - a single pass reshaping
already-bounded lists (each individually bounded by its own tracker's
max_tracked_* limit). No new scanning of candle history anywhere.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal

ZoneKind = Literal["fvg", "order_block", "breaker_block", "liquidity_pool"]
ZoneStatus = Literal["active", "resolved"]
ZoneRelativePosition = Literal["above_price", "below_price", "inside_price"]

LevelKind = Literal[
    "equal_highs", "equal_lows",
    "session_high", "session_low",
    "poc", "vah", "val", "hvn", "lvn",
]


@dataclass(frozen=True)
class Zone:
    kind: ZoneKind
    direction: str
    zone_relative_position: ZoneRelativePosition
    zone_high: float
    zone_low: float
    status: ZoneStatus
    resolution_detail: str
    resolution_pct: float | None
    touch_count: int | None
    distance_from_price: float
    created_at: datetime | None
    resolved_at: datetime | None
    source_module: str
    raw: dict[str, Any]


@dataclass(frozen=True)
class Level:
    kind: LevelKind
    price: float
    distance_from_price: float | None
    swept: bool | None
    source_module: str
    raw: dict[str, Any]


@dataclass(frozen=True)
class MarketIntelligenceSnapshot:
    symbol: str
    timeframe: str
    timestamp: datetime
    current_price: float

    structure: dict[str, Any]
    zones: list[Zone]
    levels: list[Level]
    order_flow: dict[str, Any]
    sessions: dict[str, Any]
    intermarket: dict[str, Any]
    volume_profile: dict[str, Any]
    data_quality: dict[str, Any]
    context: dict[str, Any] = field(default_factory=dict)


def _distance(current_price: float, level_price: float) -> float:
    return abs(current_price - level_price)


def _zone_relative_position(current_price: float, zone_high: float, zone_low: float) -> ZoneRelativePosition:
    if current_price < zone_low:
        return "above_price"

    if current_price > zone_high:
        return "below_price"

    return "inside_price"


def _map_zones(
    raw_entries: list[dict[str, Any]],
    kind: ZoneKind,
    status: ZoneStatus,
    source_module: str,
    current_price: float,
    resolution_field: str,
    resolved_at_field: str | None,
) -> list[Zone]:
    zones = []

    for entry in raw_entries:
        zones.append(
            Zone(
                kind=kind,
                direction=entry["direction"],
                zone_relative_position=_zone_relative_position(current_price, entry["zone_high"], entry["zone_low"]),
                zone_high=entry["zone_high"],
                zone_low=entry["zone_low"],
                status=status,
                resolution_detail=entry[resolution_field],
                resolution_pct=entry.get("mitigation_pct") if "mitigation_pct" in entry else entry.get("fill_pct"),
                touch_count=entry.get("touch_count"),
                distance_from_price=entry["distance_from_price"],
                created_at=entry.get("created_at"),
                resolved_at=entry.get(resolved_at_field) if resolved_at_field else None,
                source_module=source_module,
                raw=entry,
            )
        )

    return zones


def _map_levels(
    raw_entries: list[dict[str, Any]],
    kind: LevelKind,
    source_module: str,
    price_field: str,
    current_price: float | None,
    swept_field: str | None = None,
    distance_field: str | None = None,
) -> list[Level]:
    levels = []

    for entry in raw_entries:
        price = entry[price_field]

        if distance_field is not None and distance_field in entry:
            distance = entry[distance_field]
        elif current_price is not None:
            distance = _distance(current_price, price)
        else:
            distance = None

        swept = None
        if swept_field is not None:
            swept = entry.get(swept_field) == "swept"

        levels.append(
            Level(
                kind=kind,
                price=price,
                distance_from_price=distance,
                swept=swept,
                source_module=source_module,
                raw=entry,
            )
        )

    return levels


def build_market_intelligence_snapshot(
    symbol: str,
    timeframe: str,
    timestamp: datetime,
    current_price: float,
    *,
    market_structure: dict[str, Any] | None = None,
    fair_value_gaps: dict[str, Any] | None = None,
    order_blocks: dict[str, Any] | None = None,
    breaker_blocks: dict[str, Any] | None = None,
    equal_levels: dict[str, Any] | None = None,
    liquidity_pools: dict[str, Any] | None = None,
    session_boundaries: dict[str, Any] | None = None,
    volume_profile: dict[str, Any] | None = None,
    delta: dict[str, Any] | None = None,
    cvd: dict[str, dict[str, Any]] | None = None,
    intermarket: dict[str, dict[str, Any]] | None = None,
) -> MarketIntelligenceSnapshot:
    zones: list[Zone] = []
    levels: list[Level] = []

    if fair_value_gaps:
        zones += _map_zones(
            fair_value_gaps.get("active", []), "fvg", "active", "fair_value_gap",
            current_price, resolution_field="fill_status", resolved_at_field=None,
        )
        zones += _map_zones(
            fair_value_gaps.get("filled", []), "fvg", "resolved", "fair_value_gap",
            current_price, resolution_field="fill_status", resolved_at_field=None,
        )

    if order_blocks:
        zones += _map_zones(
            order_blocks.get("active", []), "order_block", "active", "order_block",
            current_price, resolution_field="mitigation_status", resolved_at_field=None,
        )
        zones += _map_zones(
            order_blocks.get("mitigated", []), "order_block", "resolved", "order_block",
            current_price, resolution_field="mitigation_status", resolved_at_field=None,
        )

    if breaker_blocks:
        zones += _map_zones(
            breaker_blocks.get("active", []), "breaker_block", "active", "breaker_block",
            current_price, resolution_field="mitigation_status", resolved_at_field=None,
        )
        zones += _map_zones(
            breaker_blocks.get("mitigated", []), "breaker_block", "resolved", "breaker_block",
            current_price, resolution_field="mitigation_status", resolved_at_field=None,
        )

    if liquidity_pools:
        zones += _map_zones(
            liquidity_pools.get("active", []), "liquidity_pool", "active", "liquidity_pool",
            current_price, resolution_field="swept_status", resolved_at_field=None,
        )
        zones += _map_zones(
            liquidity_pools.get("swept", []), "liquidity_pool", "resolved", "liquidity_pool",
            current_price, resolution_field="swept_status", resolved_at_field="swept_timestamp",
        )
        # Liquidity Pool's raw dict has neither "mitigation_pct" nor
        # "fill_pct" - _map_zones' resolution_pct lookup already
        # naturally falls through to None for these, honestly
        # reflecting that sweeping is binary with no partial-
        # resolution concept, without needing an explicit override.

    if equal_levels:
        levels += _map_levels(
            equal_levels.get("equal_highs", []), "equal_highs", "equal_highs_lows",
            price_field="level", current_price=current_price,
            swept_field="swept_status", distance_field="distance_from_price",
        )
        levels += _map_levels(
            equal_levels.get("equal_lows", []), "equal_lows", "equal_highs_lows",
            price_field="level", current_price=current_price,
            swept_field="swept_status", distance_field="distance_from_price",
        )

    previous_period_high_low: dict[str, Any] = {}
    active_sessions: list[str] = []

    if session_boundaries:
        for name, data in session_boundaries.items():
            if data.get("current") is not None:
                active_sessions.append(name)

            closed = data.get("closed", [])
            if closed:
                last = closed[-1]
                previous_period_high_low[name] = {
                    "session_high": last["session_high"],
                    "session_low": last["session_low"],
                    "period_end": last["period_end"],
                }
                levels += _map_levels(
                    [last], "session_high", f"session_boundaries:{name}",
                    price_field="session_high", current_price=current_price,
                )
                levels += _map_levels(
                    [last], "session_low", f"session_boundaries:{name}",
                    price_field="session_low", current_price=current_price,
                )

    if volume_profile:
        current = volume_profile.get("current_forming_profile")

        if current:
            if current.get("poc_price") is not None:
                levels += _map_levels([current], "poc", "volume_profile", price_field="poc_price", current_price=current_price)
            if current.get("value_area_high") is not None:
                levels += _map_levels([current], "vah", "volume_profile", price_field="value_area_high", current_price=current_price)
            if current.get("value_area_low") is not None:
                levels += _map_levels([current], "val", "volume_profile", price_field="value_area_low", current_price=current_price)

            levels += _map_levels(current.get("hvn_nodes", []), "hvn", "volume_profile", price_field="price", current_price=current_price)
            levels += _map_levels(current.get("lvn_nodes", []), "lvn", "volume_profile", price_field="price", current_price=current_price)

    structure = market_structure or {
        "market_structure": "UNKNOWN",
        "last_swing_high": None,
        "last_swing_low": None,
        "bos": "NO_BOS",
        "choch": "NO_CHOCH",
    }

    data_quality: dict[str, Any] = {}
    if delta:
        data_quality["delta_bars_with_missing_data"] = delta.get("bars_with_missing_data")
    if cvd:
        data_quality["cvd_bars_with_missing_data"] = {
            name: data.get("bars_with_missing_data") for name, data in cvd.items()
        }
    if volume_profile and volume_profile.get("current_forming_profile"):
        data_quality["volume_profile_data_quality"] = volume_profile["current_forming_profile"].get("data_quality")

    return MarketIntelligenceSnapshot(
        symbol=symbol,
        timeframe=timeframe,
        timestamp=timestamp,
        current_price=current_price,
        structure=structure,
        zones=zones,
        levels=levels,
        order_flow={
            "delta": delta or {},
            "cvd": cvd or {},
        },
        sessions={
            "active_now": active_sessions,
            "previous_period_high_low": previous_period_high_low,
        },
        intermarket=intermarket or {},
        volume_profile=volume_profile or {},
        data_quality=data_quality,
        context={},
    )
