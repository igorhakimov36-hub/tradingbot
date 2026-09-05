"""
Fair Value Gap (FVG) - Phase 1.2 of the Smart Money Core (see
docs/smart_money_architecture.md, "Market Structure > 2. Fair Value Gaps").

Purpose
-------
A 3-candle imbalance where candle 1's wick and candle 3's wick do not
overlap marks a level where two-sided trading did not fully occur. Price
statistically revisits ("fills") these zones - a tendency independent of
any Smart Money branding.

Inputs
------
OHLCV only, any single timeframe. Fully independent primitive - no
dependency on any other Smart Money module.

Outputs (raw features only - see FairValueGapTracker.snapshot)
----------------------------------------------------------
direction, zone_high, zone_low, created_at, timeframe, age_in_bars,
gap_size, gap_size_atr_ratio, atr_at_creation, fill_status, fill_pct,
formation_volume, distance_from_price, context. No score, no threshold,
no BUY/SELL.

Context Preservation
---------------------
Every FairValueGap is a permanent piece of market memory, not just a
self-description: it records `created_at` and `timeframe` (the caller-
supplied label for whatever candle stream it was fed - this module is
timeframe-agnostic and never infers it), `atr_at_creation` (the raw
volatility backdrop, not just the derived ratio), and an open `context`
dict that starts empty. This module does not populate `context` with
BOS/CHOCH/trend/liquidity state - that is a future orchestrator's job,
combining this module's output with others' - but the field exists now
so that attaching such information later never requires a schema change
here.

Dependencies
------------
None beyond OHLCV. Consumed by (not built yet): Order Block confluence
checks, Inverse FVG / Balanced Price Range (both direct v2s of this
module's fill_status transitions - see the architecture doc's "Future
Extensions" for Fair Value Gaps).

Replay Safety
-------------
A gap becomes confirmable the instant the third candle (C) closes - the
same 3-bar-window shape already used by the swing-pivot fractal check in
market_structure.py. Fill-status updates for an existing gap only ever
use candles ingested AFTER its confirming candle - never the confirming
candle itself, and never a candle from the future. FairValueGapTracker
rejects a candle history that goes backwards or diverges from what it has
already consumed (same guard already used by TimeframeManager and
DeltaTracker).

Live Trading
------------
Purely incremental: only the last 3 candles are needed for detection and
one already-tracked gap needs only the newest candle to update its fill
status. sync() accepts the same "full growing candle list, only new
candles processed" contract every other tracker in this codebase already
uses, so a live orchestrator needs no special-casing.

Computational Complexity
-------------------------
O(1) per new candle for detection (fixed 3-candle window) - the cheapest
detector in the whole Smart Money Core. Fill-status updates cost O(k)
where k = currently active (unfilled) gaps, bounded by age-based pruning
(see Known Limitations). ATR is computed incrementally in O(1) via
AverageTrueRangeTracker. No component of this module ever rescans the
full candle history.

Known Limitations / Future Extension Points
--------------------------------------------
- Fill tracking uses wick (high/low) penetration into the zone, not a
  close-through-the-zone requirement - "did price trade at this level"
  rather than the stronger claim "did price close beyond it". This is a
  deliberate, documented choice; a close-based variant could be added as
  an alternate fill_status computation later without changing the zone-
  detection logic.
- gap_size_atr_ratio uses the ATR measured *before* the impulsive middle
  candle is folded into the rolling average - avoids the ratio being
  self-referentially inflated by the very candle that created the gap.
- Unfilled gaps are pruned from active tracking after `max_age_bars`
  candles (default 5000) purely for bounded memory over a multi-year
  replay - this does not mean the gap is invalid, only that this module
  stops updating it; `age_in_bars` itself is never capped or hidden while
  a gap is still tracked.

Inversion lifecycle (opt-in, disabled by default)
---------------------------------------------------
Per docs/fvg_ifvg_module_logic_review.md's own decision report
(Section 6a, Path B - "in-place lifecycle extension"): a gap that
reaches `fill_status == "completely_filled"` (wick-based, unchanged
above) can OPTIONALLY continue to be watched, as the SAME object
(identity/direction/boundaries preserved), for a close-confirmed
inversion - deliberately a SEPARATE, stronger condition than fill,
never a substitute for it. Controlled entirely by `track_inversions`
(constructor flag, default False) - when False, none of the code
below this point ever executes and `snapshot()`'s own returned dict
keys are byte-identical to the pre-inversion-feature shape (verified
by tests/test_fair_value_gap.py's own existing exact-dict-equality
assertions, unmodified).

- **Inversion confirmation**: CLOSE-based (matching both reference
  implementations reviewed), strict inequality - a bullish gap
  inverts when a later, already-closed candle's own close is STRICTLY
  below `zone_low` (fully clears the gap, not merely touches it); a
  bearish gap inverts on a close strictly above `zone_high`. A close
  exactly AT the boundary does not confirm inversion - a deliberate,
  disclosed choice, not an oversight.
- **Post-inversion failure**: an already-inverted gap that is later
  reclaimed the OTHER way (close back beyond the zone's original far
  edge) is marked failed and permanently excluded from further
  inversion/retest consideration - a third, terminal lifecycle state.
- **One-shot, idempotent**: `is_inverted`/`is_failed` are sticky
  booleans set at most once each; a bar whose close again satisfies an
  already-confirmed condition is a no-op, never a duplicate event.
- **Bounded retention**: a filled-but-not-yet-inverted gap is watched
  for at most `inversion_watch_bars` candles (measured from its own
  `filled_bar_index`) before `inversion_expired` is set and it is
  excluded from further inversion checks (counted in
  `inversion_expired_count`) - mirrors the existing unfilled-gap
  `max_age_bars`/`expired_count` pattern exactly. Total retained
  filled/inverted/failed gaps remain bounded by the existing
  `max_tracked_filled` FIFO eviction on `self._filled` - not a new
  bound, the existing one now also covers this feature.
- **Retest signal** (independently optional - `track_retests`,
  requires `track_inversions` also True): a 2-bar rejection pattern
  against an already-inverted zone's own original boundary (modeled on
  the reference IFVG implementation reviewed), with a bar-count
  cooldown between repeat signals for the same gap. Never gates or
  substitutes for inversion confirmation itself.

See `docs/fvg_ifvg_module_logic_review.md` for the full design review
this implementation follows, including the exact synthetic examples
used to derive each rule above.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal

from strategy.features.utils import AverageTrueRangeTracker

Direction = Literal["bullish", "bearish"]
FillStatus = Literal["active", "partially_filled", "completely_filled"]

DEFAULT_ATR_PERIOD = 14
DEFAULT_MAX_AGE_BARS = 5000
DEFAULT_MAX_TRACKED_FILLED = 500
DEFAULT_INVERSION_WATCH_BARS = 500
DEFAULT_RETEST_COOLDOWN_BARS = 5


@dataclass
class FairValueGap:
    direction: Direction
    zone_high: float
    zone_low: float
    created_at: datetime
    origin_bar_index: int
    timeframe: str
    formation_volume: float
    gap_size: float
    gap_size_atr_ratio: float | None
    atr_at_creation: float | None

    fill_pct: float = 0.0
    fill_status: FillStatus = "active"
    context: dict[str, Any] = field(default_factory=dict)

    # Opt-in inversion lifecycle - see module docstring "Inversion
    # lifecycle" section. All default to "never happened" and are only
    # ever written by FairValueGapTracker when track_inversions=True.
    filled_at: datetime | None = None
    filled_bar_index: int | None = None
    is_inverted: bool = False
    inverted_at: datetime | None = None
    inverted_bar_index: int | None = None
    is_failed: bool = False
    failed_at: datetime | None = None
    failed_bar_index: int | None = None
    inversion_expired: bool = False
    last_retest_bar_index: int | None = None  # cooldown bookkeeping only, not itself a signal

    _deepest_penetration: float = field(init=False, repr=False)

    def __post_init__(self) -> None:
        # Bullish gaps sit below price and fill from the top (zone_high)
        # downward; bearish gaps sit above price and fill from the
        # bottom (zone_low) upward. Starts at "no penetration yet".
        self._deepest_penetration = (
            self.zone_high if self.direction == "bullish" else self.zone_low
        )

    def apply_candle(self, candle: dict[str, Any]) -> None:
        zone_span = self.zone_high - self.zone_low

        if zone_span <= 0:
            # Defensive only - detection guarantees zone_high > zone_low.
            self.fill_pct = 1.0
            self.fill_status = "completely_filled"
            return

        if self.direction == "bullish":
            self._deepest_penetration = min(
                self._deepest_penetration, candle["low"]
            )
            raw_fill = (
                self.zone_high - self._deepest_penetration
            ) / zone_span

        else:
            self._deepest_penetration = max(
                self._deepest_penetration, candle["high"]
            )
            raw_fill = (
                self._deepest_penetration - self.zone_low
            ) / zone_span

        self.fill_pct = min(1.0, max(0.0, raw_fill))

        if self.fill_pct >= 1.0:
            self.fill_status = "completely_filled"
        elif self.fill_pct > 0.0:
            self.fill_status = "partially_filled"
        else:
            self.fill_status = "active"

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
            "timeframe": self.timeframe,
            "age_in_bars": current_bar_index - self.origin_bar_index,
            "gap_size": self.gap_size,
            "gap_size_atr_ratio": self.gap_size_atr_ratio,
            "atr_at_creation": self.atr_at_creation,
            "formation_volume": self.formation_volume,
            "fill_status": self.fill_status,
            "fill_pct": self.fill_pct,
            "distance_from_price": distance_from_price,
            "context": dict(self.context),
            "filled_at": self.filled_at,
            "filled_bar_index": self.filled_bar_index,
            "is_inverted": self.is_inverted,
            "inverted_at": self.inverted_at,
            "inverted_bar_index": self.inverted_bar_index,
            "is_failed": self.is_failed,
            "failed_at": self.failed_at,
            "failed_bar_index": self.failed_bar_index,
            "inversion_expired": self.inversion_expired,
            "last_retest_bar_index": self.last_retest_bar_index,
            # True only on the EXACT bar a retest was just confirmed -
            # a consumer reading a later snapshot of the SAME gap sees
            # this revert to False (the event, not a sticky state; the
            # sticky record is last_retest_bar_index above).
            "retest_confirmed_this_bar": self.last_retest_bar_index == current_bar_index,
        }


class FairValueGapTracker:
    """
    Detects and tracks Fair Value Gaps across a growing candle history.

    One instance per backtest run (or per live session), matching the
    lifecycle already used by TimeframeManager/DeltaTracker. Call sync()
    once per replay step with the full candle history seen so far.
    """

    def __init__(
        self,
        timeframe: str = "unknown",
        atr_period: int = DEFAULT_ATR_PERIOD,
        max_age_bars: int = DEFAULT_MAX_AGE_BARS,
        max_tracked_filled: int = DEFAULT_MAX_TRACKED_FILLED,
        timestamp_key: str = "timestamp",
        track_inversions: bool = False,
        track_retests: bool = False,
        inversion_watch_bars: int = DEFAULT_INVERSION_WATCH_BARS,
        retest_cooldown_bars: int = DEFAULT_RETEST_COOLDOWN_BARS,
    ):
        """
        `timeframe` is a caller-supplied label (e.g. "1m", "15m") - this
        module never inspects candle spacing to infer it, since it is
        deliberately timeframe-agnostic (the caller decides what stream
        to feed it). Only used for context preservation on the features
        this tracker produces; never used in any detection logic.

        `track_inversions` (default False) and `track_retests` (default
        False, meaningless without `track_inversions=True`) opt into
        the inversion lifecycle described in the module docstring. When
        both are False (the default, matching every current caller of
        this tracker), NONE of the inversion/retest code below ever
        executes - snapshot()'s own returned dict keys are exactly
        {"active", "filled", "expired_count"}, unchanged from before
        this feature existed.
        """

        self.timestamp_key = timestamp_key
        self._timeframe = timeframe
        self._max_age_bars = max_age_bars
        self._max_tracked_filled = max_tracked_filled
        self._track_inversions = track_inversions
        self._track_retests = track_retests
        self._inversion_watch_bars = inversion_watch_bars
        self._retest_cooldown_bars = retest_cooldown_bars

        self._atr = AverageTrueRangeTracker(
            period=atr_period,
            timestamp_key=timestamp_key,
        )

        self._consumed = 0
        self._last_candle: dict[str, Any] | None = None
        self._recent_candles: list[dict[str, Any]] = []

        self._bar_index = -1
        self._expired_count = 0
        self._inversion_expired_count = 0

        self._active: list[FairValueGap] = []
        self._filled: list[FairValueGap] = []

    def sync(self, candles: list[dict[str, Any]]) -> None:
        if len(candles) < self._consumed:
            raise ValueError(
                "candles went backwards - FairValueGapTracker does "
                "not support rewinding"
            )

        if self._consumed > 0:
            checkpoint = candles[self._consumed - 1]

            if checkpoint != self._last_candle:
                raise ValueError(
                    "candles does not extend the history previously "
                    "seen by this FairValueGapTracker"
                )

        for candle in candles[self._consumed:]:
            self._ingest(candle)

        self._consumed = len(candles)

    def _ingest(self, candle: dict[str, Any]) -> None:
        self._bar_index += 1

        self._update_fills(candle)
        self._expire_stale_gaps()

        # Inversion/retest tracking reads self._last_candle as "the
        # PRIOR candle" (still unoverwritten at this point in _ingest)
        # - must run before self._last_candle is reassigned below, and
        # after _update_fills so a gap that fills on THIS exact candle
        # is already in self._filled and eligible for a same-candle
        # inversion check (see module docstring, "same candle" case).
        if self._track_inversions:
            self._update_inversions(candle)

        self._recent_candles.append(candle)
        if len(self._recent_candles) > 3:
            self._recent_candles.pop(0)

        self._detect_new_gap()

        # ATR is updated with this candle only *after* it was used for
        # gap detection - the ratio reflects volatility measured before
        # the impulsive candle itself, not inflated by it. ingest_one()
        # is O(1) - never reconstructs or slices a growing list.
        self._atr.ingest_one(candle)

        self._last_candle = candle

    def _update_fills(self, candle: dict[str, Any]) -> None:
        still_active = []

        for gap in self._active:
            gap.apply_candle(candle)

            if gap.fill_status == "completely_filled":
                if self._track_inversions:
                    gap.filled_at = candle[self.timestamp_key]
                    gap.filled_bar_index = self._bar_index
                self._filled.append(gap)
            else:
                still_active.append(gap)

        self._active = still_active

        if len(self._filled) > self._max_tracked_filled:
            self._filled = self._filled[-self._max_tracked_filled:]

    def _update_inversions(self, candle: dict[str, Any]) -> None:
        close = candle["close"]
        previous_candle = self._last_candle

        for gap in self._filled:
            if gap.is_failed:
                continue

            if gap.is_inverted:
                self._check_failure(gap, candle, close)
                if self._track_retests and not gap.is_failed:
                    self._check_retest(gap, candle, previous_candle)
                continue

            if gap.inversion_expired:
                continue

            if (self._bar_index - gap.filled_bar_index) > self._inversion_watch_bars:
                gap.inversion_expired = True
                self._inversion_expired_count += 1
                continue

            self._check_inversion(gap, candle, close)

    def _check_inversion(self, gap: "FairValueGap", candle: dict[str, Any], close: float) -> None:
        # Strict inequality: a close exactly AT the boundary does not
        # confirm inversion - matches both reference implementations
        # reviewed, a deliberate, disclosed choice (module docstring).
        inverted = (
            close < gap.zone_low if gap.direction == "bullish"
            else close > gap.zone_high
        )
        if not inverted:
            return

        gap.is_inverted = True
        gap.inverted_at = candle[self.timestamp_key]
        gap.inverted_bar_index = self._bar_index

    def _check_failure(self, gap: "FairValueGap", candle: dict[str, Any], close: float) -> None:
        # An inverted zone is "reclaimed the other way" if price closes
        # back beyond the zone's ORIGINAL far edge - the opposite edge
        # from the one that confirmed inversion.
        failed = (
            close > gap.zone_high if gap.direction == "bullish"
            else close < gap.zone_low
        )
        if not failed:
            return

        gap.is_failed = True
        gap.failed_at = candle[self.timestamp_key]
        gap.failed_bar_index = self._bar_index

    def _check_retest(self, gap: "FairValueGap", candle: dict[str, Any], previous_candle: dict[str, Any] | None) -> None:
        if previous_candle is None:
            return

        if gap.last_retest_bar_index is not None:
            if (self._bar_index - gap.last_retest_bar_index) <= self._retest_cooldown_bars:
                return

        # Bullish-original gap, now inverted (acting resistance): the
        # retest level is the gap's own ORIGINAL lower edge (zone_low).
        # A prior bar reaching it, followed by a current bar failing to
        # exceed it, is a rejection - "held as new resistance."
        if gap.direction == "bullish":
            level = gap.zone_low
            retested = previous_candle["high"] >= level and candle["high"] <= level
        else:
            level = gap.zone_high
            retested = previous_candle["low"] <= level and candle["low"] >= level

        if retested:
            gap.last_retest_bar_index = self._bar_index

    def _expire_stale_gaps(self) -> None:
        still_active = []

        for gap in self._active:
            if (self._bar_index - gap.origin_bar_index) > self._max_age_bars:
                self._expired_count += 1
            else:
                still_active.append(gap)

        self._active = still_active

    def _detect_new_gap(self) -> None:
        if len(self._recent_candles) < 3:
            return

        candle_a, _candle_b, candle_c = self._recent_candles
        formation_volume = _candle_b["volume"]
        atr = self._atr.current()

        if candle_a["high"] < candle_c["low"]:
            gap_size = candle_c["low"] - candle_a["high"]

            self._active.append(
                FairValueGap(
                    direction="bullish",
                    zone_low=candle_a["high"],
                    zone_high=candle_c["low"],
                    created_at=candle_c[self.timestamp_key],
                    origin_bar_index=self._bar_index,
                    timeframe=self._timeframe,
                    formation_volume=formation_volume,
                    gap_size=gap_size,
                    gap_size_atr_ratio=(gap_size / atr) if atr else None,
                    atr_at_creation=atr,
                )
            )

        elif candle_a["low"] > candle_c["high"]:
            gap_size = candle_a["low"] - candle_c["high"]

            self._active.append(
                FairValueGap(
                    direction="bearish",
                    zone_low=candle_c["high"],
                    zone_high=candle_a["low"],
                    created_at=candle_c[self.timestamp_key],
                    origin_bar_index=self._bar_index,
                    timeframe=self._timeframe,
                    formation_volume=formation_volume,
                    gap_size=gap_size,
                    gap_size_atr_ratio=(gap_size / atr) if atr else None,
                    atr_at_creation=atr,
                )
            )

    def snapshot(self) -> dict[str, Any]:
        current_price = (
            self._last_candle["close"] if self._last_candle else None
        )

        active = [
            gap.to_dict(self._bar_index, current_price)
            for gap in self._active
        ] if current_price is not None else []

        filled = [
            gap.to_dict(self._bar_index, current_price)
            for gap in self._filled
        ] if current_price is not None else []

        result = {
            "active": active,
            "filled": filled,
            "expired_count": self._expired_count,
        }

        if self._track_inversions:
            result["inverted"] = [
                g for g in filled if g["is_inverted"] and not g["is_failed"]
            ]
            result["failed"] = [g for g in filled if g["is_failed"]]
            result["inversion_expired_count"] = self._inversion_expired_count

        return result
