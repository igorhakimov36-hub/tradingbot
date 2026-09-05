"""
Focused tests for the IFVG + Retest research adapter
(strategy/research/ifvg_retest_adapter.py). Covers event timing,
direction, repeated-signal/dedup, zone failure, and state isolation.
Legacy-compatibility (production coordinator/S005 unaffected) is
covered by tests/test_fair_value_gap_inversion_compatibility.py,
reused unmodified - this file does not re-prove that.
"""

from datetime import datetime, timedelta, timezone

from strategy.research.ifvg_retest_adapter import make_ifvg_callbacks

SYMBOL = "SOLUSDT"
START = datetime(2024, 1, 1, tzinfo=timezone.utc)


def _candle(minute_offset, open_, high, low, close, volume=100.0):
    return {
        "timestamp": START + timedelta(minutes=minute_offset),
        "open": open_, "high": high, "low": low, "close": close, "volume": volume,
    }


def _bullish_gap_setup_candles():
    """A/B/C forming a bullish gap zone [101, 116]."""
    return [
        _candle(0, 100, 101, 99, 100),
        _candle(1, 100, 115, 100, 114),
        _candle(2, 116, 120, 116, 118),
    ]


def _run(candles, arm, **kwargs):
    event_log = []
    strategy_cb, trade_cb = make_ifvg_callbacks(SYMBOL, arm=arm, event_log=event_log, **kwargs)
    decisions = []
    for i in range(len(candles)):
        market_snapshot = {SYMBOL: {"15m": candles[: i + 1]}}
        result = strategy_cb(candles[i], market_snapshot)
        decisions.append(result)
        if result["decision"] in ("LONG", "SHORT"):
            trade = trade_cb(result["decision"], candles[i], market_snapshot, 10_000.0)
            decisions[-1]["_trade"] = trade
    return decisions, event_log


# =========================================================
# Arm A: inversion entry - timing, direction, no duplicate
# =========================================================


def test_inversion_arm_fires_exactly_on_the_confirming_bar():
    candles = _bullish_gap_setup_candles() + [
        _candle(3, 105, 106, 100, 110),  # fills, no inversion yet
        _candle(4, 108, 100, 94, 95),    # inverts HERE (close=95 < zone_low=101)
    ]
    decisions, event_log = _run(candles, arm="inversion")

    assert decisions[3]["decision"] == "IGNORE"
    assert decisions[4]["decision"] == "SHORT"  # originally bullish gap -> effective SHORT
    assert len(event_log) == 1
    assert event_log[0].event_type == "inversion"
    assert event_log[0].confirmed_bar_index == 4


def test_inversion_arm_effective_direction_mirrors_for_bearish_original():
    candles = [
        _candle(0, 116, 120, 116, 118),   # A - bearish gap origin high
        _candle(1, 116, 116, 101, 102),   # B - impulsive down
        _candle(2, 101, 101, 96, 98),     # C - low=96... wait need bearish gap: A.low > C.high
    ]
    # bearish gap requires candle_a["low"] > candle_c["high"]
    candles = [
        _candle(0, 116, 118, 116, 117),   # A: low=116
        _candle(1, 116, 116, 101, 102),   # B
        _candle(2, 100, 101, 96, 98),     # C: high=101 < A.low=116 -> bearish gap [zone_low=101, zone_high=116]
        _candle(3, 105, 110, 100, 104),   # fills (wick to 110 >= zone_high=116? no - need wick to reach zone_high)
    ]
    # Recompute cleanly: bearish gap zone = [C.high=101, A.low=116]. Fill requires wick reaching zone_high=116.
    candles[3] = _candle(3, 105, 116, 100, 108)  # wick to 116 fills fully
    candles.append(_candle(4, 110, 122, 110, 120))  # bar 4: close=120 > zone_high=116 -> inverts

    decisions, event_log = _run(candles, arm="inversion")
    assert decisions[4]["decision"] == "LONG"  # originally bearish gap -> effective LONG
    assert event_log[0].original_direction == "bearish"


def test_inversion_arm_never_refires_for_the_same_gap():
    candles = _bullish_gap_setup_candles() + [
        _candle(3, 105, 106, 100, 110),
        _candle(4, 108, 100, 94, 95),     # inverts (bar 4)
        _candle(5, 90, 91, 80, 85),       # closes below again - must NOT refire
        _candle(6, 80, 81, 70, 75),
    ]
    decisions, event_log = _run(candles, arm="inversion")
    assert len(event_log) == 1  # only the bar-4 event, ever
    assert decisions[5]["decision"] == "IGNORE"
    assert decisions[6]["decision"] == "IGNORE"


# =========================================================
# Arm B: retest entry - only after inversion, respects cooldown
# =========================================================


