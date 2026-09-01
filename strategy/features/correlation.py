"""
Correlation Engine - Phase 1.10 of the Smart Money Core. Establishes a
generic, reusable intermarket-comparison primitive BEFORE SMT itself is
built, per explicit direction: SMT is one specialization of a broader
correlation framework, not a separate detector.

Purpose
-------
Institutional desks rarely evaluate one market in isolation - a move's
context (confirmed by a correlated asset, isolated, or an outright
intermarket decoupling) is often more informative than the move itself.
This module compares exactly two already-time-aligned candle streams
(a "primary" and a "reference" - e.g. BTCUSDT vs ETHUSDT, BTCUSDT vs a
BTC.D or TOTAL3 index series, BTCUSDT vs DXY, or the same symbol across
two exchanges) and exposes four independent, complementary comparisons:

- Statistical price correlation - the Pearson coefficient of RETURNS
  (not raw price levels) over a rolling window. Correlating raw price
  is a classic retail mistake: two assets that both trended upward for
  a year show spuriously high correlation on price alone even with
  completely unrelated day-to-day behavior. Returns avoid this.
- Relative Strength - the raw primary/reference price ratio and its own
  windowed rate of change, independent of whether the two are
  statistically correlated at all (a BTC/ETH or BTC/BTC.D ratio chart).
- Structural correlation/divergence - do the two streams' CONFIRMED
  swing pivots agree in direction? This is the level ICT's SMT actually
  operates at (structure, not a correlation coefficient) - "SMT" is
  simply this output, watched on a chosen correlated pair. Once this
  engine exists, SMT needs no new detection logic - it is a named
  configuration of this module, exactly like Kill Zones turned out to
  be SessionWindow instances and Mitigation Blocks turned out to be
  fields on Order Block.
- Lead/Lag - cross-correlation of returns at a small, bounded range of
  candidate bar offsets, to see whether one stream's moves tend to
  precede the other's.

The architecture doc's separately-numbered future "Relative Strength"
module is expected to be entirely subsumed by this engine's own ratio
output, not a distinct tracker - flagged here rather than built twice
later.

Architectural decisions (documented, not blocking - see Phase 1.10
research notes)
------------------------------------------------------------------
1. Pairwise, not N-way: every stated use case (BTC/ETH, BTC/TOTAL3,
   BTC/BTC.D, BTC/DXY, cross-exchange) is a pair. A caller wanting
   several simultaneous comparisons runs several instances of this
   tracker - the same multi-symbol-via-independent-instances pattern
   already established for CVD/SMT.
2. Structural comparison reuses strategy.market_structure.
   find_swing_pivots (the same genuine swing-pivot primitive already
   reused by Equal Highs/Lows and Order Blocks) - NOT
   detect_market_structure, which is a cruder 2-adjacent-candle
   heuristic tied to the frozen legacy strategy_engine.py scoring path
   and not representative of genuine confirmed structure the way this
   package's other modules are built.
3. Alignment: the two candle streams are expected to be index-aligned
   once they overlap (same cadence, same timestamps at the same
   index) - exactly what the Provider Layer already guarantees when
   both symbols are synced against the same replay clock. If the
   reference stream is shorter (has not started yet, or is temporarily
   behind - e.g. TOTAL3 not existing before a certain date), this
   module simply processes the overlapping prefix and reports
   insufficient-data via bars_since_start, rather than requiring a
   caller to pre-pad/align lengths externally. A per-index timestamp
   mismatch inside the overlapping range is treated as a real data-
   integrity error, not silently tolerated.

Inputs
------
Two already growing, already point-in-time-safe candle lists -
`primary_candles`, `reference_candles`. Each candle needs `timestamp`,
`close`, `high`, `low` - no symbol-specific fields, no exchange-
specific assumptions (Exchange Agnostic, Multi-Symbol by design; a
reference series can come from Binance, another exchange, or a
non-tradeable index like BTC.D/TOTAL3/DXY, and this module cannot tell
the difference).

Outputs (raw features only - see CorrelationTracker.snapshot)
-----------------------------------------------------------------
price_correlation (Pearson coefficient of returns, None until window
fills), relative_strength_ratio, relative_strength_change_over_window,
structural_agreement: both_bullish | both_bearish | diverging |
insufficient_data, structural_divergence_flag: bullish_divergence |
bearish_divergence | none (the CURRENT, sticky-until-the-next-pivot
value), structural_divergence_history (a bounded list of every past
DivergenceEvent - direction, timestamp, primary_price,
reference_price - not just the current flag; see Phase 1.11's SMT
research notes below), lead_lag_bars, lead_lag_correlation,
bars_since_start, window, max_lag, timeframe, context. No score, no
threshold, no BUY/SELL - structural_divergence_flag is named the same
way price_cvd_divergence_flag already is (by IMPLIED future direction,
not by which side is confirming).

SMT (Phase 1.11) - a documented configuration, not a new tracker
------------------------------------------------------------------
Researched explicitly as its own phase before writing any code, with
the architectural question asked directly: does SMT need a dedicated
tracker, or can it live entirely inside this engine? Conclusion:
"SMT" IS structural_divergence_flag/structural_divergence_history,
applied to a pair of symbols chosen because they are believed to share
risk exposure (BTC/ETH, BTC/TOTAL3, BTC/BTC.D, ETH/SOL, or any future
custom pair) - there is no additional computation SMT needs that this
engine does not already produce. `SMTPair` and `COMMON_SMT_PAIRS`
below are pure labeling/documentation - constructing a
CorrelationTracker for a named pair and reading its existing
structural outputs. No new class, no duplicated correlation/pivot/
swing/divergence logic. The only thing added because of this research
was structural_divergence_history itself - a general improvement to
this engine (every correlation consumer benefits, not SMT alone),
since every other market object in this package retains bounded
history rather than a single overwritable "current" field.

Option B (a thin SMT-specific consumer wrapper) was considered and
rejected: the only thing such a wrapper could add is renaming this
engine's existing fields, which is indirection without new capability
- the same reasoning that already collapsed Kill Zones into
SessionWindow instances and Mitigation Blocks into Order Block fields.

SMT is a discretionary, pattern-recognition heuristic, not a
statistically validated edge like price_correlation's rolling Pearson
coefficient - it fires only at discrete swing-pivot confirmations, is
sensitive to the fractal/window parameters chosen, and does not
account for the underlying correlation regime itself decaying (a pair
can structurally "diverge" for reasons unrelated to smart money - a
listing, a hack, an idiosyncratic event). It is necessary-but-not-
sufficient context, meant to sit alongside Liquidity Pools/CVD/Session
Boundaries, never read in isolation - consistent with why this engine
never scores or thresholds it.

Dependencies
------------
Reuses strategy.market_structure.find_swing_pivots directly - no pivot
detection logic is duplicated a fourth time. No dependency on any other
feature module's output (unlike Breaker Blocks/Liquidity Pools/CVD,
this module's two inputs are both raw OHLCV, not another tracker's
snapshot).

Replay Safety
-------------
Both inputs are ordinary growing candle histories (historical records),
not point-in-time snapshots - unlike Breaker Blocks/Liquidity Pools/
session-anchored CVD, there is no risk from batching multiple new
candles in one sync() call, and none is imposed. sync() rejects either
stream going backwards or diverging from what it has already consumed,
and rejects a timestamp mismatch between the two streams anywhere in
their overlapping range - the same integrity guards every tracker in
this codebase uses, applied to two streams instead of one.

Live Trading
------------
Pure function of two bounded recent buffers (returns/ratio window,
lead/lag window, and each stream's own bounded confirmed-pivot
history) - no full-history rescanning. sync() uses the same "full
growing candle list, only new candles processed" contract as every
other tracker here, applied per stream.

Computational Complexity
-------------------------
O(window + max_lag) per new candle pair: correlation and lead/lag are
recomputed from a small bounded buffer each step rather than
incrementally maintained via rolling sums - a deliberate simplicity-
over-micro-optimization tradeoff, since realistic window/max_lag sizes
(tens of bars) make this negligible, and it is the same "bounded
rescan of a small fixed window" pattern OrderBlockTracker's own
structure_lookback rescanning already established, not a new
complexity precedent. Structural pivot detection is O(1) per candle
per stream (fixed 3-candle window, delegated to find_swing_pivots),
matching Equal Highs/Lows exactly.

Known Limitations / Future Extension Points
--------------------------------------------
- Correlation/lead-lag use SIMPLE returns ((close[t]/close[t-1]) - 1),
  not log returns - simpler and adequate at typical crypto bar sizes;
  revisit only if evidence shows it matters.
- Lead/lag search is a bounded grid search over integer bar offsets,
  not a continuous-time estimate - deliberately simple and fully
  explainable (a caller can see exactly which offset and correlation
  value produced the result), not a black-box statistical fit.
- Structural divergence is evaluated only at the moment the PRIMARY
  stream confirms a new swing pivot, compared against the reference
  stream's current (however recently confirmed) pivot trend - the two
  streams are not required to pivot on the same candle, since real
  price action rarely aligns that precisely.
"""

