"""
Tests for strategy/research/liquidity_pool_wick_extremity_eligibility.py -
causal defining-touch tracking and anchor resolution dispatch.
"""

from datetime import datetime, timedelta, timezone

from strategy.research.liquidity_pool_wick_extremity_eligibility import (
    anchor_for_defining_touch,
    current_defining_touch,
)

START = datetime(2024, 1, 1, tzinfo=timezone.utc)


def _touch(minute_offset, price, source="session_high", context=None):
    return {
        "timestamp": START + timedelta(minutes=minute_offset),
        "price": price,
        "source": source,
        "source_context": context,
    }


# =========================================================
# current_defining_touch
# =========================================================


def test_single_touch_is_defining():
    touches = [_touch(0, 100.0)]
    assert current_defining_touch(touches, "buy_side") == touches[0]


def test_later_strictly_higher_touch_becomes_defining_buy_side():
    touches = [_touch(0, 100.0), _touch(1, 105.0)]
    assert current_defining_touch(touches, "buy_side") == touches[1]


def test_later_lower_touch_does_not_become_defining_buy_side():
    touches = [_touch(0, 105.0), _touch(1, 100.0)]
    assert current_defining_touch(touches, "buy_side") == touches[0]


def test_later_strictly_lower_touch_becomes_defining_sell_side():
    touches = [_touch(0, 100.0), _touch(1, 95.0)]
    assert current_defining_touch(touches, "sell_side") == touches[1]


def test_later_higher_touch_does_not_become_defining_sell_side():
    touches = [_touch(0, 95.0), _touch(1, 100.0)]
    assert current_defining_touch(touches, "sell_side") == touches[0]


def test_tie_at_extreme_price_earliest_timestamp_wins():
    touches = [_touch(0, 105.0), _touch(5, 105.0), _touch(1, 105.0)]
    result = current_defining_touch(touches, "buy_side")
    assert result["timestamp"] == START  # minute_offset=0, the earliest


def test_empty_touches_returns_none():
    assert current_defining_touch([], "buy_side") is None


def test_causal_prefix_consistency_no_lookahead():
    # The defining touch after k touches must depend only on those k
    # touches, never on touches appended afterward.
    touches = [_touch(0, 100.0), _touch(1, 103.0), _touch(2, 101.0), _touch(3, 108.0)]
    assert current_defining_touch(touches[:1], "buy_side")["price"] == 100.0
    assert current_defining_touch(touches[:2], "buy_side")["price"] == 103.0
    assert current_defining_touch(touches[:3], "buy_side")["price"] == 103.0  # 101 doesn't widen
    assert current_defining_touch(touches[:4], "buy_side")["price"] == 108.0


# =========================================================
# anchor_for_defining_touch
# =========================================================


def test_round_number_never_anchorable_regardless_of_lookup():
    touch = _touch(0, 100.0, source="round_number", context=None)
    candle_lookup = {START: {"open": 99, "high": 101, "low": 98, "close": 100}}
    assert anchor_for_defining_touch(touch, candle_lookup) is None


def test_session_high_resolves_via_context():
    ts = START + timedelta(minutes=2)
    context = {"high_timestamp": ts, "low_timestamp": ts}
    touch = _touch(2, 105.0, source="session_high", context=context)
    candle_lookup = {ts: {"open": 100, "high": 105.0, "low": 99, "close": 101}}
    anchor = anchor_for_defining_touch(touch, candle_lookup)
    assert anchor is not None
    assert anchor.anchor_timestamp == ts
    assert anchor.anchor_high == 105.0


def test_equal_highs_resolves_via_context_cluster():
    ts_pivot = START + timedelta(minutes=1)
    context = {"pivot_prices": [105.0, 106.0], "pivot_timestamps": [START, ts_pivot]}
    touch = _touch(1, 105.5, source="equal_highs", context=context)
    candle_lookup = {ts_pivot: {"open": 104, "high": 106.0, "low": 103, "close": 105}}
    anchor = anchor_for_defining_touch(touch, candle_lookup)
    assert anchor is not None
    assert anchor.anchor_timestamp == ts_pivot  # the cluster's own max pivot (106.0)


def test_missing_candle_in_lookup_returns_none():
    ts = START + timedelta(minutes=2)
    context = {"high_timestamp": ts, "low_timestamp": ts}
    touch = _touch(2, 105.0, source="session_high", context=context)
    assert anchor_for_defining_touch(touch, candle_lookup={}) is None


def test_missing_source_context_returns_none():
    touch = _touch(2, 105.0, source="session_high", context=None)
    candle_lookup = {START: {"open": 99, "high": 101, "low": 98, "close": 100}}
    assert anchor_for_defining_touch(touch, candle_lookup) is None
