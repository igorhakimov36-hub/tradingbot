"""
Cumulative Volume Delta (CVD) - Phase 1.9 of the Smart Money Core (see
docs/smart_money_architecture.md, "Order Flow > 8. CVD").

Purpose
-------
Delta measures aggression within a single closed bar. CVD is the
running sum of Delta over time, revealing whether that aggression is
SUSTAINED - a single loud bar versus a persistent trend. Price and CVD
rising together confirms a move is backed by real buying pressure, not
thin drift; price making a new high while CVD does not is the classic
order-flow exhaustion/reversal tell, visible before price itself turns.

CVD is not a new computation on top of raw candles - it is Delta
promoted from a stateless bar property into a persistent, anchored
market object, the same jump every earlier module made (Delta -> FVG's
fill tracking, Order Block's mitigation lifecycle). It NEVER
recomputes taker-volume math itself: every bar's contribution comes
from strategy.features.delta.calculate_delta(), called exactly once
per bar (see Architectural decision below) - "do not duplicate
calculations" applies here as directly as anywhere in this package.

Complements (does not modify, does not reach into) Market Structure's
BOS/CHOCH, Order Blocks, or Liquidity Pools: a BOS/sweep with
supporting CVD trend is stronger context than one without, but that
comparison happens downstream (a future Strategy Engine V2 or AI layer
correlating this module's `cvd_direction`/`cvd_slope` against another
module's timestamp), never inside this module or the other way around.
Future SMT (intermarket divergence) needs zero changes here either - it
would simply run two independent CVDTracker instances, one per symbol,
and compare their outputs, the same multi-symbol-via-independent-
instances pattern every other module already follows.

Architectural decision - anchoring reuses Session Boundaries, not a
new mechanism: strategy/features/delta.py's own docstring already
flagged this forward ("cumulative_delta is NOT anchored to a session...
When [Session Boundaries] exists, a session-aware reset can be layered
on without changing this module's output field names"). Rather than
reimplementing calendar/timezone logic, CVDTracker detects a new anchor
period purely by watching a SessionBoundariesTracker's own
`period_start` change - the exact same upstream-snapshot composition
pattern Liquidity Pools already established with Equal Levels/Session
Boundaries.

Architectural decision - one tracker, multiple simultaneous anchors:
running three separate CVDTracker instances (continuous + daily +
weekly) would call calculate_delta() on the same candle three times.
Instead, CVDTracker accepts a LIST of named CVDAnchor configs in one
instance - mirroring SessionBoundariesTracker's own multi-definition
design exactly - computing calculate_delta() once per candle and
feeding that single value into every configured anchor's independent
accumulator.

Inputs
------
OHLCV + `taker_buy_volume` (via calculate_delta - optional, honestly
propagates None rather than fabricating zero aggression), plus an
optional SessionBoundariesTracker snapshot for any anchor that is not
"continuous".

Outputs (raw features only - see CVDTracker.snapshot)
------------------------------------------------------
Per configured anchor name: `cvd` (running value under that anchor),
`cvd_direction` (sign of cvd_slope, or None before the window fills),
`cvd_change_over_window`, `cvd_slope` (both None until
bars_since_anchor >= window - never a partially-computed number),
`price_cvd_divergence_flag`: bullish_divergence | bearish_divergence |
none, `cvd_exhaustion_flag`: bullish_exhaustion | bearish_exhaustion |
none, `anchor_type` (the anchor's configured session_name, or
"continuous"), `anchor_timestamp`, `bars_since_anchor`,
`bars_with_missing_data`, `timeframe`, `context`. No score, no
threshold, no BUY/SELL.

Divergence and exhaustion naming follows the SAME convention: named by
IMPLIED future direction, not by which side is active - matching
`price_cvd_divergence_flag`'s own doc-specified vocabulary
(bullish_divergence = price fell without CVD confirming = implies an
upward reversal). Exhaustion mirrors this: CVD making a new HIGH while
decelerating means BUYING pressure is fading at the top, which implies
a possible reversal DOWN -> `bearish_exhaustion`; CVD making a new LOW
while decelerating means SELLING pressure is fading at the bottom,
implying a possible reversal UP -> `bullish_exhaustion`.

Dependencies
------------
Hard dependency on strategy.features.delta.calculate_delta (never
reimplemented). Optional dependency on a SessionBoundariesTracker's
public snapshot for any session-anchored config - never its internals,
never its own anchor-resolution logic.

Replay Safety
-------------
A running sum of an already-safe input (calculate_delta is computed
entirely from a closed bar's own fields). The anchor/reset boundary
only ever refers to an already-passed boundary reported by
SessionBoundariesTracker - never a lookahead-defined one. Because
session_snapshot is a point-in-time snapshot, not a historical record
(the same risk class already discovered for Breaker Blocks/Liquidity
Pools), sync() enforces exactly one new candle per call WHENEVER at
least one configured anchor is session-based - batching could silently
skip an entire anchor period's reset if multiple period transitions
occurred within the batch. A tracker whose anchors are ALL "continuous"
has no such input and remains exactly as batchable as Delta itself -
the guard is conditional on actual risk, not applied unconditionally
out of caution.

Live Trading
------------
Same incremental accumulation; anchor/reset state persists across
calls, the same per-run stateful pattern TimeframeManager/DeltaTracker
already use. A live orchestrator with any session-anchored config must
sync SessionBoundariesTracker first, then this tracker, once per
candle - the same ordering-dependency contract already established.

Computational Complexity
-------------------------
O(a) per bar, a = number of configured anchors (a handful) - one
calculate_delta() call shared across all of them, then O(1) per-anchor
accumulation plus a bounded window (max size `window`) for
change/slope/divergence/exhaustion. No candle history is ever rescanned.

Known Limitations / Future Extension Points
--------------------------------------------
- A session-anchored config that uses a SessionWindow (a Kill Zone,
  with off-session gaps) simply pauses accumulation while
  `session_snapshot[name]["current"]` is None, rather than resetting -
  a genuinely new anchor period only begins once the window reopens
  with a new `period_start`. CalendarPeriod anchors (daily/weekly) are
  always active, so this never applies to them.
- The windowed change/slope/divergence/exhaustion statistics reset
  along with the anchor - a window straddling a reset boundary never
  mixes two anchor periods' values, at the cost of needing `window`
  fresh bars after every reset before those fields become non-None
  again (exposed honestly via `bars_since_anchor`, never silently
  partially computed).
- Exhaustion splits the SAME window in half (first-half slope vs.
  second-half slope) rather than requiring a second, larger buffer -
  one shared `window` parameter drives every windowed statistic in
  this module, deliberately, rather than introducing a second
  configurable size for a similar-but-distinct concept.
- strategy/features/delta.py's own architecture doc entry lists
  `delta_divergence_flag` as an intended per-bar output, but the
  shipped module never implemented it (confirmed absent from both
  calculate_delta() and its tests). This module's own
  `price_cvd_divergence_flag` is a different, higher-level concept
  (price vs. windowed CVD, not price vs. a single bar's delta) and did
  not need that field to exist - noted here for transparency, not
  fixed, since it is out of this phase's scope.
"""

