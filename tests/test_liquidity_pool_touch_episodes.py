"""
Tests for strategy/research/liquidity_pool_touch_episodes.py.
"""

from strategy.research.liquidity_pool_touch_episodes import (
    candle_overlaps_zone,
    classify_touch_episodes,
    touch_count_bucket,
)


def _bar(bar_i, low, high, zone_low=100.0, zone_high=105.0):
    return {"bar_i": bar_i, "low": low, "high": high, "zone_low": zone_low, "zone_high": zone_high}


# =========================================================
# candle_overlaps_zone
# =========================================================


def test_overlap_true_when_candle_inside_zone():
    assert candle_overlaps_zone(101.0, 102.0, 100.0, 105.0) is True


def test_overlap_true_at_exact_boundary_inclusive():
    assert candle_overlaps_zone(105.0, 106.0, 100.0, 105.0) is True
    assert candle_overlaps_zone(94.0, 100.0, 100.0, 105.0) is True


def test_overlap_false_when_entirely_above_or_below():
    assert candle_overlaps_zone(106.0, 108.0, 100.0, 105.0) is False
    assert candle_overlaps_zone(90.0, 99.0, 100.0, 105.0) is False


# =========================================================
# Requirement 1: creation candle is never counted
# =========================================================


def test_creation_candle_never_counted_even_if_overlapping():
    bars = [_bar(0, 101, 102)]  # bar 0 is the origin/creation bar
    episodes = classify_touch_episodes(bars, origin_bar_i=0, sweep_bar_i=None)
    assert episodes == []


# =========================================================
# Requirement 2: consecutive overlapping candles form ONE episode
# =========================================================


def test_consecutive_overlapping_candles_form_one_episode():
    bars = [_bar(0, 101, 102), _bar(1, 101, 102), _bar(2, 102, 103), _bar(3, 101, 104)]
    episodes = classify_touch_episodes(bars, origin_bar_i=0, sweep_bar_i=None)
    assert len(episodes) == 1
    assert episodes[0] == {"start_bar_i": 1, "end_bar_i": 3, "duration_bars": 3}


# =========================================================
# Requirement 3: leaving and later returning creates a SECOND episode
# =========================================================


def test_leaving_and_returning_creates_second_episode():
    bars = [
        _bar(0, 101, 102),   # origin, excluded
        _bar(1, 101, 102),   # overlap -> episode 1 starts
        _bar(2, 110, 112),   # no overlap -> episode 1 ends
        _bar(3, 110, 111),   # no overlap
        _bar(4, 102, 103),   # overlap -> episode 2 starts
    ]
    episodes = classify_touch_episodes(bars, origin_bar_i=0, sweep_bar_i=None)
    assert len(episodes) == 2
    assert episodes[0] == {"start_bar_i": 1, "end_bar_i": 1, "duration_bars": 1}
    assert episodes[1] == {"start_bar_i": 4, "end_bar_i": 4, "duration_bars": 1}


# =========================================================
# Requirement 4: sweep candle excluded from pre-sweep touches
# =========================================================


def test_sweep_candle_excluded_from_pre_sweep_episodes():
    bars = [
        _bar(0, 101, 102),               # origin
        _bar(1, 101, 102),               # episode 1
        _bar(2, 106, 110, zone_high=105.0),  # the "sweep" bar - wicks beyond, would overlap too
    ]
    episodes = classify_touch_episodes(bars, origin_bar_i=0, sweep_bar_i=2)
    assert len(episodes) == 1
    assert episodes[0]["start_bar_i"] == 1
    assert episodes[0]["end_bar_i"] == 1  # bar 2 never extends or appears in an episode


def test_in_progress_episode_ends_at_bar_before_sweep_not_at_sweep():
    bars = [
        _bar(0, 101, 102),  # origin
        _bar(1, 101, 102),  # episode starts
        _bar(2, 101, 102),  # still overlapping, continues episode
        _bar(3, 106, 110, zone_high=105.0),  # sweep bar, excluded entirely
    ]
    episodes = classify_touch_episodes(bars, origin_bar_i=0, sweep_bar_i=3)
    assert len(episodes) == 1
    assert episodes[0] == {"start_bar_i": 1, "end_bar_i": 2, "duration_bars": 2}


def test_no_episodes_when_never_overlapping():
    bars = [_bar(0, 101, 102), _bar(1, 110, 112), _bar(2, 111, 113)]
    episodes = classify_touch_episodes(bars, origin_bar_i=0, sweep_bar_i=None)
    assert episodes == []


def test_censored_pool_open_episode_counted_up_to_last_bar():
    bars = [_bar(0, 101, 102), _bar(1, 101, 102), _bar(2, 102, 103)]
    episodes = classify_touch_episodes(bars, origin_bar_i=0, sweep_bar_i=None)
    assert len(episodes) == 1
    assert episodes[0] == {"start_bar_i": 1, "end_bar_i": 2, "duration_bars": 2}


def test_uses_current_effective_zone_per_bar_not_a_fixed_snapshot():
    # zone widens between bar 1 and bar 2 - a candle that would NOT have
    # overlapped the original (narrower) zone but DOES overlap the
    # current (wider) one must still count, since episodes use the
    # CURRENT effective geometry, not creation-time geometry.
    bars = [
        _bar(0, 101, 102, zone_low=100.0, zone_high=103.0),
        _bar(1, 104, 106, zone_low=100.0, zone_high=103.0),   # no overlap vs narrow zone
        _bar(2, 104, 106, zone_low=100.0, zone_high=107.0),   # zone widened -> now overlaps
    ]
    episodes = classify_touch_episodes(bars, origin_bar_i=0, sweep_bar_i=None)
    assert len(episodes) == 1
    assert episodes[0]["start_bar_i"] == 2


# =========================================================
# touch_count_bucket
# =========================================================


def test_touch_count_buckets():
    assert touch_count_bucket(0) == "0"
    assert touch_count_bucket(1) == "1"
    assert touch_count_bucket(2) == "2"
    assert touch_count_bucket(3) == "3+"
    assert touch_count_bucket(10) == "3+"


# =========================================================
# Determinism
# =========================================================


def test_deterministic():
    bars = [_bar(0, 101, 102), _bar(1, 101, 102), _bar(2, 110, 112), _bar(3, 102, 103)]
    r1 = classify_touch_episodes(bars, origin_bar_i=0, sweep_bar_i=None)
    r2 = classify_touch_episodes(bars, origin_bar_i=0, sweep_bar_i=None)
    assert r1 == r2
