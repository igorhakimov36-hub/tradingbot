"""
Volume Profile (including HVN/LVN) - Phase 1.12 of the Smart Money Core
(see docs/smart_money_architecture.md, "Order Flow > 10. Volume
Profile").

Purpose
-------
Distribution of total traded volume across price levels over a
session/period (not per-candle like Footprint) - reveals where the
market spent the most "time and volume" (fair value) versus where it
passed through quickly (likely to be revisited fast). The Point of
Control (POC) is the single price with the most volume; the Value Area
is the price range (typically 70% of volume) the market considered
fair, centered on the POC.

Traditional platforms build this from tick-level trade prints - exact
per-trade price attribution. That infrastructure does not exist in
this project (the same gap that blocks Footprint entirely). This
module instead builds the standard, well-established COARSE
approximation: each candle's total volume is distributed uniformly
across the price buckets its own high-low range touches. Both modes
share the exact same output contract - precision is a `data_quality`
field ("approximate" today, "precise" once/if tick data ever exists),
never a different shape, so upgrading the data source later never
breaks a consumer.

HVN/LVN (local peaks/troughs in the histogram) are a post-processing
pass over a histogram this module already owns, not a separate
detector - built on strategy.market_structure.find_local_extrema, the
same 3-point fractal comparison already used for swing highs/lows,
generalized (Phase 1.12) from a time-ordered series to a volume-by-
price series. find_swing_pivots is now itself built on top of this
same primitive - one comparison rule, two ordering dimensions, no
duplicated logic.

Architectural decisions
------------------------
1. Period anchoring reuses Session Boundaries, exactly like CVD - this
   tracker watches a SessionBoundariesTracker snapshot's `period_start`
   to know when to finalize the current profile and start a new one.
   No new calendar/timezone logic. Unlike CVD, this tracker takes
   exactly ONE anchor (not a list) - there is no shared expensive
   computation across anchors here (bucketing a candle's volume is
   cheap, unlike calculate_delta()), so the multi-anchor efficiency
   argument that justified CVD's design does not apply; a caller
   wanting several simultaneous profiles (daily AND weekly) runs
   several instances, the same multi-instance pattern used everywhere.
2. `bucket_size` is a REQUIRED constructor argument with no default,
   even stricter than Liquidity Pools' `round_number_spacing=None`
   opt-out - a histogram's bucket boundaries must stay FIXED for the
   whole period (an ATR-relative size that changes bar-to-bar would
   corrupt the aggregation by shifting the grid mid-period), so unlike
   a clustering tolerance this can never be dynamically recomputed,
   and there is no valid "off" state to default to.
3. Acceptance/Rejection are exposed as two raw, continuous cross-period
   comparisons against the immediately preceding CLOSED period -
   `poc_shift_from_previous_period` (ATR-normalized) and
   `value_area_overlap_ratio` (0-1) - never a module-asserted verdict.
   A high overlap ratio reads as acceptance, a low one as rejection/
   migration, but the module never says so - the same discipline as
   every other divergence/exhaustion flag in this package.
4. Volume Migration (POC drift across MANY sessions, not just the
   previous one) is deliberately NOT implemented - the architecture
   doc says this explicitly: it is "a direct aggregation of the same
   per-period histograms - no new primitive required." Since
   `closed_profiles` already retains bounded history with each
   period's own poc_price, a consumer can already derive a multi-
   period trend from data already exposed, without this module adding
   a field for it.
5. Tick-precise mode and Footprint itself are out of scope entirely -
   the same Trade-Level Infrastructure gap, not built here.

Inputs
------
OHLCV (high, low, close, volume, timestamp) - no tick data. Optionally
a SessionBoundariesTracker snapshot for period anchoring (None means
continuous/unanchored - accumulates forever, never closes).

Outputs (raw features only - see VolumeProfileTracker.snapshot)
-----------------------------------------------------------------
`current_forming_profile` (in-progress, explicitly labeled - never to
be mistaken for a closed one) and `closed_profiles` (bounded history of
finalized periods), each exposing: poc_price, value_area_high,
value_area_low, histogram (full raw [{price_bucket, volume}, ...] -
not just summary stats), period_type, period_start, period_end (None
while forming), total_period_volume, data_quality ("approximate" -
always, in this phase), hvn_nodes / lvn_nodes (each {price,
relative_volume, width}), poc_shift_from_previous_period,
value_area_overlap_ratio (both None for the very first period, since
there is no previous one), bucket_size, value_area_percentage,
timeframe, context. No score, no threshold, no BUY/SELL.

Dependencies
------------
Optional dependency on a SessionBoundariesTracker's public snapshot for
period anchoring - never its internals. Hard dependency on
strategy.market_structure.find_local_extrema for HVN/LVN - no fractal
peak/trough logic is duplicated a second time. Consumed by (not built
yet): Liquidity Pools (HVN confluence - not wired in now), Strategy
Engine, AI Ranking.

Replay Safety
-------------
A period's profile is only final once the period itself has closed;
the forming profile is exposed separately (`current_forming_profile`)
and must never be mistaken for a closed one - the same forming/closed
split TimeframeManager already established. Because session_snapshot
is a point-in-time snapshot, not a historical record (the same risk
class already discovered for Breaker Blocks/Liquidity Pools/session-
anchored CVD), sync() enforces exactly one new candle per call WHENEVER
an anchor is configured - a continuous/unanchored tracker has no such
input and stays exactly as batchable as Delta itself.

Live Trading
------------
The current period's profile (and its HVN/LVN, POC, Value Area)
updates incrementally as each new candle closes within it, finalizing
when the session boundary passes - matching the doc's own description
exactly. A live orchestrator with a session-anchored config must sync
SessionBoundariesTracker first, then this tracker, once per candle.

Computational Complexity
-------------------------
O(buckets touched) per candle for bucketing - a candle's own high-low
range is always small relative to realistic bucket sizes, so this is
effectively O(1) amortized. POC/Value Area/HVN/LVN are recomputed from
the current period's histogram on every snapshot() call - O(total
buckets in the period so far), bounded by the period's overall price
range divided by bucket_size (realistically dozens to low hundreds for
BTC), not by candle count - matching the same "bounded rescan of a
small fixed structure" pattern already established (Order Blocks'
structure_lookback rescanning, Correlation Engine's window recompute).

Known Limitations / Future Extension Points
--------------------------------------------
- The coarse OHLCV-bucketed mode distributes a candle's volume
  UNIFORMLY across the buckets its range touches - a standard,
  well-established approximation, not a precision claim. A candle that
  actually traded most of its volume near one extreme (common near a
  reversal wick) will show that volume smoothed across its full range
  instead of concentrated correctly - exactly the imprecision
  `data_quality: "approximate"` exists to make explicit.
- Value Area uses the simpler single-bucket-step expansion (add
  whichever adjacent bucket - above or below the current Value Area -
  has more volume, repeat until the target % is reached) rather than
  the two-row-at-a-time TPO convention some platforms use - a
  deliberate simplification, not a different concept.
- HVN/LVN `width` is the count of consecutive buckets around a
  peak/trough whose volume stays within a fixed fraction of the
  peak/trough's own volume (a "plateau" measure) - one clear,
  deterministic rule, not the only possible definition.
- Very low-volume periods (illiquid altcoin sessions) produce
  unreliable profiles - `total_period_volume` is always exposed raw so
  a consumer can judge reliability itself, rather than this module
  implying equal confidence always.
"""

