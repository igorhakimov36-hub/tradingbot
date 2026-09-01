"""
Delta - Phase 1.1 of the Smart Money Core (see
docs/smart_money_architecture.md, "Order Flow > 7. Delta").

Purpose
-------
Aggressive buy vs. sell volume within a single closed bar - a directional
proxy total volume alone cannot provide. Uses Binance's own
`taker_buy_base_asset_volume` field, already present on every kline
(REST, historical, and live stream alike). No trade-level infrastructure,
no WebSocket dependency, no Provider Layer changes: Delta is a pure
function of fields already flowing through the existing candle pipeline
once the loader/downloader preserve them (see
data/historical_loader.py, exchange/download_historical_klines.py).

Inputs
------
A single candle dict with "volume" and (optionally) "taker_buy_volume".
`taker_buy_volume` is intentionally optional - not every historical
source provides it - and its absence must never be silently treated as
zero aggression. Missing data returns None fields, never a fabricated 0.

Outputs (raw features only - see calculate_delta / DeltaTracker.snapshot)
--------------------------------------------------------------------
delta, delta_pct, delta_direction, delta_strength, cumulative_delta,
bars_accumulated, bars_with_missing_data. No score, no threshold, no
BUY/SELL.

The per-bar fields (delta/delta_pct/delta_direction/delta_strength) on
DeltaTracker.snapshot() describe only the MOST RECENT bar - added in
Phase 2.1 for the Market Intelligence Snapshot Builder, which reads
only tracker snapshot() outputs and must never call calculate_delta()
directly itself. Purely additive - cumulative_delta/bars_accumulated/
bars_with_missing_data are unchanged.

Dependencies
------------
None beyond the candle's own fields. Consumed by: the future CVD module
(a direct running sum of this module's per-bar delta), and potentially by
market_structure.evaluate_bos_quality as a future enrichment (not wired
in now - out of Phase 1.1 scope).

Replay Safety
-------------
calculate_delta() is computed entirely from fields already present on a
CLOSED candle - there is nothing to look ahead into. DeltaTracker only
ever advances forward: sync() rejects a candle history that goes
backwards or diverges from what it has already consumed (same guard
TimeframeManager already uses), so it can never be fed a rewritten past.

Live Trading
------------
Binance's live kline stream carries the same taker_buy_base_asset_volume
field as the REST/historical endpoints, so calculate_delta() runs
identically on a live-closed candle. DeltaTracker.sync() accepts the same
"full growing candle list, only new candles are processed" contract
BacktestRunner already uses for TimeframeManager, so a live orchestrator
that maintains its own growing candle buffer needs no special-casing.

Computational Complexity
-------------------------
calculate_delta(): O(1) - a handful of arithmetic operations on fields
already available. DeltaTracker.sync(): O(new candles) amortized, thanks
to the same consumed-pointer pattern already used by TimeframeManager -
never O(total history) regardless of how many years have been replayed.

Known Limitations / Future Extension Points
--------------------------------------------
- `cumulative_delta` accumulates from whenever this tracker started
  observing data (backtest window start, or live-process start) - it is
  NOT anchored to a trading session (Asian/London/NY). True session
  anchoring depends on the Session Boundaries primitive, deliberately
  deferred out of Phase 0 and not built here. When it exists, a
  session-aware reset can be layered on without changing this module's
  output field names.
- taker_buy_base_asset_volume is itself an exchange-computed aggregate,
  not a true per-trade aggressor flag. If/when Trade-Level Infrastructure
  is ever built, a tick-precise Delta could replace this approximation
  without changing the output contract defined here - callers should
  never need to change because the computation method improved.
"""

from typing import Any, Literal

DeltaDirection = Literal["BULLISH", "BEARISH", "NEUTRAL"]