from collections import deque
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal, NamedTuple

from strategy.market_structure import find_swing_pivots

StructuralAgreement = Literal["both_bullish", "both_bearish", "diverging", "insufficient_data"]
DivergenceFlag = Literal["bullish_divergence", "bearish_divergence", "none"]

DEFAULT_WINDOW = 20
DEFAULT_MAX_LAG = 10
DEFAULT_MAX_TRACKED_PIVOTS = 50
DEFAULT_MAX_TRACKED_DIVERGENCE_EVENTS = 200


@dataclass(frozen=True)
class SMTPair:
    """
    Pure labeling/documentation, not a new detector - constructing a
    CorrelationTracker for these two symbols and reading its existing
    structural_divergence_flag/structural_divergence_history IS the
    SMT check (see this module's own "SMT" docstring section above).
    `primary_symbol`/`reference_symbol` are the names a caller uses to
    fetch/attach each side's candles via the existing Provider Layer -
    this dataclass carries no candle data itself.
    """

    name: str
    primary_symbol: str
    reference_symbol: str


COMMON_SMT_PAIRS: list[SMTPair] = [
    SMTPair(name="btc_eth", primary_symbol="BTCUSDT", reference_symbol="ETHUSDT"),
    SMTPair(name="btc_total3", primary_symbol="BTCUSDT", reference_symbol="TOTAL3"),
    SMTPair(name="btc_dominance", primary_symbol="BTCUSDT", reference_symbol="BTC.D"),
    SMTPair(name="eth_sol", primary_symbol="ETHUSDT", reference_symbol="SOLUSDT"),
]


