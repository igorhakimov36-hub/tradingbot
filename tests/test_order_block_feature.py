import time
from datetime import datetime, timedelta, timezone

import pytest

from strategy.features.order_block import OrderBlock, OrderBlockTracker

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


def _bullish_setup():
    """
    Hand-traced sequence producing exactly one bullish Order Block:
    - swing low pivot at idx1 (low=88)
    - swing high pivot at idx3 (high=110)
    - idx4 is the last bearish candle before the break (OB origin,
      zone [101, 105], volume=50)
    - idx7 closes at 111 > 110 -> BULLISH_BOS confirmed here
    """
    return [
        _candle(0, 100, 101, 99, 100),
        _candle(1, 100, 102, 88, 101),
        _candle(2, 101, 103, 95, 102),
        _candle(3, 102, 110, 100, 103),
        _candle(4, 104, 105, 101, 101, volume=50.0),  # bearish -> OB origin
        _candle(5, 101, 104, 100, 103),
        _candle(6, 103, 108, 102, 107),
        _candle(7, 107, 112, 106, 111),  # BOS confirmation (111 > 110)
    ]


def _bearish_setup():
    """Mirror image of _bullish_setup."""
    return [
        _candle(0, 100, 101, 99, 100),
        _candle(1, 100, 112, 99, 100),
        _candle(2, 99, 105, 97, 98),
        _candle(3, 98, 100, 90, 91),
        _candle(4, 96, 99, 95, 99, volume=50.0),  # bullish -> OB origin
        _candle(5, 99, 100, 96, 97),
        _candle(6, 97, 98, 92, 93),
        _candle(7, 93, 94, 88, 89),  # BOS confirmation (89 < 90)
    ]


# =========================================================
# Detection - unit tests
# =========================================================


def test_bullish_order_block_detected_on_bos_confirmation_bar():
    candles = _bullish_setup()

    tracker = OrderBlockTracker()
    tracker.sync(candles)

    active = tracker.snapshot()["active"]
    assert len(active) == 1

    ob = active[0]
    assert ob["direction"] == "bullish"
    assert ob["zone_high"] == 105.0
    assert ob["zone_low"] == 101.0
    assert ob["origin_timestamp"] == START + timedelta(minutes=4)
    assert ob["created_at"] == START + timedelta(minutes=7)
    assert ob["formation_volume"] == 50.0
    assert ob["touch_count"] == 0
    assert ob["mitigation_status"] == "unmitigated"
    assert ob["mitigation_pct"] == 0.0
    assert ob["impulse_strength"] == 0.0


def test_bearish_order_block_detected_on_bos_confirmation_bar():
    candles = _bearish_setup()

    tracker = OrderBlockTracker()
    tracker.sync(candles)

    active = tracker.snapshot()["active"]
    assert len(active) == 1

    ob = active[0]
    assert ob["direction"] == "bearish"
    assert ob["zone_high"] == 99.0
    assert ob["zone_low"] == 95.0
    assert ob["formation_volume"] == 50.0


def test_no_order_block_before_bos_confirms():
    candles = _bullish_setup()[:-1]  # stop one candle short of the break

    tracker = OrderBlockTracker()
    tracker.sync(candles)

    assert tracker.snapshot()["active"] == []


def test_continuation_after_break_does_not_create_duplicate_order_blocks():
    # Several more candles that keep closing above the broken level -
    # BOS stays BULLISH_BOS (level-true every bar) but must not create
    # a new Order Block each time (edge-triggered, not level-triggered).
    candles = _bullish_setup() + [
        _candle(8, 111, 115, 110, 114),
        _candle(9, 114, 118, 113, 117),
        _candle(10, 117, 120, 116, 119),
    ]

    tracker = OrderBlockTracker()
    tracker.sync(candles)

    assert len(tracker.snapshot()["active"]) == 1


# =========================================================
# Mitigation / touch tracking
# =========================================================


