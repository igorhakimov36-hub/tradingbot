"""
Tests for the Liquidity Sweep Staleness Telemetry pure functions
(strategy/research/liquidity_pool_staleness_telemetry.py). Covers the
required causal scenarios: no creation-bar spurious sweep, correct
bar-0/bar-1 counting, correct classification at and around each
boundary, censoring distinctness, and a direct confirmation production
Policy A is untouched.
"""

from datetime import datetime, timedelta, timezone

from strategy.research.liquidity_pool_staleness_telemetry import (
    classify_staleness,
    first_passage_outcome,
)

START = datetime(2024, 1, 1, tzinfo=timezone.utc)


def _candle(minute_offset, open_, high, low, close, volume=10.0):
    return {
        "timestamp": START + timedelta(minutes=minute_offset),
        "open": open_, "high": high, "low": low, "close": close, "volume": volume,
    }


# =========================================================
# Classification
# =========================================================


def test_same_candle_classification_no_prior_close_beyond():
    assert classify_staleness(current_rule_swept_bar_i=5, first_close_beyond_bar_i=None) == "SAME_CANDLE_SWEEP"


def test_same_candle_classification_close_beyond_on_sweep_bar_itself_not_prior():
    # A close-beyond timestamp equal to (or after) the sweep bar itself
    # is never "prior" - the sweep candle's own close is, by definition,
    # back inside.
    assert classify_staleness(current_rule_swept_bar_i=5, first_close_beyond_bar_i=5) == "SAME_CANDLE_SWEEP"


def test_bar_0_bar_1_counting_bar_1_is_timely():
    # first_close_beyond is bar 0; the very next completed candle is bar 1.
    assert classify_staleness(current_rule_swept_bar_i=11, first_close_beyond_bar_i=10, primary_window=16) == "TIMELY_RECLAIM"


def test_reclaim_exactly_at_boundary_16_is_timely():
    assert classify_staleness(current_rule_swept_bar_i=26, first_close_beyond_bar_i=10, primary_window=16) == "TIMELY_RECLAIM"


def test_reclaim_one_bar_beyond_boundary_16_is_late():
    assert classify_staleness(current_rule_swept_bar_i=27, first_close_beyond_bar_i=10, primary_window=16) == "LATE_RECLAIM"


def test_reclaim_exactly_at_boundary_8_is_timely():
    assert classify_staleness(current_rule_swept_bar_i=18, first_close_beyond_bar_i=10, primary_window=8) == "TIMELY_RECLAIM"


def test_reclaim_one_bar_beyond_boundary_8_is_late():
    assert classify_staleness(current_rule_swept_bar_i=19, first_close_beyond_bar_i=10, primary_window=8) == "LATE_RECLAIM"


def test_reclaim_exactly_at_boundary_32_is_timely():
    assert classify_staleness(current_rule_swept_bar_i=42, first_close_beyond_bar_i=10, primary_window=32) == "TIMELY_RECLAIM"


def test_reclaim_one_bar_beyond_boundary_32_is_late():
    assert classify_staleness(current_rule_swept_bar_i=43, first_close_beyond_bar_i=10, primary_window=32) == "LATE_RECLAIM"


def test_end_of_window_censoring_is_distinct_not_accepted():
    # Never swept at all (current_rule_swept_bar_i is None) - regardless
    # of whether a close-beyond ever occurred - is UNRESOLVED_OR_CENSORED,
    # never silently treated as any resolved outcome.
    assert classify_staleness(current_rule_swept_bar_i=None, first_close_beyond_bar_i=10) == "UNRESOLVED_OR_CENSORED"
    assert classify_staleness(current_rule_swept_bar_i=None, first_close_beyond_bar_i=None) == "UNRESOLVED_OR_CENSORED"


# =========================================================
# No creation-bar spurious sweep (documented as a harness-level concern,
# but the classification function itself must not assume/require a
# first_close_beyond_bar_i equal to the pool's own creation bar - this
# test proves an early-index close-beyond is treated identically to a
# later one, i.e. the function itself has no special-cased bias)
# =========================================================