class _PairPoint(NamedTuple):
    primary_return: float
    reference_return: float
    ratio: float


class DivergenceEvent(NamedTuple):
    """
    One resolved structural divergence, retained as history - not just
    the current sticky flag. Every other market object in this package
    (Order Blocks' mitigated, Liquidity Pools' swept, FVG's filled)
    keeps bounded history rather than a single overwritable field; this
    was the one gap found while researching SMT (Phase 1.11) - a
    general Correlation Engine improvement, not SMT-specific code.
    """

    direction: DivergenceFlag
    timestamp: datetime
    primary_price: float
    reference_price: float


class _StreamStructuralState:
    """
    Tracks one stream's own confirmed swing pivots - mirrors Equal
    Highs/Lows' exact bookkeeping (a fixed 3-candle window feeding
    find_swing_pivots, plus a bounded history of confirmed pivot
    prices), but this module only needs trend direction, not
    clustering, so it keeps just the prices.
    """

    __slots__ = ("recent_candles", "pivot_highs", "pivot_lows")

    def __init__(self, max_tracked_pivots: int):
        self.recent_candles: list[dict[str, Any]] = []
        self.pivot_highs: deque[float] = deque(maxlen=max_tracked_pivots)
        self.pivot_lows: deque[float] = deque(maxlen=max_tracked_pivots)

    def ingest(self, candle: dict[str, Any]) -> tuple[bool, bool]:
        """Returns (new_high_pivot_confirmed, new_low_pivot_confirmed)."""

        self.recent_candles.append(candle)
        if len(self.recent_candles) > 3:
            self.recent_candles.pop(0)

        if len(self.recent_candles) < 3:
            return False, False

        highs = [c["high"] for c in self.recent_candles]
        lows = [c["low"] for c in self.recent_candles]
        swing_highs, swing_lows = find_swing_pivots(highs, lows)

        new_high = bool(swing_highs)
        new_low = bool(swing_lows)

        if new_high:
            self.pivot_highs.append(highs[1])

        if new_low:
            self.pivot_lows.append(lows[1])

        return new_high, new_low

    def trend(self) -> tuple[bool | None, bool | None]:
        """(higher_high, higher_low) vs each type's own prior pivot -
        None for either if fewer than 2 pivots of that type exist yet."""

        higher_high = None
        if len(self.pivot_highs) >= 2:
            higher_high = self.pivot_highs[-1] > self.pivot_highs[-2]

        higher_low = None
        if len(self.pivot_lows) >= 2:
            higher_low = self.pivot_lows[-1] > self.pivot_lows[-2]

        return higher_high, higher_low