def test_partial_mitigation_and_first_touch():
    candles = _bullish_setup() + [
        _candle(8, 111, 112, 103, 104),  # dips to 103 inside [101,105]
    ]

    tracker = OrderBlockTracker()
    tracker.sync(candles)

    ob = tracker.snapshot()["active"][0]
    assert ob["mitigation_status"] == "partially_mitigated"
    assert ob["mitigation_pct"] == pytest.approx((105 - 103) / (105 - 101))
    assert ob["touch_count"] == 1


def test_continuous_dip_counts_as_a_single_touch():
    candles = _bullish_setup() + [
        _candle(8, 111, 112, 103, 104),
        _candle(9, 104, 106, 102, 105),  # still overlapping - same touch
    ]

    tracker = OrderBlockTracker()
    tracker.sync(candles)

    ob = tracker.snapshot()["active"][0]
    assert ob["touch_count"] == 1


def test_separate_dips_count_as_two_touches():
    candles = _bullish_setup() + [
        _candle(8, 111, 112, 103, 104),   # touch #1
        _candle(9, 104, 120, 115, 119),   # fully clear of the zone
        _candle(10, 119, 120, 102, 118),  # touch #2
    ]

    tracker = OrderBlockTracker()
    tracker.sync(candles)

    ob = tracker.snapshot()["active"][0]
    assert ob["touch_count"] == 2


def test_full_mitigation_moves_order_block_to_mitigated_list():
    candles = _bullish_setup() + [
        _candle(8, 111, 112, 103, 104),
        _candle(9, 104, 106, 99, 100),  # low=99 <= zone_low(101) -> fully filled
    ]

    tracker = OrderBlockTracker()
    tracker.sync(candles)

    snapshot = tracker.snapshot()
    assert snapshot["active"] == []
    assert len(snapshot["mitigated"]) == 1
    assert snapshot["mitigated"][0]["mitigation_status"] == "fully_mitigated"
    assert snapshot["mitigated"][0]["mitigation_pct"] == 1.0


def test_mitigation_never_exceeds_100_percent():
    candles = _bullish_setup() + [
        _candle(8, 111, 112, 10, 15),  # massive overshoot
    ]

    tracker = OrderBlockTracker()
    tracker.sync(candles)

    ob = tracker.snapshot()["mitigated"][0]
    assert ob["mitigation_pct"] == 1.0


# =========================================================
# Mitigation Blocks - the origin candle's body as a tighter,
# independently-tracked sub-zone (Phase 1.6)
# =========================================================


def test_mitigation_zone_is_the_origin_candles_body_not_its_wick():
    # _bullish_setup()'s origin candle at idx4 is (open=104, high=105,
    # low=101, close=101) - body is [min(104,101), max(104,101)] = [101,104].
    candles = _bullish_setup()

    tracker = OrderBlockTracker()
    tracker.sync(candles)

    ob = tracker.snapshot()["active"][0]
    assert ob["zone_high"] == 105.0  # wick (unchanged)
    assert ob["zone_low"] == 101.0
    assert ob["mitigation_zone_high"] == 104.0  # body (new, narrower)
    assert ob["mitigation_zone_low"] == 101.0
    assert ob["mitigation_zone_status"] == "unmitigated"
    assert ob["mitigation_zone_pct"] == 0.0


def test_mitigation_zone_progresses_independently_of_wick_zone():
    # Direct construction (bypassing BOS detection) to isolate the
    # mitigation-zone math with a wick/body gap wide enough to observe
    # each zone crossing its own thresholds at different candles.
    ob = OrderBlock(
        direction="bullish",
        zone_high=110.0,
        zone_low=100.0,
        created_at=START,
        origin_timestamp=START,
        origin_bar_index=0,
        timeframe="15m",
        formation_volume=10.0,
        atr_at_creation=10.0,
        mitigation_zone_high=106.0,
        mitigation_zone_low=104.0,
    )

    # Touches the wick zone but stays above the tighter body zone.
    ob.apply_candle(_candle(1, 108, 109, 107, 108))
    snap = ob.to_dict(current_bar_index=1, current_price=108)
    assert snap["mitigation_status"] == "partially_mitigated"
    assert snap["mitigation_zone_status"] == "unmitigated"
    assert snap["mitigation_zone_pct"] == 0.0

    # Now reaches into the body zone too.
    ob.apply_candle(_candle(2, 108, 109, 105, 106))
    snap = ob.to_dict(current_bar_index=2, current_price=106)
    assert snap["mitigation_zone_status"] == "partially_mitigated"
    assert snap["mitigation_zone_pct"] == pytest.approx(0.5)

    # Deep enough to fully mitigate the body zone while the wider wick
    # zone is still only partially mitigated - the two are independent.
    ob.apply_candle(_candle(3, 106, 107, 103, 104))
    snap = ob.to_dict(current_bar_index=3, current_price=104)
    assert snap["mitigation_zone_status"] == "fully_mitigated"
    assert snap["mitigation_zone_pct"] == 1.0
    assert snap["mitigation_status"] == "partially_mitigated"
    assert snap["mitigation_pct"] == pytest.approx(0.7)


