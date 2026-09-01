import time as time_module
from datetime import datetime, timedelta, timezone

import pytest

from strategy.features.cvd import CVDAnchor, CVDTracker

START = datetime(2024, 1, 1, tzinfo=timezone.utc)


def _candle(minute_offset, taker_buy_volume=None, volume=10.0, high=100.0, low=90.0, close=None):
    if close is None:
        close = (high + low) / 2

    return {
        "timestamp": START + timedelta(minutes=minute_offset),
        "open": close,
        "high": high,
        "low": low,
        "close": close,
        "volume": volume,
        "taker_buy_volume": taker_buy_volume,
    }


def _delta_candle(minute_offset, delta, volume=10.0, high=100.0, low=90.0):
    """A candle engineered to produce an exact `delta` value (via
    calculate_delta's own formula: delta = 2*taker_buy - volume)."""
    taker_buy_volume = (delta + volume) / 2
    return _candle(minute_offset, taker_buy_volume=taker_buy_volume, volume=volume, high=high, low=low)


def _missing_candle(minute_offset):
    return _candle(minute_offset, taker_buy_volume=None)


def _session(period_start):
    return {"current": {"period_start": period_start}}


def _off_session():
    return {"current": None}


# =========================================================
# Basic accumulation (continuous anchor)
# =========================================================


def test_cvd_accumulates_delta_across_bars():
    tracker = CVDTracker([CVDAnchor(name="continuous")], window=3)

    candles = [
        _delta_candle(0, delta=2),
        _delta_candle(1, delta=4),
        _delta_candle(2, delta=0),
    ]

    for n in range(1, len(candles) + 1):
        tracker.sync(candles[:n])

    snap = tracker.snapshot()["continuous"]
    assert snap["cvd"] == pytest.approx(6.0)  # 2 + 4 + 0
    assert snap["bars_since_anchor"] == 3
    assert snap["bars_with_missing_data"] == 0
    assert snap["anchor_type"] == "continuous"
    assert snap["anchor_timestamp"] == candles[0]["timestamp"]


def test_missing_taker_buy_volume_is_skipped_not_treated_as_zero():
    tracker = CVDTracker([CVDAnchor(name="continuous")], window=3)

    candles = [
        _delta_candle(0, delta=5),
        _missing_candle(1),
        _delta_candle(2, delta=3),
    ]

    for n in range(1, len(candles) + 1):
        tracker.sync(candles[:n])

    snap = tracker.snapshot()["continuous"]
    assert snap["cvd"] == pytest.approx(8.0)  # 5 + 3, missing bar contributes nothing
    assert snap["bars_since_anchor"] == 3
    assert snap["bars_with_missing_data"] == 1


def test_continuous_anchor_allows_batched_sync():
    # No session anchor configured - safe to batch, exactly like Delta.
    tracker = CVDTracker([CVDAnchor(name="continuous")], window=3)

    candles = [_delta_candle(i, delta=1) for i in range(5)]
    tracker.sync(candles)  # all 5 in a single call

    assert tracker.snapshot()["continuous"]["cvd"] == pytest.approx(5.0)


# =========================================================
# Windowed change / slope / direction
# =========================================================


def test_windowed_stats_are_none_before_window_fills():
    tracker = CVDTracker([CVDAnchor(name="continuous")], window=3)

    tracker.sync([_delta_candle(0, delta=2)])
    snap = tracker.snapshot()["continuous"]
    assert snap["cvd_change_over_window"] is None
    assert snap["cvd_slope"] is None
    assert snap["cvd_direction"] is None


def test_windowed_change_and_slope_once_window_fills():
    tracker = CVDTracker([CVDAnchor(name="continuous")], window=3)

    candles = [
        _delta_candle(0, delta=2),  # cvd=2
        _delta_candle(1, delta=4),  # cvd=6
        _delta_candle(2, delta=0),  # cvd=6
    ]

    for n in range(1, len(candles) + 1):
        tracker.sync(candles[:n])

    snap = tracker.snapshot()["continuous"]
    assert snap["cvd_change_over_window"] == pytest.approx(4.0)  # 6 - 2
    assert snap["cvd_slope"] == pytest.approx(2.0)  # 4 / (3-1)
    assert snap["cvd_direction"] == "BULLISH"


