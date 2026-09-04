"""
Equal Highs / Equal Lows (EQH/EQL) - Phase 1.3 of the Smart Money Core
(see docs/smart_money_architecture.md, "Market Structure > 6. Equal
Highs / Equal Lows").

Purpose
-------
The most specific, most common form of visible liquidity clustering: two
or more swing highs (or lows) at approximately the same price - an
obvious level many participants place stops/breakout orders around.
Rooted in classical "double top/bottom" technical analysis (Edwards &
Magee), later reframed through a market-microstructure lens: academic
work on stop-loss/take-profit clustering (e.g. Osler, 2003, "Currency
Orders and Exchange Rate Dynamics") found statistically significant
clustering of resting orders around round numbers and prior highs/lows.

Institutional framing chosen over the alternative (volume-at-price
clustering, which needs Volume Profile - a later module): this module
answers "where did price print similar extremes", a distinct question
from "where did the most volume trade". Conflating the two would blur
two different microstructure phenomena into one module.

Inputs
------
OHLCV only, any single timeframe - deliberately timeframe-agnostic, same
convention as Delta and Fair Value Gaps. The caller decides what stream
to feed it (1m for micro-structure, 15m/1h for levels intended to be
institutionally meaningful).

Outputs (raw features only - see EqualLevelsTracker.snapshot)
-----------------------------------------------------------
direction, level, pivot_prices, pivot_timestamps, pivot_count,
max_deviation, created_at, timeframe, age_in_bars, swept_status,
swept_timestamp, distance_from_price, context. No score, no threshold,
no BUY/SELL.

Dependencies
------------
Reuses strategy.market_structure.find_swing_pivots (the same 3-bar
fractal rule get_last_swing_levels has always used) instead of
reimplementing pivot detection - avoids duplicating that logic a third
time. Consumed by (not built yet): Liquidity Pools, which aggregates
this module's clusters with session extremes and round numbers.

Replay Safety
-------------
A pivot confirms exactly one bar after it forms - the same delay
get_last_swing_levels has always had, since a 3-bar fractal needs its
right-hand neighbor to close before it can be confirmed. A cluster only
exists once a second already-confirmed pivot lands within tolerance of
an existing one - never earlier. Sweep checks use only the current
candle's already-known high/low/close. sync() rejects a candle history
that goes backwards or diverges from what it has already consumed (same
guard as every other tracker in this codebase).

Live Trading
------------
Fully incremental: pivot confirmation only ever needs the last 3
candles, and cluster matching only ever compares a newly confirmed pivot
against a bounded, age-pruned set of recent pivots - never the full
history. sync() uses the same "full growing candle list, only new
candles processed" contract as every other tracker here.

Computational Complexity
-------------------------
O(1) per new candle for pivot confirmation (fixed 3-candle window,
delegated to find_swing_pivots on that window only). Clustering a new
pivot is O(p) where p = currently tracked pivots of that direction,
bounded by `max_tracked_pivots` (default 200) - deliberately NOT the
naive O(n^2) all-pairs comparison flagged as a real risk in the
architecture document; only the newest pivot is ever compared against
the bounded recent set, never all pivots against each other. ATR is
O(1) via the shared AverageTrueRangeTracker.

Known Limitations / Future Extension Points
--------------------------------------------
- Clustering is greedy and order-dependent (first tolerance match wins,
  in arrival order) rather than a global optimal clustering - matches
  how the market itself reveals pivots one at a time during replay, and
  keeps the algorithm deterministic and O(p) instead of needing a full
  re-clustering pass.
- A cluster's `age_in_bars` is measured from its formation (the second
  contributing pivot), not from its most recent touch - a cluster that
  keeps collecting new touches still expires on the same fixed schedule
  as one that never gets touched again. Revisit if real usage shows
  actively-touched levels being pruned too eagerly.
- Sweep detection uses the same single-candle wick-beyond-then-close-
  back-inside convention already used by strategy/liquidity.py's
  detect_liquidity_sweep - not reimplemented differently here.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal

from strategy.features.utils import AverageTrueRangeTracker
from strategy.features.zone_lifecycle import copy_snapshot_dict
from strategy.market_structure import find_swing_pivots

Direction = Literal["equal_highs", "equal_lows"]
SweptStatus = Literal["unswept", "swept"]

DEFAULT_ATR_PERIOD = 14
DEFAULT_TOLERANCE_ATR_MULTIPLIER = 0.1
DEFAULT_MAX_AGE_BARS = 5000
DEFAULT_MAX_TRACKED_PIVOTS = 200


@dataclass
class EqualLevelCluster:
    direction: Direction
    level: float
    pivot_prices: list[float]
    pivot_timestamps: list[datetime]
    pivot_bar_indices: list[int]
    max_deviation: float
    created_at: datetime
    origin_bar_index: int
    timeframe: str

    swept_status: SweptStatus = "unswept"
    swept_timestamp: datetime | None = None
    context: dict[str, Any] = field(default_factory=dict)

    def register_touch(
        self,
        price: float,
        timestamp: datetime,
        bar_index: int,
    ) -> None:
        self.pivot_prices.append(price)
        self.pivot_timestamps.append(timestamp)
        self.pivot_bar_indices.append(bar_index)
        self.max_deviation = max(self.pivot_prices) - min(self.pivot_prices)
        self.level = sum(self.pivot_prices) / len(self.pivot_prices)

    def check_sweep(self, candle: dict[str, Any], timestamp_key: str) -> None:
        if self.swept_status != "unswept":
            return

        if self.direction == "equal_highs":
            swept = candle["high"] > self.level and candle["close"] < self.level
        else:
            swept = candle["low"] < self.level and candle["close"] > self.level

        if swept:
            self.swept_status = "swept"
            self.swept_timestamp = candle[timestamp_key]

    def to_dict(
        self,
        current_bar_index: int,
        current_price: float,
    ) -> dict[str, Any]:

        return {
            "direction": self.direction,
            "level": self.level,
            "pivot_prices": list(self.pivot_prices),
            "pivot_timestamps": list(self.pivot_timestamps),
            "pivot_count": len(self.pivot_prices),
            "max_deviation": self.max_deviation,
            "created_at": self.created_at,
            "timeframe": self.timeframe,
            "age_in_bars": current_bar_index - self.origin_bar_index,
            "swept_status": self.swept_status,
            "swept_timestamp": self.swept_timestamp,
            "distance_from_price": abs(current_price - self.level),
            "context": dict(self.context),
        }


class EqualLevelsTracker:
    """
    Detects and tracks Equal Highs / Equal Lows clusters across a
    growing candle history.

    One instance per backtest run (or per live session), matching the
    lifecycle already used by every other tracker in this codebase.
    Call sync() once per replay step with the full candle history seen
    so far.
    """

    def __init__(
        self,
        timeframe: str = "unknown",
        atr_period: int = DEFAULT_ATR_PERIOD,
        tolerance_atr_multiplier: float = DEFAULT_TOLERANCE_ATR_MULTIPLIER,
        max_age_bars: int = DEFAULT_MAX_AGE_BARS,
        max_tracked_pivots: int = DEFAULT_MAX_TRACKED_PIVOTS,
        timestamp_key: str = "timestamp",
    ):
        self.timestamp_key = timestamp_key
        self._timeframe = timeframe
        self._tolerance_atr_multiplier = tolerance_atr_multiplier
        self._max_age_bars = max_age_bars
        self._max_tracked_pivots = max_tracked_pivots

        self._atr = AverageTrueRangeTracker(
            period=atr_period,
            timestamp_key=timestamp_key,
        )

        self._consumed = 0
        self._last_candle: dict[str, Any] | None = None
        self._recent_candles: list[dict[str, Any]] = []

        self._bar_index = -1
        self._expired_count = 0

        # Each entry: {"price": float, "timestamp": datetime,
        #              "bar_index": int, "cluster": EqualLevelCluster|None}
        self._pivot_highs: list[dict[str, Any]] = []
        self._pivot_lows: list[dict[str, Any]] = []

        self._high_clusters: list[EqualLevelCluster] = []
        self._low_clusters: list[EqualLevelCluster] = []

        # Snapshot cache (Sprint 1B, performance-only) - see the
        # identical, more fully-commented pattern in
        # strategy/features/order_block.py. _bar_index already
        # increments exactly once per _ingest() call and snapshot()
        # takes no external arguments, so caching keyed on it alone is
        # exact.
        self._snapshot_cache: dict[str, Any] | None = None
        self._snapshot_cache_bar_index: int | None = None

    def sync(self, candles: list[dict[str, Any]]) -> None:
        if len(candles) < self._consumed:
            raise ValueError(
                "candles went backwards - EqualLevelsTracker does not "
                "support rewinding"
            )

        if self._consumed > 0:
            checkpoint = candles[self._consumed - 1]

            if checkpoint != self._last_candle:
                raise ValueError(
                    "candles does not extend the history previously "
                    "seen by this EqualLevelsTracker"
                )

        for candle in candles[self._consumed:]:
            self._ingest(candle)

        self._consumed = len(candles)

    def _ingest(self, candle: dict[str, Any]) -> None:
        self._bar_index += 1

        self._check_sweeps(candle)
        self._expire_stale_clusters()

        self._recent_candles.append(candle)
        if len(self._recent_candles) > 3:
            self._recent_candles.pop(0)

        self._detect_new_pivot()

        # ATR reflects volatility up to (not including) this candle -
        # ingest_one() is O(1), never reconstructs a growing list.
        self._atr.ingest_one(candle)

        self._last_candle = candle

    def _check_sweeps(self, candle: dict[str, Any]) -> None:
        for cluster in self._high_clusters:
            cluster.check_sweep(candle, self.timestamp_key)

        for cluster in self._low_clusters:
            cluster.check_sweep(candle, self.timestamp_key)

    def _expire_stale_clusters(self) -> None:
        for clusters in (self._high_clusters, self._low_clusters):
            still_tracked = []

            for cluster in clusters:
                if (self._bar_index - cluster.origin_bar_index) > self._max_age_bars:
                    self._expired_count += 1
                else:
                    still_tracked.append(cluster)

            clusters[:] = still_tracked

    def _detect_new_pivot(self) -> None:
        if len(self._recent_candles) < 3:
            return

        highs = [c["high"] for c in self._recent_candles]
        lows = [c["low"] for c in self._recent_candles]

        # A 3-element window only ever yields a pivot at relative index
        # 1 - the middle candle, confirmed by its two neighbors.
        swing_highs, swing_lows = find_swing_pivots(highs, lows)

        middle_candle = self._recent_candles[1]
        middle_bar_index = self._bar_index - 1
        atr = self._atr.current()

        if swing_highs:
            self._register_pivot(
                direction="equal_highs",
                price=middle_candle["high"],
                timestamp=middle_candle[self.timestamp_key],
                bar_index=middle_bar_index,
                atr=atr,
            )

        if swing_lows:
            self._register_pivot(
                direction="equal_lows",
                price=middle_candle["low"],
                timestamp=middle_candle[self.timestamp_key],
                bar_index=middle_bar_index,
                atr=atr,
            )

    def _register_pivot(
        self,
        direction: Direction,
        price: float,
        timestamp: datetime,
        bar_index: int,
        atr: float | None,
    ) -> None:
        pivots = (
            self._pivot_highs if direction == "equal_highs" else self._pivot_lows
        )
        clusters = (
            self._high_clusters if direction == "equal_highs" else self._low_clusters
        )

        tolerance = (atr * self._tolerance_atr_multiplier) if atr else 0.0

        matched_cluster: EqualLevelCluster | None = None
        matched_lone_pivot: dict[str, Any] | None = None

        for pivot in pivots:
            if abs(pivot["price"] - price) <= tolerance:
                if pivot["cluster"] is not None:
                    matched_cluster = pivot["cluster"]
                else:
                    matched_lone_pivot = pivot
                break

        new_pivot_record: dict[str, Any] = {
            "price": price,
            "timestamp": timestamp,
            "bar_index": bar_index,
            "cluster": None,
        }

        if matched_cluster is not None:
            matched_cluster.register_touch(price, timestamp, bar_index)
            new_pivot_record["cluster"] = matched_cluster

        elif matched_lone_pivot is not None:
            cluster = EqualLevelCluster(
                direction=direction,
                level=(matched_lone_pivot["price"] + price) / 2,
                pivot_prices=[matched_lone_pivot["price"], price],
                pivot_timestamps=[matched_lone_pivot["timestamp"], timestamp],
                pivot_bar_indices=[matched_lone_pivot["bar_index"], bar_index],
                max_deviation=abs(matched_lone_pivot["price"] - price),
                created_at=timestamp,
                origin_bar_index=bar_index,
                timeframe=self._timeframe,
            )
            clusters.append(cluster)
            matched_lone_pivot["cluster"] = cluster
            new_pivot_record["cluster"] = cluster

        pivots.append(new_pivot_record)

        if len(pivots) > self._max_tracked_pivots:
            pivots.pop(0)

    def snapshot(self) -> dict[str, Any]:
        if self._snapshot_cache is None or self._snapshot_cache_bar_index != self._bar_index:
            self._snapshot_cache = self._build_snapshot()
            self._snapshot_cache_bar_index = self._bar_index

        return copy_snapshot_dict(self._snapshot_cache)

    def _build_snapshot(self) -> dict[str, Any]:
        if self._last_candle is None:
            return {
                "equal_highs": [],
                "equal_lows": [],
                "expired_count": self._expired_count,
            }

        current_price = self._last_candle["close"]

        return {
            "equal_highs": [
                cluster.to_dict(self._bar_index, current_price)
                for cluster in self._high_clusters
            ],
            "equal_lows": [
                cluster.to_dict(self._bar_index, current_price)
                for cluster in self._low_clusters
            ],
            "expired_count": self._expired_count,
        }
