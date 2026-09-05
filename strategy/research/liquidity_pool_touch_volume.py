"""
Touch Volume telemetry for the Liquidity Pool Touch Count and Volume
research sprint. RESEARCH-ONLY, not wired into production.

Uses ACTUAL TOTAL TRADED VOLUME only - never taker_buy_volume, delta,
CVD, or any directional order-flow feature (those belong to a later,
separate sprint).

Zone-volume proxy (frozen, explicitly disclosed as approximate)
------------------------------------------------------------------------
Where causally aligned 1-minute data is available, a strategy-timeframe
(15m) candle's own "zone volume" is estimated by summing the full
`volume` of every COMPLETED 1-minute candle within that 15m candle's
own time window whose [low, high] range overlaps the pool's zone at
that bar (the same overlap test used for touch-episode detection).
OHLCV data cannot prove that all - or even most - of a 1-minute
candle's volume actually traded inside the exact price zone; a 1m
candle that merely wicks through the zone contributes its ENTIRE
volume, which is a proxy, not a measurement. A 1-minute candle whose
own range never overlaps the zone contributes exactly zero - no
uniform-within-range allocation is ever invented.

Relative volume normalization (frozen)
------------------------------------------------------------------------
No existing point-in-time TRAILING volume-over-time convention exists
in this repository (strategy/features/volume_profile.py's own
`relative_volume` is a same-period, cross-sectional bucket-vs-average
figure - a different axis, not reusable here). A new trailing,
causal, scale-invariant MEDIAN baseline is used instead:
`relative_volume(t) = volume(t) / trailing_median(t)`, where
`trailing_median(t)` is the median `volume` of the
`lookback_minutes` completed 1-minute candles strictly before t.
Frozen: `lookback_minutes=240` (4 hours), `min_warmup=240` (a candle
before the 240th of the month has an undefined/None relative volume -
excluded from relative-volume-dependent aggregates, never treated as
zero). Never normalized using the full month or any future candle.
"""

from typing import Any


def relative_volume_series(
    candles_1m: list[dict[str, Any]],
    lookback_minutes: int = 240,
    min_warmup: int = 240,
) -> list[float | None]:
    """
    Causal, point-in-time relative volume for every candle in
    `candles_1m` (same order, same length). Candle i's relative volume
    uses only `candles_1m[max(0, i-lookback_minutes):i]` (strictly
    prior candles) - never candle i itself or any later candle. `None`
    until at least `min_warmup` prior candles exist.
    """

    import statistics

    volumes = [c["volume"] for c in candles_1m]
    result: list[float | None] = []

    for i in range(len(volumes)):
        if i < min_warmup:
            result.append(None)
            continue

        window = volumes[max(0, i - lookback_minutes):i]
        baseline = statistics.median(window)

        if not baseline:
            result.append(None)
            continue

        result.append(volumes[i] / baseline)

    return result


def bucket_1m_candles(
    candle_15m_timestamp: Any,
    candles_1m_sorted: list[dict[str, Any]],
    index_by_timestamp: dict[Any, int],
    minutes: int = 15,
) -> list[int]:
    """
    Returns the indices (into `candles_1m_sorted`) of the 1-minute
    candles belonging to the 15m candle starting at
    `candle_15m_timestamp` - i.e. timestamps in
    [candle_15m_timestamp, candle_15m_timestamp + minutes). Uses a
    caller-supplied timestamp -> index map for O(1) lookup of the
    bucket's first candle, matching the convention that a 15m candle's
    own timestamp is its OPEN time (data.timeframe_manager's own
    `_bucket_start`).
    """

    from datetime import timedelta

    start_index = index_by_timestamp.get(candle_15m_timestamp)
    if start_index is None:
        return []

    end_timestamp = candle_15m_timestamp + timedelta(minutes=minutes)
    indices = []
    i = start_index
    while i < len(candles_1m_sorted) and candles_1m_sorted[i]["timestamp"] < end_timestamp:
        indices.append(i)
        i += 1

    return indices


def zone_overlapping_1m_indices(
    indices: list[int],
    candles_1m_sorted: list[dict[str, Any]],
    zone_low: float,
    zone_high: float,
) -> list[int]:
    """
    Of the given 1-minute candle indices, returns only those whose own
    [low, high] range overlaps [zone_low, zone_high] (same inclusive
    overlap test as touch-episode detection). A non-overlapping 1m
    candle is never included - it contributes zero.
    """

    from strategy.research.liquidity_pool_touch_episodes import candle_overlaps_zone

    return [
        i for i in indices
        if candle_overlaps_zone(candles_1m_sorted[i]["low"], candles_1m_sorted[i]["high"], zone_low, zone_high)
    ]


def candle_zone_volume(
    overlapping_indices: list[int],
    candles_1m_sorted: list[dict[str, Any]],
) -> float:
    """Raw zone volume for one 15m candle: sum of its own zone-overlapping 1m candles' volume."""

    return sum(candles_1m_sorted[i]["volume"] for i in overlapping_indices)


def candle_zone_relative_volumes(
    overlapping_indices: list[int],
    relative_volumes_1m: list[float | None],
) -> list[float]:
    """
    Relative volume of a 15m candle's own zone-overlapping 1m candles,
    skipping any still in the min_warmup period (None).
    """

    return [relative_volumes_1m[i] for i in overlapping_indices if relative_volumes_1m[i] is not None]
