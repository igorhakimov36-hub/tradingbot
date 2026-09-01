import time
from datetime import datetime, timedelta, timezone

import pytest

from strategy.features.breaker_block import BreakerBlockTracker
from strategy.features.order_block import OrderBlockTracker

START = datetime(2024, 1, 1, tzinfo=timezone.utc)


def _candle(minute_offset, open_, high, low, close, volume=10.0):
    return {
        "timestamp": START + timedelta(minutes=minute_offset),
        "open": open_,
        "high": high,
        "low": low,
        "close": close,
        "volume": volume,
    }


def _mitigated_ob(
    direction="bullish",
    zone_high=110.0,
    zone_low=100.0,
    origin_timestamp=None,
    created_at=None,
):
    """A minimal stand-in for OrderBlockTracker.snapshot()["mitigated"]
    entries - only the fields BreakerBlockTracker actually reads."""
    return {
        "direction": direction,
        "zone_high": zone_high,
        "zone_low": zone_low,
        "origin_timestamp": origin_timestamp or START,
        "created_at": created_at or START,
    }


# =========================================================
# Detection - a fully mitigated Order Block becomes a flipped Breaker
# =========================================================


def test_no_breaker_without_any_mitigated_order_blocks():
    candles = [_candle(0, 100, 101, 99, 100)]

    tracker = BreakerBlockTracker()
    tracker.sync(candles, source_mitigated=[])

    snap = tracker.snapshot()
    assert snap["active"] == []
    assert snap["mitigated"] == []


def test_bullish_order_block_flips_into_bearish_breaker():
    candles = [_candle(0, 100, 101, 99, 100)]
    mitigated_ob = _mitigated_ob(direction="bullish", zone_high=110, zone_low=100)

    tracker = BreakerBlockTracker()
    tracker.sync(candles, source_mitigated=[mitigated_ob])

    active = tracker.snapshot()["active"]
    assert len(active) == 1

    breaker = active[0]
    assert breaker["direction"] == "bearish"  # flipped
    assert breaker["zone_high"] == 110
    assert breaker["zone_low"] == 100
    assert breaker["source_direction"] == "bullish"
    assert breaker["source_origin_timestamp"] == START
    assert breaker["created_at"] == candles[0]["timestamp"]
    assert breaker["touch_count"] == 0
    assert breaker["mitigation_status"] == "unmitigated"
    assert breaker["mitigation_pct"] == 0.0


def test_bearish_order_block_flips_into_bullish_breaker():
    candles = [_candle(0, 100, 101, 99, 100)]
    mitigated_ob = _mitigated_ob(direction="bearish", zone_high=99, zone_low=95)

    tracker = BreakerBlockTracker()
    tracker.sync(candles, source_mitigated=[mitigated_ob])

    breaker = tracker.snapshot()["active"][0]
    assert breaker["direction"] == "bullish"
    assert breaker["zone_high"] == 99
    assert breaker["zone_low"] == 95


def test_same_mitigated_order_block_does_not_create_duplicate_breakers():
    mitigated_ob = _mitigated_ob()

    tracker = BreakerBlockTracker()
    tracker.sync([_candle(0, 100, 101, 99, 100)], source_mitigated=[mitigated_ob])
    tracker.sync(
        [_candle(0, 100, 101, 99, 100), _candle(1, 100, 101, 99, 100)],
        source_mitigated=[mitigated_ob],  # still the same OB, unchanged
    )

    active = tracker.snapshot()["active"]
    assert len(active) == 1


def test_two_distinct_mitigated_order_blocks_create_two_breakers():
    ob_a = _mitigated_ob(direction="bullish", zone_high=110, zone_low=100, origin_timestamp=START)
    ob_b = _mitigated_ob(
        direction="bearish",
        zone_high=130,
        zone_low=125,
        origin_timestamp=START + timedelta(minutes=1),
    )

    tracker = BreakerBlockTracker()
    tracker.sync([_candle(0, 100, 101, 99, 100)], source_mitigated=[ob_a, ob_b])

    active = tracker.snapshot()["active"]
    assert len(active) == 2
    directions = {b["direction"] for b in active}
    assert directions == {"bearish", "bullish"}