class CorrelationTracker:
    """
    Compares a primary and a reference candle stream across
    statistical, relative-strength, structural, and lead/lag
    dimensions.

    One instance per pair per backtest run (or per live session). Call
    sync() once per replay step with both streams' full candle history
    seen so far.
    """

    def __init__(
        self,
        timeframe: str = "unknown",
        window: int = DEFAULT_WINDOW,
        max_lag: int = DEFAULT_MAX_LAG,
        max_tracked_pivots: int = DEFAULT_MAX_TRACKED_PIVOTS,
        max_tracked_divergence_events: int = DEFAULT_MAX_TRACKED_DIVERGENCE_EVENTS,
        timestamp_key: str = "timestamp",
    ):
        if window < 2:
            raise ValueError("window must be >= 2 (a correlation needs at least two samples)")

        if max_lag < 0:
            raise ValueError("max_lag must be >= 0")

        self.timestamp_key = timestamp_key
        self._timeframe = timeframe
        self._window = window
        self._max_lag = max_lag

        self._consumed = 0
        self._last_primary_candle: dict[str, Any] | None = None
        self._last_reference_candle: dict[str, Any] | None = None
        self._last_primary_close: float | None = None
        self._last_reference_close: float | None = None

        self._buffer: deque[_PairPoint] = deque(maxlen=window + max_lag)
        self._bars_since_start = 0

        self._primary_structure = _StreamStructuralState(max_tracked_pivots)
        self._reference_structure = _StreamStructuralState(max_tracked_pivots)

        self._divergence_flag: DivergenceFlag = "none"
        self._divergence_history: deque[DivergenceEvent] = deque(maxlen=max_tracked_divergence_events)

    def sync(
        self,
        primary_candles: list[dict[str, Any]],
        reference_candles: list[dict[str, Any]],
    ) -> None:
        common_length = min(len(primary_candles), len(reference_candles))

        if common_length < self._consumed:
            raise ValueError(
                "candles went backwards - CorrelationTracker does not "
                "support rewinding"
            )

        if self._consumed > 0:
            primary_checkpoint = primary_candles[self._consumed - 1]
            reference_checkpoint = reference_candles[self._consumed - 1]

            if (
                primary_checkpoint != self._last_primary_candle
                or reference_checkpoint != self._last_reference_candle
            ):
                raise ValueError(
                    "candles does not extend the history previously "
                    "seen by this CorrelationTracker"
                )

        for i in range(self._consumed, common_length):
            primary_candle = primary_candles[i]
            reference_candle = reference_candles[i]

            if primary_candle[self.timestamp_key] != reference_candle[self.timestamp_key]:
                raise ValueError(
                    f"primary and reference candles diverge at index {i} - "
                    "CorrelationTracker requires index-aligned, same-"
                    "timestamp streams once they overlap"
                )

            self._ingest(primary_candle, reference_candle)

        self._consumed = common_length

    def _ingest(
        self,
        primary_candle: dict[str, Any],
        reference_candle: dict[str, Any],
    ) -> None:
        self._bars_since_start += 1

        primary_close = primary_candle["close"]
        reference_close = reference_candle["close"]

        if self._last_primary_close is not None and self._last_reference_close is not None:
            primary_return = (primary_close / self._last_primary_close) - 1
            reference_return = (reference_close / self._last_reference_close) - 1
            ratio = primary_close / reference_close if reference_close > 0 else None

            if ratio is not None:
                self._buffer.append(
                    _PairPoint(primary_return=primary_return, reference_return=reference_return, ratio=ratio)
                )

        new_primary_high, new_primary_low = self._primary_structure.ingest(primary_candle)
        self._reference_structure.ingest(reference_candle)

        if new_primary_high or new_primary_low:
            self._update_divergence(new_primary_high, new_primary_low, primary_candle, reference_candle)

        self._last_primary_close = primary_close
        self._last_reference_close = reference_close
        self._last_primary_candle = primary_candle
        self._last_reference_candle = reference_candle

    def _update_divergence(
        self,
        new_primary_high: bool,
        new_primary_low: bool,
        primary_candle: dict[str, Any],
        reference_candle: dict[str, Any],
    ) -> None:
        primary_higher_high, primary_higher_low = self._primary_structure.trend()
        reference_higher_high, reference_higher_low = self._reference_structure.trend()

        if new_primary_high and primary_higher_high is True and reference_higher_high is False:
            self._divergence_flag = "bearish_divergence"
        elif new_primary_low and primary_higher_low is False and reference_higher_low is True:
            self._divergence_flag = "bullish_divergence"
        else:
            self._divergence_flag = "none"
            return

        self._divergence_history.append(
            DivergenceEvent(
                direction=self._divergence_flag,
                timestamp=primary_candle[self.timestamp_key],
                primary_price=primary_candle["close"],
                reference_price=reference_candle["close"],
            )
        )

    def snapshot(self) -> dict[str, Any]:
        correlation = self._correlation(lag=0)
        ratio_pct_change = self._ratio_change()
        lead_lag_bars, lead_lag_correlation = self._lead_lag()

        current_ratio = self._buffer[-1].ratio if self._buffer else None

        return {
            "price_correlation": correlation,
            "relative_strength_ratio": current_ratio,
            "relative_strength_change_over_window": ratio_pct_change,
            "structural_agreement": self._structural_agreement(),
            "structural_divergence_flag": self._divergence_flag,
            "structural_divergence_history": [
                event._asdict() for event in self._divergence_history
            ],
            "lead_lag_bars": lead_lag_bars,
            "lead_lag_correlation": lead_lag_correlation,
            "bars_since_start": self._bars_since_start,
            "window": self._window,
            "max_lag": self._max_lag,
            "timeframe": self._timeframe,
            "context": {},
        }

    def _structural_agreement(self) -> StructuralAgreement:
        p_high, p_low = self._primary_structure.trend()
        r_high, r_low = self._reference_structure.trend()

        if p_high is None or p_low is None or r_high is None or r_low is None:
            return "insufficient_data"

        if p_high and p_low and r_high and r_low:
            return "both_bullish"

        if not p_high and not p_low and not r_high and not r_low:
            return "both_bearish"

        return "diverging"

    def _correlation(self, lag: int) -> float | None:
        if len(self._buffer) < self._window:
            return None

        points = list(self._buffer)[-self._window:]
        return _pearson(
            [p.primary_return for p in points],
            [p.reference_return for p in points],
        )

    def _ratio_change(self) -> float | None:
        """
        Percentage change, not raw point change: a raw change of 5 in
        a ~600 BTC/DXY ratio means something wildly different than a
        raw change of 5 in a ~20 BTC/ETH ratio - percentage is the
        cross-pair-comparable convention, matching why relative
        strength is expressed as a ratio (or its % change) rather than
        a price difference in the first place. The current raw ratio
        is already exposed separately as relative_strength_ratio, so a
        caller who wants the raw point change can derive it from that.
        """

        if len(self._buffer) < self._window:
            return None

        points = list(self._buffer)[-self._window:]

        if not points[0].ratio:
            return None

        return (points[-1].ratio - points[0].ratio) / points[0].ratio

    def _lead_lag(self) -> tuple[int | None, float | None]:
        if len(self._buffer) < self._window + self._max_lag:
            return None, None

        points = list(self._buffer)
        primary = [p.primary_return for p in points]
        reference = [p.reference_return for p in points]

        best_lag = 0
        best_corr = 0.0

        for lag in range(-self._max_lag, self._max_lag + 1):
            corr = _lagged_pearson(primary, reference, lag, self._window)

            if corr is not None and abs(corr) > abs(best_corr):
                best_lag = lag
                best_corr = corr

        return best_lag, best_corr