from collections import deque
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal, NamedTuple

from strategy.features.delta import calculate_delta

Direction = Literal["BULLISH", "BEARISH", "NEUTRAL"]
DivergenceFlag = Literal["bullish_divergence", "bearish_divergence", "none"]
ExhaustionFlag = Literal["bullish_exhaustion", "bearish_exhaustion", "none"]

DEFAULT_WINDOW = 20

_UNSET = object()


@dataclass(frozen=True)
class CVDAnchor:
    """
    `session_name=None` means continuous/unanchored - accumulates from
    whenever this tracker started, never resets. Otherwise, resets
    whenever session_snapshot[session_name]["current"]["period_start"]
    changes (or pauses while ["current"] is None - see module Known
    Limitations).
    """

    name: str
    session_name: str | None = None


class _WindowPoint(NamedTuple):
    cvd: float
    high: float
    low: float


class _AnchorState:
    __slots__ = ("cvd", "bars_since_anchor", "bars_with_missing_data", "anchor_timestamp", "last_session_key", "window")

    def __init__(self, window_size: int):
        self.cvd = 0.0
        self.bars_since_anchor = 0
        self.bars_with_missing_data = 0
        self.anchor_timestamp: datetime | None = None
        self.last_session_key: Any = _UNSET
        # Holds exactly `window_size` points once ready - the standard
        # "N-period change" convention (N samples spanning N-1
        # intervals), not N+1 samples.
        self.window: deque[_WindowPoint] = deque(maxlen=window_size)