def test_same_origin_candle_reused_by_two_order_blocks_creates_two_breakers():
    # Discovered validating against real BTCUSDT data: the same origin
    # candle can legitimately become the origin of two distinct Order
    # Blocks confirmed at different times (see _source_key()'s
    # docstring in breaker_block.py). Only created_at differs.
    ob_first = _mitigated_ob(
        direction="bullish",
        zone_high=110,
        zone_low=100,
        origin_timestamp=START,
        created_at=START + timedelta(minutes=5),
    )
    ob_second = _mitigated_ob(
        direction="bullish",
        zone_high=110,
        zone_low=100,
        origin_timestamp=START,  # identical origin candle
        created_at=START + timedelta(minutes=20),  # different BOS confirmation
    )

    tracker = BreakerBlockTracker()
    tracker.sync([_candle(0, 100, 101, 99, 100)], source_mitigated=[ob_first])
    tracker.sync(
        [_candle(0, 100, 101, 99, 100), _candle(1, 100, 101, 99, 100)],
        source_mitigated=[ob_first, ob_second],
    )

    active = tracker.snapshot()["active"]
    assert len(active) == 2  # not deduplicated away


def test_breakers_distinguished_by_composite_key_not_just_direction():
    # Two different bullish OBs (different zones) both mitigated in the
    # same step must both become separate bearish breakers.
    ob_a = _mitigated_ob(zone_high=110, zone_low=100, origin_timestamp=START)
    ob_b = _mitigated_ob(zone_high=95, zone_low=90, origin_timestamp=START + timedelta(minutes=1))

    tracker = BreakerBlockTracker()
    tracker.sync([_candle(0, 100, 101, 99, 100)], source_mitigated=[ob_a, ob_b])

    active = tracker.snapshot()["active"]
    assert len(active) == 2
    zones = {(b["zone_high"], b["zone_low"]) for b in active}
    assert zones == {(110.0, 100.0), (95.0, 90.0)}


# =========================================================
# Breaker's own lifecycle - touch / mitigation / impulse
# =========================================================


def test_breaker_touch_count_and_mitigation_progress():
    mitigated_ob = _mitigated_ob(direction="bullish", zone_high=110, zone_low=100)

    candles = [
        _candle(0, 100, 101, 99, 100),  # creation candle
        _candle(1, 100, 106, 100, 105),  # touches the new bearish breaker [100,110]
        _candle(2, 105, 108, 103, 107),  # still touching
    ]

    tracker = BreakerBlockTracker()
    tracker.sync(candles[:1], source_mitigated=[mitigated_ob])
    tracker.sync(candles[:2], source_mitigated=[mitigated_ob])
    tracker.sync(candles[:3], source_mitigated=[mitigated_ob])

    breaker = tracker.snapshot()["active"][0]
    assert breaker["direction"] == "bearish"
    assert breaker["touch_count"] == 1  # one contiguous touch, not per-candle
    assert breaker["mitigation_status"] == "partially_mitigated"
    assert breaker["mitigation_pct"] == pytest.approx(0.8)  # deepest close=108->(108-100)/10


def test_breaker_moves_to_mitigated_list_when_fully_filled():
    mitigated_ob = _mitigated_ob(direction="bullish", zone_high=110, zone_low=100)

    candles = [
        _candle(0, 100, 101, 99, 100),  # creation -> bearish breaker [100,110]
        _candle(1, 100, 112, 100, 111),  # fully fills the breaker (high >= 110)
    ]

    tracker = BreakerBlockTracker()
    tracker.sync(candles[:1], source_mitigated=[mitigated_ob])
    tracker.sync(candles[:2], source_mitigated=[mitigated_ob])

    snap = tracker.snapshot()
    assert snap["active"] == []
    assert len(snap["mitigated"]) == 1
    assert snap["mitigated"][0]["mitigation_status"] == "fully_mitigated"


def test_fully_mitigated_breaker_is_retired_not_flipped_again():
    mitigated_ob = _mitigated_ob(direction="bullish", zone_high=110, zone_low=100)

    candles = [
        _candle(0, 100, 101, 99, 100),
        _candle(1, 100, 112, 100, 111),  # fills the breaker fully
        _candle(2, 111, 115, 109, 113),  # extra candles afterwards
        _candle(3, 113, 116, 111, 114),
    ]

    tracker = BreakerBlockTracker()
    for n in range(1, len(candles) + 1):
        tracker.sync(candles[:n], source_mitigated=[mitigated_ob])

    snap = tracker.snapshot()
    assert snap["active"] == []
    assert len(snap["mitigated"]) == 1  # stays retired, no duplicate resurrection


