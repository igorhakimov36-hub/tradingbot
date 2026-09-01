"""
Liquidity Pools - Phase 1.8 of the Smart Money Core (see
docs/smart_money_architecture.md, "Market Structure > 5. Liquidity
Pools").

Purpose
-------
Aggregates weaker individual signals - equal highs/lows, session
extremes, round numbers - into unified zones of likely resting stop/
breakout orders. Price is statistically drawn to sweep these zones
before reversing: triggering resting stops benefits participants
positioned to absorb the other side. This module does not detect a new
pattern; it is explicitly a composite/aggregator that merges three
independent sub-detectors' outputs into one persistent market object,
exactly as the architecture doc requires ("Design note - this is
explicitly a composite/aggregator module").

The three sub-detector sources:
- Equal Highs / Equal Lows (strategy.features.equal_highs_lows) - the
  primary structural sub-detector, already produces pre-clustered
  pivot groups.
- Session extremes (strategy.features.session_boundaries) - only
  CLOSED periods' highs/lows are used, never a still-forming session's
  running extreme. ICT/SMC convention refers to "previous session/day/
  week high-low" as the liquidity target, not a session's current,
  still-changing extreme - using the current one would also mean
  reclustering on every tick as it moves, adding noise for no
  institutional benefit.
- Round numbers - pure price arithmetic, no candle pattern. A round
  number becomes a candidate touch only when the CURRENT candle's own
  high/low range actually crosses it (never pre-emptively enumerated
  far from price) - this keeps it an actual touch event, replay-safe,
  and O(1) per candle (a candle's range is always tiny relative to
  realistic spacing).

Trading Logic
-------------
A pool forms where two or more candidate points (from any mix of the
three sources) land within an ATR-relative tolerance of each other -
mirroring EqualLevelsTracker's own greedy, order-dependent matching
algorithm (first tolerance match wins), generalized from one candidate
stream to three. A lone candidate is held pending until a second one
confirms it - a pool is never exposed from a single touch (see Replay
Safety). Once formed, a pool keeps absorbing new same-direction
candidates that land within tolerance of its current zone, widening
zone_high/zone_low as needed. A sweep is a wick beyond the pool's outer
edge that closes back inside/beyond in the opposite direction - the
same wick-then-close-back convention as strategy/liquidity.py's
detect_liquidity_sweep, generalized from a single level to a zone's
outer boundary. Once swept, a pool is retired (moved out of active
matching, like Order Blocks/Breaker Blocks/FVGs on resolution) - the
resting orders that made up that liquidity are gone; new orders
accumulating near the same price afterward are a genuinely NEW pool,
not a continuation of consumed liquidity.

Design decision - contribution is a one-time snapshot, not a live
link: an Equal Highs/Lows cluster's own `level` can drift as it gathers
more pivots after being absorbed into a pool (EqualLevelCluster.level
is a running mean, unlike Order Block's zone which is fixed at
creation). Re-reading a live reference to the source cluster on every
tick to keep a pool's zone in perfect sync would need a different
composition style than anything else in this codebase (which always
composes via one-time reads of another tracker's public dict output,
never a held reference). This module instead treats each source
becoming newly visible in its tracker's snapshot as a discrete event,
contributing its price/timestamp at that specific moment - matching
exactly how Breaker Blocks treats a newly-fully-mitigated Order Block.
If an Equal-Highs cluster gains further pivots after being absorbed, a
future revisit-driven-by-evidence could register incremental touches
for it too; documented as a Known Limitation, not silently patched.

Inputs
------
OHLCV (for round-number touches and the tracker's own ATR), plus the
already-produced public snapshots of an EqualLevelsTracker and a
SessionBoundariesTracker - never their internals. A per-symbol
round-number spacing (e.g. 500.0 for BTC) - required to opt in, never a
hardcoded default (Multi-Symbol-by-Design; the architecture doc's own
Edge Cases section says this explicitly: "Round-number granularity must
be symbol-configured, never hardcoded"). `round_number_spacing=None`
(the default) disables that sub-detector entirely rather than guessing
a value.

Outputs (raw features only - see LiquidityPoolTracker.snapshot)
-----------------------------------------------------------------
direction: buy_side | sell_side (buy_side aggregates HIGHS - equal
highs, session highs - the liquidity resting above those levels that
triggering causes buying pressure into, per standard ICT buy-side/
sell-side liquidity terminology; fixed at formation, exactly like every
other module's `direction` field - never recomputed relative to a
moving current price), level, zone_high, zone_low, created_at,
timeframe, age_in_bars, bars_since_last_touch, contributing_touches
(raw timestamps - provenance, not a hidden count), touch_count,
sources (which sub-detectors flagged it, e.g. ["equal_highs",
"round_number"]), swept_status: unswept | swept, swept_timestamp,
sweep_penetration, sweep_rejection, distance_from_price, context. No
score, no threshold, no BUY/SELL.

Sweep penetration/rejection are expressed in ATR units, not the
percentage-of-level convention strategy/liquidity.py's
calculate_sweep_strength uses - the CONCEPT is reused (wick-beyond,
then close-back, split into two separate raw numbers rather than one
combined score), but the normalization follows this whole package's
established ATR-relative convention instead of copying the old
percentage formula verbatim, for Multi-Symbol consistency with every
other module here.

Dependencies
------------
Hard dependency on EqualLevelsTracker's and SessionBoundariesTracker's
public dict output only. Consumed by (not built yet): Order Block
confluence checks, Strategy Engine, AI Ranking.

Replay Safety
-------------
A pool is only knowable once >=2 contributing touches have occurred,
each already point-in-time-safe individually (a confirmed EQH/EQL
pivot, a CLOSED session's fixed extreme, or a round number actually
touched by the current candle's own high/low). Because
equal_levels_snapshot/session_snapshot are point-in-time snapshots, not
historical records (the exact same risk class discovered and fixed for
BreakerBlockTracker's source_mitigated), sync() enforces exactly one
new candle per call - a batch would misattribute every already-visible
source in the snapshot to the batch's first candle instead of each
one's true moment of appearance. sync() also rejects a candle history
that goes backwards or diverges from what it has already consumed (same
guard every tracker in this codebase uses).

Live Trading
------------
A live orchestrator must sync EqualLevelsTracker and
SessionBoundariesTracker first, then this tracker, once per candle,
every candle - the same ordering-dependency contract Breaker Blocks
established with Order Blocks, now extended to two upstream sources
instead of one.

Computational Complexity
-------------------------
The architecture doc flags clustering as the one deliberate complexity
decision in this whole document (naive pairwise comparison is O(n^2)
and will not scale). This module never does pairwise comparison: each
new candidate is matched greedily against a bounded set of existing
pools/pending lone candidates of the same direction - O(p) per new
candidate, p bounded by max_tracked_pending and the number of active
pools (itself bounded by age-based pruning), mirroring
EqualLevelsTracker's own O(p) pivot-matching exactly. Round-number
candidate generation is O(1) amortized per candle (a candle's range is
always tiny relative to realistic spacing).

Known Limitations / Future Extension Points
--------------------------------------------
- An Equal-Highs/Lows cluster contributes once, at the moment it first
  becomes visible in its tracker's snapshot - further pivots it gathers
  afterward do not additionally widen the pool they already joined (see
  Design decision above). Revisit if real usage shows this loses
  meaningful signal.
- Swept pools are retired, not reused - see Trading Logic above.
- A pool's `level` is the mean of its contributing prices (matching
  EqualLevelCluster's own convention), not the zone's midpoint - these
  differ whenever contributions are not symmetric around the center.
- Two clusters near but not within tolerance are simply never merged;
  the raw candidate prices remain visible via each source tracker's own
  snapshot for a caller to re-cluster with a different threshold,
  rather than this module silently hiding the boundary call (the
  architecture doc's own Edge Cases guidance).
"""

