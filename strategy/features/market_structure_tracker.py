"""
Market Structure Tracker - not a new Phase 1 module in the sense of new
detection logic, but a gap found while designing the Strategy Engine V2
Snapshot Builder (Phase 2.1): every other Market Intelligence family
(Zones, Levels, Order Flow, Intermarket) is backed by a persistent
tracker with its own sync()/snapshot() - Market Structure was not. It
only existed as the stateless helper functions in
strategy/market_structure.py (find_swing_pivots, detect_bos,
detect_choch, get_last_swing_levels, detect_market_structure), called
fresh every bar by the frozen strategy_engine.py with no persistent
object of its own.

Purpose
-------
Exposes BOS/CHOCH/swing-level state through the exact same
sync()/snapshot() interface as every other tracker in this package -
so the Snapshot Builder can read it like any other Market Intelligence
module instead of recomputing structure itself (which would have made
the Snapshot Builder do feature calculation, explicitly disallowed for
that layer).

This module introduces ZERO new detection logic. It wraps
strategy.market_structure's existing functions with the EXACT same
wiring strategy_engine.py already uses - previous_swing_high/low and
market_structure computed from all candles except the current one,
BOS/CHOCH evaluated against the current candle's close - so this
tracker's output is provably identical to what the frozen pipeline has
always computed for the same candle history, just persisted and
exposed as its own object.

Deliberately not addressed here: `detect_market_structure`'s
market_structure regime is a crude two-adjacent-candle heuristic
(flagged as an obsolete concern in the Phase 2 architectural review,
docs/strategy_engine_v2_architecture.md) - it is still reused here
UNCHANGED, because `detect_choch` takes it as a required input in the
existing wiring, and replacing it with something better would be new
detection logic, which this module is explicitly not meant to
introduce. Any improvement to regime detection is a Strategy Engine V2
/ Setup Evaluation concern, not this wrapper's.

Inputs
------
OHLCV only, any single timeframe - deliberately timeframe-agnostic,
same convention as every other module in this package.

Outputs (raw features only - see MarketStructureTracker.snapshot)
-------------------------------------------------------------------
`market_structure` (BULLISH | BEARISH | RANGE | UNKNOWN - the existing
detect_market_structure reading), `last_swing_high`, `last_swing_low`
(from get_last_swing_levels), `bos` (NO_BOS | BULLISH_BOS |
BEARISH_BOS, the CURRENT bar's raw reading - see Replay Safety), `choch`
(NO_CHOCH | BULLISH_CHOCH | BEARISH_CHOCH, current bar's raw reading),
timeframe, context. No score, no threshold, no BUY/SELL.

`bos`/`choch` are level-based readings, not edge-triggered events -
`detect_bos` returns BULLISH_BOS on every bar where close is still
above the broken swing high, not just the bar where the break first
occurred (this is the same semantics strategy_engine.py has always
relied on). This tracker does not layer an edge-detection state machine
on top, since that would be new logic beyond wrapping - OrderBlockTracker
already demonstrates the edge-triggering PATTERN for a consumer that
needs it (comparing consecutive raw BOS readings itself), and any future
Strategy Engine V2 setup that wants "did BOS just happen" rather than
"is BOS currently true" should do the same comparison itself, not have
it hidden inside this wrapper.

Dependencies
------------
Hard dependency on strategy.market_structure's existing functions - no
detection logic is duplicated. Consumed by (not built yet): the Market
Intelligence Snapshot Builder (Strategy Engine V2 Phase 2.1).

Replay Safety
-------------
Every value is computed fresh from a bounded recent candle window
(structure_lookback, matching strategy_engine.py's own STRUCTURE_LOOKBACK
convention) - no lookahead, since detect_bos/detect_choch are evaluated
against the current candle's own already-known close. sync() rejects a
candle history that goes backwards or diverges from what it has already
consumed (same guard every tracker in this codebase uses).

Live Trading
------------
Pure function of a bounded recent window of closed candles - identical
shape to OrderBlockTracker's own structure_lookback rescanning. sync()
uses the same "full growing candle list, only new candles processed"
contract as every other tracker here.

Computational Complexity
-------------------------
O(structure_lookback) per new candle - matching strategy_engine.py's
existing, already-validated approach exactly (bounded rescanning, not a
full unbounded history scan).

Known Limitations / Future Extension Points
--------------------------------------------
- `market_structure`'s crude two-candle heuristic and `bos`/`choch`'s
  level-based (not edge-triggered) semantics are both carried forward
  UNCHANGED from the existing frozen pipeline - see Purpose above for
  why neither is improved here.
- No mitigation/touch/lifecycle tracking of any kind - this tracker
  exposes point-in-time structural facts only, unlike the zone-shaped
  modules (Order Blocks, FVG, etc.) built on top of the same primitives.

Structural Break Event (Module Logic Correction 1 - additive only)
--------------------------------------------------------------------
`bos`/`choch` above are deliberately persistent, level-based readings
(Purpose section) - by design they say "close is CURRENTLY beyond the
last broken level," not "a break just happened." Some future consumers
(Order Block, in a later, separately-approved correction) need the
latter: a causal, one-shot identity for each distinct confirmed
structural level actually being broken, so that a sustained trend which
never returns to NO_BOS can still be recognized as breaking several
different levels in sequence, not just the first one.

`structural_break_event` is an ADDITIVE snapshot field carrying a
`StructuralBreakEvent | None` - present only on the bar where a
previously-unconsumed swing/pivot is first closed beyond, `None` on
every other bar (edge-triggered, not persistent - the opposite shape
from `bos`/`choch` on purpose, so a consumer can never mistake a stale
value for a fresh one). It does not replace, does not affect the
computation of, and cannot be derived by mutating `bos`/`choch` - they
remain computed by the exact same unchanged calls as before.

Identity: (direction, pivot candle's own timestamp) - not the pivot's
price alone, since `find_swing_pivots` already returns the pivot's
local index within the scanned window, letting this tracker recover
the exact originating candle (and hence its timestamp) without any
change to strategy/market_structure.py. A pivot can fire at most one
event per direction, tracked via a consumed-pivot set that is pruned to
exactly the pivots still visible in `_recent_candles` every bar -
bounding its size to the same O(structure_lookback) this tracker
already uses everywhere else, since a pivot that has scrolled out of
the window can never be reported as "last swing high/low" again.

Crossing definition: strict close-based crossing against the level,
identical to `detect_bos`'s own existing convention (`close > level`,
not merely a wick beyond it, and not `close >= level`) - chosen for
consistency with the existing persistent BOS definition, not for any
performance reason. A pivot that is *first confirmed* on a bar where
close is already beyond it fires immediately on that bar (this is when
the break first becomes knowable - never backdated to the pivot's own,
earlier candle). The alternative of requiring an edge relative to the
previous bar's close (i.e. previous close below the level, current
close above it) was considered and rejected: it would permanently miss
a level that was already-broken by the time it became the tracked
"last" pivot, violating "every distinct broken level produces exactly
one event." A gap across the level is handled identically to a smooth
crossing, since only the current bar's close is ever compared - no
separate gap-detection logic exists or is needed.
"""