def test_impulse_strength_reflects_favorable_move_after_creation():
    mitigated_ob = _mitigated_ob(direction="bullish", zone_high=110, zone_low=100)

    candles = [
        _candle(0, 100, 101, 99, 100),  # ATR at creation will be current() = None (no history yet)
        _candle(1, 100, 101, 99, 100),
    ]

    tracker = BreakerBlockTracker(atr_period=1)
    tracker.sync(candles[:1], source_mitigated=[mitigated_ob])
    # second sync only advances candle history, does not re-detect
    tracker.sync(candles[:2], source_mitigated=[mitigated_ob])

    breaker = tracker.snapshot()["active"][0]
    # No favorable (upward, since it's now bearish) excursion yet beyond
    # zone_high -> impulse should be 0 or None depending on ATR
    assert breaker["impulse_strength"] in (0.0, None)


# =========================================================
# Replay safety / incremental vs single-shot consistency
# =========================================================


def test_sync_rejects_rewound_candles():
    tracker = BreakerBlockTracker()
    tracker.sync([_candle(0, 100, 101, 99, 100)], source_mitigated=[])
    tracker.sync([_candle(0, 100, 101, 99, 100), _candle(1, 100, 101, 99, 100)], source_mitigated=[])

    with pytest.raises(ValueError):
        tracker.sync([_candle(0, 100, 101, 99, 100)], source_mitigated=[])


def test_sync_rejects_diverging_history():
    tracker = BreakerBlockTracker()
    tracker.sync([_candle(0, 100, 101, 99, 100)], source_mitigated=[])

    diverged = [_candle(0, 999, 999, 999, 999)]  # same length, different content
    with pytest.raises(ValueError):
        tracker.sync(diverged, source_mitigated=[])


def test_sync_rejects_batching_more_than_one_new_candle():
    # source_mitigated is a point-in-time snapshot, not a historical
    # record like candles - a multi-candle batch behind one snapshot
    # would misattribute when a breaker was actually created (see
    # sync()'s docstring). Discovered empirically on real BTCUSDT data.
    candles = [
        _candle(0, 100, 101, 99, 100),
        _candle(1, 100, 106, 100, 105),
    ]

    tracker = BreakerBlockTracker()
    with pytest.raises(ValueError):
        tracker.sync(candles, source_mitigated=[])


def test_two_independent_incremental_replays_are_deterministic():
    mitigated_ob = _mitigated_ob(direction="bullish", zone_high=110, zone_low=100)

    candles = [
        _candle(0, 100, 101, 99, 100),
        _candle(1, 100, 106, 100, 105),
        _candle(2, 105, 108, 103, 107),
        _candle(3, 107, 109, 104, 106),
    ]

    replay_a = BreakerBlockTracker()
    replay_b = BreakerBlockTracker()

    for n in range(1, len(candles) + 1):
        replay_a.sync(candles[:n], source_mitigated=[mitigated_ob])
        replay_b.sync(candles[:n], source_mitigated=[mitigated_ob])

    assert replay_a.snapshot() == replay_b.snapshot()


# =========================================================
# Pruning - age-based expiry and bounded mitigated history
# =========================================================


def test_stale_active_breaker_is_expired_after_max_age():
    mitigated_ob = _mitigated_ob(direction="bullish", zone_high=110, zone_low=100)

    tracker = BreakerBlockTracker(max_age_bars=2)
    candles = [_candle(0, 100, 101, 99, 100)]
    tracker.sync(candles, source_mitigated=[mitigated_ob])

    for i in range(1, 5):
        candles.append(_candle(i, 100, 101, 99, 100))
        tracker.sync(candles, source_mitigated=[mitigated_ob])

    snap = tracker.snapshot()
    assert snap["active"] == []
    assert snap["expired_count"] == 1


def test_mitigated_list_is_bounded():
    tracker = BreakerBlockTracker(max_tracked_mitigated=2)

    candles = []
    mitigated_obs = []

    for i in range(4):
        origin_ts = START + timedelta(minutes=i)
        ob = _mitigated_ob(
            direction="bullish",
            zone_high=110 + i,
            zone_low=100 + i,
            origin_timestamp=origin_ts,
        )
        mitigated_obs.append(ob)

        # creation candle
        candles.append(_candle(len(candles), 100, 101, 99, 100))
        tracker.sync(candles, source_mitigated=mitigated_obs)

        # candle that immediately fully fills this breaker
        candles.append(_candle(len(candles), 100, 200, 100, 150))
        tracker.sync(candles, source_mitigated=mitigated_obs)

    snap = tracker.snapshot()
    assert len(snap["mitigated"]) == 2


