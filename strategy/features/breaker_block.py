"""
Breaker Blocks - Phase 1.5 of the Smart Money Core (see
docs/smart_money_architecture.md, "Market Structure > 3. Breaker
Blocks").

Purpose
-------
A Breaker Block is not a new pattern - it is a polarity flip of a
failed Order Block. This predates ICT entirely: classical technical
analysis (Edwards & Magee) already describes "broken support becomes
resistance", explained by trapped-trader psychology - participants who
bought an Order Block are underwater once it fully breaks, and their
eventual breakeven-exit selling reinforces the zone as new resistance
(symmetrically, a failed bearish Order Block becomes support). This is
a genuine positioning shift at that level, not noise.

Trading Logic
-------------
This module has NO independent candle-scanning of its own. It is a
pure state-transition subscriber to Order Blocks: the instant an Order
Block's mitigation_status becomes "fully_mitigated", the SAME zone is
reborn here with FLIPPED direction and its own fresh mitigation
lifecycle. If a Breaker Block itself later becomes fully mitigated, it
is retired - never flipped back a second time (avoids an oscillating
state machine, per the edge case already documented for Order Blocks).
A genuine reversal back to the original polarity, if the market really
does that, will be independently detected as a brand new Order Block
by OrderBlockTracker's own BOS-based logic - not by this module.

Inputs
------
1. OHLCV (any single timeframe, same stream driving the source
   OrderBlockTracker) - needed for this module's OWN mitigation/touch/
   impulse tracking once a breaker exists, exactly like Order Blocks.
2. OrderBlockTracker.snapshot()["mitigated"] - the ONLY source of new
   Breaker Blocks. This is the first module in this package to depend
   on another feature module's output rather than raw OHLCV alone. The
   dependency is explicit, not hidden: sync() takes it as a parameter,
   so a caller wires two trackers together each step, and a test can
   inject a synthetic upstream snapshot without needing a real
   OrderBlockTracker at all.

Outputs (raw features only - see BreakerBlockTracker.snapshot)
----------------------------------------------------------
direction, zone_high, zone_low, created_at, source_direction,
source_origin_timestamp, timeframe, age_in_bars, atr_at_creation,
impulse_strength, touch_count, mitigation_status, mitigation_pct,
distance_from_price, context. No score, no threshold, no BUY/SELL.

Dependencies
------------
Hard dependency on OrderBlockTracker's public dict output only - never
its internals. Because Order Block's public dict does not expose a raw
bar index (only the derived age_in_bars), a newly-mitigated Order Block
is identified by the composite key (direction, origin_timestamp,
zone_high, zone_low, created_at) - reading only the public contract.
created_at (the BOS confirmation bar) is a required part of the key,
not just origin/zone: real BTCUSDT data showed the same origin candle
can legitimately become the origin of two distinct Order Blocks at
different times, which would otherwise collide - see
_source_key()'s docstring. Shares mitigation/touch/impulse math with
Order Blocks via strategy.features.zone_lifecycle - no lifecycle logic
is duplicated a second time.

Replay Safety
-------------
A Breaker Block is only exposed once its source Order Block has
actually been observed as fully_mitigated in this step's snapshot -
created_at records that moment, not the source Order Block's own
(earlier) origin_timestamp, which is preserved separately for
provenance. sync() rejects a candle history that goes backwards or
diverges from what it has already consumed (same guard every tracker in
this codebase uses).

Because source_mitigated is a point-in-time snapshot rather than a
historical record like `candles`, sync() also rejects a call that tries
to advance by more than one new candle at once - see sync()'s own
docstring. This was discovered empirically while validating against
real BTCUSDT data: an unguarded version that allowed batching produced
different results for the same history depending on how many candles
were fed per call, since every OB that mitigated anywhere inside a
batch would incorrectly get its breaker's created_at pinned to the
batch's first new candle instead of its own true mitigation moment.

Live Trading
------------
Purely reactive: on every step, check whether OrderBlockTracker's
mitigated list contains any composite key not already turned into a
breaker, and apply the current candle to existing breakers' lifecycle
tracking. No history rescanning. A live orchestrator must call both
trackers' sync() in the same order every step (Order Blocks first, then
this module) - documented explicitly since this is the first ordering
dependency between two feature modules in this codebase.

Computational Complexity
-------------------------
O(m) per step to scan OrderBlockTracker's mitigated list for unseen
composite keys, where m = len(mitigated) (bounded by
OrderBlockTracker's own max_tracked_mitigated). O(k) to update existing
breakers, k = active breakers, bounded by age-based pruning. No
component of this module ever rescans candle history.

Known Limitations / Future Extension Points
--------------------------------------------
- Relies on OrderBlockTracker and BreakerBlockTracker being sync()'d in
  lockstep, exactly one new candle per step, in that order - enforced
  by sync() itself (see its docstring and Replay Safety above), not
  just documented.
- Composite-key identity (direction, origin_timestamp, zone_high,
  zone_low, created_at) is bounded by OrderBlockTracker's own
  max_tracked_mitigated. If a caller kept sync()'d in lockstep still
  somehow let more Order Blocks get mitigated than that bound before
  this tracker observed them, an already-evicted-and-reused composite
  key could theoretically be missed. Not a practical risk at the
  default bound (500) with the one-candle-per-step contract now
  enforced.
- A Breaker Block that gets swept back through in the original
  direction is retired, not flipped back - see Trading Logic above.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal

from strategy.features.utils import AverageTrueRangeTracker
from strategy.features.zone_lifecycle import (
    compute_impulse_strength,
    compute_mitigation,
    is_touching_zone,
    mitigation_status_from_pct,
    update_favorable_extreme,
)

Direction = Literal["bullish", "bearish"]
MitigationStatus = Literal["unmitigated", "partially_mitigated", "fully_mitigated"]

DEFAULT_ATR_PERIOD = 14
DEFAULT_MAX_AGE_BARS = 5000
DEFAULT_MAX_TRACKED_MITIGATED = 500


def _opposite(direction: Direction) -> Direction:
    return "bearish" if direction == "bullish" else "bullish"


def _source_key(order_block: dict[str, Any]) -> tuple[Any, Any, Any, Any, Any]:
    """
    Identifies a specific Order Block using only its public dict
    contract. (direction, origin_timestamp, zone_high, zone_low) alone
    is NOT sufficient: validation on real BTCUSDT data showed the same
    origin candle can legitimately become the origin of two distinct
    Order Blocks at different times (price breaks structure, forms an
    OB referencing candle X, later re-tests and breaks structure again
    while X is still within the lookback window, and the "last opposite
    candle" scan finds X a second time). created_at (the BOS
    confirmation bar) is included to disambiguate - it necessarily
    differs between the two, since only one Order Block can be created
    per confirmation candle.
    """
    return (
        order_block["direction"],
        order_block["origin_timestamp"],
        order_block["zone_high"],
        order_block["zone_low"],
        order_block["created_at"],
    )


@dataclass
class BreakerBlock:
    direction: Direction
    zone_high: float
    zone_low: float
    created_at: datetime
    source_direction: Direction
    source_origin_timestamp: datetime
    origin_bar_index: int
    timeframe: str
    atr_at_creation: float | None

    touch_count: int = 0
    mitigation_pct: float = 0.0
    mitigation_status: MitigationStatus = "unmitigated"
    context: dict[str, Any] = field(default_factory=dict)

    _deepest_penetration: float = field(init=False, repr=False)
    _extreme_since_creation: float = field(init=False, repr=False)
    _currently_touching: bool = field(init=False, repr=False, default=False)

    def __post_init__(self) -> None:
        anchor = self.zone_high if self.direction == "bullish" else self.zone_low
        self._deepest_penetration = anchor
        self._extreme_since_creation = anchor

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
            "source_direction": self.source_direction,
            "source_origin_timestamp": self.source_origin_timestamp,
            "timeframe": self.timeframe,
            "age_in_bars": current_bar_index - self.origin_bar_index,
            "atr_at_creation": self.atr_at_creation,
            "impulse_strength": compute_impulse_strength(
                self.direction,
                self.zone_high,
                self.zone_low,
                self._extreme_since_creation,
                self.atr_at_creation,
            ),
            "touch_count": self.touch_count,
            "mitigation_status": self.mitigation_status,
            "mitigation_pct": self.mitigation_pct,
            "distance_from_price": distance_from_price,
            "context": dict(self.context),
        }


class BreakerBlockTracker:
    """
    Detects and tracks Breaker Blocks by watching another
    OrderBlockTracker's mitigated Order Blocks.

    One instance per backtest run (or per live session). Call sync()
    once per replay step, AFTER syncing the source OrderBlockTracker,
    passing this candle step's OHLCV history and the source tracker's
    current snapshot()["mitigated"] list.
    """

    def __init__(
        self,
        timeframe: str = "unknown",
        atr_period: int = DEFAULT_ATR_PERIOD,
        max_age_bars: int = DEFAULT_MAX_AGE_BARS,
        max_tracked_mitigated: int = DEFAULT_MAX_TRACKED_MITIGATED,
        timestamp_key: str = "timestamp",
    ):
        self.timestamp_key = timestamp_key
        self._timeframe = timeframe
        self._max_age_bars = max_age_bars
        self._max_tracked_mitigated = max_tracked_mitigated

        self._atr = AverageTrueRangeTracker(
            period=atr_period,
            timestamp_key=timestamp_key,
        )

        self._consumed = 0
        self._last_candle: dict[str, Any] | None = None

        self._bar_index = -1
        self._expired_count = 0

        self._seen_source_keys: set[tuple[Any, Any, Any, Any, Any]] = set()

        self._active: list[BreakerBlock] = []
        self._mitigated: list[BreakerBlock] = []

    def sync(
        self,
        candles: list[dict[str, Any]],
        source_mitigated: list[dict[str, Any]],
    ) -> None:
        """
        Unlike every other tracker in this package, `candles` is not
        the only time-varying input here: `source_mitigated` is a
        point-in-time snapshot (like a PointEventProvider event), valid
        only at the instant it was read from OrderBlockTracker. A
        single call is therefore only allowed to advance by exactly one
        new candle - batching multiple new candles behind one
        source_mitigated snapshot would let OBs that mitigate mid-batch
        spawn breakers as of the batch's start instead of the moment
        they actually mitigated, a look-ahead violation. This was
        discovered, not assumed: an initial version of this method
        allowed arbitrary batches and produced exactly that mismatch
        against real BTCUSDT data. A caller must sync() this tracker
        once per replay step, immediately after syncing the source
        OrderBlockTracker for that same step.
        """

        if len(candles) < self._consumed:
            raise ValueError(
                "candles went backwards - BreakerBlockTracker does "
                "not support rewinding"
            )

        if len(candles) - self._consumed > 1:
            raise ValueError(
                "BreakerBlockTracker.sync() can only advance by one "
                "new candle per call - source_mitigated is a "
                "point-in-time snapshot, not a historical record, so "
                "batching multiple new candles behind a single "
                "snapshot would misattribute when each breaker was "
                "actually created"
            )

        if self._consumed > 0:
            checkpoint = candles[self._consumed - 1]

            if checkpoint != self._last_candle:
                raise ValueError(
                    "candles does not extend the history previously "
                    "seen by this BreakerBlockTracker"
                )

        for candle in candles[self._consumed:]:
            self._ingest(candle, source_mitigated)

        self._consumed = len(candles)

    def _ingest(
        self,
        candle: dict[str, Any],
        source_mitigated: list[dict[str, Any]],
    ) -> None:
        self._bar_index += 1

        self._update_active(candle)
        self._expire_stale()
        self._detect_new_breakers(candle, source_mitigated)

        # ATR reflects volatility up to (not including) this candle -
        # ingest_one() is O(1), never reconstructs a growing list.
        self._atr.ingest_one(candle)

        self._last_candle = candle

    def _update_active(self, candle: dict[str, Any]) -> None:
        still_active = []

        for breaker in self._active:
            breaker.apply_candle(candle)

            if breaker.mitigation_status == "fully_mitigated":
                self._mitigated.append(breaker)
            else:
                still_active.append(breaker)

        self._active = still_active

        if len(self._mitigated) > self._max_tracked_mitigated:
            self._mitigated = self._mitigated[-self._max_tracked_mitigated:]

    def _expire_stale(self) -> None:
        still_active = []

        for breaker in self._active:
            age = self._bar_index - breaker.origin_bar_index

            if age > self._max_age_bars:
                self._expired_count += 1
            else:
                still_active.append(breaker)

        self._active = still_active

    def _detect_new_breakers(
        self,
        candle: dict[str, Any],
        source_mitigated: list[dict[str, Any]],
    ) -> None:
        atr = self._atr.current()

        for order_block in source_mitigated:
            key = _source_key(order_block)

            if key in self._seen_source_keys:
                continue

            self._seen_source_keys.add(key)

            self._active.append(
                BreakerBlock(
                    direction=_opposite(order_block["direction"]),
                    zone_high=order_block["zone_high"],
                    zone_low=order_block["zone_low"],
                    created_at=candle[self.timestamp_key],
                    source_direction=order_block["direction"],
                    source_origin_timestamp=order_block["origin_timestamp"],
                    origin_bar_index=self._bar_index,
                    timeframe=self._timeframe,
                    atr_at_creation=atr,
                )
            )

    def snapshot(self) -> dict[str, Any]:
        if self._last_candle is None:
            return {
                "active": [],
                "mitigated": [],
                "expired_count": self._expired_count,
            }

        current_price = self._last_candle["close"]

        return {
            "active": [
                breaker.to_dict(self._bar_index, current_price)
                for breaker in self._active
            ],
            "mitigated": [
                breaker.to_dict(self._bar_index, current_price)
                for breaker in self._mitigated
            ],
            "expired_count": self._expired_count,
        }
