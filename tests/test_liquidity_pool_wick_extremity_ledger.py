"""
Tests for the research-only touch ledger
(strategy/research/liquidity_pool_wick_extremity_ledger.py) that wraps
LiquidityPoolTracker to capture per-touch price/source/context granularity
production discards.
"""

from datetime import datetime, timedelta, timezone

import pytest

from strategy.features.liquidity_pool import LiquidityPool, LiquidityPoolTracker
from strategy.research.liquidity_pool_wick_extremity_ledger import install_touch_ledger

START = datetime(2024, 1, 1, tzinfo=timezone.utc)


def _candle(minute_offset, open_, high, low, close, volume=10.0):
    return {
        "timestamp": START + timedelta(minutes=minute_offset),
        "open": open_, "high": high, "low": low, "close": close, "volume": volume,
    }


def _run_sequence(tracker):
    """
    candle0: baseline, no candidates.
    candle1: equal_highs cluster (buy_side, level=105.0) - lone candidate, no pool yet.
    candle2: session_high period (buy_side, session_high=105.0) - exact-matches the
             lone candidate -> forms a NEW pool (2 touches).
    candle3: a second, later equal_highs cluster (level=105.0, exact match) -> widens
             the existing pool (3rd touch).
    """
    ts0, ts1, ts2, ts3 = (START + timedelta(minutes=i) for i in range(4))
    candles = [
        _candle(0, 100, 101, 99, 100),
        _candle(1, 100, 101, 99, 100),
        _candle(2, 100, 101, 99, 100),
        _candle(3, 100, 101, 99, 100),
    ]

    empty = {"equal_highs": [], "equal_lows": []}
    tracker.sync(candles[:1], empty, {})

    snap1 = {
        "equal_highs": [{
            "direction": "buy_side", "created_at": ts1, "level": 105.0,
            "pivot_prices": [105.0, 105.0], "pivot_timestamps": [ts0, ts1],
        }],
        "equal_lows": [],
    }
    tracker.sync(candles[:2], snap1, {})

    session_snap2 = {
        "daily": {"closed": [{
            "period_start": ts0, "session_high": 105.0, "high_timestamp": ts2,
            "session_low": 90.0, "low_timestamp": ts2,
        }]},
    }
    tracker.sync(candles[:3], snap1, session_snap2)

    snap3 = {
        "equal_highs": snap1["equal_highs"] + [{
            "direction": "buy_side", "created_at": ts3, "level": 105.0,
            "pivot_prices": [105.0, 105.0], "pivot_timestamps": [ts2, ts3],
        }],
        "equal_lows": [],
    }
    tracker.sync(candles[:4], snap3, session_snap2)

    return ts0, ts1, ts2, ts3


def test_ledger_captures_both_pool_formation_touches():
    tracker = LiquidityPoolTracker(timeframe="15m")
    handle = install_touch_ledger(tracker)
    try:
        ts0, ts1, ts2, ts3 = _run_sequence(tracker)
    finally:
        handle.uninstall()

    pool_id = ("buy_side", ts2)
    entries = [e for e in handle.ledger if e["pool_id"] == pool_id]
    assert len(entries) == 3

    first, second, third = entries
    assert first["timestamp"] == ts1 and first["source"] == "equal_highs"
    assert second["timestamp"] == ts2 and second["source"] == "session_high"
    assert third["timestamp"] == ts3 and third["source"] == "equal_highs"


def test_ledger_attaches_correct_source_context():
    tracker = LiquidityPoolTracker(timeframe="15m")
    handle = install_touch_ledger(tracker)
    try:
        _run_sequence(tracker)
    finally:
        handle.uninstall()

    session_touch = next(e for e in handle.ledger if e["source"] == "session_high")
    assert session_touch["source_context"]["high_timestamp"] == session_touch["timestamp"]

    eqh_touches = [e for e in handle.ledger if e["source"] == "equal_highs"]
    for touch in eqh_touches:
        assert touch["source_context"] is not None
        assert "pivot_prices" in touch["source_context"]
        assert "pivot_timestamps" in touch["source_context"]


def test_ledger_omits_context_for_round_number_source():
    tracker = LiquidityPoolTracker(timeframe="15m", round_number_spacing=1.0)
    handle = install_touch_ledger(tracker)
    try:
        candles = [_candle(i, 100 + i, 101 + i, 99 + i, 100 + i) for i in range(3)]
        empty = {"equal_highs": [], "equal_lows": []}
        for n in range(1, len(candles) + 1):
            tracker.sync(candles[:n], empty, {})
    finally:
        handle.uninstall()

    round_number_touches = [e for e in handle.ledger if e["source"] == "round_number"]
    assert round_number_touches, "expected at least one round_number touch to be registered"
    for touch in round_number_touches:
        assert touch["source_context"] is None


def test_uninstall_restores_exact_original_method():
    original = LiquidityPool.register_touch
    tracker = LiquidityPoolTracker(timeframe="15m")
    handle = install_touch_ledger(tracker)
    assert LiquidityPool.register_touch is not original
    handle.uninstall()
    assert LiquidityPool.register_touch is original


def test_only_one_ledger_installation_active_at_a_time():
    tracker_a = LiquidityPoolTracker(timeframe="15m")
    tracker_b = LiquidityPoolTracker(timeframe="15m")
    handle_a = install_touch_ledger(tracker_a)
    try:
        with pytest.raises(RuntimeError):
            install_touch_ledger(tracker_b)
    finally:
        handle_a.uninstall()


def test_production_output_byte_identical_with_and_without_ledger():
    tracker_plain = LiquidityPoolTracker(timeframe="15m")
    _run_sequence(tracker_plain)
    snapshot_plain = tracker_plain.snapshot()

    tracker_instrumented = LiquidityPoolTracker(timeframe="15m")
    handle = install_touch_ledger(tracker_instrumented)
    try:
        _run_sequence(tracker_instrumented)
    finally:
        handle.uninstall()
    snapshot_instrumented = tracker_instrumented.snapshot()

    assert snapshot_plain == snapshot_instrumented
