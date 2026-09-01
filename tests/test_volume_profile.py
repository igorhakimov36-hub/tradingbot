import time as time_module
from datetime import datetime, timedelta, timezone

import pytest

from strategy.features.volume_profile import VolumeProfileTracker

START = datetime(2024, 1, 1, tzinfo=timezone.utc)


def _candle(minute_offset, high, low, volume, close=None):
    if close is None:
        close = (high + low) / 2

    return {
        "timestamp": START + timedelta(minutes=minute_offset),
        "open": close,
        "high": high,
        "low": low,
        "close": close,
        "volume": volume,
    }


def _session(period_start):
    return {"current": {"period_start": period_start}}


def _off_session():
    return {"current": None}


def _histogram_dict(snapshot_profile):
    return {b["price_bucket"]: b["volume"] for b in snapshot_profile["histogram"]}


# =========================================================
# Basic bucketing
# =========================================================


def test_single_candle_spanning_multiple_buckets_splits_volume_evenly():
    tracker = VolumeProfileTracker(bucket_size=10.0)
    tracker.sync([_candle(0, high=25, low=5, volume=30)])

    profile = tracker.snapshot()["current_forming_profile"]
    histogram = _histogram_dict(profile)

    assert histogram == {0.0: pytest.approx(10.0), 10.0: pytest.approx(10.0), 20.0: pytest.approx(10.0)}
    assert profile["total_period_volume"] == pytest.approx(30.0)
    assert profile["is_closed"] is False
    assert profile["period_end"] is None


def test_poc_and_value_area_on_flat_evenly_split_candle():
    tracker = VolumeProfileTracker(bucket_size=10.0)
    tracker.sync([_candle(0, high=25, low=5, volume=30)])

    profile = tracker.snapshot()["current_forming_profile"]

    assert profile["poc_price"] == 0.0  # ties resolve to lowest price bucket
    assert profile["value_area_low"] == 0.0
    assert profile["value_area_high"] == 20.0  # 70% of an even 3-way split needs all 3


def test_candle_within_a_single_bucket_does_not_split():
    tracker = VolumeProfileTracker(bucket_size=10.0)
    tracker.sync([_candle(0, high=8, low=2, volume=15)])

    histogram = _histogram_dict(tracker.snapshot()["current_forming_profile"])
    assert histogram == {0.0: pytest.approx(15.0)}


# =========================================================
# POC / Value Area / HVN / LVN on a hand-computed bimodal profile
# =========================================================


def _bimodal_candles():
    # bucket 0 -> 10, bucket 10 -> 100 (peak), bucket 20 -> 5 (trough),
    # bucket 30 -> 90 (peak), bucket 40 -> 10
    return [
        _candle(0, high=9, low=0, volume=10),
        _candle(1, high=19, low=10, volume=100),
        _candle(2, high=29, low=20, volume=5),
        _candle(3, high=39, low=30, volume=90),
        _candle(4, high=49, low=40, volume=10),
    ]


def test_bimodal_profile_poc_and_value_area():
    tracker = VolumeProfileTracker(bucket_size=10.0)
    tracker.sync(_bimodal_candles())

    profile = tracker.snapshot()["current_forming_profile"]

    assert profile["poc_price"] == 10.0
    assert profile["total_period_volume"] == pytest.approx(215.0)
    assert profile["value_area_low"] == 0.0
    assert profile["value_area_high"] == 30.0


def test_bimodal_profile_hvn_and_lvn():
    tracker = VolumeProfileTracker(bucket_size=10.0)
    tracker.sync(_bimodal_candles())

    profile = tracker.snapshot()["current_forming_profile"]

    hvn_prices = {n["price"] for n in profile["hvn_nodes"]}
    lvn_prices = {n["price"] for n in profile["lvn_nodes"]}

    assert hvn_prices == {10.0, 30.0}
    assert lvn_prices == {20.0}

    hvn_10 = next(n for n in profile["hvn_nodes"] if n["price"] == 10.0)
    assert hvn_10["relative_volume"] == pytest.approx(100 / 43, rel=1e-3)
    assert hvn_10["width"] == 1

    lvn_20 = next(n for n in profile["lvn_nodes"] if n["price"] == 20.0)
    assert lvn_20["relative_volume"] == pytest.approx(5 / 43, rel=1e-3)


# =========================================================
# Developing vs completed profile (session-anchored)
# =========================================================


def test_profile_closes_and_starts_fresh_on_new_anchor_period():
    tracker = VolumeProfileTracker(bucket_size=10.0, anchor_name="daily")

    period_a = START
    period_b = START + timedelta(days=1)

    tracker.sync([_candle(0, high=15, low=5, volume=20)], session_snapshot={"daily": _session(period_a)})

    candles = [_candle(0, high=15, low=5, volume=20), _candle(1, high=15, low=5, volume=10)]
    tracker.sync(candles, session_snapshot={"daily": _session(period_a)})

    candles.append(_candle(2, high=15, low=5, volume=5))
    tracker.sync(candles, session_snapshot={"daily": _session(period_b)})

    snap = tracker.snapshot()
    assert len(snap["closed_profiles"]) == 1

    closed = snap["closed_profiles"][0]
    assert closed["is_closed"] is True
    assert closed["period_end"] == candles[1]["timestamp"]  # last candle of the OLD period
    assert closed["total_period_volume"] == pytest.approx(30.0)  # candles 0+1 only

    current = snap["current_forming_profile"]
    assert current["is_closed"] is False
    assert current["total_period_volume"] == pytest.approx(5.0)  # only the new period's candle