def calculate_delta(candle: dict[str, Any]) -> dict[str, Any]:
    """
    Pure, stateless per-candle Delta computation.

    Returns a dict with keys: delta, delta_pct, delta_direction,
    delta_strength. Every field is None if `taker_buy_volume` is
    missing from `candle` - never a fabricated zero.
    """

    volume = candle.get("volume")
    taker_buy_volume = candle.get("taker_buy_volume")

    if volume is None or taker_buy_volume is None:
        return {
            "delta": None,
            "delta_pct": None,
            "delta_direction": None,
            "delta_strength": None,
        }

    taker_sell_volume = volume - taker_buy_volume
    delta = taker_buy_volume - taker_sell_volume

    if volume > 0:
        delta_pct = (delta / volume) * 100
    else:
        # No volume traded at all - no aggression in either direction,
        # not an undefined ratio.
        delta_pct = 0.0

    if delta > 0:
        direction: DeltaDirection = "BULLISH"
    elif delta < 0:
        direction = "BEARISH"
    else:
        direction = "NEUTRAL"

    return {
        "delta": delta,
        "delta_pct": delta_pct,
        "delta_direction": direction,
        "delta_strength": abs(delta_pct),
    }


class DeltaTracker:
    """
    Incrementally accumulates Delta across a growing candle history.

    One instance is meant to live for exactly one backtest run (or one
    live session), matching the same lifecycle convention already used
    by TimeframeManager. Call sync() once per replay step with the full
    candle history seen so far; only candles added since the last call
    are processed.
    """

    def __init__(self, timeframe: str = "unknown", timestamp_key: str = "timestamp"):
        """
        `timeframe` is a caller-supplied label (e.g. "1m", "15m"),
        preserved only for context on the snapshot this tracker
        produces - never inferred, never used in the accumulation
        itself, matching the same timeframe-agnostic convention as
        FairValueGapTracker.
        """

        self.timestamp_key = timestamp_key
        self._timeframe = timeframe

        self._consumed = 0
        self._last_candle: dict[str, Any] | None = None

        self._cumulative_delta = 0.0
        self._bars_accumulated = 0
        self._bars_with_missing_data = 0
        self._last_features: dict[str, Any] = calculate_delta({})

    def sync(self, candles: list[dict[str, Any]]) -> None:
        if len(candles) < self._consumed:
            raise ValueError(
                "candles went backwards - DeltaTracker does not "
                "support rewinding"
            )

        if self._consumed > 0:
            checkpoint = candles[self._consumed - 1]

            if checkpoint != self._last_candle:
                raise ValueError(
                    "candles does not extend the history previously "
                    "seen by this DeltaTracker"
                )

        for candle in candles[self._consumed:]:
            self._ingest(candle)

        self._consumed = len(candles)

    def _ingest(self, candle: dict[str, Any]) -> None:
        features = calculate_delta(candle)

        if features["delta"] is None:
            self._bars_with_missing_data += 1
        else:
            self._cumulative_delta += features["delta"]

        self._bars_accumulated += 1
        self._last_features = features
        self._last_candle = candle

    def snapshot(self) -> dict[str, Any]:
        """
        cumulative_delta sums only the bars where Delta was computable -
        bars_with_missing_data tells you how many were skipped, so a
        consumer can judge completeness rather than being handed a
        silently-approximate number.

        delta/delta_pct/delta_direction/delta_strength describe only
        the MOST RECENT bar - the same single-bar reading
        calculate_delta() would give directly, exposed here so a
        consumer (the Market Intelligence Snapshot Builder, Phase 2.1)
        never needs to call calculate_delta() itself and can read this
        tracker's snapshot() like every other module's. All four are
        None before the first candle is processed, or if the most
        recent candle was itself missing taker_buy_volume - never a
        fabricated value.
        """

        return {
            "timeframe": self._timeframe,
            "cumulative_delta": self._cumulative_delta,
            "bars_accumulated": self._bars_accumulated,
            "bars_with_missing_data": self._bars_with_missing_data,
            "delta": self._last_features["delta"],
            "delta_pct": self._last_features["delta_pct"],
            "delta_direction": self._last_features["delta_direction"],
            "delta_strength": self._last_features["delta_strength"],
        }
