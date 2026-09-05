"""
Per-pool telemetry assembly for the Liquidity Pool Touch Count and
Volume research sprint. RESEARCH-ONLY, pure, no tracker dependency -
consumes already-collected raw per-bar/per-touch/per-1m-candle data (a
harness assembles those from the real, unmodified LiquidityPoolTracker
plus strategy/research/liquidity_pool_wick_extremity_ledger.py's own
touch ledger, exactly as this sprint's earlier Wick-Extremity sibling
reused the same ledger unchanged) and produces one record per pool with
every field the frozen protocol requires.

Formation contributors (touches on the pool's own creation bar) and
post-confirmation touch episodes (candle-overlap events on later bars)
are computed independently and never merged into one number - see the
frozen protocol's Touch Episode section.
"""

from typing import Any

from strategy.research.liquidity_pool_touch_episodes import classify_touch_episodes, touch_count_bucket
from strategy.research.liquidity_pool_touch_volume import (
    candle_zone_relative_volumes,
    candle_zone_volume,
    zone_overlapping_1m_indices,
)


def assemble_pool_telemetry(
    pool_id: tuple[str, Any],
    direction: str,
    sources_at_creation: list[str],
    origin_bar_i: int,
    pool_confirmed_at: Any,
    sweep_bar_i: int | None,
    sweep_timestamp: Any,
    censored: bool,
    bars: list[dict[str, Any]],
    formation_touches: list[dict[str, Any]],
    post_confirmation_touches: list[dict[str, Any]],
    bucket_indices_by_bar_i: dict[int, list[int]],
    candles_1m_sorted: list[dict[str, Any]],
    relative_volumes_1m: list[float | None],
) -> dict[str, Any]:
    """
    `bars`: ordered {"bar_i","low","high","zone_low","zone_high","timestamp"}
    for every bar from origin_bar_i through resolution/censoring.
    `formation_touches`: ledger entries with bar_index == origin_bar_i.
    `post_confirmation_touches`: ledger entries with bar_index > origin_bar_i.
    `bucket_indices_by_bar_i`: bar_i -> 1-minute candle indices for that
    15m bar (already resolved by the caller via bucket_1m_candles()).
    """

    episodes = classify_touch_episodes(bars, origin_bar_i=origin_bar_i, sweep_bar_i=sweep_bar_i)
    n_episodes = len(episodes)

    pre_sweep_raw_volume = 0.0
    pre_sweep_relative_samples: list[float] = []

    for episode in episodes:
        for bar_i in range(episode["start_bar_i"], episode["end_bar_i"] + 1):
            indices = bucket_indices_by_bar_i.get(bar_i, [])
            bar = next((b for b in bars if b["bar_i"] == bar_i), None)
            if bar is None:
                continue
            overlapping = zone_overlapping_1m_indices(indices, candles_1m_sorted, bar["zone_low"], bar["zone_high"])
            pre_sweep_raw_volume += candle_zone_volume(overlapping, candles_1m_sorted)
            pre_sweep_relative_samples.extend(candle_zone_relative_volumes(overlapping, relative_volumes_1m))

    mean_relative_touch_volume_intensity = (
        sum(pre_sweep_relative_samples) / len(pre_sweep_relative_samples)
        if pre_sweep_relative_samples else None
    )

    sweep_candle_raw_volume = None
    sweep_candle_relative_volume = None
    if sweep_bar_i is not None:
        sweep_bar = next((b for b in bars if b["bar_i"] == sweep_bar_i), None)
        indices = bucket_indices_by_bar_i.get(sweep_bar_i, [])
        if sweep_bar is not None:
            overlapping = zone_overlapping_1m_indices(indices, candles_1m_sorted, sweep_bar["zone_low"], sweep_bar["zone_high"])
            sweep_candle_raw_volume = candle_zone_volume(overlapping, candles_1m_sorted)
            rel_samples = candle_zone_relative_volumes(overlapping, relative_volumes_1m)
            sweep_candle_relative_volume = (sum(rel_samples) / len(rel_samples)) if rel_samples else None

    first_touch_timestamp = post_confirmation_touches[0]["timestamp"] if post_confirmation_touches else None
    last_touch_timestamp = post_confirmation_touches[-1]["timestamp"] if post_confirmation_touches else None

    return {
        "pool_id": pool_id,
        "direction": direction,
        "sources_at_creation": list(sources_at_creation),
        "pool_confirmed_at": pool_confirmed_at,
        "formation_contributor_count": len(formation_touches),
        "n_touch_episodes": n_episodes,
        "touch_count_bucket": touch_count_bucket(n_episodes),
        "episodes": episodes,
        "first_touch_timestamp": first_touch_timestamp,
        "last_touch_timestamp": last_touch_timestamp,
        "sweep_bar_i": sweep_bar_i,
        "sweep_timestamp": sweep_timestamp,
        "pool_age_at_sweep_bars": (sweep_bar_i - origin_bar_i) if sweep_bar_i is not None else None,
        "censored": censored,
        "never_swept": sweep_bar_i is None,
        "pre_sweep_cumulative_touch_volume_raw": pre_sweep_raw_volume,
        "pre_sweep_cumulative_touch_relative_volume": sum(pre_sweep_relative_samples) if pre_sweep_relative_samples else 0.0,
        "mean_relative_touch_volume_intensity": mean_relative_touch_volume_intensity,
        "sweep_candle_volume_raw": sweep_candle_raw_volume,
        "sweep_candle_relative_volume": sweep_candle_relative_volume,
    }