# =========================================================
# Distance from price
# =========================================================


def test_distance_from_price_zero_when_price_inside_zone():
    mitigated_ob = _mitigated_ob(direction="bullish", zone_high=110, zone_low=100)
    candles = [_candle(0, 100, 106, 104, 105)]  # close=105, inside [100,110]

    tracker = BreakerBlockTracker()
    tracker.sync(candles, source_mitigated=[mitigated_ob])

    breaker = tracker.snapshot()["active"][0]
    assert breaker["distance_from_price"] == 0.0


def test_distance_from_price_positive_when_price_outside_zone():
    mitigated_ob = _mitigated_ob(direction="bullish", zone_high=110, zone_low=100)
    candles = [_candle(0, 120, 121, 119, 120)]  # close=120, above zone_high=110

    tracker = BreakerBlockTracker()
    tracker.sync(candles, source_mitigated=[mitigated_ob])

    breaker = tracker.snapshot()["active"][0]
    assert breaker["distance_from_price"] == pytest.approx(10.0)


# =========================================================
# Integration - wired to a real OrderBlockTracker
# =========================================================


def _bullish_ob_setup():
    """Same hand-traced sequence as test_order_block_feature.py's
    _bullish_setup(): produces one bullish Order Block at [101, 105],
    confirmed at minute 7."""
    return [
        _candle(0, 100, 101, 99, 100),
        _candle(1, 100, 102, 88, 101),
        _candle(2, 101, 103, 95, 102),
        _candle(3, 102, 110, 100, 103),
        _candle(4, 104, 105, 101, 101, volume=50.0),
        _candle(5, 101, 104, 100, 103),
        _candle(6, 103, 108, 102, 107),
        _candle(7, 107, 112, 106, 111),
    ]


def test_wired_to_real_order_block_tracker_end_to_end():
    # Drive the Order Block all the way to full mitigation, then keep
    # going far enough for a real BreakerBlockTracker (fed only the
    # public snapshot()["mitigated"] contract, per the documented
    # ordering: Order Blocks synced first, then Breaker Blocks) to pick
    # it up and flip it.
    candles = _bullish_ob_setup() + [
        _candle(8, 111, 112, 100, 101),  # wicks back down through [101,105] -> fully mitigates the OB
        _candle(9, 101, 103, 99, 100),  # touches the resulting bearish breaker zone [101,105]
        _candle(10, 100, 102, 99, 101),  # still touching, not deep enough to refill it
    ]

    ob_tracker = OrderBlockTracker()
    breaker_tracker = BreakerBlockTracker()

    for i in range(1, len(candles) + 1):
        step = candles[:i]
        ob_tracker.sync(step)
        breaker_tracker.sync(step, source_mitigated=ob_tracker.snapshot()["mitigated"])

    ob_snapshot = ob_tracker.snapshot()
    assert len(ob_snapshot["mitigated"]) == 1

    breaker_snapshot = breaker_tracker.snapshot()
    assert len(breaker_snapshot["active"]) == 1

    breaker = breaker_snapshot["active"][0]
    assert breaker["direction"] == "bearish"
    assert breaker["zone_high"] == 105.0
    assert breaker["zone_low"] == 101.0
    assert breaker["source_direction"] == "bullish"
    assert breaker["touch_count"] == 1


# =========================================================
# Performance validation
# =========================================================


def test_large_history_stays_fast_and_bounded():
    # One new candle per call, matching the enforced contract - unlike
    # OrderBlockTracker's own performance test, this cannot batch
    # multiple candles per sync() (source_mitigated is point-in-time).
    candle_count = 20_000
    candles = [_candle(i, 100, 101, 99, 100) for i in range(candle_count)]

    tracker = BreakerBlockTracker()

    start_time = time.perf_counter()

    for i in range(1, candle_count + 1):
        tracker.sync(candles[:i], source_mitigated=[])

    elapsed = time.perf_counter() - start_time

    assert elapsed < 5.0
    assert tracker.snapshot()["active"] == []