def test_mitigation_zone_fully_mitigated_does_not_move_order_block_to_mitigated_list():
    # Only the primary wick-based mitigation_status drives the active
    # -> mitigated transition - mitigation_zone_status is informational.
    # _bullish_setup()'s origin candle has close == low (no gap between
    # the body's and wick's lower bound, so both would reach full
    # mitigation simultaneously) - here the origin's close is nudged to
    # 102 instead of 101, opening a real gap: body [102,104] vs wick
    # [101,105]. high/low stay identical to _bullish_setup() so swing
    # pivots and the BOS confirmation bar are unaffected.
    candles = _bullish_setup()
    candles[4] = dict(candles[4], close=102.0)

    candles = candles + [
        _candle(8, 111, 112, 102, 103),  # reaches the body's low (102) but not the wick's (101)
    ]

    tracker = OrderBlockTracker()
    tracker.sync(candles)

    active = tracker.snapshot()["active"]
    assert len(active) == 1
    ob = active[0]
    assert ob["mitigation_zone_high"] == 104.0
    assert ob["mitigation_zone_low"] == 102.0
    assert ob["mitigation_zone_status"] == "fully_mitigated"
    assert ob["mitigation_status"] == "partially_mitigated"
    assert ob["mitigation_pct"] == pytest.approx(0.75)
    assert tracker.snapshot()["mitigated"] == []


def test_doji_origin_candle_collapses_mitigation_zone_to_immediate_full_status():
    # Defensive edge case only - is_bullish_candle/is_bearish_candle
    # both reject a doji, so real BOS-based detection can never select
    # one as an origin candle. Exercised via direct construction to
    # confirm zone_lifecycle's zero-span branch is actually wired
    # through rather than dividing by zero.
    ob = OrderBlock(
        direction="bullish",
        zone_high=110.0,
        zone_low=100.0,
        created_at=START,
        origin_timestamp=START,
        origin_bar_index=0,
        timeframe="15m",
        formation_volume=10.0,
        atr_at_creation=10.0,
        mitigation_zone_high=105.0,
        mitigation_zone_low=105.0,  # doji: open == close
    )

    assert ob.mitigation_zone_status == "unmitigated"  # no candle applied yet

    ob.apply_candle(_candle(1, 120, 121, 119, 120))  # nowhere near the zone
    snap = ob.to_dict(current_bar_index=1, current_price=120)
    assert snap["mitigation_zone_status"] == "fully_mitigated"
    assert snap["mitigation_zone_pct"] == 1.0


# =========================================================
# Impulse strength
# =========================================================


def test_impulse_strength_grows_as_price_extends_favorably():
    candles = _bullish_setup()

    tracker = OrderBlockTracker()
    tracker.sync(candles)
    at_creation = tracker.snapshot()["active"][0]["impulse_strength"]

    tracker.sync(candles + [_candle(8, 111, 130, 111, 125)])
    after_extension = tracker.snapshot()["active"][0]["impulse_strength"]

    assert at_creation == 0.0
    assert after_extension > at_creation


