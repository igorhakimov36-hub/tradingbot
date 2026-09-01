import time as time_module
from datetime import datetime, timedelta, timezone

import pytest

from strategy.features.liquidity_pool import LiquidityPoolTracker

START = datetime(2024, 1, 1, tzinfo=timezone.utc)


def _candle(minute_offset, high, low, close=None, volume=10.0):
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


def _eqh(level, created_at, direction="equal_highs"):
    return {"direction": direction, "level": level, "created_at": created_at}


def _eql(level, created_at):
    return _eqh(level, created_at, direction="equal_lows")


def _empty_equal_levels():
    return {"equal_highs": [], "equal_lows": [], "expired_count": 0}


def _empty_sessions():
    return {}


def _session_snapshot(**closed_by_name):
    return {name: {"current": None, "closed": periods} for name, periods in closed_by_name.items()}


def _session_period(period_start, session_high, high_ts, session_low, low_ts):
    return {
        "period_start": period_start,
        "session_high": session_high,
        "high_timestamp": high_ts,
        "session_low": session_low,
        "low_timestamp": low_ts,
    }


# ATR is unavailable (None -> tolerance 0.0) until the 3rd candle has
# been processed - the same one-candle-delay convention as every other
# ATR-relative module in this package (FVG, Order Blocks: "ATR computed
# BEFORE the impulsive candle is folded in, avoids self-referential
# inflation"). Every test below warms up with two plain candles (empty
# snapshots, no candidates) before registering anything that needs a
# nonzero tolerance to cluster.
WARM_UP = [_candle(-2, 101, 99), _candle(-1, 101, 99)]

# A separate warm-up range for round-number tests: 101/99 straddles the
# spacing=100.0 round number those tests use, which would make the
# warm-up candles themselves register phantom round-number touches at
# exactly 100.0 - contaminating the very level being tested. Offset
# away from any multiple of 100 instead.
WARM_UP_OFFSET = [_candle(-2, 131, 129), _candle(-1, 131, 129)]


def _warm_up(tracker: LiquidityPoolTracker, candles: list[dict] = WARM_UP) -> list[dict]:
    history = []

    for candle in candles:
        history.append(candle)
        tracker.sync(history, equal_levels_snapshot=_empty_equal_levels(), session_snapshot=_empty_sessions())

    return history


# =========================================================
# Basic pool formation
# =========================================================


def test_lone_candidate_does_not_form_a_pool():
    tracker = LiquidityPoolTracker()
    candles = _warm_up(tracker)

    candles.append(_candle(0, 101, 99))
    tracker.sync(
        candles,
        equal_levels_snapshot={"equal_highs": [_eqh(100.0, START)], "equal_lows": [], "expired_count": 0},
        session_snapshot=_empty_sessions(),
    )

    assert tracker.snapshot()["active"] == []


def test_two_equal_highs_clusters_within_tolerance_form_a_buy_side_pool():
    tracker = LiquidityPoolTracker()
    candles = _warm_up(tracker)

    candles.append(_candle(0, 101, 99))
    tracker.sync(
        candles,
        equal_levels_snapshot={"equal_highs": [_eqh(100.0, START)], "equal_lows": [], "expired_count": 0},
        session_snapshot=_empty_sessions(),
    )

    candles.append(_candle(1, 101, 99))
    tracker.sync(
        candles,
        equal_levels_snapshot={
            "equal_highs": [_eqh(100.0, START), _eqh(100.05, START + timedelta(minutes=1))],
            "equal_lows": [],
            "expired_count": 0,
        },
        session_snapshot=_empty_sessions(),
    )

    active = tracker.snapshot()["active"]
    assert len(active) == 1

    pool = active[0]
    assert pool["direction"] == "buy_side"
    assert pool["zone_high"] == 100.05
    assert pool["zone_low"] == 100.0
    assert pool["level"] == pytest.approx(100.025)
    assert pool["touch_count"] == 2
    assert pool["sources"] == ["equal_highs"]
    assert pool["swept_status"] == "unswept"