def test_negative_slope_gives_bearish_direction():
    tracker = CVDTracker([CVDAnchor(name="continuous")], window=3)

    candles = [
        _delta_candle(0, delta=-2),
        _delta_candle(1, delta=-4),
        _delta_candle(2, delta=0),
    ]

    for n in range(1, len(candles) + 1):
        tracker.sync(candles[:n])

    assert tracker.snapshot()["continuous"]["cvd_direction"] == "BEARISH"


# =========================================================
# Divergence
# =========================================================


def test_price_new_high_without_cvd_confirming_is_bearish_divergence():
    tracker = CVDTracker([CVDAnchor(name="continuous")], window=3)

    candles = [
        _delta_candle(0, delta=5, high=100, low=90),
        _delta_candle(1, delta=5, high=105, low=90),   # cvd=10, higher high
        _delta_candle(2, delta=-2, high=110, low=90),  # cvd=8 (NOT a new cvd high), price IS a new high
    ]

    for n in range(1, len(candles) + 1):
        tracker.sync(candles[:n])

    assert tracker.snapshot()["continuous"]["price_cvd_divergence_flag"] == "bearish_divergence"


def test_price_new_low_without_cvd_confirming_is_bullish_divergence():
    tracker = CVDTracker([CVDAnchor(name="continuous")], window=3)

    candles = [
        _delta_candle(0, delta=-5, high=110, low=100),
        _delta_candle(1, delta=-5, high=110, low=95),   # cvd=-10, lower low
        _delta_candle(2, delta=2, high=110, low=90),    # cvd=-8 (NOT a new cvd low), price IS a new low
    ]

    for n in range(1, len(candles) + 1):
        tracker.sync(candles[:n])

    assert tracker.snapshot()["continuous"]["price_cvd_divergence_flag"] == "bullish_divergence"


def test_price_and_cvd_moving_together_is_no_divergence():
    tracker = CVDTracker([CVDAnchor(name="continuous")], window=3)

    candles = [
        _delta_candle(0, delta=5, high=100, low=90),
        _delta_candle(1, delta=5, high=105, low=90),
        _delta_candle(2, delta=5, high=110, low=90),  # cvd also makes a new high
    ]

    for n in range(1, len(candles) + 1):
        tracker.sync(candles[:n])

    assert tracker.snapshot()["continuous"]["price_cvd_divergence_flag"] == "none"


# =========================================================
# Exhaustion
# =========================================================


def test_decelerating_cvd_new_high_is_bearish_exhaustion():
    tracker = CVDTracker([CVDAnchor(name="continuous")], window=3)

    candles = [
        _delta_candle(0, delta=0),   # cvd=0
        _delta_candle(1, delta=10),  # cvd=10 (first-half slope = 10)
        _delta_candle(2, delta=2),   # cvd=12 (second-half slope = 2) - new high, decelerating
    ]

    for n in range(1, len(candles) + 1):
        tracker.sync(candles[:n])

    assert tracker.snapshot()["continuous"]["cvd_exhaustion_flag"] == "bearish_exhaustion"


def test_decelerating_cvd_new_low_is_bullish_exhaustion():
    tracker = CVDTracker([CVDAnchor(name="continuous")], window=3)

    candles = [
        _delta_candle(0, delta=0),    # cvd=0
        _delta_candle(1, delta=-10),  # cvd=-10 (first-half slope = -10)
        _delta_candle(2, delta=-2),   # cvd=-12 (second-half slope = -2) - new low, decelerating
    ]

    for n in range(1, len(candles) + 1):
        tracker.sync(candles[:n])

    assert tracker.snapshot()["continuous"]["cvd_exhaustion_flag"] == "bullish_exhaustion"


