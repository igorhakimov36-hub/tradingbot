"""
Order Blocks (redesigned as market objects) - Phase 1.4 of the Smart
Money Core (see docs/smart_money_architecture.md, "Market Structure > 1.
Order Blocks").

Purpose
-------
The last opposing-direction candle before an impulsive move that breaks
structure marks where positioning against the eventual move was last
transacted - conceptually tied to dealer/market-maker inventory theory
(large participants build/adjust inventory before price moves away, and
price statistically revisits that zone as remaining orders get filled).
Price returning to this zone offers a better-defined, better-risk
re-entry than chasing the breakout candle itself.

This is NOT a new detection algorithm - the underlying rule (BOS, then
scan backward for the last opposite-colored candle) is exactly what
strategy/order_block.py already implements and strategy_engine.py
already consumes for live scoring. What changes here is the OUTPUT:
instead of a single bucketed Signal ("bullish_order_block" /
"bearish_order_block" / "no_order_block"), every detected Order Block
becomes a persistent, trackable market object with continuous
mitigation depth, touch count, and impulse strength - none of which the
original bucketed signal could express.

IMPORTANT: strategy/order_block.py and strategy_engine.py are NOT
touched or replaced by this module. They remain the live, frozen
scoring pipeline. This module is an independent Market Intelligence
Layer object, not wired into any decision-making path yet - the two
"Order Block" implementations are intended to coexist until a future
Strategy Engine redesign (out of scope here) migrates over.

Inputs
------
OHLCV only, any single timeframe - deliberately timeframe-agnostic, same
convention as every other module in this package.

Outputs (raw features only - see OrderBlockTracker.snapshot)
------------------------------------------------------------
direction, zone_high, zone_low, created_at, origin_timestamp, timeframe,
age_in_bars, formation_volume, atr_at_creation, impulse_strength,
touch_count, mitigation_status, mitigation_pct, distance_from_price,
mitigation_zone_high, mitigation_zone_low, mitigation_zone_pct,
mitigation_zone_status, context. No score, no threshold, no BUY/SELL.

Mitigation Blocks (Phase 1.6, see docs/smart_money_architecture.md,
"Market Structure > 4. Mitigation Blocks") are NOT a separate module -
the architecture doc explicitly recommends against a standalone
detector, since it would duplicate this module's own origin-candle
identification. Instead, `mitigation_zone_high`/`mitigation_zone_low`
are the origin candle's BODY (min/max of open, close) rather than its
full wick range - a tighter, higher-confidence re-entry sub-zone - with
its own independent `mitigation_zone_status`/`mitigation_zone_pct`
lifecycle tracked in parallel to the primary wick-zone fields, reusing
the exact same strategy.features.zone_lifecycle functions against a
second, narrower (zone_high, zone_low) pair. The rationale: a wick
often reflects a rejected stop-hunt rather than durable positioning,
while the body reflects where the market actually settled - a return
into the body is a stricter, more selective re-entry signal than a
return anywhere into the wick range. mitigation_zone_status/pct are
purely informational: only the primary (wick-based) mitigation_status
drives an Order Block's active -> mitigated transition, unchanged.

Dependencies
------------
Consumes MarketStructureTracker's `structural_break_event` snapshot
field (Module Logic Correction 1) for new-break detection - see
"New-Break Detection" above - and the shared is_bullish_candle /
is_bearish_candle predicates from strategy.features.utils for origin
selection. No detection logic is duplicated a second time. Consumed by:
Breaker Blocks (watches this module's `mitigated` list for
freshly-fully-mitigated entries and re-exposes them with flipped
polarity - no new plumbing required on this module for that to work,
see Future Extension Points), Liquidity Pools (zone/pool confluence).

Replay Safety
-------------
An Order Block is only exposed once its confirming break of structure
has actually happened - `created_at` records that confirmation bar's
timestamp, not the origin candle's own (earlier) timestamp, which is
preserved separately as `origin_timestamp` for provenance. You could not
have known this candle was an Order Block until the break occurred.
New-break detection consumes MarketStructureTracker's additive
`structural_break_event` (Module Logic Correction 1) rather than
re-deriving edge-triggering from a raw `bos` reading itself (Module
Logic Correction 2, Phase 2A) - see "New-Break Detection" below for why.
sync() rejects a candle history that goes backwards or diverges from
what it has already consumed (same guard every tracker in this codebase
uses), and - like LiquidityPoolTracker's equal_levels_snapshot/
session_snapshot - accepts at most one new candle per call, since
structural_break_event is a point-in-time snapshot, not a historical
record.

New-Break Detection (Module Logic Correction 2, Phase 2A)
-----------------------------------------------------------
Previously this tracker re-derived "did a break just happen" itself, by
comparing consecutive raw `bos` readings it computed independently
(`bos != "NO_BOS" and bos != self._last_bos_state`). This collapsed a
sustained trend that broke several distinct structural levels in
sequence - without ever returning to NO_BOS in between - into a single
detected break, because the comparison only distinguished *direction*,
not *which specific level* was broken (confirmed defect, see
docs/module_correction2_order_block_report.md). It now instead consumes
the `structural_break_event` its caller passes into `sync()` -
MarketStructureTracker's own additive, one-shot, per-pivot-identity
event (Module Logic Correction 1) - and creates at most one Order Block
per event. Since that event is already proven one-shot per distinct
pivot upstream, this tracker needs no separate consumption-tracking of
its own: "event is not None this bar" is the entire, sufficient trigger
condition. `previous_swing_high`/`previous_swing_low`/`bos` are no
longer computed independently here at all - removing a second,
redundant computation of exactly what MarketStructureTracker already
computes, not just fixing the comparison.

Live Trading
------------
Pure function of a bounded recent window of closed candles (matching
strategy_engine.py's own STRUCTURE_LOOKBACK convention) plus incremental
mitigation/touch/impulse tracking on already-created objects. sync()
uses the same "full growing candle list, only new candles processed"
contract as every other tracker here.

Computational Complexity
-------------------------
O(structure_lookback) per new candle for swing-level/BOS recomputation -
matching strategy_engine.py's existing, already-validated approach
(bounded rescanning, not a full unbounded history scan). Origin-candle
search is a reversed scan of the bounded impulse leg (Phase 2B), not
the full recent-candle window - short-circuiting on the first match,
and never scanning further back than the leg boundary regardless of
whether a match is found there.

Origin-Candle Search: Impulse-Leg Boundary (Module Logic Correction 2,
Phase 2B)
------------------------------------------------------------------------
Previously `_find_last_opposite_candle` scanned the ENTIRE
`structure_lookback` window (up to 500 candles), which could select an
economically unrelated candle from prior, already-used structure if the
actual impulse leg contained no opposite-colored candle at all (e.g., a
long same-direction momentum run) - confirmed defect, see
docs/module_correction2_order_block_report.md. It now bounds the search
to the leg between the broken structural pivot's OWN candle (inclusive)
and the current (breaking) candle - using
`structural_break_event.pivot_timestamp` directly, the exact same pivot
identity Module Logic Correction 1 already established, rather than
re-deriving it independently. See `_find_impulse_leg`'s own docstring
for why this boundary was chosen over the other candidate considered
(the most recent OPPOSING-direction swing pivot) - the latter failed to
reproduce this codebase's own established reference case. If the pivot
candle cannot be located in the current window, the leg cannot be
determined and no Order Block is created for that event - the same,
already-existing conservative behavior as "no opposite-colored candle
found" (`origin is None`), not a new failure mode.

Known Limitations / Future Extension Points
--------------------------------------------
- impulse_strength measures the furthest favorable excursion since
  creation, normalized by the ATR measured at creation time - it grows
  as the move continues and is never capped, unlike mitigation_pct.
- Breaker Blocks can be built as a pure subscriber to this module's
  `mitigated` list (diffing what is newly present each sync() call) -
  no event API needed here, matching how `active`/`filled` already work
  for Fair Value Gaps.
- A doji origin candle (open == close) collapses the mitigation zone to
  a single price - zone_lifecycle.compute_mitigation()'s existing
  zero-span defensive branch already handles this by treating it as
  immediately fully mitigated, rather than dividing by zero.
- Breaker Blocks do not currently get an equivalent tighter sub-zone -
  the architecture doc only scopes this to Order Blocks. Trivial to add
  later by reusing the same pattern if real usage calls for it.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Literal

from strategy.features.market_structure_tracker import StructuralBreakEvent
from strategy.features.utils import (
    AverageTrueRangeTracker,
    is_bearish_candle,
    is_bullish_candle,
)
from strategy.features.zone_lifecycle import (
    compute_impulse_strength,
    compute_mitigation,
    copy_snapshot_dict,
    is_touching_zone,
    mitigation_status_from_pct,
    update_favorable_extreme,
)

Direction = Literal["bullish", "bearish"]
MitigationStatus = Literal["unmitigated", "partially_mitigated", "fully_mitigated"]

DEFAULT_STRUCTURE_LOOKBACK = 500  # matches strategy_engine.py's STRUCTURE_LOOKBACK
DEFAULT_ATR_PERIOD = 14
DEFAULT_MAX_AGE_BARS = 5000
DEFAULT_MAX_TRACKED_MITIGATED = 500
MINIMUM_CANDLES_FOR_DETECTION = 6  # matches strategy/order_block.py's own minimum


def _find_last_opposite_candle(
    candles: list[dict[str, Any]],
    is_opposite: Callable[[dict[str, Any]], bool],
) -> dict[str, Any] | None:
    for candle in reversed(candles):
        if is_opposite(candle):
            return candle

    return None


def _find_impulse_leg(
    recent_candles: list[dict[str, Any]],
    structural_break_event: StructuralBreakEvent,
    timestamp_key: str,
) -> list[dict[str, Any]] | None:
    """
    Bounds origin-candle search to the leg between the broken
    structural pivot's OWN candle (inclusive) and the current, breaking
    candle (exclusive) - see module docstring "Origin-Candle Search:
    Impulse-Leg Boundary" (Module Logic Correction 2, Phase 2B).

    Uses `structural_break_event.pivot_timestamp` directly - the exact
    same pivot identity Module Logic Correction 1 already established -
    rather than re-deriving the pivot independently. An earlier design
    bounded the leg to the most recent OPPOSING-direction swing pivot
    instead; this was rejected after it failed to reproduce the
    already-established origin candle for this codebase's own canonical
    reference case (a swing high followed by a brief consolidation
    before the actual breakout - the consolidation's own most recent
    opposing-direction fractal pivot sits AFTER the origin candle,
    incorrectly excluding it). Anchoring to the broken pivot's own
    candle instead is directly, causally tied to the specific level
    being broken - any opposite-colored candle between that level's
    formation and its eventual break represents genuine positioning
    against this specific breakout, which is the concept an Order Block
    is meant to capture - and it reproduces every already-established
    reference case exactly.

    `recent_candles` is the tracker's own already-point-in-time-safe
    window, including the current (breaking) candle as its last
    element - exactly what `_detect_new_order_block` already has.

    Returns None if the pivot candle cannot be located in the current
    window - defensive only; both trackers are fed identical candle
    histories in lockstep by their caller, so this should not occur in
    normal operation, but is treated as "no leg -> no Order Block", the
    same conservative behavior as "no opposite-colored candle found".
    """

    pivot_timestamp = structural_break_event.pivot_timestamp

    for index, candle in enumerate(recent_candles):
        if candle[timestamp_key] == pivot_timestamp:
            return recent_candles[index:-1]

    return None


@dataclass
class OrderBlock:
    direction: Direction
    zone_high: float
    zone_low: float
    created_at: datetime
    origin_timestamp: datetime
    origin_bar_index: int
    timeframe: str
    formation_volume: float
    atr_at_creation: float | None
    mitigation_zone_high: float
    mitigation_zone_low: float

    touch_count: int = 0
    mitigation_pct: float = 0.0
    mitigation_status: MitigationStatus = "unmitigated"
    mitigation_zone_pct: float = 0.0
    mitigation_zone_status: MitigationStatus = "unmitigated"
    context: dict[str, Any] = field(default_factory=dict)

    _deepest_penetration: float = field(init=False, repr=False)
    _extreme_since_creation: float = field(init=False, repr=False)
    _currently_touching: bool = field(init=False, repr=False, default=False)
    _mitigation_zone_deepest_penetration: float = field(init=False, repr=False)

    def __post_init__(self) -> None:
        anchor = self.zone_high if self.direction == "bullish" else self.zone_low
        self._deepest_penetration = anchor
        self._extreme_since_creation = anchor

        mitigation_zone_anchor = (
            self.mitigation_zone_high
            if self.direction == "bullish"
            else self.mitigation_zone_low
        )
        self._mitigation_zone_deepest_penetration = mitigation_zone_anchor

    def apply_candle(self, candle: dict[str, Any]) -> None:
        self._extreme_since_creation = update_favorable_extreme(
            self.direction, self._extreme_since_creation, candle
        )

        overlapping = is_touching_zone(candle, self.zone_high, self.zone_low)

        if overlapping and not self._currently_touching:
            self.touch_count += 1

        self._currently_touching = overlapping

        self._deepest_penetration, self.mitigation_pct = compute_mitigation(
            self.direction,
            self.zone_high,
            self.zone_low,
            self._deepest_penetration,
            candle,
        )

        self.mitigation_status = mitigation_status_from_pct(self.mitigation_pct)

        self._mitigation_zone_deepest_penetration, self.mitigation_zone_pct = (
            compute_mitigation(
                self.direction,
                self.mitigation_zone_high,
                self.mitigation_zone_low,
                self._mitigation_zone_deepest_penetration,
                candle,
            )
        )

        self.mitigation_zone_status = mitigation_status_from_pct(
            self.mitigation_zone_pct
        )

    def _impulse_strength(self) -> float | None:
        return compute_impulse_strength(
            self.direction,
            self.zone_high,
            self.zone_low,
            self._extreme_since_creation,
            self.atr_at_creation,
        )

    def to_dict(
        self,
        current_bar_index: int,
        current_price: float,
    ) -> dict[str, Any]:

        if current_price < self.zone_low:
            distance_from_price = self.zone_low - current_price
        elif current_price > self.zone_high:
            distance_from_price = current_price - self.zone_high
        else:
            distance_from_price = 0.0

        return {
            "direction": self.direction,
            "zone_high": self.zone_high,
            "zone_low": self.zone_low,
            "created_at": self.created_at,
            "origin_timestamp": self.origin_timestamp,
            "timeframe": self.timeframe,
            "age_in_bars": current_bar_index - self.origin_bar_index,
            "formation_volume": self.formation_volume,
            "atr_at_creation": self.atr_at_creation,
            "impulse_strength": self._impulse_strength(),
            "touch_count": self.touch_count,
            "mitigation_status": self.mitigation_status,
            "mitigation_pct": self.mitigation_pct,
            "distance_from_price": distance_from_price,
            "mitigation_zone_high": self.mitigation_zone_high,
            "mitigation_zone_low": self.mitigation_zone_low,
            "mitigation_zone_pct": self.mitigation_zone_pct,
            "mitigation_zone_status": self.mitigation_zone_status,
            "context": dict(self.context),
        }


class OrderBlockTracker:
    """
    Detects and tracks Order Blocks across a growing candle history.

    One instance per backtest run (or per live session), matching the
    lifecycle already used by every other tracker in this codebase.
    Call sync() once per replay step with the full candle history seen
    so far.
    """

    def __init__(
        self,
        timeframe: str = "unknown",
        structure_lookback: int = DEFAULT_STRUCTURE_LOOKBACK,
        atr_period: int = DEFAULT_ATR_PERIOD,
        max_age_bars: int = DEFAULT_MAX_AGE_BARS,
        max_tracked_mitigated: int = DEFAULT_MAX_TRACKED_MITIGATED,
        timestamp_key: str = "timestamp",
    ):
        self.timestamp_key = timestamp_key
        self._timeframe = timeframe
        self._structure_lookback = structure_lookback
        self._max_age_bars = max_age_bars
        self._max_tracked_mitigated = max_tracked_mitigated

        self._atr = AverageTrueRangeTracker(
            period=atr_period,
            timestamp_key=timestamp_key,
        )

        self._consumed = 0
        self._last_candle: dict[str, Any] | None = None
        self._recent_candles: list[dict[str, Any]] = []

        self._bar_index = -1
        self._expired_count = 0

        self._active: list[OrderBlock] = []
        self._mitigated: list[OrderBlock] = []

        # Snapshot cache (Sprint 1B, performance-only): every output-
        # visible field snapshot() reads (_bar_index, _last_candle,
        # _active, _mitigated, _expired_count) changes ONLY inside
        # _ingest() - _bar_index itself already increments exactly once
        # per _ingest() call, so it is a free, already-existing version
        # number. snapshot() takes no external arguments (in particular,
        # NOT the live per-1-minute-bar current_price - it reads
        # self._last_candle["close"], which only advances on ingest),
        # so caching keyed on _bar_index alone is exact, not an
        # approximation. See docs/sprint1b_snapshot_cache_report.md.
        self._snapshot_cache: dict[str, Any] | None = None
        self._snapshot_cache_bar_index: int | None = None

    def sync(
        self,
        candles: list[dict[str, Any]],
        structural_break_event: StructuralBreakEvent | None,
    ) -> None:
        """
        structural_break_event is MarketStructureTracker's own
        point-in-time snapshot field for the SAME new candle being
        ingested here (its caller is expected to sync()
        MarketStructureTracker first and pass its resulting snapshot
        value straight through - exactly how MarketIntelligenceCoordinator
        wires equal_levels_snapshot/session_snapshot into
        LiquidityPoolTracker). Like those, it is a point-in-time
        snapshot, not a historical record, so a single call is only
        allowed to advance by exactly one new candle.
        """

        if len(candles) < self._consumed:
            raise ValueError(
                "candles went backwards - OrderBlockTracker does not "
                "support rewinding"
            )

        if len(candles) - self._consumed > 1:
            raise ValueError(
                "OrderBlockTracker.sync() can only advance by one new "
                "candle per call - structural_break_event is a "
                "point-in-time snapshot, not a historical record, so "
                "batching multiple new candles behind a single event "
                "would misattribute when the break actually occurred"
            )

        if self._consumed > 0:
            checkpoint = candles[self._consumed - 1]

            if checkpoint != self._last_candle:
                raise ValueError(
                    "candles does not extend the history previously "
                    "seen by this OrderBlockTracker"
                )

        for candle in candles[self._consumed:]:
            self._ingest(candle, structural_break_event)

        self._consumed = len(candles)

    def _ingest(
        self,
        candle: dict[str, Any],
        structural_break_event: StructuralBreakEvent | None,
    ) -> None:
        self._bar_index += 1

        self._update_active(candle)
        self._expire_stale()

        self._recent_candles.append(candle)
        if len(self._recent_candles) > self._structure_lookback:
            self._recent_candles.pop(0)

        self._detect_new_order_block(structural_break_event)

        # ATR reflects volatility up to (not including) this candle -
        # ingest_one() is O(1), never reconstructs a growing list.
        self._atr.ingest_one(candle)

        self._last_candle = candle

    def _update_active(self, candle: dict[str, Any]) -> None:
        still_active = []

        for order_block in self._active:
            order_block.apply_candle(candle)

            if order_block.mitigation_status == "fully_mitigated":
                self._mitigated.append(order_block)
            else:
                still_active.append(order_block)

        self._active = still_active

        if len(self._mitigated) > self._max_tracked_mitigated:
            self._mitigated = self._mitigated[-self._max_tracked_mitigated:]

    def _expire_stale(self) -> None:
        still_active = []

        for order_block in self._active:
            age = self._bar_index - order_block.origin_bar_index

            if age > self._max_age_bars:
                self._expired_count += 1
            else:
                still_active.append(order_block)

        self._active = still_active

    def _detect_new_order_block(
        self,
        structural_break_event: StructuralBreakEvent | None,
    ) -> None:
        if len(self._recent_candles) < MINIMUM_CANDLES_FOR_DETECTION:
            return

        if structural_break_event is None:
            return

        current_candle = self._recent_candles[-1]
        direction: Direction = structural_break_event.direction

        leg = _find_impulse_leg(self._recent_candles, structural_break_event, self.timestamp_key)
        if leg is None:
            return

        atr = self._atr.current()

        if direction == "bullish":
            origin = _find_last_opposite_candle(leg, is_bearish_candle)
        else:
            origin = _find_last_opposite_candle(leg, is_bullish_candle)

        if origin is None:
            return

        self._active.append(
            OrderBlock(
                direction=direction,
                zone_high=origin["high"],
                zone_low=origin["low"],
                created_at=current_candle[self.timestamp_key],
                origin_timestamp=origin[self.timestamp_key],
                origin_bar_index=self._bar_index,
                timeframe=self._timeframe,
                formation_volume=origin["volume"],
                atr_at_creation=atr,
                mitigation_zone_high=max(origin["open"], origin["close"]),
                mitigation_zone_low=min(origin["open"], origin["close"]),
            )
        )

    def snapshot(self) -> dict[str, Any]:
        if self._snapshot_cache is None or self._snapshot_cache_bar_index != self._bar_index:
            self._snapshot_cache = self._build_snapshot()
            self._snapshot_cache_bar_index = self._bar_index

        # Always hand out an independent copy - the cached master is
        # never exposed directly, so a caller mutating its result can
        # never corrupt this tracker's state, a later snapshot() call,
        # or another caller's already-returned snapshot. Uses
        # copy_snapshot_dict(), NOT copy.deepcopy() - see that
        # function's own docstring for why (a measured ~7.5x
        # regression from deepcopy's overhead at this object count).
        return copy_snapshot_dict(self._snapshot_cache)

    def _build_snapshot(self) -> dict[str, Any]:
        if self._last_candle is None:
            return {
                "active": [],
                "mitigated": [],
                "expired_count": self._expired_count,
            }

        current_price = self._last_candle["close"]

        return {
            "active": [
                ob.to_dict(self._bar_index, current_price)
                for ob in self._active
            ],
            "mitigated": [
                ob.to_dict(self._bar_index, current_price)
                for ob in self._mitigated
            ],
            "expired_count": self._expired_count,
        }
