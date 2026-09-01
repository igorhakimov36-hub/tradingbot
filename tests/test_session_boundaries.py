import time as time_module
from datetime import date, datetime, time, timedelta, timezone

import pytest

from strategy.features.session_boundaries import (
    DEFAULT_SESSIONS,
    CalendarPeriod,
    SessionBoundariesTracker,
    SessionWindow,
)


def _candle(ts: datetime, high: float, low: float, volume: float = 10.0):
    return {
        "timestamp": ts,
        "open": (high + low) / 2,
        "high": high,
        "low": low,
        "close": (high + low) / 2,
        "volume": volume,
    }


def _utc(y, m, d, hh=0, mm=0):
    return datetime(y, m, d, hh, mm, tzinfo=timezone.utc)


# =========================================================
# Non-wrapping SessionWindow - open, update, close
# =========================================================


def test_candle_inside_window_opens_a_current_session():
    # Asian session: Tokyo 00:00-09:00 local, which is a FIXED UTC
    # window (15:00 prev day - 00:00) since Tokyo has no DST.
    definitions = [SessionWindow(name="asian", timezone="Asia/Tokyo", start_time=time(0, 0), end_time=time(9, 0))]
    tracker = SessionBoundariesTracker(definitions)

    # 2024-01-15 16:00 UTC = 2024-01-16 01:00 JST - inside the window.
    tracker.sync([_candle(_utc(2024, 1, 15, 16, 0), high=100, low=95)])

    current = tracker.snapshot()["asian"]["current"]
    assert current is not None
    assert current["is_closed"] is False
    assert current["session_high"] == 100
    assert current["session_low"] == 95
    assert current["candle_count"] == 1
    assert current["period_start"] == _utc(2024, 1, 15, 15, 0)  # 00:00 JST -> 15:00 UTC prev day


def test_candle_outside_window_leaves_no_current_session():
    definitions = [SessionWindow(name="asian", timezone="Asia/Tokyo", start_time=time(0, 0), end_time=time(9, 0))]
    tracker = SessionBoundariesTracker(definitions)

    # 2024-01-15 05:00 UTC = 14:00 JST - well outside 00:00-09:00 JST.
    tracker.sync([_candle(_utc(2024, 1, 15, 5, 0), high=100, low=95)])

    assert tracker.snapshot()["asian"]["current"] is None
    assert tracker.snapshot()["asian"]["closed"] == []


def test_session_high_low_and_timestamps_track_across_candles():
    definitions = [SessionWindow(name="asian", timezone="Asia/Tokyo", start_time=time(0, 0), end_time=time(9, 0))]
    tracker = SessionBoundariesTracker(definitions)

    c1 = _candle(_utc(2024, 1, 15, 15, 0), high=100, low=95)
    c2 = _candle(_utc(2024, 1, 15, 15, 15), high=110, low=90)
    c3 = _candle(_utc(2024, 1, 15, 15, 30), high=105, low=98)

    tracker.sync([c1])
    tracker.sync([c1, c2])
    tracker.sync([c1, c2, c3])

    current = tracker.snapshot()["asian"]["current"]
    assert current["session_high"] == 110
    assert current["high_timestamp"] == c2["timestamp"]
    assert current["session_low"] == 90
    assert current["low_timestamp"] == c2["timestamp"]
    assert current["candle_count"] == 3


def test_session_closes_when_a_candle_falls_outside_the_window():
    definitions = [SessionWindow(name="asian", timezone="Asia/Tokyo", start_time=time(0, 0), end_time=time(9, 0))]
    tracker = SessionBoundariesTracker(definitions)

    inside = _candle(_utc(2024, 1, 15, 15, 0), high=100, low=95)  # 00:00 JST
    outside = _candle(_utc(2024, 1, 15, 22, 0), high=50, low=40)  # 07:00 JST -> still inside actually

    # Use a candle clearly past the window end (09:00 JST = 00:00 UTC next day).
    outside = _candle(_utc(2024, 1, 16, 5, 0), high=50, low=40)  # 14:00 JST - outside

    tracker.sync([inside])
    tracker.sync([inside, outside])

    snap = tracker.snapshot()["asian"]
    assert snap["current"] is None
    assert len(snap["closed"]) == 1

    closed = snap["closed"][0]
    assert closed["is_closed"] is True
    assert closed["session_high"] == 100
    assert closed["period_start"] == _utc(2024, 1, 15, 15, 0)
    assert closed["period_end"] == _utc(2024, 1, 16, 0, 0)  # 09:00 JST