def test_accelerating_cvd_new_high_is_not_exhaustion():
    tracker = CVDTracker([CVDAnchor(name="continuous")], window=3)

    candles = [
        _delta_candle(0, delta=0),   # cvd=0
        _delta_candle(1, delta=2),   # cvd=2 (first-half slope = 2)
        _delta_candle(2, delta=10),  # cvd=12 (second-half slope = 10) - new high, ACCELERATING
    ]

    for n in range(1, len(candles) + 1):
        tracker.sync(candles[:n])

    assert tracker.snapshot()["continuous"]["cvd_exhaustion_flag"] == "none"


def test_no_new_extreme_is_not_exhaustion():
    tracker = CVDTracker([CVDAnchor(name="continuous")], window=3)

    candles = [
        _delta_candle(0, delta=10),  # cvd=10
        _delta_candle(1, delta=-1),  # cvd=9
        _delta_candle(2, delta=-1),  # cvd=8 - neither a new high nor new low vs [10, 9]
    ]

    for n in range(1, len(candles) + 1):
        tracker.sync(candles[:n])

    assert tracker.snapshot()["continuous"]["cvd_exhaustion_flag"] == "none"


# =========================================================
# Session-anchored resets
# =========================================================


def test_session_anchor_resets_when_period_start_changes():
    tracker = CVDTracker([CVDAnchor(name="daily", session_name="daily")], window=3)

    period_a = START
    period_b = START + timedelta(days=1)

    candles = [
        _delta_candle(0, delta=5),
        _delta_candle(1, delta=5),
    ]
    tracker.sync(candles[:1], session_snapshot={"daily": _session(period_a)})
    tracker.sync(candles[:2], session_snapshot={"daily": _session(period_a)})

    snap = tracker.snapshot()["daily"]
    assert snap["cvd"] == pytest.approx(10.0)
    assert snap["bars_since_anchor"] == 2

    candles.append(_delta_candle(2, delta=3))
    tracker.sync(candles, session_snapshot={"daily": _session(period_b)})

    snap = tracker.snapshot()["daily"]
    assert snap["cvd"] == pytest.approx(3.0)  # reset - only the new period's bar counts
    assert snap["bars_since_anchor"] == 1
    assert snap["anchor_timestamp"] == candles[2]["timestamp"]


def test_off_session_gap_pauses_rather_than_resets():
    tracker = CVDTracker([CVDAnchor(name="kz", session_name="kz")], window=3)

    period_a = START

    candles = [_delta_candle(0, delta=5)]
    tracker.sync(candles, session_snapshot={"kz": _session(period_a)})
    assert tracker.snapshot()["kz"]["cvd"] == pytest.approx(5.0)

    candles.append(_delta_candle(1, delta=100))  # would matter a lot if NOT paused
    tracker.sync(candles, session_snapshot={"kz": _off_session()})

    snap = tracker.snapshot()["kz"]
    assert snap["cvd"] == pytest.approx(5.0)  # unchanged - paused, not accumulated
    assert snap["bars_since_anchor"] == 1

    # Window reopens later (same period_start as before - not a new period).
    candles.append(_delta_candle(2, delta=5))
    tracker.sync(candles, session_snapshot={"kz": _session(period_a)})

    assert tracker.snapshot()["kz"]["cvd"] == pytest.approx(10.0)  # resumed, no reset
    assert tracker.snapshot()["kz"]["bars_since_anchor"] == 2


# =========================================================
# Multiple simultaneous anchors, one shared Delta computation
# =========================================================


def test_multiple_anchors_tracked_independently_in_one_instance():
    tracker = CVDTracker(
        [CVDAnchor(name="continuous"), CVDAnchor(name="daily", session_name="daily")],
        window=3,
    )

    candles = [_delta_candle(0, delta=5), _delta_candle(1, delta=5)]
    tracker.sync(candles[:1], session_snapshot={"daily": _session(START)})
    tracker.sync(candles[:2], session_snapshot={"daily": _session(START)})

    candles.append(_delta_candle(2, delta=3))
    tracker.sync(candles, session_snapshot={"daily": _session(START + timedelta(days=1))})

    snap = tracker.snapshot()
    assert set(snap.keys()) == {"continuous", "daily"}
    assert snap["continuous"]["cvd"] == pytest.approx(13.0)  # never resets
    assert snap["daily"]["cvd"] == pytest.approx(3.0)  # reset on the new day