def test_equal_lows_clusters_form_a_sell_side_pool():
    tracker = LiquidityPoolTracker()
    candles = _warm_up(tracker)

    candles.append(_candle(0, 101, 99))
    tracker.sync(candles, equal_levels_snapshot=_empty_equal_levels(), session_snapshot=_empty_sessions())

    candles.append(_candle(1, 101, 99))
    tracker.sync(
        candles,
        equal_levels_snapshot={"equal_highs": [], "equal_lows": [_eql(50.0, START), _eql(50.02, START + timedelta(minutes=1))], "expired_count": 0},
        session_snapshot=_empty_sessions(),
    )

    active = tracker.snapshot()["active"]
    assert len(active) == 1
    assert active[0]["direction"] == "sell_side"
    assert active[0]["zone_low"] == 50.0
    assert active[0]["zone_high"] == 50.02


def test_candidates_outside_tolerance_stay_separate_lone_candidates():
    tracker = LiquidityPoolTracker()
    candles = _warm_up(tracker)

    candles.append(_candle(0, 101, 99))
    tracker.sync(
        candles,
        equal_levels_snapshot={
            "equal_highs": [_eqh(100.0, START), _eqh(500.0, START)],
            "equal_lows": [],
            "expired_count": 0,
        },
        session_snapshot=_empty_sessions(),
    )

    assert tracker.snapshot()["active"] == []


def test_third_candidate_extends_an_existing_pool():
    tracker = LiquidityPoolTracker()
    candles = _warm_up(tracker)

    candles.append(_candle(0, 101, 99))
    tracker.sync(candles, equal_levels_snapshot={"equal_highs": [_eqh(100.0, START)], "equal_lows": [], "expired_count": 0}, session_snapshot=_empty_sessions())

    candles.append(_candle(1, 101, 99))
    tracker.sync(
        candles,
        equal_levels_snapshot={"equal_highs": [_eqh(100.0, START), _eqh(100.02, START + timedelta(minutes=1))], "equal_lows": [], "expired_count": 0},
        session_snapshot=_empty_sessions(),
    )

    # Stays within the pool's existing zone [100.0, 100.02] - a filler
    # candle wide enough to exceed the zone (like the 101/99 warm-up
    # shape) would trigger an accidental sweep before the extension is
    # even registered.
    candles.append(_candle(2, 100.02, 100.0))
    tracker.sync(
        candles,
        equal_levels_snapshot={
            "equal_highs": [_eqh(100.0, START), _eqh(100.02, START + timedelta(minutes=1)), _eqh(100.01, START + timedelta(minutes=2))],
            "equal_lows": [],
            "expired_count": 0,
        },
        session_snapshot=_empty_sessions(),
    )

    active = tracker.snapshot()["active"]
    assert len(active) == 1
    assert active[0]["touch_count"] == 3
    assert active[0]["zone_high"] == 100.02
    assert active[0]["zone_low"] == 100.0


# =========================================================
# Mixed sources - the "composite/aggregator" property
# =========================================================


def test_pool_can_form_from_a_mix_of_equal_highs_and_session_high():
    tracker = LiquidityPoolTracker()
    candles = _warm_up(tracker)

    candles.append(_candle(0, 101, 99))
    tracker.sync(
        candles,
        equal_levels_snapshot={"equal_highs": [_eqh(100.0, START)], "equal_lows": [], "expired_count": 0},
        session_snapshot=_empty_sessions(),
    )

    candles.append(_candle(1, 101, 99))
    tracker.sync(
        candles,
        equal_levels_snapshot={"equal_highs": [_eqh(100.0, START)], "equal_lows": [], "expired_count": 0},
        session_snapshot=_session_snapshot(
            asian=[_session_period(START, 100.03, START + timedelta(minutes=1), 90.0, START)]
        ),
    )

    active = tracker.snapshot()["active"]
    assert len(active) == 1
    assert set(active[0]["sources"]) == {"equal_highs", "session_high"}


def test_round_number_touch_combines_with_equal_highs_cluster():
    tracker = LiquidityPoolTracker(round_number_spacing=100.0)
    candles = _warm_up(tracker, WARM_UP_OFFSET)

    # Stays near the EQH cluster itself (100.05) without crossing the
    # round number 100.0 yet - only the EQH candidate should register.
    candles.append(_candle(0, 100.06, 100.04))
    tracker.sync(candles, equal_levels_snapshot={"equal_highs": [_eqh(100.05, START)], "equal_lows": [], "expired_count": 0}, session_snapshot=_empty_sessions())
    assert tracker.snapshot()["active"] == []

    candles.append(_candle(1, 100.5, 99.5))  # NOW crosses the round number 100.0
    tracker.sync(
        candles,
        equal_levels_snapshot={"equal_highs": [_eqh(100.05, START)], "equal_lows": [], "expired_count": 0},
        session_snapshot=_empty_sessions(),
    )

    active = tracker.snapshot()["active"]
    assert len(active) == 1
    assert "round_number" in active[0]["sources"]
    assert "equal_highs" in active[0]["sources"]