def test_new_instance_of_the_same_window_the_next_day_opens_a_fresh_session():
    definitions = [SessionWindow(name="asian", timezone="Asia/Tokyo", start_time=time(0, 0), end_time=time(9, 0))]
    tracker = SessionBoundariesTracker(definitions)

    day1 = _candle(_utc(2024, 1, 15, 15, 0), high=100, low=95)
    day2 = _candle(_utc(2024, 1, 16, 15, 0), high=200, low=190)

    tracker.sync([day1])
    tracker.sync([day1, day2])

    snap = tracker.snapshot()["asian"]
    assert len(snap["closed"]) == 1
    assert snap["closed"][0]["session_high"] == 100
    assert snap["current"]["session_high"] == 200
    assert snap["current"]["period_start"] == _utc(2024, 1, 16, 15, 0)


# =========================================================
# Wrapping window (crosses local midnight)
# =========================================================


def test_wrapping_window_groups_both_sides_of_local_midnight_into_one_session():
    # Local window 22:00 -> 02:00 (wraps). Use UTC directly as the tz
    # to keep the arithmetic simple and exact.
    definitions = [SessionWindow(name="overnight", timezone="UTC", start_time=time(22, 0), end_time=time(2, 0))]
    tracker = SessionBoundariesTracker(definitions)

    before_midnight = _candle(_utc(2024, 1, 15, 23, 0), high=100, low=95)
    after_midnight = _candle(_utc(2024, 1, 16, 1, 0), high=110, low=90)

    tracker.sync([before_midnight])
    tracker.sync([before_midnight, after_midnight])

    current = tracker.snapshot()["overnight"]["current"]
    assert current is not None  # still the SAME session instance
    assert current["period_start"] == _utc(2024, 1, 15, 22, 0)
    assert current["session_high"] == 110
    assert current["session_low"] == 90
    assert current["candle_count"] == 2


def test_wrapping_window_closes_correctly_after_end_time():
    definitions = [SessionWindow(name="overnight", timezone="UTC", start_time=time(22, 0), end_time=time(2, 0))]
    tracker = SessionBoundariesTracker(definitions)

    inside = _candle(_utc(2024, 1, 15, 23, 0), high=100, low=95)
    outside = _candle(_utc(2024, 1, 16, 5, 0), high=50, low=40)  # past 02:00

    tracker.sync([inside])
    tracker.sync([inside, outside])

    snap = tracker.snapshot()["overnight"]
    assert snap["current"] is None
    assert snap["closed"][0]["period_end"] == _utc(2024, 1, 16, 2, 0)


# =========================================================
# DST correctness - the core institutional-grade property
# =========================================================


def test_dst_shifts_the_utc_period_start_for_the_same_local_clock_time():
    # London local 08:00 in winter (GMT, UTC+0) vs summer (BST, UTC+1)
    # must map to DIFFERENT UTC instants for the exact same wall-clock
    # local start time - a fixed-UTC-window design could never do this.
    definitions = [SessionWindow(name="london", timezone="Europe/London", start_time=time(8, 0), end_time=time(16, 30))]

    winter_tracker = SessionBoundariesTracker(list(definitions))
    winter_tracker.sync([_candle(_utc(2024, 1, 15, 8, 0), high=100, low=95)])  # GMT: local 08:00 = 08:00 UTC
    winter_period_start = winter_tracker.snapshot()["london"]["current"]["period_start"]

    summer_tracker = SessionBoundariesTracker(list(definitions))
    summer_tracker.sync([_candle(_utc(2024, 7, 15, 7, 0), high=100, low=95)])  # BST: local 08:00 = 07:00 UTC
    summer_period_start = summer_tracker.snapshot()["london"]["current"]["period_start"]

    assert winter_period_start == _utc(2024, 1, 15, 8, 0)
    assert summer_period_start == _utc(2024, 7, 15, 7, 0)

    # Direct proof, not just an incidental period_start difference: a
    # candle at 07:00 UTC in winter is NOT yet 08:00 London local time
    # (still 07:00 GMT), so it must NOT open the session - only in
    # summer (BST) does 07:00 UTC equal local 08:00.
    winter_early = SessionBoundariesTracker(list(definitions))
    winter_early.sync([_candle(_utc(2024, 1, 15, 7, 0), high=1, low=1)])
    assert winter_early.snapshot()["london"]["current"] is None

    summer_early = SessionBoundariesTracker(list(definitions))
    summer_early.sync([_candle(_utc(2024, 7, 15, 7, 0), high=1, low=1)])
    assert summer_early.snapshot()["london"]["current"] is not None