def _pearson(xs: list[float], ys: list[float]) -> float | None:
    n = len(xs)

    if n < 2:
        return None

    mean_x = sum(xs) / n
    mean_y = sum(ys) / n

    cov = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
    var_x = sum((x - mean_x) ** 2 for x in xs)
    var_y = sum((y - mean_y) ** 2 for y in ys)

    denominator = (var_x * var_y) ** 0.5

    if denominator == 0:
        return None

    return cov / denominator


def _lagged_pearson(
    primary: list[float],
    reference: list[float],
    lag: int,
    window: int,
) -> float | None:
    """
    Positive lag: primary LEADS reference by `lag` bars - compares
    primary[t] against reference[t + lag] (primary's return at time t
    resembling reference's return `lag` bars later means primary's
    pattern shows up in reference afterward, i.e. primary leads).
    Negative lag: reference leads primary by |lag| bars. Always
    compares the most recent `window` aligned samples available for
    this lag.
    """

    n = len(primary)

    if lag >= 0:
        primary_slice = primary[: n - lag] if lag > 0 else primary
        reference_slice = reference[lag:]
    else:
        k = -lag
        primary_slice = primary[k:]
        reference_slice = reference[: n - k]

    if len(primary_slice) < window:
        return None

    return _pearson(primary_slice[-window:], reference_slice[-window:])