def test_round_number_disabled_by_default():
    tracker = LiquidityPoolTracker()  # round_number_spacing=None
    candles = _warm_up(tracker)

    candles.append(_candle(0, 100.5, 99.5))  # crosses 100.0 but round numbers are off
    tracker.sync(candles, equal_levels_snapshot=_empty_equal_levels(), session_snapshot=_empty_sessions())

    candles.append(_candle(1, 200.5, 199.5))  # crosses 200.0
    tracker.sync(candles, equal_levels_snapshot=_empty_equal_levels(), session_snapshot=_empty_sessions())

    assert tracker.snapshot()["active"] == []


def test_round_number_touches_test_both_directions_independently():
    tracker = LiquidityPoolTracker(round_number_spacing=100.0)
    candles = _warm_up(tracker, WARM_UP_OFFSET)

    candles.append(_candle(0, 100.5, 99.5))  # touches 100.0
    tracker.sync(candles, equal_levels_snapshot=_empty_equal_levels(), session_snapshot=_empty_sessions())

    candles.append(_candle(1, 100.5, 99.5))  # touches 100.0 again
    tracker.sync(candles, equal_levels_snapshot=_empty_equal_levels(), session_snapshot=_empty_sessions())

    active = tracker.snapshot()["active"]
    directions = {p["direction"] for p in active}
    assert directions == {"buy_side", "sell_side"}  # same round number seeds a pool on BOTH sides


# =========================================================
# Sweep detection and retirement
# =========================================================


def test_buy_side_pool_swept_when_wick_beyond_zone_high_closes_back_inside():
    tracker = LiquidityPoolTracker()
    candles = _warm_up(tracker)

    candles.append(_candle(0, 101, 99))
    tracker.sync(candles, equal_levels_snapshot={"equal_highs": [_eqh(100.0, START)], "equal_lows": [], "expired_count": 0}, session_snapshot=_empty_sessions())

    eqh_snapshot = {"equal_highs": [_eqh(100.0, START), _eqh(100.02, START + timedelta(minutes=1))], "equal_lows": [], "expired_count": 0}
    candles.append(_candle(1, 101, 99))
    tracker.sync(candles, equal_levels_snapshot=eqh_snapshot, session_snapshot=_empty_sessions())

    sweeping_candle = _candle(2, high=105, low=99, close=100.01)  # wicks above zone_high(100.02), closes back inside
    candles.append(sweeping_candle)
    tracker.sync(candles, equal_levels_snapshot=eqh_snapshot, session_snapshot=_empty_sessions())

    snap = tracker.snapshot()
    assert snap["active"] == []
    assert len(snap["swept"]) == 1

    swept = snap["swept"][0]
    assert swept["swept_status"] == "swept"
    assert swept["swept_timestamp"] == sweeping_candle["timestamp"]
    assert swept["sweep_penetration"] is not None
    assert swept["sweep_rejection"] is not None
    assert swept["sweep_penetration"] > 0
    assert swept["sweep_rejection"] > 0


def test_sell_side_pool_swept_when_wick_beyond_zone_low_closes_back_inside():
    tracker = LiquidityPoolTracker()
    candles = _warm_up(tracker)

    candles.append(_candle(0, 101, 99))
    tracker.sync(candles, equal_levels_snapshot=_empty_equal_levels(), session_snapshot=_empty_sessions())

    eql_snapshot = {"equal_highs": [], "equal_lows": [_eql(50.0, START), _eql(50.02, START + timedelta(minutes=1))], "expired_count": 0}
    candles.append(_candle(1, 101, 99))
    tracker.sync(candles, equal_levels_snapshot=eql_snapshot, session_snapshot=_empty_sessions())

    sweeping_candle = _candle(2, high=51, low=45, close=50.01)  # wicks below zone_low(50.0), closes back above
    candles.append(sweeping_candle)
    tracker.sync(candles, equal_levels_snapshot=eql_snapshot, session_snapshot=_empty_sessions())

    snap = tracker.snapshot()
    assert snap["active"] == []
    assert len(snap["swept"]) == 1
    assert snap["swept"][0]["swept_status"] == "swept"