# =========================================================
# CalendarPeriod - daily
# =========================================================


def test_daily_period_covers_full_utc_day_and_rolls_over_at_midnight():
    definitions = [CalendarPeriod(name="daily", timezone="UTC", period="daily")]
    tracker = SessionBoundariesTracker(definitions)

    c1 = _candle(_utc(2024, 1, 15, 10, 0), high=100, low=95)
    c2 = _candle(_utc(2024, 1, 15, 23, 59), high=120, low=90)
    c3 = _candle(_utc(2024, 1, 16, 0, 1), high=50, low=40)  # new day

    tracker.sync([c1])
    tracker.sync([c1, c2])
    tracker.sync([c1, c2, c3])

    snap = tracker.snapshot()["daily"]
    assert len(snap["closed"]) == 1
    assert snap["closed"][0]["period_start"] == _utc(2024, 1, 15, 0, 0)
    assert snap["closed"][0]["period_end"] == _utc(2024, 1, 16, 0, 0)
    assert snap["closed"][0]["session_high"] == 120
    assert snap["current"]["period_start"] == _utc(2024, 1, 16, 0, 0)
    assert snap["current"]["session_high"] == 50


def test_daily_period_never_has_a_gap_unlike_a_session_window():
    # Every candle belongs to SOME calendar day - current is never None.
    definitions = [CalendarPeriod(name="daily", timezone="UTC", period="daily")]
    tracker = SessionBoundariesTracker(definitions)

    tracker.sync([_candle(_utc(2024, 1, 15, 3, 0), high=1, low=1)])
    assert tracker.snapshot()["daily"]["current"] is not None


# =========================================================
# CalendarPeriod - weekly
# =========================================================


def test_weekly_period_anchors_to_monday_by_default():
    definitions = [CalendarPeriod(name="weekly", timezone="UTC", period="weekly", week_anchor_day=0)]
    tracker = SessionBoundariesTracker(definitions)

    # 2024-01-15 is a Monday.
    monday = _candle(_utc(2024, 1, 15, 12, 0), high=100, low=95)
    wednesday = _candle(_utc(2024, 1, 17, 12, 0), high=120, low=90)
    next_monday = _candle(_utc(2024, 1, 22, 12, 0), high=50, low=40)

    tracker.sync([monday])
    tracker.sync([monday, wednesday])
    tracker.sync([monday, wednesday, next_monday])

    snap = tracker.snapshot()["weekly"]
    assert len(snap["closed"]) == 1
    assert snap["closed"][0]["period_start"] == _utc(2024, 1, 15, 0, 0)
    assert snap["closed"][0]["period_end"] == _utc(2024, 1, 22, 0, 0)
    assert snap["closed"][0]["session_high"] == 120
    assert snap["current"]["period_start"] == _utc(2024, 1, 22, 0, 0)


def test_weekly_period_respects_custom_week_anchor_day():
    # week_anchor_day=6 (Sunday) - week starts Sunday.
    definitions = [CalendarPeriod(name="weekly", timezone="UTC", period="weekly", week_anchor_day=6)]
    tracker = SessionBoundariesTracker(definitions)

    # 2024-01-14 is a Sunday.
    sunday = _candle(_utc(2024, 1, 14, 1, 0), high=100, low=95)
    tracker.sync([sunday])

    assert tracker.snapshot()["weekly"]["current"]["period_start"] == _utc(2024, 1, 14, 0, 0)


# =========================================================
# Multiple concurrent definitions
# =========================================================


def test_multiple_definitions_tracked_independently_in_one_tracker():
    definitions = [
        SessionWindow(name="asian", timezone="Asia/Tokyo", start_time=time(0, 0), end_time=time(9, 0)),
        CalendarPeriod(name="daily", timezone="UTC", period="daily"),
    ]
    tracker = SessionBoundariesTracker(definitions)

    tracker.sync([_candle(_utc(2024, 1, 15, 15, 0), high=100, low=95)])

    snap = tracker.snapshot()
    assert set(snap.keys()) == {"asian", "daily"}
    assert snap["asian"]["current"]["session_high"] == 100
    assert snap["daily"]["current"]["session_high"] == 100
    # Independent identities even though they happen to share a value.
    assert snap["asian"]["current"]["name"] == "asian"
    assert snap["daily"]["current"]["name"] == "daily"