from dataclasses import dataclass, field
from datetime import datetime
from math import ceil, floor
from typing import Any, Literal

from strategy.features.utils import AverageTrueRangeTracker
from strategy.market_structure import find_local_extrema

DataQuality = Literal["approximate", "precise"]

DEFAULT_VALUE_AREA_PERCENTAGE = 0.70
DEFAULT_ATR_PERIOD = 14
DEFAULT_MAX_TRACKED_CLOSED = 200
DEFAULT_NODE_WIDTH_THRESHOLD = 0.8


@dataclass
class VolumeNode:
    price: float
    relative_volume: float
    width: int


@dataclass
class VolumeProfile:
    period_type: str
    period_start: datetime
    timeframe: str
    bucket_size: float
    value_area_percentage: float

    period_end: datetime | None = None
    poc_price: float | None = None
    value_area_high: float | None = None
    value_area_low: float | None = None
    total_period_volume: float = 0.0
    data_quality: DataQuality = "approximate"
    hvn_nodes: list[VolumeNode] = field(default_factory=list)
    lvn_nodes: list[VolumeNode] = field(default_factory=list)
    poc_shift_from_previous_period: float | None = None
    value_area_overlap_ratio: float | None = None
    is_closed: bool = False
    context: dict[str, Any] = field(default_factory=dict)

    _volume_by_bucket: dict[float, float] = field(init=False, repr=False, default_factory=dict)

    def apply_candle(self, candle: dict[str, Any]) -> None:
        high, low, volume = candle["high"], candle["low"], candle["volume"]

        first_bucket = floor(low / self.bucket_size) * self.bucket_size
        last_bucket = floor(high / self.bucket_size) * self.bucket_size

        bucket_count = round((last_bucket - first_bucket) / self.bucket_size) + 1
        volume_per_bucket = volume / bucket_count

        for i in range(bucket_count):
            bucket = round(first_bucket + i * self.bucket_size, 10)
            self._volume_by_bucket[bucket] = self._volume_by_bucket.get(bucket, 0.0) + volume_per_bucket

        self.total_period_volume += volume
        self._recompute()

    def _recompute(self) -> None:
        if not self._volume_by_bucket:
            return

        sorted_buckets = sorted(self._volume_by_bucket.keys())
        volumes = [self._volume_by_bucket[b] for b in sorted_buckets]

        poc_index = max(range(len(volumes)), key=lambda i: volumes[i])
        self.poc_price = sorted_buckets[poc_index]

        va_low_index, va_high_index = _expand_value_area(
            volumes, poc_index, self.total_period_volume, self.value_area_percentage
        )
        self.value_area_low = sorted_buckets[va_low_index]
        self.value_area_high = sorted_buckets[va_high_index]

        self.hvn_nodes, self.lvn_nodes = _find_volume_nodes(sorted_buckets, volumes)

    def close(self, period_end: datetime) -> None:
        self.period_end = period_end
        self.is_closed = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "period_type": self.period_type,
            "period_start": self.period_start,
            "period_end": self.period_end,
            "poc_price": self.poc_price,
            "value_area_high": self.value_area_high,
            "value_area_low": self.value_area_low,
            "histogram": [
                {"price_bucket": price, "volume": volume}
                for price, volume in sorted(self._volume_by_bucket.items())
            ],
            "total_period_volume": self.total_period_volume,
            "data_quality": self.data_quality,
            "hvn_nodes": [n.__dict__ for n in self.hvn_nodes],
            "lvn_nodes": [n.__dict__ for n in self.lvn_nodes],
            "poc_shift_from_previous_period": self.poc_shift_from_previous_period,
            "value_area_overlap_ratio": self.value_area_overlap_ratio,
            "bucket_size": self.bucket_size,
            "value_area_percentage": self.value_area_percentage,
            "timeframe": self.timeframe,
            "is_closed": self.is_closed,
            "context": dict(self.context),
        }