class CVDTracker:
    """
    Tracks Cumulative Volume Delta across a growing candle history,
    under one or more simultaneous anchor policies.

    One instance per backtest run (or per live session). Call sync()
    once per replay step. If any configured CVDAnchor is session-based,
    pass that same step's SessionBoundariesTracker snapshot and advance
    by exactly one new candle per call (see sync()'s docstring).
    """

    def __init__(
        self,
        anchors: list[CVDAnchor],
        timeframe: str = "unknown",
        window: int = DEFAULT_WINDOW,
        timestamp_key: str = "timestamp",
    ):
        if not anchors:
            raise ValueError("anchors cannot be empty")

        names = [a.name for a in anchors]
        if len(names) != len(set(names)):
            raise ValueError("anchor names must be unique")

        if window < 2:
            raise ValueError("window must be >= 2 (a rate-of-change needs at least two samples)")

        self.timestamp_key = timestamp_key
        self._timeframe = timeframe
        self._window = window
        self._anchors = list(anchors)
        self._requires_session_snapshot = any(a.session_name is not None for a in anchors)

        self._states: dict[str, _AnchorState] = {
            a.name: _AnchorState(window) for a in anchors
        }

        self._consumed = 0
        self._last_candle: dict[str, Any] | None = None

    def sync(
        self,
        candles: list[dict[str, Any]],
        session_snapshot: dict[str, Any] | None = None,
    ) -> None:
        if self._requires_session_snapshot and session_snapshot is None:
            raise ValueError(
                "session_snapshot is required - at least one configured "
                "CVDAnchor uses session_name"
            )

        if len(candles) < self._consumed:
            raise ValueError(
                "candles went backwards - CVDTracker does not support "
                "rewinding"
            )

        if self._requires_session_snapshot and len(candles) - self._consumed > 1:
            raise ValueError(
                "CVDTracker.sync() can only advance by one new candle "
                "per call while any anchor is session-based - "
                "session_snapshot is a point-in-time snapshot, not a "
                "historical record, so batching could silently skip an "
                "entire anchor period's reset"
            )

        if self._consumed > 0:
            checkpoint = candles[self._consumed - 1]

            if checkpoint != self._last_candle:
                raise ValueError(
                    "candles does not extend the history previously "
                    "seen by this CVDTracker"
                )

        for candle in candles[self._consumed:]:
            self._ingest(candle, session_snapshot)

        self._consumed = len(candles)

    def _ingest(
        self,
        candle: dict[str, Any],
        session_snapshot: dict[str, Any] | None,
    ) -> None:
        delta = calculate_delta(candle)["delta"]
        timestamp = candle[self.timestamp_key]

        for anchor in self._anchors:
            state = self._states[anchor.name]

            if anchor.session_name is None:
                session_key = "__continuous__"
            else:
                current = session_snapshot[anchor.session_name]["current"]

                if current is None:
                    continue  # off-session gap - paused, not reset

                session_key = current["period_start"]

            if session_key != state.last_session_key:
                state.cvd = 0.0
                state.bars_since_anchor = 0
                state.bars_with_missing_data = 0
                state.anchor_timestamp = timestamp
                state.window.clear()
                state.last_session_key = session_key

            if delta is None:
                state.bars_with_missing_data += 1
            else:
                state.cvd += delta

            state.bars_since_anchor += 1
            state.window.append(_WindowPoint(cvd=state.cvd, high=candle["high"], low=candle["low"]))

        self._last_candle = candle

    def snapshot(self) -> dict[str, Any]:
        return {
            anchor.name: self._anchor_snapshot(anchor)
            for anchor in self._anchors
        }

    def _anchor_snapshot(self, anchor: CVDAnchor) -> dict[str, Any]:
        state = self._states[anchor.name]

        change, slope, direction = self._windowed_change(state)
        divergence = self._divergence(state)
        exhaustion = self._exhaustion(state)

        return {
            "cvd": state.cvd,
            "cvd_direction": direction,
            "cvd_change_over_window": change,
            "cvd_slope": slope,
            "price_cvd_divergence_flag": divergence,
            "cvd_exhaustion_flag": exhaustion,
            "anchor_type": anchor.session_name if anchor.session_name else "continuous",
            "anchor_timestamp": state.anchor_timestamp,
            "bars_since_anchor": state.bars_since_anchor,
            "bars_with_missing_data": state.bars_with_missing_data,
            "timeframe": self._timeframe,
            "context": {},
        }

    def _windowed_change(
        self,
        state: _AnchorState,
    ) -> tuple[float | None, float | None, Direction | None]:
        if state.bars_since_anchor < self._window:
            return None, None, None

        change = state.window[-1].cvd - state.window[0].cvd
        slope = change / (self._window - 1)  # window samples span window-1 intervals

        if slope > 0:
            direction: Direction = "BULLISH"
        elif slope < 0:
            direction = "BEARISH"
        else:
            direction = "NEUTRAL"

        return change, slope, direction

    def _divergence(self, state: _AnchorState) -> DivergenceFlag:
        if state.bars_since_anchor < self._window:
            return "none"

        current = state.window[-1]
        prior = list(state.window)[:-1]

        price_new_high = current.high > max(p.high for p in prior)
        price_new_low = current.low < min(p.low for p in prior)
        cvd_new_high = current.cvd > max(p.cvd for p in prior)
        cvd_new_low = current.cvd < min(p.cvd for p in prior)

        if price_new_high and not cvd_new_high:
            return "bearish_divergence"

        if price_new_low and not cvd_new_low:
            return "bullish_divergence"

        return "none"

    def _exhaustion(self, state: _AnchorState) -> ExhaustionFlag:
        if state.bars_since_anchor < self._window:
            return "none"

        # points has exactly `window` samples (indices 0..window-1),
        # spanning window-1 intervals total. Splitting at `mid` needs
        # both halves to span at least one interval each.
        mid = self._window // 2
        second_half_intervals = (self._window - 1) - mid

        if mid < 1 or second_half_intervals < 1:
            return "none"

        points = list(state.window)
        current = points[-1]
        prior = points[:-1]

        cvd_new_high = current.cvd > max(p.cvd for p in prior)
        cvd_new_low = current.cvd < min(p.cvd for p in prior)

        if not cvd_new_high and not cvd_new_low:
            return "none"

        first_half_slope = (points[mid].cvd - points[0].cvd) / mid
        second_half_slope = (points[-1].cvd - points[mid].cvd) / second_half_intervals
        decelerating = abs(second_half_slope) < abs(first_half_slope)

        if not decelerating:
            return "none"

        if cvd_new_high:
            return "bearish_exhaustion"

        return "bullish_exhaustion"