def test_retest_arm_never_fires_before_inversion_confirmed():
    candles = _bullish_gap_setup_candles() + [
        _candle(3, 105, 106, 100, 110),   # fills, NOT inverted
        _candle(4, 95, 101, 90, 105),     # prior bar's high reaches 101, closes back inside (still not inverted)
        _candle(5, 95, 100, 90, 102),     # current bar's high stays <= 101 - geometrically a retest shape, but never inverted
    ]
    decisions, event_log = _run(candles, arm="retest")
    assert all(d["decision"] == "IGNORE" for d in decisions)
    assert event_log == []


def test_retest_arm_fires_on_the_confirming_bar_with_correct_direction():
    candles = _bullish_gap_setup_candles() + [
        _candle(3, 105, 106, 100, 110),
        _candle(4, 100, 100, 94, 95),      # inverts
        _candle(5, 95, 101, 90, 96),       # prior-bar setup (high reaches 101)
        _candle(6, 96, 100, 90, 95),       # retest confirms HERE
    ]
    decisions, event_log = _run(candles, arm="retest")
    assert decisions[6]["decision"] == "SHORT"
    assert len(event_log) == 1
    assert event_log[0].event_type == "retest"
    assert event_log[0].confirmed_bar_index == 6


def test_retest_arm_respects_cooldown_between_repeat_signals():
    candles = _bullish_gap_setup_candles() + [
        _candle(3, 105, 106, 100, 110),
        _candle(4, 100, 100, 94, 95),
        _candle(5, 95, 101, 90, 96),
        _candle(6, 96, 100, 90, 95),       # retest #1
        _candle(7, 95, 101, 90, 96),       # setup again immediately
        _candle(8, 96, 100, 90, 95),       # would be retest #2 - within cooldown, suppressed
    ]
    decisions, event_log = _run(candles, arm="retest", retest_cooldown_bars=5)
    assert decisions[6]["decision"] == "SHORT"
    assert decisions[8]["decision"] == "IGNORE"
    assert len(event_log) == 1


# =========================================================
# Zone failure excludes further retest signals
# =========================================================


def test_failed_gap_produces_no_further_retest_signal():
    candles = _bullish_gap_setup_candles() + [
        _candle(3, 105, 106, 100, 110),
        _candle(4, 100, 100, 94, 95),      # inverts
        _candle(5, 96, 116.5, 96, 116.5),  # fails (close > zone_high=116)
        _candle(6, 95, 101, 90, 96),       # would-be retest setup - gap already failed
        _candle(7, 96, 100, 90, 95),
    ]
    decisions, event_log = _run(candles, arm="retest")
    assert all(d["decision"] == "IGNORE" for d in decisions)
    assert event_log == []


# =========================================================
# State isolation across independent adapter instances
# =========================================================


def test_two_independent_adapters_share_no_state():
    candles = _bullish_gap_setup_candles() + [
        _candle(3, 105, 106, 100, 110),
        _candle(4, 108, 100, 94, 95),
    ]
    decisions_a, _ = _run(candles, arm="inversion")
    decisions_b, _ = _run(candles, arm="inversion")
    assert [d["decision"] for d in decisions_a] == [d["decision"] for d in decisions_b]


# =========================================================
# Actionability / no retroactive signal: incremental sync matches
# a single growing-history walk (mirrors the tracker's own guarantee)
# =========================================================


def test_event_bar_attribution_is_not_retroactive_under_incremental_sync():
    candles = _bullish_gap_setup_candles() + [
        _candle(3, 105, 106, 100, 110),
        _candle(4, 108, 100, 94, 95),   # inverts at bar 4
    ]
    # Walk one bar at a time (as the real replay does) and confirm the
    # event is only ever seen at bar 4, never earlier and never re-seen later.
    decisions, event_log = _run(candles, arm="inversion")
    fire_bars = [i for i, d in enumerate(decisions) if d["decision"] != "IGNORE"]
    assert fire_bars == [4]
    assert event_log[0].confirmed_bar_index == 4


# =========================================================
# Stop/target sanity: stop uses the ORIGINAL far edge, floored, 2R target
# =========================================================


def test_stop_uses_original_far_edge_with_min_risk_floor_and_fixed_2r():
    candles = _bullish_gap_setup_candles() + [
        _candle(3, 105, 106, 100, 110),
        _candle(4, 108, 100, 94, 95),   # inverts, entry price = 95 (close), decision=SHORT
    ]
    decisions, _ = _run(candles, arm="inversion")
    trade = decisions[4]["_trade"]
    entry = 95.0
    # boundary = zone_high = 116, stop should be beyond it (above entry, SHORT)
    assert trade.stop_loss > entry
    risk = trade.stop_loss - entry
    assert trade.take_profit == entry - risk * 2.0
    # min-risk floor: risk must be at least MIN_RISK_PERCENT of entry
    assert risk >= entry * 0.006 - 1e-9