def _expand_value_area(
    volumes: list[float],
    poc_index: int,
    total_volume: float,
    target_percentage: float,
) -> tuple[int, int]:
    """Single-bucket-step expansion from POC (see module Known
    Limitations for why this is simpler than the two-row TPO
    convention)."""

    low_index = poc_index
    high_index = poc_index
    accumulated = volumes[poc_index]
    target = total_volume * target_percentage

    while accumulated < target and (low_index > 0 or high_index < len(volumes) - 1):
        can_go_low = low_index > 0
        can_go_high = high_index < len(volumes) - 1

        if can_go_low and (not can_go_high or volumes[low_index - 1] >= volumes[high_index + 1]):
            low_index -= 1
            accumulated += volumes[low_index]
        elif can_go_high:
            high_index += 1
            accumulated += volumes[high_index]

    return low_index, high_index


def _find_volume_nodes(
    prices: list[float],
    volumes: list[float],
    width_threshold: float = DEFAULT_NODE_WIDTH_THRESHOLD,
) -> tuple[list[VolumeNode], list[VolumeNode]]:
    if len(volumes) < 3:
        return [], []

    average_volume = sum(volumes) / len(volumes)
    if average_volume == 0:
        return [], []

    peak_indices, trough_indices = find_local_extrema(volumes)

    hvn_nodes = [
        VolumeNode(
            price=prices[i],
            relative_volume=volumes[i] / average_volume,
            width=_node_width(i, volumes, is_peak=True, threshold_fraction=width_threshold),
        )
        for i in peak_indices
    ]

    lvn_nodes = [
        VolumeNode(
            price=prices[i],
            relative_volume=volumes[i] / average_volume,
            width=_node_width(i, volumes, is_peak=False, threshold_fraction=width_threshold),
        )
        for i in trough_indices
    ]

    return hvn_nodes, lvn_nodes