from dataclasses import dataclass
from typing import Any, Literal

from strategy.market_structure import (
    detect_bos,
    detect_choch,
    detect_market_structure,
    find_swing_pivots,
    get_last_swing_levels,
)

MarketStructureRegime = Literal["BULLISH", "BEARISH", "RANGE", "UNKNOWN"]
BosReading = Literal["NO_BOS", "BULLISH_BOS", "BEARISH_BOS"]
ChochReading = Literal["NO_CHOCH", "BULLISH_CHOCH", "BEARISH_CHOCH"]
BreakDirection = Literal["bullish", "bearish"]

DEFAULT_STRUCTURE_LOOKBACK = 500  # matches strategy_engine.py's STRUCTURE_LOOKBACK


@dataclass(frozen=True)
class StructuralBreakEvent:
    """
    Additive, one-shot identity for "this specific, already-confirmed
    structural level was broken on this candle" - independent of, and
    never a replacement for, the persistent bos/choch readings. See
    the module docstring's "Structural Break Event" section.
    """

    direction: BreakDirection
    level: float
    pivot_timestamp: Any
    confirmed_at: Any
    confirming_close: float
    event_id: str


class MarketStructureTracker:
    """
    Persists BOS/CHOCH/swing-level state across a growing candle
    history, using the exact same functions and wiring
    strategy_engine.py already relies on.

    One instance per backtest run (or per live session). Call sync()
    once per replay step with the full candle history seen so far.
    """

    def __init__(
        self,
        timeframe: str = "unknown",
        structure_lookback: int = DEFAULT_STRUCTURE_LOOKBACK,
        timestamp_key: str = "timestamp",
    ):
        self.timestamp_key = timestamp_key
        self._timeframe = timeframe
        self._structure_lookback = structure_lookback

        self._consumed = 0
        self._last_candle: dict[str, Any] | None = None
        self._recent_candles: list[dict[str, Any]] = []

        self._market_structure: MarketStructureRegime = "UNKNOWN"
        self._last_swing_high: float | None = None
        self._last_swing_low: float | None = None
        self._bos: BosReading = "NO_BOS"
        self._choch: ChochReading = "NO_CHOCH"

        self._consumed_break_pivots: set[tuple[BreakDirection, Any]] = set()
        self._latest_structural_break_event: StructuralBreakEvent | None = None

    def sync(self, candles: list[dict[str, Any]]) -> None:
        if len(candles) < self._consumed:
            raise ValueError(
                "candles went backwards - MarketStructureTracker does "
                "not support rewinding"
            )

        if self._consumed > 0:
            checkpoint = candles[self._consumed - 1]

            if checkpoint != self._last_candle:
                raise ValueError(
                    "candles does not extend the history previously "
                    "seen by this MarketStructureTracker"
                )

        for candle in candles[self._consumed:]:
            self._ingest(candle)

        self._consumed = len(candles)

    def _ingest(self, candle: dict[str, Any]) -> None:
        self._recent_candles.append(candle)
        if len(self._recent_candles) > self._structure_lookback:
            self._recent_candles.pop(0)

        highs = [c["high"] for c in self._recent_candles]
        lows = [c["low"] for c in self._recent_candles]

        # Exactly strategy_engine.py's own wiring: previous swing
        # levels and the market structure regime are read from every
        # candle EXCEPT the current one, then BOS/CHOCH are evaluated
        # against the current candle's own already-known close.
        previous_swing_high, previous_swing_low = get_last_swing_levels(
            highs[:-1],
            lows[:-1],
        )

        self._market_structure = detect_market_structure(
            highs[:-1],
            lows[:-1],
        )
        self._last_swing_high = previous_swing_high
        self._last_swing_low = previous_swing_low

        self._bos = detect_bos(
            candle["close"],
            previous_swing_high,
            previous_swing_low,
        )

        self._choch = detect_choch(
            self._market_structure,
            candle["close"],
            previous_swing_high,
            previous_swing_low,
        )

        # Additive only: none of the fields computed above are read or
        # affected by this block - see module docstring "Structural
        # Break Event". Recomputes swing pivots (already computed
        # above, inside get_last_swing_levels) a second time via
        # find_swing_pivots purely to recover the pivot's own index,
        # which get_last_swing_levels discards - this keeps every
        # existing call/return path completely untouched.
        prior_candles = self._recent_candles[:-1]
        swing_highs, swing_lows = find_swing_pivots(highs[:-1], lows[:-1])

        new_event: StructuralBreakEvent | None = None
        if swing_highs and candle["close"] > swing_highs[-1][1]:
            pivot_index, pivot_price = swing_highs[-1]
            new_event = self._maybe_create_break_event(
                direction="bullish",
                pivot_candle=prior_candles[pivot_index],
                pivot_price=pivot_price,
                candle=candle,
            )
        elif swing_lows and candle["close"] < swing_lows[-1][1]:
            pivot_index, pivot_price = swing_lows[-1]
            new_event = self._maybe_create_break_event(
                direction="bearish",
                pivot_candle=prior_candles[pivot_index],
                pivot_price=pivot_price,
                candle=candle,
            )

        self._latest_structural_break_event = new_event
        self._prune_consumed_break_pivots()

        self._last_candle = candle

    def _maybe_create_break_event(
        self,
        direction: BreakDirection,
        pivot_candle: dict[str, Any],
        pivot_price: float,
        candle: dict[str, Any],
    ) -> StructuralBreakEvent | None:
        pivot_timestamp = pivot_candle[self.timestamp_key]
        pivot_key = (direction, pivot_timestamp)

        if pivot_key in self._consumed_break_pivots:
            return None

        self._consumed_break_pivots.add(pivot_key)

        event_id = f"{self._timeframe}:{direction}:{pivot_timestamp!r}"

        return StructuralBreakEvent(
            direction=direction,
            level=pivot_price,
            pivot_timestamp=pivot_timestamp,
            confirmed_at=candle[self.timestamp_key],
            confirming_close=candle["close"],
            event_id=event_id,
        )

    def _prune_consumed_break_pivots(self) -> None:
        # A pivot that has scrolled out of _recent_candles can never
        # again be reported as the "last" swing high/low (find_swing_pivots
        # only ever scans the current window) - so its consumption
        # marker can be safely forgotten, bounding this set to the same
        # O(structure_lookback) as everything else in this tracker.
        window_timestamps = {c[self.timestamp_key] for c in self._recent_candles}
        self._consumed_break_pivots = {
            (direction, timestamp)
            for direction, timestamp in self._consumed_break_pivots
            if timestamp in window_timestamps
        }

    def snapshot(self) -> dict[str, Any]:
        return {
            "market_structure": self._market_structure,
            "last_swing_high": self._last_swing_high,
            "last_swing_low": self._last_swing_low,
            "bos": self._bos,
            "choch": self._choch,
            "timeframe": self._timeframe,
            "context": {},
            "structural_break_event": self._latest_structural_break_event,
        }