def test_swept_pool_is_retired_and_new_touch_starts_a_fresh_pool():
    tracker = LiquidityPoolTracker()
    candles = _warm_up(tracker)

    candles.append(_candle(0, 101, 99))
    tracker.sync(candles, equal_levels_snapshot={"equal_highs": [_eqh(100.0, START)], "equal_lows": [], "expired_count": 0}, session_snapshot=_empty_sessions())

    eqh_snapshot_2 = {"equal_highs": [_eqh(100.0, START), _eqh(100.02, START + timedelta(minutes=1))], "equal_lows": [], "expired_count": 0}
    candles.append(_candle(1, 101, 99))
    tracker.sync(candles, equal_levels_snapshot=eqh_snapshot_2, session_snapshot=_empty_sessions())

    sweeping = _candle(2, high=105, low=99, close=100.01)
    candles.append(sweeping)
    tracker.sync(candles, equal_levels_snapshot=eqh_snapshot_2, session_snapshot=_empty_sessions())

    eqh_snapshot_3 = {
        "equal_highs": [
            _eqh(100.0, START),
            _eqh(100.02, START + timedelta(minutes=1)),
            _eqh(100.01, START + timedelta(minutes=3)),  # new candidate near the OLD (now-swept) zone
        ],
        "equal_lows": [],
        "expired_count": 0,
    }
    after = _candle(3, 101, 99)
    candles.append(after)
    tracker.sync(candles, equal_levels_snapshot=eqh_snapshot_3, session_snapshot=_empty_sessions())

    snap = tracker.snapshot()
    assert len(snap["swept"]) == 1
    # The new candidate near the swept zone is only a LONE candidate so
    # far (only one new touch since the sweep) - no new pool yet.
    assert snap["active"] == []


# =========================================================
# Replay safety
# =========================================================


def test_sync_rejects_rewound_candles():
    tracker = LiquidityPoolTracker()
    candles = _warm_up(tracker)

    with pytest.raises(ValueError):
        tracker.sync(candles[:0], equal_levels_snapshot=_empty_equal_levels(), session_snapshot=_empty_sessions())


def test_sync_rejects_diverging_history():
    tracker = LiquidityPoolTracker()
    _warm_up(tracker)

    with pytest.raises(ValueError):
        tracker.sync([_candle(-2, 999, 998), _candle(-1, 999, 998)], equal_levels_snapshot=_empty_equal_levels(), session_snapshot=_empty_sessions())


def test_sync_rejects_batching_more_than_one_new_candle():
    tracker = LiquidityPoolTracker()

    with pytest.raises(ValueError):
        tracker.sync(
            [_candle(0, 101, 99), _candle(1, 101, 99)],
            equal_levels_snapshot=_empty_equal_levels(),
            session_snapshot=_empty_sessions(),
        )


def test_two_independent_incremental_replays_are_deterministic():
    eqh_snapshot = {"equal_highs": [_eqh(100.0, START), _eqh(100.02, START + timedelta(minutes=1))], "equal_lows": [], "expired_count": 0}

    replay_a = LiquidityPoolTracker()
    replay_b = LiquidityPoolTracker()

    candles_a = _warm_up(replay_a)
    candles_b = _warm_up(replay_b)

    for i in range(3):
        candles_a.append(_candle(i, 101, 99))
        candles_b.append(_candle(i, 101, 99))
        replay_a.sync(candles_a, equal_levels_snapshot=eqh_snapshot, session_snapshot=_empty_sessions())
        replay_b.sync(candles_b, equal_levels_snapshot=eqh_snapshot, session_snapshot=_empty_sessions())

    assert replay_a.snapshot() == replay_b.snapshot()


# =========================================================
# Pruning
# =========================================================


def test_pending_candidates_list_is_bounded():
    tracker = LiquidityPoolTracker(max_tracked_pending=2)
    candles = _warm_up(tracker)

    for i in range(4):
        candles.append(_candle(i, 101, 99))
        # Each candidate is far from all others (spacing 1000) so none cluster.
        snapshot = {"equal_highs": [_eqh(1000.0 * (i + 1), START + timedelta(minutes=i))], "equal_lows": [], "expired_count": 0}
        tracker.sync(candles, equal_levels_snapshot=snapshot, session_snapshot=_empty_sessions())

    assert len(tracker._pending_buy_side) == 2