def _node_width(index: int, values: list[float], is_peak: bool, threshold_fraction: float) -> int:
    node_value = values[index]
    threshold = node_value * threshold_fraction

    width = 1

    i = index - 1
    while i >= 0 and ((values[i] >= threshold) if is_peak else (values[i] <= threshold)):
        width += 1
        i -= 1

    i = index + 1
    while i < len(values) and ((values[i] >= threshold) if is_peak else (values[i] <= threshold)):
        width += 1
        i += 1

    return width


class VolumeProfileTracker:
    """
    Builds and tracks a Volume Profile across a growing candle history,
    under a single anchor policy (continuous, or a named period from a
    SessionBoundariesTracker).

    One instance per backtest run (or per live session). Call sync()
    once per replay step. If an anchor is configured, pass that same
    step's SessionBoundariesTracker snapshot and advance by exactly one
    new candle per call (see sync()'s docstring).
    """

    def __init__(
        self,
        bucket_size: float,
        timeframe: str = "unknown",
        anchor_name: str | None = None,
        value_area_percentage: float = DEFAULT_VALUE_AREA_PERCENTAGE,
        atr_period: int = DEFAULT_ATR_PERIOD,
        max_tracked_closed: int = DEFAULT_MAX_TRACKED_CLOSED,
        timestamp_key: str = "timestamp",
    ):
        if bucket_size <= 0:
            raise ValueError("bucket_size must be > 0")

        if not 0 < value_area_percentage <= 1:
            raise ValueError("value_area_percentage must be in (0, 1]")

        self.timestamp_key = timestamp_key
        self._bucket_size = bucket_size
        self._timeframe = timeframe
        self._anchor_name = anchor_name
        self._value_area_percentage = value_area_percentage
        self._max_tracked_closed = max_tracked_closed

        self._atr = AverageTrueRangeTracker(period=atr_period, timestamp_key=timestamp_key)

        self._consumed = 0
        self._last_candle: dict[str, Any] | None = None

        self._current: VolumeProfile | None = None
        self._closed: list[VolumeProfile] = []
        self._last_session_key: Any = object()  # unique sentinel, never equals a real key

        self._previous_poc: float | None = None
        self._previous_vah: float | None = None
        self._previous_val: float | None = None

    def sync(
        self,
        candles: list[dict[str, Any]],
        session_snapshot: dict[str, Any] | None = None,
    ) -> None:
        requires_session = self._anchor_name is not None

        if requires_session and session_snapshot is None:
            raise ValueError(
                "session_snapshot is required - this tracker is "
                "configured with a session-based anchor_name"
            )

        if len(candles) < self._consumed:
            raise ValueError(
                "candles went backwards - VolumeProfileTracker does "
                "not support rewinding"
            )

        if requires_session and len(candles) - self._consumed > 1:
            raise ValueError(
                "VolumeProfileTracker.sync() can only advance by one "
                "new candle per call while a session anchor is "
                "configured - session_snapshot is a point-in-time "
                "snapshot, not a historical record, so batching could "
                "silently skip an entire period's reset"
            )

        if self._consumed > 0:
            checkpoint = candles[self._consumed - 1]

            if checkpoint != self._last_candle:
                raise ValueError(
                    "candles does not extend the history previously "
                    "seen by this VolumeProfileTracker"
                )

        for candle in candles[self._consumed:]:
            self._ingest(candle, session_snapshot)

        self._consumed = len(candles)

    def _ingest(
        self,
        candle: dict[str, Any],
        session_snapshot: dict[str, Any] | None,
    ) -> None:
        timestamp = candle[self.timestamp_key]

        if self._anchor_name is None:
            session_key = "__continuous__"
        else:
            current = session_snapshot[self._anchor_name]["current"]

            if current is None:
                self._atr.ingest_one(candle)
                self._last_candle = candle
                return  # off-session gap - paused, not reset

            session_key = current["period_start"]

        if session_key != self._last_session_key:
            self._start_new_period(session_key, timestamp)

        self._current.apply_candle(candle)

        self._atr.ingest_one(candle)
        self._last_candle = candle

    def _start_new_period(self, session_key: Any, timestamp: datetime) -> None:
        if self._current is not None:
            # The reference session's own period_end is not reliably
            # available yet at this instant (SessionBoundariesTracker
            # only sets it once ITS OWN period closes, which we cannot
            # wait for without delaying this transition) - the last
            # candle actually processed for the closing profile is
            # this system's own honest, candle-driven notion of when
            # that period ended.
            self._close_current(self._last_candle[self.timestamp_key])

        period_type = self._anchor_name if self._anchor_name else "continuous"

        self._current = VolumeProfile(
            period_type=period_type,
            period_start=timestamp,
            timeframe=self._timeframe,
            bucket_size=self._bucket_size,
            value_area_percentage=self._value_area_percentage,
        )
        self._last_session_key = session_key

    def _close_current(self, period_end: datetime) -> None:
        current = self._current

        if current.poc_price is not None and self._previous_poc is not None:
            atr = self._atr.current()

            if atr:
                current.poc_shift_from_previous_period = (current.poc_price - self._previous_poc) / atr

            current.value_area_overlap_ratio = _overlap_ratio(
                current.value_area_low, current.value_area_high,
                self._previous_val, self._previous_vah,
            )

        current.close(period_end)
        self._closed.append(current)

        if len(self._closed) > self._max_tracked_closed:
            self._closed = self._closed[-self._max_tracked_closed:]

        self._previous_poc = current.poc_price
        self._previous_vah = current.value_area_high
        self._previous_val = current.value_area_low

        self._current = None

    def snapshot(self) -> dict[str, Any]:
        current_dict = None

        if self._current is not None:
            current_dict = self._current.to_dict()

            if self._previous_poc is not None and self._current.poc_price is not None:
                atr = self._atr.current()

                if atr:
                    current_dict["poc_shift_from_previous_period"] = (
                        self._current.poc_price - self._previous_poc
                    ) / atr

                current_dict["value_area_overlap_ratio"] = _overlap_ratio(
                    self._current.value_area_low, self._current.value_area_high,
                    self._previous_val, self._previous_vah,
                )

        return {
            "current_forming_profile": current_dict,
            "closed_profiles": [p.to_dict() for p in self._closed],
        }


def _overlap_ratio(
    low_a: float | None,
    high_a: float | None,
    low_b: float | None,
    high_b: float | None,
) -> float | None:
    if None in (low_a, high_a, low_b, high_b):
        return None

    overlap = max(0.0, min(high_a, high_b) - max(low_a, low_b))
    span_a = high_a - low_a

    if span_a <= 0:
        return 1.0 if overlap > 0 or low_a == low_b else 0.0

    return overlap / span_a