from dataclasses import dataclass, field
from datetime import datetime
from math import ceil, floor
from typing import Any, Literal

from strategy.features.utils import AverageTrueRangeTracker

Direction = Literal["buy_side", "sell_side"]
SweptStatus = Literal["unswept", "swept"]

DEFAULT_ATR_PERIOD = 14
DEFAULT_TOLERANCE_ATR_MULTIPLIER = 0.1
DEFAULT_MAX_AGE_BARS = 5000
DEFAULT_MAX_TRACKED_PENDING = 200
DEFAULT_MAX_TRACKED_SWEPT = 500


@dataclass
class LiquidityPool:
    direction: Direction
    zone_high: float
    zone_low: float
    level: float
    created_at: datetime
    origin_bar_index: int
    timeframe: str

    sources: list[str] = field(default_factory=list)
    contributing_touches: list[datetime] = field(default_factory=list)
    swept_status: SweptStatus = "unswept"
    swept_timestamp: datetime | None = None
    sweep_penetration: float | None = None
    sweep_rejection: float | None = None
    context: dict[str, Any] = field(default_factory=dict)

    _contributing_price_sum: float = field(init=False, repr=False, default=0.0)
    _last_touch_bar_index: int = field(init=False, repr=False, default=0)

    def __post_init__(self) -> None:
        self._contributing_price_sum = 0.0
        self._last_touch_bar_index = self.origin_bar_index

    def register_touch(
        self,
        price: float,
        timestamp: datetime,
        bar_index: int,
        source: str,
    ) -> None:
        self._contributing_price_sum += price
        self.contributing_touches.append(timestamp)

        if source not in self.sources:
            self.sources.append(source)

        self.zone_high = max(self.zone_high, price)
        self.zone_low = min(self.zone_low, price)
        self.level = self._contributing_price_sum / len(self.contributing_touches)
        self._last_touch_bar_index = bar_index

    def check_sweep(
        self,
        candle: dict[str, Any],
        timestamp_key: str,
        atr: float | None,
    ) -> None:
        if self.swept_status != "unswept":
            return

        if self.direction == "buy_side":
            swept = candle["high"] > self.zone_high and candle["close"] < self.zone_high

            if swept and atr:
                self.sweep_penetration = (candle["high"] - self.zone_high) / atr
                self.sweep_rejection = (candle["high"] - candle["close"]) / atr

        else:
            swept = candle["low"] < self.zone_low and candle["close"] > self.zone_low

            if swept and atr:
                self.sweep_penetration = (self.zone_low - candle["low"]) / atr
                self.sweep_rejection = (candle["close"] - candle["low"]) / atr

        if swept:
            self.swept_status = "swept"
            self.swept_timestamp = candle[timestamp_key]

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
            "level": self.level,
            "zone_high": self.zone_high,
            "zone_low": self.zone_low,
            "created_at": self.created_at,
            "timeframe": self.timeframe,
            "age_in_bars": current_bar_index - self.origin_bar_index,
            "bars_since_last_touch": current_bar_index - self._last_touch_bar_index,
            "contributing_touches": list(self.contributing_touches),
            "touch_count": len(self.contributing_touches),
            "sources": list(self.sources),
            "swept_status": self.swept_status,
            "swept_timestamp": self.swept_timestamp,
            "sweep_penetration": self.sweep_penetration,
            "sweep_rejection": self.sweep_rejection,
            "distance_from_price": distance_from_price,
            "context": dict(self.context),
        }