def test_stale_active_pool_is_expired_after_max_age():
    tracker = LiquidityPoolTracker(max_age_bars=2)
    candles = _warm_up(tracker)

    candles.append(_candle(0, 101, 99))
    tracker.sync(candles, equal_levels_snapshot={"equal_highs": [_eqh(100.0, START)], "equal_lows": [], "expired_count": 0}, session_snapshot=_empty_sessions())

    eqh_snapshot = {"equal_highs": [_eqh(100.0, START), _eqh(100.01, START + timedelta(minutes=1))], "equal_lows": [], "expired_count": 0}
    candles.append(_candle(1, 101, 99))
    tracker.sync(candles, equal_levels_snapshot=eqh_snapshot, session_snapshot=_empty_sessions())

    # Stays within the pool's zone [100.0, 100.01] so it ages out via
    # max_age_bars rather than being accidentally swept by a filler
    # candle wide enough to wick beyond the zone.
    for i in range(2, 6):
        candles.append(_candle(i, 100.01, 100.0))
        tracker.sync(candles, equal_levels_snapshot=eqh_snapshot, session_snapshot=_empty_sessions())

    snap = tracker.snapshot()
    assert snap["active"] == []
    assert snap["expired_count"] == 1


# =========================================================
# Distance from price
# =========================================================


def test_distance_from_price():
    tracker = LiquidityPoolTracker()
    candles = _warm_up(tracker)

    candles.append(_candle(0, 101, 99))
    tracker.sync(candles, equal_levels_snapshot={"equal_highs": [_eqh(100.0, START)], "equal_lows": [], "expired_count": 0}, session_snapshot=_empty_sessions())

    candles.append(_candle(1, high=101, low=99, close=80.0))  # current price far below the pool
    tracker.sync(
        candles,
        equal_levels_snapshot={"equal_highs": [_eqh(100.0, START), _eqh(100.02, START + timedelta(minutes=1))], "equal_lows": [], "expired_count": 0},
        session_snapshot=_empty_sessions(),
    )

    active = tracker.snapshot()["active"]
    assert active[0]["distance_from_price"] == pytest.approx(20.0)


# =========================================================
# Integration - wired to real EqualLevelsTracker + SessionBoundariesTracker
# =========================================================


def test_wired_to_real_upstream_trackers_end_to_end():
    from strategy.features.equal_highs_lows import EqualLevelsTracker
    from strategy.features.session_boundaries import CalendarPeriod, SessionBoundariesTracker

    candles = [
        _candle(0, 90, 85),
        _candle(1, 95, 88),
        _candle(2, 100, 90),  # pivot 1 candidate (confirmed 1 bar later)
        _candle(3, 92, 87),
        _candle(4, 96, 89),
        _candle(5, 100.5, 90),  # pivot 2 candidate
        _candle(6, 93, 86),
    ]

    eq_tracker = EqualLevelsTracker()
    session_tracker = SessionBoundariesTracker([CalendarPeriod(name="daily", timezone="UTC", period="daily")])
    pool_tracker = LiquidityPoolTracker()

    for i in range(1, len(candles) + 1):
        step = candles[:i]
        eq_tracker.sync(step)
        session_tracker.sync(step)
        pool_tracker.sync(
            step,
            equal_levels_snapshot=eq_tracker.snapshot(),
            session_snapshot=session_tracker.snapshot(),
        )

    # Whatever EqualLevelsTracker actually detected, LiquidityPoolTracker
    # must not have invented anything - just confirm the wiring runs
    # end-to-end without error and produces internally consistent output.
    snap = pool_tracker.snapshot()
    for pool in snap["active"] + snap["swept"]:
        assert pool["touch_count"] == len(pool["contributing_touches"])
        assert pool["zone_high"] >= pool["zone_low"]


# =========================================================
# Performance validation
# =========================================================


def test_large_history_stays_fast_and_bounded():
    candle_count = 20_000
    candles = [_candle(i, 101, 99) for i in range(candle_count)]

    tracker = LiquidityPoolTracker()

    start_time = time_module.perf_counter()

    for i in range(1, candle_count + 1):
        tracker.sync(candles[:i], equal_levels_snapshot=_empty_equal_levels(), session_snapshot=_empty_sessions())

    elapsed = time_module.perf_counter() - start_time

    assert elapsed < 5.0