def test_no_special_casing_of_bar_index_zero():
    # A close-beyond recorded at bar index 0 behaves identically to one
    # recorded at any other index - the function does not silently
    # exempt or specially treat "bar zero" (the actual creation-bar
    # exclusion is a harness-level responsibility, tested separately in
    # the harness's own tests against the real LiquidityPoolTracker).
    assert classify_staleness(current_rule_swept_bar_i=1, first_close_beyond_bar_i=0, primary_window=16) == "TIMELY_RECLAIM"


# =========================================================
# Telemetry cannot modify Policy A state transitions or signals
# =========================================================


def test_production_policy_a_unchanged_by_telemetry_module_existing():
    from strategy.features.liquidity_pool import LiquidityPool

    pool = LiquidityPool(
        direction="buy_side", zone_high=105.0, zone_low=100.0, level=102.5,
        created_at=START, origin_bar_index=0, timeframe="15m",
    )
    pool.check_sweep(_candle(1, 105, 108, 104, 107), "timestamp", atr=5.0)
    assert pool.swept_status == "unswept"  # a clean close beyond still does not sweep under A

    pool.check_sweep(_candle(2, 107, 109, 99, 100), "timestamp", atr=5.0)
    assert pool.swept_status == "swept"  # wick beyond + close back still sweeps under A, unmodified


# =========================================================
# Determinism
# =========================================================


def test_classify_staleness_deterministic():
    results = [classify_staleness(current_rule_swept_bar_i=30, first_close_beyond_bar_i=10, primary_window=16) for _ in range(5)]
    assert all(r == results[0] for r in results)


# =========================================================
# first_passage_outcome
# =========================================================


def test_first_passage_favorable_buy_side():
    forward = [_candle(1, 100, 101, 94, 95)]  # low=94, reference_close=100 -> 100-94=6 >= 5 (1 ATR)
    result = first_passage_outcome("buy_side", reference_close=100.0, atr=5.0, forward_candles=forward)
    assert result["outcome"] == "favorable"


def test_first_passage_adverse_buy_side():
    forward = [_candle(1, 100, 106, 99, 101)]  # high=106, 106-100=6>=5 -> adverse
    result = first_passage_outcome("buy_side", reference_close=100.0, atr=5.0, forward_candles=forward)
    assert result["outcome"] == "adverse"


def test_first_passage_sell_side_symmetry():
    forward = [_candle(1, 100, 106, 99, 105)]  # high=106, 106-100=6>=5 -> favorable for sell_side (expects UP)
    result = first_passage_outcome("sell_side", reference_close=100.0, atr=5.0, forward_candles=forward)
    assert result["outcome"] == "favorable"


def test_first_passage_ambiguous_same_bar_counted_as_adverse():
    forward = [_candle(1, 100, 106, 94, 100)]  # both conditions true (buy_side): low=94 fav, high=106 adverse
    result = first_passage_outcome("buy_side", reference_close=100.0, atr=5.0, forward_candles=forward)
    assert result["outcome"] == "adverse"
    assert result["ambiguous"] is True


def test_first_passage_censored():
    forward = [_candle(1, 100, 101, 99, 100)]
    result = first_passage_outcome("buy_side", reference_close=100.0, atr=5.0, forward_candles=forward)
    assert result["outcome"] == "censored"


def test_first_passage_no_lookahead_empty_forward():
    result = first_passage_outcome("buy_side", reference_close=100.0, atr=5.0, forward_candles=[])
    assert result["outcome"] == "censored"


def test_first_passage_2atr_secondary_threshold():
    forward = [_candle(1, 100, 101, 90, 91)]  # 100-90=10 = 2*5 ATR
    result = first_passage_outcome("buy_side", reference_close=100.0, atr=5.0, forward_candles=forward, favorable_atr_multiple=2.0)
    assert result["outcome"] == "favorable"