# =========================================================
# Validation / replay safety
# =========================================================


def test_empty_anchors_list_is_rejected():
    with pytest.raises(ValueError):
        CVDTracker([])


def test_duplicate_anchor_names_are_rejected():
    with pytest.raises(ValueError):
        CVDTracker([CVDAnchor(name="dup"), CVDAnchor(name="dup", session_name="daily")])


def test_window_below_two_is_rejected():
    with pytest.raises(ValueError):
        CVDTracker([CVDAnchor(name="continuous")], window=1)


def test_missing_session_snapshot_when_required_is_rejected():
    tracker = CVDTracker([CVDAnchor(name="daily", session_name="daily")], window=3)

    with pytest.raises(ValueError):
        tracker.sync([_delta_candle(0, delta=1)])


def test_session_anchored_tracker_rejects_batching_more_than_one_new_candle():
    tracker = CVDTracker([CVDAnchor(name="daily", session_name="daily")], window=3)

    with pytest.raises(ValueError):
        tracker.sync(
            [_delta_candle(0, delta=1), _delta_candle(1, delta=1)],
            session_snapshot={"daily": _session(START)},
        )


def test_sync_rejects_rewound_candles():
    tracker = CVDTracker([CVDAnchor(name="continuous")], window=3)
    tracker.sync([_delta_candle(0, delta=1), _delta_candle(1, delta=1)])

    with pytest.raises(ValueError):
        tracker.sync([_delta_candle(0, delta=1)])


def test_sync_rejects_diverging_history():
    tracker = CVDTracker([CVDAnchor(name="continuous")], window=3)
    tracker.sync([_delta_candle(0, delta=1)])

    with pytest.raises(ValueError):
        tracker.sync([_delta_candle(0, delta=999)])


def test_two_independent_incremental_replays_are_deterministic():
    candles = [_delta_candle(i, delta=(i % 3) - 1) for i in range(6)]
    session_snapshot = {"daily": _session(START)}

    replay_a = CVDTracker([CVDAnchor(name="daily", session_name="daily")], window=3)
    replay_b = CVDTracker([CVDAnchor(name="daily", session_name="daily")], window=3)

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
    cvd_tracker = CVDTracker([CVDAnchor(name="daily", session_name="daily")], window=3)

    candles = [
        _delta_candle(0, delta=5),
        _delta_candle(60 * 20, delta=5),   # still day 1 (20h later)
        _delta_candle(60 * 30, delta=3),   # day 2 (30h later) - triggers a reset
    ]

    for n in range(1, len(candles) + 1):
        step = candles[:n]
        session_tracker.sync(step)
        cvd_tracker.sync(step, session_snapshot=session_tracker.snapshot())

    snap = cvd_tracker.snapshot()["daily"]
    assert snap["cvd"] == pytest.approx(3.0)  # only day 2's bar so far
    assert snap["bars_since_anchor"] == 1


# =========================================================
# Performance validation
# =========================================================


def test_large_history_stays_fast_continuous_batched():
    candle_count = 20_000
    candles = [_delta_candle(i, delta=1) for i in range(candle_count)]

    tracker = CVDTracker([CVDAnchor(name="continuous")], window=20)

    start_time = time_module.perf_counter()

    step = 500
    for i in range(step, candle_count + 1, step):
        tracker.sync(candles[:i])

    elapsed = time_module.perf_counter() - start_time

    assert elapsed < 5.0
    assert tracker.snapshot()["continuous"]["cvd"] == pytest.approx(float(candle_count))


def test_large_history_stays_fast_session_anchored_one_candle_per_call():
    candle_count = 20_000
    candles = [_delta_candle(i, delta=1) for i in range(candle_count)]
    session_snapshot = {"daily": _session(START)}

    tracker = CVDTracker([CVDAnchor(name="daily", session_name="daily")], window=20)

    start_time = time_module.perf_counter()

    for i in range(1, candle_count + 1):
        tracker.sync(candles[:i], session_snapshot=session_snapshot)

    elapsed = time_module.perf_counter() - start_time

    assert elapsed < 5.0