def test_off_session_gap_pauses_rather_than_resets():
    tracker = VolumeProfileTracker(bucket_size=10.0, anchor_name="kz")

    period_a = START
    tracker.sync([_candle(0, high=15, low=5, volume=20)], session_snapshot={"kz": _session(period_a)})

    candles = [_candle(0, high=15, low=5, volume=20), _candle(1, high=15, low=5, volume=999)]
    tracker.sync(candles, session_snapshot={"kz": _off_session()})

    profile = tracker.snapshot()["current_forming_profile"]
    assert profile["total_period_volume"] == pytest.approx(20.0)  # unchanged - paused

    candles.append(_candle(2, high=15, low=5, volume=5))
    tracker.sync(candles, session_snapshot={"kz": _session(period_a)})  # window reopens, same period

    profile = tracker.snapshot()["current_forming_profile"]
    assert profile["total_period_volume"] == pytest.approx(25.0)  # resumed, no reset


def test_continuous_anchor_never_closes():
    tracker = VolumeProfileTracker(bucket_size=10.0)  # anchor_name=None

    candles = [_candle(i, high=15, low=5, volume=10) for i in range(5)]
    tracker.sync(candles)

    snap = tracker.snapshot()
    assert snap["closed_profiles"] == []
    assert snap["current_forming_profile"]["total_period_volume"] == pytest.approx(50.0)


# =========================================================
# Acceptance/rejection raw comparisons (poc_shift, value_area_overlap)
# =========================================================


def test_first_period_has_no_previous_period_comparison():
    tracker = VolumeProfileTracker(bucket_size=10.0, anchor_name="daily")
    tracker.sync([_candle(0, high=15, low=5, volume=20)], session_snapshot={"daily": _session(START)})

    profile = tracker.snapshot()["current_forming_profile"]
    assert profile["poc_shift_from_previous_period"] is None
    assert profile["value_area_overlap_ratio"] is None


def test_value_area_overlap_ratio_full_when_same_range_repeats():
    tracker = VolumeProfileTracker(bucket_size=10.0, anchor_name="daily", atr_period=2)

    period_a = START
    period_b = START + timedelta(days=1)

    candles = [_candle(0, high=15, low=5, volume=20), _candle(1, high=25, low=15, volume=20)]
    tracker.sync(candles[:1], session_snapshot={"daily": _session(period_a)})
    tracker.sync(candles, session_snapshot={"daily": _session(period_a)})

    # New period repeats the EXACT same candle pattern -> same value area.
    candles.append(_candle(2, high=15, low=5, volume=20))
    tracker.sync(candles, session_snapshot={"daily": _session(period_b)})
    candles.append(_candle(3, high=25, low=15, volume=20))
    tracker.sync(candles, session_snapshot={"daily": _session(period_b)})

    profile = tracker.snapshot()["current_forming_profile"]
    assert profile["value_area_overlap_ratio"] == pytest.approx(1.0)


def test_value_area_overlap_ratio_zero_when_ranges_dont_overlap():
    tracker = VolumeProfileTracker(bucket_size=10.0, anchor_name="daily", atr_period=2)

    period_a = START
    period_b = START + timedelta(days=1)

    tracker.sync([_candle(0, high=15, low=5, volume=20)], session_snapshot={"daily": _session(period_a)})

    # Entirely different, non-overlapping price range in the new period.
    candles = [_candle(0, high=15, low=5, volume=20), _candle(1, high=1015, low=1005, volume=20)]
    tracker.sync(candles, session_snapshot={"daily": _session(period_b)})

    profile = tracker.snapshot()["current_forming_profile"]
    assert profile["value_area_overlap_ratio"] == pytest.approx(0.0)


# =========================================================
# Bounded history / config validation
# =========================================================


def test_closed_profiles_history_is_bounded():
    tracker = VolumeProfileTracker(bucket_size=10.0, anchor_name="daily", max_tracked_closed=2)

    candles = []
    for day in range(4):
        candles.append(_candle(day, high=15, low=5, volume=10))
        tracker.sync(candles, session_snapshot={"daily": _session(START + timedelta(days=day))})

    assert len(tracker.snapshot()["closed_profiles"]) == 2


def test_bucket_size_must_be_positive():
    with pytest.raises(ValueError):
        VolumeProfileTracker(bucket_size=0)

    with pytest.raises(ValueError):
        VolumeProfileTracker(bucket_size=-5)


def test_value_area_percentage_must_be_in_range():
    with pytest.raises(ValueError):
        VolumeProfileTracker(bucket_size=10.0, value_area_percentage=0)

    with pytest.raises(ValueError):
        VolumeProfileTracker(bucket_size=10.0, value_area_percentage=1.5)