def test_duplicate_definition_names_are_rejected():
    with pytest.raises(ValueError):
        SessionBoundariesTracker([
            SessionWindow(name="dup", timezone="UTC", start_time=time(0, 0), end_time=time(1, 0)),
            CalendarPeriod(name="dup", timezone="UTC", period="daily"),
        ])


def test_empty_definitions_list_is_rejected():
    with pytest.raises(ValueError):
        SessionBoundariesTracker([])


# =========================================================
# Bounded history and replay safety
# =========================================================


def test_closed_history_is_bounded():
    definitions = [CalendarPeriod(name="daily", timezone="UTC", period="daily")]
    tracker = SessionBoundariesTracker(definitions, max_tracked_closed=2)

    candles = []
    for day in range(5):
        candles.append(_candle(_utc(2024, 1, 15 + day, 12, 0), high=100 + day, low=90 + day))
        tracker.sync(candles)

    snap = tracker.snapshot()["daily"]
    assert len(snap["closed"]) == 2


def test_sync_rejects_rewound_candles():
    definitions = [CalendarPeriod(name="daily", timezone="UTC", period="daily")]
    tracker = SessionBoundariesTracker(definitions)

    tracker.sync([_candle(_utc(2024, 1, 15), high=1, low=1), _candle(_utc(2024, 1, 16), high=2, low=2)])

    with pytest.raises(ValueError):
        tracker.sync([_candle(_utc(2024, 1, 15), high=1, low=1)])


def test_sync_rejects_diverging_history():
    definitions = [CalendarPeriod(name="daily", timezone="UTC", period="daily")]
    tracker = SessionBoundariesTracker(definitions)

    tracker.sync([_candle(_utc(2024, 1, 15), high=1, low=1)])

    with pytest.raises(ValueError):
        tracker.sync([_candle(_utc(2024, 1, 15), high=999, low=999)])


def test_incremental_sync_matches_single_shot_sync():
    # Unlike BreakerBlockTracker, this module has no external
    # point-in-time input - it is a pure function of OHLCV alone, so
    # batching candles per call is safe.
    definitions = [
        SessionWindow(name="asian", timezone="Asia/Tokyo", start_time=time(0, 0), end_time=time(9, 0)),
        CalendarPeriod(name="weekly", timezone="UTC", period="weekly"),
    ]

    candles = [
        _candle(_utc(2024, 1, 15, 15, 0), high=100, low=95),
        _candle(_utc(2024, 1, 16, 15, 0), high=110, low=90),
        _candle(_utc(2024, 1, 17, 5, 0), high=105, low=98),
        _candle(_utc(2024, 1, 22, 12, 0), high=50, low=40),
    ]

    single_shot = SessionBoundariesTracker(list(definitions))
    single_shot.sync(candles)

    incremental = SessionBoundariesTracker(list(definitions))
    for n in range(1, len(candles) + 1):
        incremental.sync(candles[:n])

    assert single_shot.snapshot() == incremental.snapshot()


# =========================================================
# DEFAULT_SESSIONS smoke test
# =========================================================


def test_default_sessions_preset_is_directly_usable():
    tracker = SessionBoundariesTracker(list(DEFAULT_SESSIONS))
    tracker.sync([_candle(_utc(2024, 1, 15, 9, 0), high=100, low=95)])

    snap = tracker.snapshot()
    expected_names = {d.name for d in DEFAULT_SESSIONS}
    assert set(snap.keys()) == expected_names
    assert snap["daily"]["current"] is not None  # always in session


# =========================================================
# Performance validation
# =========================================================


def test_large_history_stays_fast_and_bounded():
    candle_count = 20_000
    start = _utc(2024, 1, 1)
    candles = [
        _candle(start + timedelta(minutes=15 * i), high=100, low=95)
        for i in range(candle_count)
    ]

    tracker = SessionBoundariesTracker(list(DEFAULT_SESSIONS))

    start_time = time_module.perf_counter()

    step = 500
    for i in range(step, candle_count + 1, step):
        tracker.sync(candles[:i])

    elapsed = time_module.perf_counter() - start_time

    assert elapsed < 5.0
