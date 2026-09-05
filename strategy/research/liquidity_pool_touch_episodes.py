"""
Touch Episode detection for the Liquidity Pool Touch Count and Volume
research sprint. RESEARCH-ONLY, not wired into production.

Frozen definition (see docs/liquidity_pool_touch_volume_train_protocol.md)
------------------------------------------------------------------------
Measured on completed strategy-timeframe (15m) candles only, matching
LiquidityPoolTracker's own timeframe. A new touch episode begins when
the current completed candle overlaps the pool's CURRENT effective
zone (its live zone_high/zone_low at that bar, not a fixed
creation-time snapshot) and the previous completed candle did not.
Consecutive overlapping candles are one episode, not multiple touches.
An episode ends only once at least one complete candle is outside the
zone.

Overlap (frozen, inclusive both ends): a candle's [low, high] range
overlaps [zone_low, zone_high] iff `candle_low <= zone_high AND
candle_high >= zone_low`.

Exclusions (frozen):
- The pool's own creation/confirmation candle never counts (excluded
  from the input sequence by the caller, or `origin_bar_i` is passed
  and internally skipped).
- The confirmed sweep candle is excluded from pre-sweep touch-episode
  counting entirely - it is evaluated separately (sweep-candle
  interaction), never as part of an episode, even if an episode was
  already in progress going into it (that episode simply ends at the
  bar before the sweep candle).
- No candle after the pool's own resolution (sweep) or the dataset's
  last available bar (right-censoring) is ever considered - this
  function only ever receives bars already known to be causally
  available to the caller.
"""

from typing import Any, Literal

TouchCountBucket = Literal["0", "1", "2", "3+"]


def candle_overlaps_zone(candle_low: float, candle_high: float, zone_low: float, zone_high: float) -> bool:
    return candle_low <= zone_high and candle_high >= zone_low


def classify_touch_episodes(
    bars: list[dict[str, Any]],
    origin_bar_i: int,
    sweep_bar_i: int | None,
) -> list[dict[str, Any]]:
    """
    `bars`: ordered list of {"bar_i", "low", "high", "zone_low",
    "zone_high"} for every completed candle from the pool's creation
    through its own resolution (or dataset end if censored) - the
    caller supplies the CURRENT effective zone bounds for that bar
    (production's own live, possibly-widened zone_high/zone_low),
    already causally correct.

    Returns a list of episodes: {"start_bar_i", "end_bar_i",
    "duration_bars"}. `origin_bar_i` and `sweep_bar_i` (if any) are
    always excluded from consideration, regardless of whether they
    appear in `bars`.
    """

    episodes: list[dict[str, Any]] = []
    in_episode = False
    current_start: int | None = None
    current_end: int | None = None

    for bar in bars:
        bar_i = bar["bar_i"]

        if bar_i == origin_bar_i or (sweep_bar_i is not None and bar_i == sweep_bar_i):
            continue

        is_overlap = candle_overlaps_zone(bar["low"], bar["high"], bar["zone_low"], bar["zone_high"])

        if is_overlap and not in_episode:
            in_episode = True
            current_start = bar_i
            current_end = bar_i
        elif is_overlap and in_episode:
            current_end = bar_i
        elif not is_overlap and in_episode:
            episodes.append({
                "start_bar_i": current_start, "end_bar_i": current_end,
                "duration_bars": current_end - current_start + 1,
            })
            in_episode = False
            current_start = None
            current_end = None

    if in_episode:
        episodes.append({
            "start_bar_i": current_start, "end_bar_i": current_end,
            "duration_bars": current_end - current_start + 1,
        })

    return episodes


def touch_count_bucket(n_episodes: int) -> TouchCountBucket:
    if n_episodes <= 0:
        return "0"
    if n_episodes == 1:
        return "1"
    if n_episodes == 2:
        return "2"
    return "3+"