def _round_numbers_touched(
    candle: dict[str, Any],
    spacing: float,
) -> list[float]:
    low, high = candle["low"], candle["high"]

    first = ceil(low / spacing) * spacing
    last = floor(high / spacing) * spacing

    if first > last:
        return []

    numbers = []
    count = round((last - first) / spacing) + 1

    for i in range(count):
        numbers.append(round(first + i * spacing, 10))

    return numbers


class LiquidityPoolTracker:
    """
    Aggregates Equal Highs/Lows clusters, closed-session extremes, and
    round numbers into persistent Liquidity Pool market objects.

    One instance per backtest run (or per live session). Call sync()
    once per replay step, AFTER syncing the source EqualLevelsTracker
    and SessionBoundariesTracker for that same step, passing exactly
    one new candle's worth of history each call (see sync()'s
    docstring - equal_levels_snapshot/session_snapshot are point-in-
    time, not historical records).
    """

    def __init__(
        self,
        timeframe: str = "unknown",
        atr_period: int = DEFAULT_ATR_PERIOD,
        tolerance_atr_multiplier: float = DEFAULT_TOLERANCE_ATR_MULTIPLIER,
        round_number_spacing: float | None = None,
        max_age_bars: int = DEFAULT_MAX_AGE_BARS,
        max_tracked_pending: int = DEFAULT_MAX_TRACKED_PENDING,
        max_tracked_swept: int = DEFAULT_MAX_TRACKED_SWEPT,
        timestamp_key: str = "timestamp",
    ):
        self.timestamp_key = timestamp_key
        self._timeframe = timeframe
        self._tolerance_atr_multiplier = tolerance_atr_multiplier
        self._round_number_spacing = round_number_spacing
        self._max_age_bars = max_age_bars
        self._max_tracked_pending = max_tracked_pending
        self._max_tracked_swept = max_tracked_swept

        self._atr = AverageTrueRangeTracker(period=atr_period, timestamp_key=timestamp_key)

        self._consumed = 0
        self._last_candle: dict[str, Any] | None = None
        self._bar_index = -1
        self._expired_count = 0

        # Each entry: {"price", "timestamp", "source", "pool": LiquidityPool|None}
        self._pending_buy_side: list[dict[str, Any]] = []
        self._pending_sell_side: list[dict[str, Any]] = []

        self._active: list[LiquidityPool] = []
        self._swept: list[LiquidityPool] = []

        self._seen_eqh_keys: set[tuple[Any, Any]] = set()
        self._seen_eql_keys: set[tuple[Any, Any]] = set()
        self._seen_session_keys: set[tuple[str, Any]] = set()

    def sync(
        self,
        candles: list[dict[str, Any]],
        equal_levels_snapshot: dict[str, Any],
        session_snapshot: dict[str, Any],
    ) -> None:
        """
        equal_levels_snapshot/session_snapshot are point-in-time
        snapshots, not historical records - the same risk class
        discovered and fixed for BreakerBlockTracker's
        source_mitigated. A single call is therefore only allowed to
        advance by exactly one new candle; batching would misattribute
        every source already visible in the snapshot to the batch's
        first candle instead of each one's true moment of appearance.
        """

        if len(candles) < self._consumed:
            raise ValueError(
                "candles went backwards - LiquidityPoolTracker does "
                "not support rewinding"
            )

        if len(candles) - self._consumed > 1:
            raise ValueError(
                "LiquidityPoolTracker.sync() can only advance by one "
                "new candle per call - equal_levels_snapshot/"
                "session_snapshot are point-in-time snapshots, not "
                "historical records, so batching multiple new candles "
                "behind a single pair of snapshots would misattribute "
                "when each pool's contributing touches actually occurred"
            )

        if self._consumed > 0:
            checkpoint = candles[self._consumed - 1]

            if checkpoint != self._last_candle:
                raise ValueError(
                    "candles does not extend the history previously "
                    "seen by this LiquidityPoolTracker"
                )

        for candle in candles[self._consumed:]:
            self._ingest(candle, equal_levels_snapshot, session_snapshot)

        self._consumed = len(candles)

    def _ingest(
        self,
        candle: dict[str, Any],
        equal_levels_snapshot: dict[str, Any],
        session_snapshot: dict[str, Any],
    ) -> None:
        self._bar_index += 1

        self._check_sweeps(candle)
        self._expire_stale()

        self._detect_new_equal_level_candidates(equal_levels_snapshot)
        self._detect_new_session_candidates(session_snapshot)
        self._detect_round_number_touches(candle)

        self._atr.ingest_one(candle)
        self._last_candle = candle

    def _check_sweeps(self, candle: dict[str, Any]) -> None:
        atr = self._atr.current()
        still_active = []

        for pool in self._active:
            pool.check_sweep(candle, self.timestamp_key, atr)

            if pool.swept_status == "swept":
                self._swept.append(pool)
            else:
                still_active.append(pool)

        self._active = still_active

        if len(self._swept) > self._max_tracked_swept:
            self._swept = self._swept[-self._max_tracked_swept:]

    def _expire_stale(self) -> None:
        still_active = []

        for pool in self._active:
            if (self._bar_index - pool.origin_bar_index) > self._max_age_bars:
                self._expired_count += 1
            else:
                still_active.append(pool)

        self._active = still_active

    def _detect_new_equal_level_candidates(self, equal_levels_snapshot: dict[str, Any]) -> None:
        for cluster in equal_levels_snapshot.get("equal_highs", []):
            key = (cluster["direction"], cluster["created_at"])

            if key in self._seen_eqh_keys:
                continue

            self._seen_eqh_keys.add(key)
            self._register_candidate(
                direction="buy_side",
                price=cluster["level"],
                timestamp=cluster["created_at"],
                source="equal_highs",
            )

        for cluster in equal_levels_snapshot.get("equal_lows", []):
            key = (cluster["direction"], cluster["created_at"])

            if key in self._seen_eql_keys:
                continue

            self._seen_eql_keys.add(key)
            self._register_candidate(
                direction="sell_side",
                price=cluster["level"],
                timestamp=cluster["created_at"],
                source="equal_lows",
            )

    def _detect_new_session_candidates(self, session_snapshot: dict[str, Any]) -> None:
        for name, data in session_snapshot.items():
            for period in data.get("closed", []):
                key = (name, period["period_start"])

                if key in self._seen_session_keys:
                    continue

                self._seen_session_keys.add(key)

                self._register_candidate(
                    direction="buy_side",
                    price=period["session_high"],
                    timestamp=period["high_timestamp"],
                    source="session_high",
                )
                self._register_candidate(
                    direction="sell_side",
                    price=period["session_low"],
                    timestamp=period["low_timestamp"],
                    source="session_low",
                )

    def _detect_round_number_touches(self, candle: dict[str, Any]) -> None:
        if not self._round_number_spacing:
            return

        timestamp = candle[self.timestamp_key]

        for price in _round_numbers_touched(candle, self._round_number_spacing):
            self._register_candidate(
                direction="buy_side",
                price=price,
                timestamp=timestamp,
                source="round_number",
            )
            self._register_candidate(
                direction="sell_side",
                price=price,
                timestamp=timestamp,
                source="round_number",
            )

    def _register_candidate(
        self,
        direction: Direction,
        price: float,
        timestamp: datetime,
        source: str,
    ) -> None:
        pending = self._pending_buy_side if direction == "buy_side" else self._pending_sell_side
        atr = self._atr.current()
        tolerance = (atr * self._tolerance_atr_multiplier) if atr else 0.0

        for pool in self._active:
            if pool.direction != direction:
                continue

            if pool.zone_low - tolerance <= price <= pool.zone_high + tolerance:
                pool.register_touch(price, timestamp, self._bar_index, source)
                return

        matched_lone: dict[str, Any] | None = None

        for candidate in pending:
            if abs(candidate["price"] - price) <= tolerance:
                matched_lone = candidate
                break

        new_record: dict[str, Any] = {
            "price": price,
            "timestamp": timestamp,
            "source": source,
        }

        if matched_lone is not None:
            pool = LiquidityPool(
                direction=direction,
                zone_high=max(matched_lone["price"], price),
                zone_low=min(matched_lone["price"], price),
                level=price,
                created_at=timestamp,
                origin_bar_index=self._bar_index,
                timeframe=self._timeframe,
            )
            pool.register_touch(matched_lone["price"], matched_lone["timestamp"], self._bar_index, matched_lone["source"])
            pool.register_touch(price, timestamp, self._bar_index, source)

            self._active.append(pool)
            pending.remove(matched_lone)
        else:
            pending.append(new_record)

            if len(pending) > self._max_tracked_pending:
                pending.pop(0)

    def snapshot(self) -> dict[str, Any]:
        if self._last_candle is None:
            return {
                "active": [],
                "swept": [],
                "expired_count": self._expired_count,
            }

        current_price = self._last_candle["close"]

        return {
            "active": [
                pool.to_dict(self._bar_index, current_price)
                for pool in self._active
            ],
            "swept": [
                pool.to_dict(self._bar_index, current_price)
                for pool in self._swept
            ],
            "expired_count": self._expired_count,
        }
