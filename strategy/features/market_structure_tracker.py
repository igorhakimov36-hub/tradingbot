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
"""

from typing import Any, Literal

from strategy.market_structure import detect_bos, detect_choch, detect_market_structure, get_last_swing_levels

MarketStructureRegime = Literal["BULLISH", "BEARISH", "RANGE", "UNKNOWN"]
BosReading = Literal["NO_BOS", "BULLISH_BOS", "BEARISH_BOS"]
ChochReading = Literal["NO_CHOCH", "BULLISH_CHOCH", "BEARISH_CHOCH"]

DEFAULT_STRUCTURE_LOOKBACK = 500  # matches strategy_engine.py's STRUCTURE_LOOKBACK


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

        self._last_candle = candle

    def snapshot(self) -> dict[str, Any]:
        return {
            "market_structure": self._market_structure,
            "last_swing_high": self._last_swing_high,
            "last_swing_low": self._last_swing_low,
            "bos": self._bos,
            "choch": self._choch,
            "timeframe": self._timeframe,
            "context": {},
        }
