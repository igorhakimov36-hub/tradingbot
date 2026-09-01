import time as time_module
from datetime import datetime, timedelta, timezone

import pytest

from strategy.features.market_structure_tracker import MarketStructureTracker
from strategy.market_structure import detect_bos, detect_choch, detect_market_structure, get_last_swing_levels

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
    """Same hand-traced sequence as test_order_block_feature.py's
    _bullish_setup(): produces a confirmed BULLISH_BOS at the last
    candle (close 111 > prior swing high 110)."""
    return [
        _candle(0, 100, 101, 99, 100),
        _candle(1, 100, 102, 88, 101),
        _candle(2, 101, 103, 95, 102),
        _candle(3, 102, 110, 100, 103),
        _candle(4, 104, 105, 101, 101, volume=50.0),
        _candle(5, 101, 104, 100, 103),
        _candle(6, 103, 108, 102, 107),
        _candle(7, 107, 112, 106, 111),  # BOS confirmation (111 > 110)
    ]


def _reference_computation(candles):
    """Recomputes the EXACT same wiring strategy_engine.py uses,
    independently of MarketStructureTracker, to prove the tracker
    introduces no new logic - not just by inspection but by direct
    comparison on the same candle history."""

    highs = [c["high"] for c in candles]
    lows = [c["low"] for c in candles]

    previous_swing_high, previous_swing_low = get_last_swing_levels(highs[:-1], lows[:-1])
    market_structure = detect_market_structure(highs[:-1], lows[:-1])
    bos = detect_bos(candles[-1]["close"], previous_swing_high, previous_swing_low)
    choch = detect_choch(market_structure, candles[-1]["close"], previous_swing_high, previous_swing_low)

    return {
        "market_structure": market_structure,
        "last_swing_high": previous_swing_high,
        "last_swing_low": previous_swing_low,
        "bos": bos,
        "choch": choch,
    }


# =========================================================
# Equivalence with the existing frozen wiring - the core property
# =========================================================


def test_matches_reference_computation_bar_by_bar():
    candles = _bullish_setup()
    tracker = MarketStructureTracker()

    for n in range(1, len(candles) + 1):
        tracker.sync(candles[:n])
        snap = tracker.snapshot()
        reference = _reference_computation(candles[:n])

        assert snap["market_structure"] == reference["market_structure"]
        assert snap["last_swing_high"] == reference["last_swing_high"]
        assert snap["last_swing_low"] == reference["last_swing_low"]
        assert snap["bos"] == reference["bos"]
        assert snap["choch"] == reference["choch"]


def test_bullish_bos_detected_on_confirmation_bar():
    candles = _bullish_setup()
    tracker = MarketStructureTracker()
    tracker.sync(candles)

    snap = tracker.snapshot()
    assert snap["bos"] == "BULLISH_BOS"
    assert snap["last_swing_high"] == 110.0
    # The MOST RECENT swing low pivot in the window (idx5, low=100) -
    # not the earlier idx1 pivot (low=88) another tracker's differently
    # bounded window happens to reference; get_last_swing_levels always
    # returns the latest one, confirmed correct by the independent
    # bar-by-bar equivalence check above.
    assert snap["last_swing_low"] == 100.0


def test_no_bos_before_confirmation():
    candles = _bullish_setup()[:-1]  # stop one candle short of the break
    tracker = MarketStructureTracker()
    tracker.sync(candles)

    assert tracker.snapshot()["bos"] == "NO_BOS"


def test_bos_stays_true_while_close_remains_beyond_the_broken_level():
    # detect_bos is level-based, not edge-triggered - this is a
    # deliberate, documented property, not a bug.
    candles = _bullish_setup() + [
        _candle(8, 111, 115, 110, 114),
        _candle(9, 114, 118, 113, 117),
    ]
    tracker = MarketStructureTracker()
    tracker.sync(candles)

    assert tracker.snapshot()["bos"] == "BULLISH_BOS"


# =========================================================
# Structure lookback bounding
# =========================================================


def test_structure_lookback_bounds_the_scanned_window():
    tracker = MarketStructureTracker(structure_lookback=5)

    candles = [_candle(i, 100, 101, 99, 100) for i in range(20)]
    tracker.sync(candles)

    assert len(tracker._recent_candles) == 5


# =========================================================
# Replay safety
# =========================================================


def test_sync_rejects_rewound_candles():
    tracker = MarketStructureTracker()
    tracker.sync(_bullish_setup())

    with pytest.raises(ValueError):
        tracker.sync(_bullish_setup()[:3])


def test_sync_rejects_diverging_history():
    tracker = MarketStructureTracker()
    tracker.sync(_bullish_setup()[:3])

    diverged = _bullish_setup()[:2] + [_candle(2, 999, 999, 999, 999)]
    with pytest.raises(ValueError):
        tracker.sync(diverged)


def test_incremental_sync_matches_single_shot_sync():
    candles = _bullish_setup()

    incremental = MarketStructureTracker()
    for n in range(1, len(candles) + 1):
        incremental.sync(candles[:n])

    single_shot = MarketStructureTracker()
    single_shot.sync(candles)

    assert incremental.snapshot() == single_shot.snapshot()


def test_snapshot_before_any_candle():
    tracker = MarketStructureTracker()
    snap = tracker.snapshot()

    assert snap["market_structure"] == "UNKNOWN"
    assert snap["bos"] == "NO_BOS"
    assert snap["choch"] == "NO_CHOCH"
    assert snap["last_swing_high"] is None
    assert snap["last_swing_low"] is None


# =========================================================
# Performance validation
# =========================================================


def test_large_history_stays_fast_and_bounded():
    candle_count = 20_000
    candles = [_candle(i, 100, 101, 99, 100) for i in range(candle_count)]

    tracker = MarketStructureTracker()

    start_time = time_module.perf_counter()

    step = 500
    for i in range(step, candle_count + 1, step):
        tracker.sync(candles[:i])

    elapsed = time_module.perf_counter() - start_time

    assert elapsed < 5.0