def test_data_quality_is_always_approximate_in_this_phase():
    tracker = VolumeProfileTracker(bucket_size=10.0)
    tracker.sync([_candle(0, high=15, low=5, volume=20)])

    assert tracker.snapshot()["current_forming_profile"]["data_quality"] == "approximate"


# =========================================================
# Replay safety
# =========================================================


def test_missing_session_snapshot_when_anchored_is_rejected():
    tracker = VolumeProfileTracker(bucket_size=10.0, anchor_name="daily")

    with pytest.raises(ValueError):
        tracker.sync([_candle(0, high=15, low=5, volume=20)])


def test_session_anchored_tracker_rejects_batching_more_than_one_new_candle():
    tracker = VolumeProfileTracker(bucket_size=10.0, anchor_name="daily")

    with pytest.raises(ValueError):
        tracker.sync(
            [_candle(0, high=15, low=5, volume=20), _candle(1, high=15, low=5, volume=20)],
            session_snapshot={"daily": _session(START)},
        )


def test_continuous_anchor_allows_batched_sync():
    tracker = VolumeProfileTracker(bucket_size=10.0)
    candles = [_candle(i, high=15, low=5, volume=10) for i in range(5)]

    tracker.sync(candles)  # all 5 in a single call, no anchor configured

    assert tracker.snapshot()["current_forming_profile"]["total_period_volume"] == pytest.approx(50.0)


def test_sync_rejects_rewound_candles():
    tracker = VolumeProfileTracker(bucket_size=10.0)
    tracker.sync([_candle(0, high=15, low=5, volume=20), _candle(1, high=15, low=5, volume=20)])

    with pytest.raises(ValueError):
        tracker.sync([_candle(0, high=15, low=5, volume=20)])


def test_sync_rejects_diverging_history():
    tracker = VolumeProfileTracker(bucket_size=10.0)
    tracker.sync([_candle(0, high=15, low=5, volume=20)])

    with pytest.raises(ValueError):
        tracker.sync([_candle(0, high=999, low=998, volume=1)])


def test_two_independent_incremental_replays_are_deterministic():
    candles = [_candle(i, high=15 + i, low=5 + i, volume=10 + i) for i in range(10)]
    session_snapshot = {"daily": _session(START)}

    replay_a = VolumeProfileTracker(bucket_size=5.0, anchor_name="daily")
    replay_b = VolumeProfileTracker(bucket_size=5.0, anchor_name="daily")

    for n in range(1, len(candles) + 1):
        replay_a.sync(candles[:n], session_snapshot=session_snapshot)
        replay_b.sync(candles[:n], session_snapshot=session_snapshot)

    assert replay_a.snapshot() == replay_b.snapshot()


# =========================================================
# Integration - wired to a real SessionBoundariesTracker
# =========================================================


def test_wired_to_real_session_boundaries_tracker():
    from strategy.features.session_boundaries import CalendarPeriod, SessionBoundariesTracker

    session_tracker = SessionBoundariesTracker([CalendarPeriod(name="daily", timezone="UTC", period="daily")])
    profile_tracker = VolumeProfileTracker(bucket_size=10.0, anchor_name="daily")

    candles = [
        _candle(0, high=15, low=5, volume=20),
        _candle(60 * 20, high=15, low=5, volume=20),   # still day 1
        _candle(60 * 30, high=15, low=5, volume=10),   # day 2 - triggers a close
    ]

    for n in range(1, len(candles) + 1):
        step = candles[:n]
        session_tracker.sync(step)
        profile_tracker.sync(step, session_snapshot=session_tracker.snapshot())

    snap = profile_tracker.snapshot()
    assert len(snap["closed_profiles"]) == 1
    assert snap["closed_profiles"][0]["total_period_volume"] == pytest.approx(40.0)
    assert snap["current_forming_profile"]["total_period_volume"] == pytest.approx(10.0)


# =========================================================
# Performance validation
# =========================================================


def test_large_history_stays_fast_continuous_batched():
    candle_count = 20_000
    candles = [_candle(i, high=100 + (i % 50), low=90 + (i % 50), volume=10) for i in range(candle_count)]

    tracker = VolumeProfileTracker(bucket_size=5.0)

    start_time = time_module.perf_counter()

    step = 500
    for i in range(step, candle_count + 1, step):
        tracker.sync(candles[:i])

    elapsed = time_module.perf_counter() - start_time

    assert elapsed < 5.0


def test_large_history_stays_fast_session_anchored_one_candle_per_call():
    candle_count = 5_000
    candles = [_candle(i, high=100 + (i % 50), low=90 + (i % 50), volume=10) for i in range(candle_count)]
    session_snapshot = {"daily": _session(START)}

    tracker = VolumeProfileTracker(bucket_size=5.0, anchor_name="daily")

    start_time = time_module.perf_counter()

    for i in range(1, candle_count + 1):
        tracker.sync(candles[:i], session_snapshot=session_snapshot)

    elapsed = time_module.perf_counter() - start_time

    assert elapsed < 5.0