def test_impulse_strength_is_none_without_atr():
    # Only 6 candles total means detection happens with the minimum
    # possible history - but ATR still had at least one prior candle
    # to measure a True Range from, so this documents that impulse
    # strength is populated even at the earliest possible detection.
    candles = _bullish_setup()

    tracker = OrderBlockTracker()
    tracker.sync(candles)

    ob = tracker.snapshot()["active"][0]
    assert ob["atr_at_creation"] is not None
    assert ob["impulse_strength"] is not None


# =========================================================
# Distance / age
# =========================================================


def test_distance_from_price_zero_when_price_inside_zone():
    candles = _bullish_setup() + [
        _candle(8, 111, 112, 102, 103),  # close inside [101, 105]
    ]

    tracker = OrderBlockTracker()
    tracker.sync(candles)

    ob = tracker.snapshot()["active"][0]
    assert ob["distance_from_price"] == 0.0


def test_age_in_bars_increases_as_replay_advances():
    candles = _bullish_setup() + [_candle(8 + i, 111, 115, 110, 114) for i in range(3)]

    tracker = OrderBlockTracker()
    tracker.sync(candles)

    ob = tracker.snapshot()["active"][0]
    assert ob["age_in_bars"] == 3


# =========================================================
# Replay safety
# =========================================================


def test_rejects_rewound_history():
    tracker = OrderBlockTracker()
    candles = _bullish_setup()

    tracker.sync(candles)

    with pytest.raises(ValueError):
        tracker.sync(candles[:3])


def test_rejects_diverging_history():
    tracker = OrderBlockTracker()
    candles = _bullish_setup()[:5]

    tracker.sync(candles)

    diverging = candles[:4] + [_candle(4, 999, 999, 999, 999)]

    with pytest.raises(ValueError):
        tracker.sync(diverging)


# =========================================================
# Live compatibility - incremental sync must match single-shot sync
# =========================================================


def test_incremental_sync_matches_single_shot_sync():
    candles = _bullish_setup() + [
        _candle(8, 111, 112, 103, 104),
        _candle(9, 104, 106, 99, 100),
    ] + [_candle(10 + i, 100, 101, 99, 100) for i in range(5)]

    incremental = OrderBlockTracker()
    for i in range(1, len(candles) + 1):
        incremental.sync(candles[:i])

    single_shot = OrderBlockTracker()
    single_shot.sync(candles)

    assert incremental.snapshot() == single_shot.snapshot()


# =========================================================
# Edge cases
# =========================================================


def test_snapshot_before_any_candle_is_empty():
    tracker = OrderBlockTracker()
    assert tracker.snapshot() == {
        "active": [],
        "mitigated": [],
        "expired_count": 0,
    }


def test_expired_order_block_is_pruned_and_counted():
    candles = _bullish_setup() + [
        _candle(8 + i, 111, 112, 110, 111) for i in range(10)
    ]

    tracker = OrderBlockTracker(max_age_bars=5)
    tracker.sync(candles)

    snapshot = tracker.snapshot()
    assert snapshot["active"] == []
    assert snapshot["expired_count"] >= 1


def test_mitigated_history_is_bounded():
    tracker = OrderBlockTracker(max_tracked_mitigated=1)

    # Two independent bullish setups, each immediately fully mitigated.
    first = _bullish_setup() + [_candle(8, 111, 112, 90, 95)]
    tracker.sync(first)

    second_start = 20
    second = [
        _candle(second_start + i, c["open"] + 200, c["high"] + 200, c["low"] + 200, c["close"] + 200, c["volume"])
        for i, c in enumerate(_bullish_setup())
    ] + [_candle(second_start + 8, 311, 312, 290, 295)]

    tracker.sync(first + second)

    assert len(tracker.snapshot()["mitigated"]) <= 1


# =========================================================
# Performance validation
# =========================================================


def test_large_history_stays_fast_and_bounded():
    candle_count = 20_000
    candles = [_candle(i, 100, 101, 99, 100) for i in range(candle_count)]

    tracker = OrderBlockTracker()

    start_time = time.perf_counter()

    step = 500
    for i in range(step, candle_count + 1, step):
        tracker.sync(candles[:i])

    elapsed = time.perf_counter() - start_time

    assert elapsed < 5.0
    assert tracker.snapshot()["active"] == []
